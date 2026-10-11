"""SENSITIVITY CHECK ONLY (decisions.md 2026-09-27, 92027fa). Post-hoc, on already-analysed data; nothing here is a test.
CV_box twins ratio under V0 (stored primary), V1 (stored flare-excluded) and V2 (image-only spike removal; 3 s primary,
2.5 s / 4 s robustness) x T_a (magnetic twins) / T_b (magnetic + flare-history twins). Sets S1-S3 reported separately."""
import glob, json, os, sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from scipy.stats import binomtest
from euv_dctrl import cv
from descriptive_aia94 import SETS, load_set
from euv_f2_replication import twins
from phase_f import boot_many, ratio_jobs, pct, W

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
KS = [3.0, 2.5, 4.0]                                              # V2 threshold (x s); 3 s primary
SLOTS = 120                                                       # 12-min slots in (t-24h, t], as euv_full's fill grid
VERS = [("V0", "V0 stored primary"), ("V1", "V1 flare frames removed"), ("V2_3", "V2 image-only 3 s"),
        ("V2_2.5", "V2 image-only 2.5 s (robustness)"), ("V2_4", "V2 image-only 4 s (robustness)")]
S1_S1_TEST = (47, 2.817, 1.017, 6.823)                            # TEST 1 secondary s1 (ae1b174), decisions.md


def spikes(b, k, diag=False):
    """V2 a)-d): -> keep mask. Running median over 5 remaining frames centred on i (shrinks at the ends); flag r_i > k s.
    diag: also (s == 0 in any round, still flagging in round 5, fraction of round-1 residuals exactly 0) — descriptive only."""
    keep = np.ones(len(b), bool); s0, cap, z1 = False, False, np.nan
    for rnd in range(5):
        ix = np.where(keep)[0]; x = b[ix]; n = len(x)
        r = x - np.array([np.median(x[max(0, i - 2):i + 3]) for i in range(n)])
        s = 1.4826 * np.median(np.abs(r)); f = r > k * s; s0 |= s == 0
        if rnd == 0:
            z1 = float(np.mean(r == 0))
        if not f.any():
            break
        keep[ix[f]] = False; cap = rnd == 4
    return (keep, s0, cap, z1) if diag else keep


def versions(c, root):
    rows = []
    for e in c.itertuples():
        s = pd.read_csv(f"{root}/series/{e.eid}.csv", parse_dates=["t_obs"], float_precision="round_trip")
        v = s[s.valid_primary].sort_values("t_obs", kind="stable"); t, b = v.t_obs.to_numpy(), v.box.to_numpy()
        fl = v.flare.to_numpy(bool); sv = s[s.valid_sens]
        r = dict(eid=e.eid, V0_repro=cv(t, b), V1_repro=cv(sv.t_obs.to_numpy(), sv.box.to_numpy()), n_valid=len(v), n_flare=int(fl.sum()))
        for k in KS:
            keep, s0, cap, z1 = spikes(b, k, diag=True); fill = keep.sum() / SLOTS
            r.update({f"V2_{k:g}": cv(t[keep], b[keep]) if fill >= 0.80 else np.nan, f"fill2_{k:g}": fill, f"s0_{k:g}": s0, f"cap_{k:g}": cap,
                      f"zero_r1": z1,
                      f"nflag_{k:g}": int((~keep).sum()), f"nflag_in_flare_{k:g}": int((~keep & fl).sum())})
        rows.append(r)
    return pd.DataFrame(rows)


def reading(r, lo):
    return "direction holds, CI above 1" if r > 1 and lo > 1 else "direction holds, CI includes 1" if r > 1 else "direction reversed"


