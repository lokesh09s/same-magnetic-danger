"""DESCRIPTIVE AIA 94 A FOLLOW-UPS (decisions.md 2026-09-27, 947e4c0). EXPLORATORY / DESCRIPTIVE ONLY — post-hoc, not
pre-registered; nothing here is a test. Sets S1-S3 are reported separately and never pooled. Frozen euv_extra models only.
Part 1 alert tiers; Part 2 CV_box artifact check (exposure, saturation, photon + read noise); Part 3 calm-flarer profile."""
import glob, json, os, sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import swpc
from astropy.io import fits
from euv_dctrl import cv
from euv_full import hmi_files
from euv_confirm_retest import load_models, pred
from euv_confirm_tests import log_r
from phase_f import boot_many, ratio_jobs, pct, W
from euv_f2_replication import twins

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 200)
TIERS = ["NO ALERT", "WATCH", "WARNING"]
# AIA 94 A constants, no download: aiapy.calibrate.utils.get_error_table(<aiapy/tests/data/aia_V3_error_table.txt>), a file whose
# SHA-256 (66ff0349...) equals aiapy's recorded hash of the SSW V3 table -> DNPERPHT = 1.975 DN/photon; read noise 1.14 DN/pixel for
# camera 4 (telescope_number(94 A) = 4), from aiapy.calibrate.estimate_error, which cites Boerner et al. 2012 Table 6.
G_DN_PER_PH, READ_DN, AIA_ARCSEC = 1.975, 1.14, 0.6
SETS = {
    "S1": dict(name="S1 2025-26 confirmation <=2-region", root="data/euv_confirm", cohort="data/euv_confirm/cohort_le2.csv", manifest=None,
               lab="data/labelled_20250101_20260817.csv", evR=("2024-12-29", "2026-08-18 23:59"), evL=("2024-12-29", "2026-08-18 23:59"),
               twins="data/euv_confirm/twins_le2.csv", orig=(3.2624, 1.2956, 9.4887), n=378),
    "S2": dict(name="S2 EUV-unseen PRIMARY 2021/23/24", root="data/euv_extra/primary", cohort="data/euv_extra/cohort_primary_all_eligible.csv",
               manifest="primary", lab="data/labelled_20100501_20250101.csv", evR=("2020-12-29", "2025-01-01"), evL=("2020-12-29", "2025-01-02 23:59"),
               twins=None, orig=(1.6295, 0.7907, 3.8386), n=155),
    "S3": dict(name="S3 2022 sensitivity", root="data/euv_extra/s2022", cohort="data/euv_extra/cohort_s2022_all_eligible.csv",
               manifest="s2022", lab="data/labelled_20100501_20250101.csv", evR=("2020-12-29", "2025-01-01"), evL=("2020-12-29", "2025-01-02 23:59"),
               twins=None, orig=(3.2350, 1.2554, 4.5452), n=152),
}


def load_set(k):
    """Same construction as the tests (retest e4eb16e for S1; filter test 5abc40a for S2/S3)."""
    S = SETS[k]
    coh = pd.read_csv(S["cohort"], parse_dates=["t"])
    if S["manifest"]:
        M = pd.read_csv("data/euv_extra/manifest.csv", parse_dates=["t"]); M = M[(M.set == S["manifest"]) & (M.reason == "INCLUDED")]
        coh = M[["harpnum", "t"]].merge(coh, on=["harpnum", "t"], how="left", validate="one_to_one")
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{S['root']}/results/*.json")])[["eid", "primary_fill", "primary_CV_box"]]
    r[["primary_fill", "primary_CV_box"]] = r[["primary_fill", "primary_CV_box"]].apply(pd.to_numeric, errors="coerce")
    c = coh.merge(r, on="eid", how="left")
    c = c[(c.primary_fill >= 0.80) & np.isfinite(c.primary_CV_box) & (c.primary_CV_box > 0)].reset_index(drop=True)
    c["log10_CV_box"] = np.log10(c.primary_CV_box)
    c["logR"] = log_r(c, pd.Timestamp(S["evR"][0]), pd.Timestamp(S["evR"][1]))
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
    lab = pd.read_csv(S["lab"], usecols=["harpnum", "t_rec_utc", "t_rec_tai", "lon_fwt"], parse_dates=["t_rec_utc"], low_memory=False)
    c = c.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert len(c) == S["n"], (k, len(c))
    return c


def series_variants(c, root):
    rows = []
    for e in c.itertuples():
        s = pd.read_csv(f"{root}/series/{e.eid}.csv", parse_dates=["t_obs"], float_precision="round_trip")
        v = s[s.valid_primary]; t, b = v.t_obs.to_numpy(), v.box.to_numpy()
        cv0 = cv(t, b)                                            # = euv_dctrl.summarise CV_box (valid_primary frames)
        med = np.median(v.exptime); ke = (np.abs(v.exptime - med) <= 0.05 * med).to_numpy(); ks = (v.sat_px == 0).to_numpy()
        m, _ = hmi_files(f"{root}/hmi/{e.harpnum}", e.t_rec_tai); hd = fits.getheader(m, 1)
        n_hmi = int(hd["NAXIS1"]) * int(hd["NAXIS2"]); n_aia = n_hmi * (float(hd["CDELT1"]) / AIA_ARCSEC) ** 2
        ex = v.exptime.to_numpy(); n_i = n_aia * (1 - v.frac_outside.to_numpy()); ok = np.isfinite(b)
        sig = np.sqrt(G_DN_PER_PH * b[ok] * ex[ok] + READ_DN ** 2) / np.sqrt(n_i[ok]) / ex[ok]      # DN/s, per frame, box mean
        cvn = float(np.sqrt(np.mean(sig ** 2)) / np.mean(b[ok])) if ok.sum() >= 3 else np.nan
        rows.append(dict(eid=e.eid, cv_repro=cv0, n_valid=len(v), CV_exp=cv(t[ke], b[ke]), frac_removed_exp=1 - ke.mean(),
                         CV_sat=cv(t[ks], b[ks]), frac_removed_sat=1 - ks.mean(), n_hmi=n_hmi, n_aia=n_aia, CV_noise=cvn,
                         n_sat_frames=int((v.sat_flag == True).sum())))
    return pd.DataFrame(rows)


def flare_details(c, ev):
    """The label code's event list (build_dataset: swpc.fetch -> joinable M1+, region in noaa_ars at t, start in (t, t+24h])."""
    _, m1 = swpc.fetch(pd.Timestamp(ev[0]), pd.Timestamp(ev[1]), verbose=False)
    by = {int(a): g[["start", "flux"]].sort_values("start") for a, g in m1.groupby("noaa_ar")}
    out = []
    for e in c.itertuples():
        ars = [int(a) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()]
        f = pd.concat([g[(g.start > e.t) & (g.start <= e.t + pd.Timedelta("24h"))] for a in ars if (g := by.get(a)) is not None] or
                      [pd.DataFrame(columns=["start", "flux"])])
        if len(f):
            mx = float(f.flux.max()); L = swpc.class_of(mx)
            out.append(dict(eid=e.eid, pos=1, peak_class=f"{L}{mx / {'X': 1e-4, 'M': 1e-5}[L]:.1f}",
                            hours_to_first_M1=(f.start.min() - e.t).total_seconds() / 3600))
        else:
            out.append(dict(eid=e.eid, pos=0, peak_class="", hours_to_first_M1=np.nan))
    return pd.DataFrame(out)


if __name__ == "__main__":
    t00 = time.time(); hs, TH, MOD = load_models()
    D = {}
    for k in SETS:
        c = load_set(k); c = c.merge(series_variants(c, SETS[k]["root"]), on="eid", how="left")
        c = c.merge(flare_details(c, SETS[k]["evL"]), on="eid", how="left"); D[k] = c
    # ---- STOP checks before anything is reported
    bad = {k: int((np.abs(D[k].cv_repro - D[k].primary_CV_box) >= 1e-9).sum()) for k in D}
    if any(bad.values()):
        print(f"STOP: stored CV_box not reproduced (|diff| >= 1e-9) in {bad}"); sys.exit(1)
    mism = {k: D[k].loc[D[k].pos != D[k].true_alarm, "eid"].tolist() for k in D}
    if any(mism.values()):
        print(f"STOP: label code does not reproduce stored true_alarm: {mism}"); sys.exit(1)
    pool = ProcessPoolExecutor(W); out = {}
    for k, c in D.items():
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy(); groups = [np.where(h == v)[0] for v in np.unique(h)]
        pC, pCV = pred(MOD["C"], c), pred(MOD["C_CV"], c); kC, kCV = pC >= TH["C"]["tau"], pCV >= TH["C_CV"]["tau"]
        c["tier"] = np.where(~kC, "NO ALERT", np.where(~kCV, "WATCH", "WARNING")); c["cv_only"] = ~kC & kCV
        c["hist_group"] = np.where(c.n_M + c.n_X >= 1, "JUST-FLARED", np.where(c.n_C + c.n_M + c.n_X == 0, "QUIET-NOW", "C-only"))
        c["regions"] = c.noaa_ars.astype(str).str.count(",") + 1
        c["CV_corr"] = np.sqrt(np.maximum(c.primary_CV_box ** 2 - c.CV_noise ** 2, 0))
        B = np.array(boot_many({"r": ("rate", dict(y=y, w=w, g=c.tier.to_numpy(), levels=TIERS, groups=groups), 2000, 0)}, pool)["r"], float)
        tw = pd.read_csv(SETS[k]["twins"]) if SETS[k]["twins"] else twins(c)[0]
        ests, jobs = [], {}
        for col in ["primary_CV_box", "CV_exp", "CV_sat", "CV_corr"]:
            e, j = ratio_jobs(f"{k} {col}", c, col, "ratio", tw); ests.append(e); jobs.update(j)
        RB = boot_many(jobs, pool)
        for e in ests:
            e["tw_CI"] = pct(RB[(e["measure"], "tw")])
        out[k] = (c, B, tw, ests)
    pool.shutdown()
    for k, (c, B, tw, ests) in out.items():                       # original twins ratio must reproduce the committed one
        o = ests[0]
        assert (round(o["ratio_twins"], 4), round(o["tw_CI"][0], 4), round(o["tw_CI"][1], 4)) == SETS[k]["orig"], (k, o["ratio_twins"], o["tw_CI"])

    print("DESCRIPTIVE AIA 94 A FOLLOW-UPS — EXPLORATORY / DESCRIPTIVE, post-hoc, not pre-registered (947e4c0). Sets never pooled.")
    print(f"integrity: {len(hs)} frozen files + thresholds.json hash-verified; tau_C {TH['C']['tau']:.6f}, tau_C_CV {TH['C_CV']['tau']:.6f}; no refitting")
    print("checks: stored CV_box reproduced from the series (|diff| < 1e-9) for all episodes: "
          + ", ".join(f"{k} {len(D[k])}/{len(D[k])} (max |diff| {np.abs(D[k].cv_repro - D[k].primary_CV_box).max():.1e})" for k in D)
          + "; label code reproduces stored true_alarm for every episode (0 mismatches); original twins ratios reproduced exactly")
    fig_rows = []
    for k, (c, B, tw, ests) in out.items():
        y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
        print(f"\n{'=' * 100}\n{SETS[k]['name']}: {len(c)} episodes (true {int(y.sum())}, false {int((y == 0).sum())}, HARPs {c.harpnum.nunique()})")
        print("\nPART 1 — ALERT TIERS (NO ALERT: p_C < tau_C; WATCH: p_C >= tau_C and p_C_CV < tau_C_CV; WARNING: both >=); "
              "weighted flare rate = weighted share of true alarm episodes; HARP bootstrap 2,000, seed 0")
        rows = []
        for i, t in enumerate(TIERS):
            m = (c.tier == t).to_numpy(); lo, hi = pct(B[:, i])
            rate = (w * y * m).sum() / (w * m).sum() if m.any() else np.nan
            f = m & (y == 0)
            rows.append(dict(tier=t, episodes=int(m.sum()), true=int((m & (y == 1)).sum()), false=int(f.sum()), rate_w=rate, rate_lo=lo, rate_hi=hi,
                             share_true_n=(m & (y == 1)).sum() / y.sum(), share_true_w=(w * y * m).sum() / (w * y).sum(),
                             delayed_in_false=f"{int((f & (c.delayed == 1)).sum())}/{int(f.sum())}",
                             delayed_in_false_w=(w * f * (c.delayed == 1)).sum() / (w * f).sum() if f.any() else np.nan))
            fig_rows.append(dict(set=k, tier=t, rate=rate, lo=lo, hi=hi, n=int(m.sum())))
        T1 = pd.DataFrame(rows); print(T1.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        rr = B[:, 2] / B[:, 1]; rr = rr[np.isfinite(rr)]
        pt = T1.rate_w[2] / T1.rate_w[1]
        print(f"rate ratio WARNING/WATCH: {pt:.4f} [{np.percentile(rr, 2.5):.4f}, {np.percentile(rr, 97.5):.4f}] ({len(rr)} of 2,000 resamples defined)")
        co = c[c.cv_only]
        print(f"CV-only (p_C < tau_C and p_C_CV >= tau_C_CV; not a tier, contained in NO ALERT): {len(co)} episodes (true {int(co.true_alarm.sum())}, "
              f"false {int((co.true_alarm == 0).sum())})")
        print("\nPART 2 — IS CV_box AN ARTIFACT? (recomputed with only the frame set changed; euv_dctrl.cv, valid_primary frames)")
        tr, fa = c[c.true_alarm == 1], c[c.true_alarm == 0]
        for lab, fr in [("2a exposure within +-5% of the episode's median exptime (valid frames)", "frac_removed_exp"),
                        ("2b saturation: sat_px == 0", "frac_removed_sat")]:
            print(f"  {lab}: valid frames removed {100 * (c[fr] * c.n_valid).sum() / c.n_valid.sum():.2f}% of {int(c.n_valid.sum())}; "
                  f"per-episode median removed: true {100 * tr[fr].median():.2f}%, false {100 * fa[fr].median():.2f}%")
        rn = c.CV_noise / c.primary_CV_box
        print(f"  2c photon + read noise (g = {G_DN_PER_PH} DN/photon, read noise {READ_DN} DN/px; n_AIA = n_HMI x (CDELT1_HMI / 0.6)^2 x (1 - frac_outside)): "
              f"median CV_noise/CV_box all {rn.median():.4f}, true {rn[c.true_alarm == 1].median():.4f}, false {rn[c.true_alarm == 0].median():.4f}; "
              f"max {rn.max():.4f}; CV_corr = 0 in {int((c.CV_corr == 0).sum())} episodes")
        print(f"  twins ratio, median true / median false ({'TEST 1 stored pairs (ae1b174)' if k == 'S1' else 'pairs regenerated with the 5abc40a code, verified by reproducing its ratio'}; "
              f"pairs resampled by true HARP, 2,000, seed 0):")
        for e, lab in zip(ests, ["original CV_box", "2a CV_exp", "2b CV_sat", "2c CV_corr"]):
            und = int(c[e["measure"].split(" ", 1)[1]].isna().sum())
            print(f"    {lab:16s} {e['ratio_twins']:.4f} [{e['tw_CI'][0]:.4f}, {e['tw_CI'][1]:.4f}]  pairs {e['pairs']} of {len(tw)} "
                  f"(dropped {len(tw) - e['pairs']}); undefined episodes {und}; medians {e['twin_med_true']:.4f} / {e['twin_med_false']:.4f}")
        print("\nPART 3 — CALM-FLARER PROFILE (true alarm episodes only; flare details from the label code's event list; K2 true scale)")
        t = c[c.true_alarm == 1].copy(); t["abs_lon"] = t.lon_fwt.abs(); t["peak_letter"] = t.peak_class.str[0]
        g = t.groupby("tier").agg(n=("eid", "size"), hours_to_first_M1_med=("hours_to_first_M1", "median"), score_med=("score", "median"),
                                  CV_box_med=("primary_CV_box", "median"), fill_med=("primary_fill", "median"), abs_lon_med=("abs_lon", "median"),
                                  sat_frames_med=("n_sat_frames", "median"), two_region=("regions", lambda s: int((s == 2).sum())))
        print(g.reindex([x for x in TIERS if x in g.index]).to_string(float_format=lambda v: f"{v:.4f}"))
        for col in ["peak_letter", "hist_group"]:
            print(f"  counts by tier x {col}: " + "; ".join(f"{tt}: {t[t.tier == tt][col].value_counts().sort_index().to_dict()}" for tt in TIERS if (t.tier == tt).any()))
        if k == "S1":
            print("\n  S1 — every true alarm episode:")
            print(t.sort_values(["tier", "t"])[["eid", "tier", "peak_class", "hours_to_first_M1", "hist_group", "regions", "score", "primary_CV_box",
                                                "primary_fill", "abs_lon", "n_sat_frames"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        c.drop(columns=[x for x in ["delayed_followup_incomplete"] if x in c]).to_csv(f"data/descriptive_aia94_{k}.csv", index=False)
    # ---- figure (descriptive, post-hoc): weighted flare rate per tier, one panel per set
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    F = pd.DataFrame(fig_rows); fig, axs = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True, facecolor="#fcfcfb")
    for ax, k in zip(axs, SETS):
        f = F[F.set == k]; x = np.arange(len(TIERS)); ax.set_facecolor("#fcfcfb")
        ax.errorbar(x, f.rate, yerr=[f.rate - f.lo, f.hi - f.rate], fmt="o", ms=8, color="#2a78d6", ecolor="#2a78d6", elinewidth=2, capsize=0)
        for xi, (_, r) in zip(x, f.iterrows()):
            ax.annotate(f"n={r.n}", (xi, 0), xytext=(0, -2), textcoords="offset points", ha="center", va="top", fontsize=8, color="#52514e")
        ax.set_xticks(x, TIERS, fontsize=9, color="#0b0b0b"); ax.set_xlim(-0.5, 2.5); ax.set_ylim(-0.08, 1)
        ax.set_title(SETS[k]["name"], fontsize=9, color="#0b0b0b"); ax.grid(axis="y", color="#e6e5e0", lw=0.8); ax.set_axisbelow(True)
        for sp in ["top", "right", "left"]:
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#b9b8b0"); ax.tick_params(colors="#52514e", length=0)
    axs[0].set_ylabel("weighted flare rate (true alarm share)", fontsize=9, color="#52514e")
    fig.suptitle("Weighted flare rate by alert tier (C / C_CV at frozen dev thresholds), 95% HARP-bootstrap CI — descriptive, post-hoc",
                 fontsize=10, color="#0b0b0b")
    fig.tight_layout(); os.makedirs("figures", exist_ok=True); fig.savefig("figures/alert_tiers.png", dpi=160, facecolor="#fcfcfb")
    print(f"\nfigure: figures/alert_tiers.png; wall {time.time() - t00:.1f} s, workers {W}")