if __name__ == "__main__":
    z = 10 + np.random.RandomState(0).normal(0, 0.1, 120); z[50] += 5; z[51] -= 5      # V2 self-check: one up-spike flagged, a dip is not
    assert not spikes(z, 3.0)[50] and spikes(z, 3.0)[51] and spikes(z[:50], 3.0).sum() >= 45
    t00 = time.time(); D, TW = {}, {}
    for k, S in SETS.items():
        c = load_set(k)
        r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{S['root']}/results/*.json")])[["eid", "sens_fill", "sens_CV_box"]]
        r[["sens_fill", "sens_CV_box"]] = r[["sens_fill", "sens_CV_box"]].apply(pd.to_numeric, errors="coerce")
        c = c.merge(r, on="eid", how="left").merge(versions(c, S["root"]), on="eid", how="left")
        c["V0"] = c.primary_CV_box
        c["V1"] = np.where((c.sens_fill >= 0.80) & np.isfinite(c.sens_CV_box) & (c.sens_CV_box > 0), c.sens_CV_box, np.nan)
        D[k] = c
        Ta = pd.read_csv(S["twins"]) if S["twins"] else twins(c)[0]
        if S["twins"]:                                            # regenerated S1 pairs must equal the stored TEST 1 pairs (same set and order)
            g = twins(c)[0]
            assert len(g) == len(Ta) and (g.true_eid.values == Ta.true_eid.values).all() and (g.false_eid.values == Ta.false_eid.values).all()
        TW[k] = {"T_a": Ta, "T_b": twins(c, by_group=True)[0]}
    # ---- CHECKS FIRST (STOP if any fails)
    bad = {}
    for k, c in D.items():
        d0 = np.abs(c.V0_repro - c.primary_CV_box)
        s1 = np.isfinite(c.sens_CV_box); d1 = np.abs(c.V1_repro - c.sens_CV_box)
        bad[k] = dict(V0=int((~(d0 < 1e-9)).sum()), V1=int((s1 & ~(d1 < 1e-9)).sum() + (~s1 & np.isfinite(c.V1_repro)).sum()),
                      max0=float(d0.max()), max1=float(d1[s1].max()), n_sens_nan=int((~s1).sum()))
    if any(b["V0"] or b["V1"] for b in bad.values()):
        print(f"STOP: stored V0/V1 not reproduced from the series files: {bad}"); sys.exit(1)

    pool = ProcessPoolExecutor(W); jobs, cells = {}, []
    for k, c in D.items():
        for tn, tw in TW[k].items():
            for col, lab in VERS:
                key = f"{k} {tn} {col}"; e, j = ratio_jobs(key, c, col, "ratio", tw)
                if e["pairs"]:                                    # 0 pairs: no bootstrap; ratio, CI and reading undefined
                    jobs[(key, "tw")] = j[(key, "tw")]
                v = c.set_index("eid")[col]; p = tw.assign(xt=tw.true_eid.map(v), xf=tw.false_eid.map(v)).dropna(subset=["xt", "xf"])
                hi_, ties = int((p.xt > p.xf).sum()), int((p.xt == p.xf).sum())
                cells.append(dict(set=k, twins=tn, version=col, label=lab, pairs_all=len(tw), pairs=e["pairs"], dropped=len(tw) - e["pairs"],
                                  med_true=e["twin_med_true"], med_false=e["twin_med_false"], ratio=e["ratio_twins"], true_higher=hi_, ties=ties,
                                  sign_p=binomtest(hi_, len(p) - ties, 0.5, alternative="two-sided").pvalue if len(p) - ties else np.nan))
    B = boot_many(jobs, pool); pool.shutdown()
    T = pd.DataFrame(cells)
    bb = lambda r: B.get((f"{r.set} {r.twins} {r.version}", "tw"), [])
    T["CI_lo"], T["CI_hi"] = zip(*[pct(bb(r)) for r in T.itertuples()])
    T["undef_resamples"] = [int(np.sum(~np.isfinite(np.asarray(bb(r), float)))) for r in T.itertuples()]
    T["reading"] = [reading(r.ratio, r.CI_lo) if r.pairs else "undefined (0 pairs)" for r in T.itertuples()]
    for k in SETS:                                                # original ratios must reproduce (T_a V0 = committed; S1 T_b V0 = TEST 1 s1)
        o = T[(T.set == k) & (T.twins == "T_a") & (T.version == "V0")].iloc[0]
        assert (round(o.ratio, 4), round(o.CI_lo, 4), round(o.CI_hi, 4)) == SETS[k]["orig"], (k, o.ratio, o.CI_lo, o.CI_hi)
    o = T[(T.set == "S1") & (T.twins == "T_b") & (T.version == "V0")].iloc[0]
    assert (o.pairs, round(o.ratio, 3), round(o.CI_lo, 3), round(o.CI_hi, 3)) == S1_S1_TEST, (o.pairs, o.ratio, o.CI_lo, o.CI_hi)

    print("SENSITIVITY CHECK ONLY — post-hoc, on already-analysed data (92027fa). Not a test; sets never pooled.")
    print("checks: stored V0 and V1 reproduced from the series files with the frame-subset code path (euv_dctrl.cv; |diff| < 1e-9): "
          + "; ".join(f"{k} {len(D[k])}/{len(D[k])} (max |diff| V0 {b['max0']:.1e}, V1 {b['max1']:.1e}; stored V1 undefined (< 3 frames) "
                      f"{b['n_sens_nan']}, reproduced undefined too)" for k, b in bad.items()))
    print("       T_a = stored TEST 1 pairs (S1; regenerated pairs identical) / pairs regenerated with the 5abc40a code (S2, S3); T_a x V0 reproduces the "
          f"committed ratios for S1-S3; S1 T_b x V0 reproduces TEST 1 s1 ({S1_S1_TEST[0]} pairs, {S1_S1_TEST[1]} [{S1_S1_TEST[2]}, {S1_S1_TEST[3]}])")
    print(f"V2 fill = remaining frames / {SLOTS} expected 12-min slots in (t-24h, t]; V1 defined if stored sens_fill >= 0.80")
    for k, c in D.items():
        tr, fa = c[c.true_alarm == 1], c[c.true_alarm == 0]
        print(f"\n{'=' * 100}\n{SETS[k]['name']}: {len(c)} episodes (true {len(tr)}, false {len(fa)}, HARPs {c.harpnum.nunique()}); "
              f"valid frames {int(c.n_valid.sum())}, of which inside V1 flare windows {int(c.n_flare.sum())}")
        print(f"  defined episodes: V0 {int(c.V0.notna().sum())}, V1 {int(c.V1.notna().sum())}, "
              + ", ".join(f"V2 {q:g} s {int(c[f'V2_{q:g}'].notna().sum())}" for q in KS))
        for q in KS:
            nf, nif = int(c[f"nflag_{q:g}"].sum()), int(c[f"nflag_in_flare_{q:g}"].sum())
            print(f"  V2 {q:g} s frames removed per episode: true median {tr[f'nflag_{q:g}'].median():.1f}, mean {tr[f'nflag_{q:g}'].mean():.2f}; "
                  f"false median {fa[f'nflag_{q:g}'].median():.1f}, mean {fa[f'nflag_{q:g}'].mean():.2f}; flagged frames {nf}; "
                  f"of V2-flagged frames inside V1 flare windows {nif}/{nf} = {nif / nf if nf else np.nan:.4f}; "
                  f"of V1 flare frames flagged by V2 {nif}/{int(c.n_flare.sum())} = {nif / c.n_flare.sum() if c.n_flare.sum() else np.nan:.4f}; "
                  f"fill >= 0.80 in {int((c[f'fill2_{q:g}'] >= 0.80).sum())}; median fill {c[f'fill2_{q:g}'].median():.4f}; "
                  f"s = 0 in some round in {int(c[f's0_{q:g}'].sum())} episodes; still flagging in round 5 (cap) in {int(c[f'cap_{q:g}'].sum())}")
        print(f"  round-1 residuals exactly 0 (median of 5 = the frame's own value), per-episode fraction: median {c.zero_r1.median():.4f}, "
              f"IQR [{c.zero_r1.quantile(.25):.4f}, {c.zero_r1.quantile(.75):.4f}] (descriptive)")
        print("\n  twins ratio = median(true) / median(false) over pairs with both members defined; 95% CI pairs resampled by true HARP, 2,000, seed 0; "
              "sign test two-sided (true higher vs lower; ties excluded)")
        print(T[T.set == k][["twins", "label", "pairs_all", "pairs", "dropped", "med_true", "med_false", "ratio", "CI_lo", "CI_hi", "true_higher",
                              "ties", "sign_p", "undef_resamples", "reading"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        c.to_csv(f"data/sensitivity_combined_{k}.csv", index=False)
    T.to_csv("data/sensitivity_combined_cells.csv", index=False)
    # ---- figure: twins ratio with CI per cell (log x), S1 on top, S2 / S3 below
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    COL = {"T_a": "#2a78d6", "T_b": "#eb6834"}; NAME = {"T_a": "T_a magnetic twins", "T_b": "T_b magnetic + flare-history twins"}
    fig = plt.figure(figsize=(11, 8.2), facecolor="#fcfcfb"); gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.08)
    axs = {"S1": fig.add_subplot(gs[0, :]), "S2": fig.add_subplot(gs[1, 0]), "S3": fig.add_subplot(gs[1, 1])}
    for k, ax in axs.items():
        ax.set_facecolor("#fcfcfb"); y0 = np.arange(len(VERS))[::-1]
        for dy, tn in [(0.14, "T_a"), (-0.14, "T_b")]:
            f = T[(T.set == k) & (T.twins == tn)].set_index("version").loc[[v for v, _ in VERS]]
            ax.errorbar(f.ratio, y0 + dy, xerr=[f.ratio - f.CI_lo, f.CI_hi - f.ratio], fmt="o", ms=7, color=COL[tn], ecolor=COL[tn],
                        elinewidth=2, capsize=0, label=NAME[tn])
            for yy, (_, r) in zip(y0 + dy, f.iterrows()):
                if r.pairs:
                    ax.annotate(f"{r.ratio:.2f} ({r.pairs})", (r.CI_hi, yy), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7, color="#52514e")
                else:
                    ax.annotate(f"{NAME[tn].split()[0]}: 0 pairs (undefined)", (1, yy), xytext=(4, 0), textcoords="offset points", va="center",
                                fontsize=7, color="#52514e")
        ax.axvline(1, color="#8a8984", lw=1, zorder=0); ax.set_xscale("log"); ax.set_xlim(0.3, 60); ax.set_ylim(-0.5, len(VERS) - 0.5)
        ax.set_yticks(y0, [l for _, l in VERS] if k != "S3" else [""] * len(VERS), fontsize=8, color="#0b0b0b")
        ax.set_title(SETS[k]["name"], fontsize=9, color="#0b0b0b"); ax.grid(axis="x", color="#e6e5e0", lw=0.8); ax.set_axisbelow(True)
        for sp in ["top", "right", "left"]:
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#b9b8b0"); ax.tick_params(colors="#52514e", length=0, labelsize=8)
        ax.set_xlabel("twins ratio, median true / median false (log scale); label: ratio (pairs)", fontsize=8, color="#52514e")
    axs["S1"].legend(loc="lower right", fontsize=8, frameon=False)
    fig.suptitle("CV_box twins ratio with 95% CI by frame set and twin type — post-hoc sensitivity", fontsize=10, color="#0b0b0b")
    os.makedirs("figures", exist_ok=True); fig.savefig("figures/sensitivity_combined.png", dpi=160, facecolor="#fcfcfb", bbox_inches="tight")
    print(f"\nfigure: figures/sensitivity_combined.png; wall {time.time() - t00:.1f} s, workers {W}")
