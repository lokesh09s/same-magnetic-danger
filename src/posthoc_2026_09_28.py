"""PART 1 of the 2026-09-28 documentation update (decisions.md 8aa1797 / 784b1a8). POST-HOC, exploratory: reproduces analyses originally
computed by Claude AI in chat on 2026-09-27/28, with the repo's label code (swpc.fetch joinable events, K2 true scale, noaa_ars region join)
and frozen models only (euv_extra A, A_CV, C, C_CV; data/combo_t COMBO-T). Dev predictions out-of-fold (dev_rows.csv folds); new-set
predictions = mean of 5 fold models. No new data, no JSOC. Writes docs/posthoc_2026-09-28.md; stdout = checks + mismatch summary."""
import hashlib, json, os, sys, time, warnings
import numpy as np, pandas as pd, joblib, swpc
from scipy.stats import spearmanr, wilcoxon, binomtest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.preprocessing import StandardScaler
from concurrent.futures import ProcessPoolExecutor
from stage4_models import LR, K
from phase_f import load_base, prep, tau_keep, op_stats, wlogloss, boot_many, choices, pct, med_ratio, A_COLS, W
from euv_confirm_tests import log_r
from euv_confirm_retest import load_models
from descriptive_aia94 import load_set

warnings.filterwarnings("ignore")
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
LAB = "POST-HOC, exploratory, originally computed by Claude AI in chat on 2026-09-27/28; reproduced here"
SETS = ["dev", "test", "extra", "2022", "2025-26"]; LATER = SETS[1:]; Y2124 = ["test", "extra", "2022"]
NAME = {"dev": "dev 2010-19", "test": "2021/23/24 test (euv_test)", "extra": "2021/23/24 extra", "2022": "2022", "2025-26": "2025-26"}
WIN = {"dev": ("2010-04-26", "2020-01-02"), "test": ("2020-12-27", "2025-01-02 23:59"), "extra": ("2020-12-27", "2025-01-02 23:59"),
       "2022": ("2020-12-27", "2025-01-02 23:59"), "2025-26": ("2024-12-27", "2026-08-18 23:59")}
LEVELS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0]
BINS = [(0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"), (5, 10 ** 6, "5+")]
TIERS = [(0, 0.05, "<5%"), (0.05, 0.15, "5-15%"), (0.15, 0.30, "15-30%"), (0.30, 1.01, ">30%")]
OUT = []; MIS = {}
say = OUT.append


def md(df, nd=4):
    f = lambda v: ("—" if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)) else
                   f"{v:.{nd}f}" if isinstance(v, (float, np.floating)) else str(v))
    return "\n".join(["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)] +
                     ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)]) + "\n"


def chk(item, label, repo, chat, nd):
    """compare at the chat's precision; record mismatches (nothing is adjusted)."""
    r = round(float(repo), nd) if nd is not None else repo
    ok = (r == chat) if not isinstance(chat, float) else abs(r - chat) < 1e-9
    MIS.setdefault(item, [0, []]); MIS[item][0] += 1
    if not ok:
        MIS[item][1].append(f"{label}: repo {r} vs chat {chat}")


def statement(item):
    n, bad = MIS.get(item, [0, []])
    if not n:
        return f"**Match statement ({item}):** no chat numbers to compare.\n"
    return (f"**Match statement ({item}):** the reproduction matches the chat numbers ({n} values compared at the chat's precision).\n" if not bad else
            f"**Match statement ({item}):** {n - len(bad)} of {n} compared values match; MISMATCHES (repo vs chat, nothing adjusted): " + "; ".join(bad) + ".\n")


# ================================================================ data
def fit(c, cols, Cv):
    """= euv_heldout.fit_folds with LogisticRegression C = Cv (Step 6 settings otherwise)."""
    y, w, f = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.fold.to_numpy(); p, ms = np.empty(len(c)), []
    for k in range(K):
        tr, te = f != k, f == k
        sc = StandardScaler().fit(c.loc[tr, cols]); m = LogisticRegression(**dict(LR, C=Cv)).fit(sc.transform(c.loc[tr, cols]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]; ms.append((sc, m, cols))
    return ms, p


pred = lambda ms, c: np.mean([m.predict_proba(sc.transform(c[cols]))[:, 1] for sc, m, cols in ms], axis=0)


def oof(ms, c):
    p = np.full(len(c), np.nan)
    for k, (sc, m, cols) in enumerate(ms):
        te = c.fold.to_numpy() == k; p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]
    return p


def cls(f):
    L = swpc.class_of(f); return f"{L}{f / {'C': 1e-6, 'M': 1e-5, 'X': 1e-4}.get(L, 1e-7):.1f}"


def flare_features(c, lo, hi):
    """Repo label code: swpc.fetch joinable events (K2 true scale), regions in noaa_ars; prior window start in (t - W, t)."""
    fl, _ = swpc.fetch(pd.Timestamp(lo), pd.Timestamp(hi), verbose=False)
    by = {int(a): g[["start", "flux"]] for a, g in fl.groupby("noaa_ar")}
    rows = []
    for e in c.itertuples():
        ars = [int(a) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()]
        g = pd.concat([by[a] for a in ars if a in by] or [pd.DataFrame(columns=["start", "flux"])]).drop_duplicates().sort_values("start")
        g["flux"] = g.flux.astype(float); t = e.t
        pre = lambda h: g[(g.start > t - pd.Timedelta(hours=h)) & (g.start < t)]
        p24, post = pre(24), g[(g.start > t) & (g.start <= t + pd.Timedelta("24h"))]
        Cc = p24[(p24.flux >= 1e-6) & (p24.flux < 1e-5)]; m1 = post[post.flux >= 1e-5]
        r = dict(eid=e.eid, nC24=len(Cc), anyC24=len(Cc) > 0, anyCplus24=bool((p24.flux >= 1e-6).any()), anyMX24=bool((p24.flux >= 1e-5).any()),
                 maxCclass24=float(Cc.flux.max()) if len(Cc) else 0.0, pos=int(len(m1) > 0),
                 h_to_M1=(m1.start.min() - t).total_seconds() / 3600 if len(m1) else np.nan,
                 flares24="; ".join(f"{cls(f)} {s:%Y-%m-%d %H:%M}" for s, f in zip(p24.start, p24.flux) if f >= 1e-6))
        for Wh in (12, 24, 48):
            mx = pre(Wh).flux.max() if len(pre(Wh)) else 0.0
            for L in (1e-6, 2e-6, 5e-6):
                r[f"prot_{Wh}_{int(L * 1e6)}"] = int(mx >= L)
        rows.append(r)
    return pd.DataFrame(rows)


def load_all():
    hs, TH, MOD = load_models()
    ht = json.load(open("data/combo_t/model_hashes.json")); assert all(H(f) == h for f, h in ht.items()), "COMBO-T files changed"
    TT = json.load(open("data/combo_t/thresholds.json"))
    MOD["T"] = [(lambda d: (d["scaler"], d["model"], d["cols"]))(joblib.load(f"data/combo_t/models/COMBO_T_fold{k}.joblib")) for k in range(5)]
    D = {}
    dv = load_base(); c = prep(dv, dv.P & np.isfinite(dv.primary_CV_box) & (dv.primary_CV_box > 0))
    dr = pd.read_csv("data/euv_extra/dev_rows.csv")
    assert (c.eid.to_numpy() == dr.eid.to_numpy()).all() and (c.fold.to_numpy() == dr.fold.to_numpy()).all()
    c["logR"] = log_r(c, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59")); c["log10_CV_box"] = np.log10(c.primary_CV_box); D["dev"] = c
    tc = pd.read_csv("data/stage5/cohort_test_primary.csv", parse_dates=["t"]); tc["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(tc.harpnum, tc.t)]
    r = pd.DataFrame([json.load(open(p)) for p in __import__("glob").glob("data/euv_test/results/*.json")])[["eid", "primary_fill", "primary_CV_box"]]
    r[["primary_fill", "primary_CV_box"]] = r[["primary_fill", "primary_CV_box"]].apply(pd.to_numeric, errors="coerce")
    c = tc.drop(columns=["weight"]).merge(r, on="eid", how="left")
    c = c[(c.primary_fill >= 0.80) & np.isfinite(c.primary_CV_box) & (c.primary_CV_box > 0)].reset_index(drop=True); assert len(c) == 306
    c["log10_CV_box"] = np.log10(c.primary_CV_box); c["logR"] = log_r(c, pd.Timestamp("2020-12-29"), pd.Timestamp("2025-01-01"))
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size"); D["test"] = c
    for k, s in [("extra", "S2"), ("2022", "S3"), ("2025-26", "S1")]:
        D[k] = load_set(s)
    for k, c in D.items():
        F = flare_features(c, *WIN[k]); D[k] = c.merge(F, on="eid", how="left", validate="one_to_one")
        D[k]["prot12"] = D[k].prot_12_2; D[k]["prot24_1"] = D[k].prot_24_1; D[k]["inter24_1"] = D[k].prot_24_1 * D[k].log10_CV_box
    return hs, TH, TT, MOD, D


# ================================================================ main
if __name__ == "__main__":
    t00 = time.time(); hs, TH, TT, MOD, D = load_all()
    dvrows = pd.read_csv("data/combo_t/dev_rows.csv")
    assert (D["dev"].prot12.to_numpy() == dvrows.prot12.to_numpy()).all(), "prot12 does not reproduce the frozen COMBO-T dev rows"
    lab_mis = {k: int((c.pos != c.true_alarm).sum()) for k, c in D.items()}
    # COMBO default + 90-configuration grid (dev only)
    dev = D["dev"]; yd, wd = dev.true_alarm.to_numpy(), dev.weight.to_numpy(); grid = []
    for Wh in (12, 24, 48):
        for L in (1, 2, 5):
            dev[f"x_{Wh}_{L}"] = dev[f"prot_{Wh}_{L}"] * dev.log10_CV_box
            for inter in (True, False):
                for Cv in (0.03, 0.1, 0.3, 1, 3):
                    cols = A_COLS + ["logR", "log10_CV_box", f"prot_{Wh}_{L}"] + ([f"x_{Wh}_{L}"] if inter else [])
                    _, p = fit(dev, cols, Cv); tau = tau_keep(p, yd, wd); tk, fr, _ = op_stats(yd, wd, p >= tau)
                    grid.append(dict(W_h=Wh, L=f"C{L}.0", interaction="yes" if inter else "no", C=Cv, tau=tau, false_removed_w=fr, true_kept_w=tk,
                                     LL=wlogloss(yd, p, wd), AUC_w=roc_auc_score(yd, p, sample_weight=wd)))
    G = pd.DataFrame(grid).sort_values(["false_removed_w", "LL"], ascending=[False, True]).reset_index(drop=True); G.insert(0, "rank", G.index + 1)
    top = G.iloc[0]
    MOD["D"], pD_dev = fit(dev, A_COLS + ["logR", "log10_CV_box", "prot24_1", "inter24_1"], 1.0)
    TAU = {m: TH[m]["tau"] for m in ["A", "A_CV", "C", "C_CV"]}; TAU["T"] = TT["tau"]; TAU["D"] = tau_keep(pD_dev, yd, wd)
    # predictions
    P = {}
    for k, c in D.items():
        P[k] = {m: (oof(MOD[m], c) if k == "dev" and m != "D" else pD_dev if k == "dev" else pred(MOD[m], c)) for m in ["A", "A_CV", "C", "C_CV", "T", "D"]}
    oof_ok = all(wlogloss(yd, P["dev"][m], wd) == TH[m]["dev_oof_logloss"] for m in ["A", "A_CV", "C", "C_CV"]) and \
        wlogloss(yd, P["dev"]["T"], wd) == TT["dev_oof_logloss"] and tau_keep(P["dev"]["T"], yd, wd) == TT["tau"]
    assert oof_ok, "frozen-model dev OOF does not reproduce the frozen dev log-loss / tau"
    grid_ok = (top.W_h, top.L, top.interaction, top.C) == (12, "C2.0", "no", 0.3) and top.tau == TT["tau"] and top.LL == TT["dev_oof_logloss"]
    KEEP = {k: {m: P[k][m] >= TAU[m] for m in P[k]} for k in D}
    print(f"checks: frozen euv_extra ({len(hs)} files) and COMBO-T hashes verified; dev set = euv_extra dev_rows (541, same folds); dev OOF from the frozen "
          f"fold models reproduces the frozen dev log-loss for A, A_CV, C, C_CV, COMBO-T and the COMBO-T tau; prot12 reproduces the COMBO-T dev rows; "
          f"grid top = frozen COMBO-T: {grid_ok}; label-code M1+ in (t, t+24h] vs stored true_alarm mismatches: {lab_mis}")
    say(f"# Post-hoc analyses reproduced from the Claude-chat sessions (2026-09-27/28)\n\n**{LAB}.**\n\nGenerated by `posthoc_2026_09_28.py` "
        f"(Part 1 of the 2026-09-28 documentation update; decisions.md 8aa1797, 784b1a8). Already-seen data; nothing here is a test or a confirmation. "
        f"Sets are reported separately (dev = out-of-fold; later sets = mean of the 5 frozen fold models). Simple counts are unweighted n/N; weighted values "
        f"use 1/n per HARP within each set. Flares come from the repo's label code (swpc.fetch joinable events, K2 true scale, noaa_ars region join), not "
        f"the chat's own SWPC parser.\n")
    say("## Checks\n")
    say(f"- Frozen euv_extra models ({len(hs)} files) and COMBO-T files hash-verified; exact frozen thresholds: "
        + ", ".join(f"τ_{m} {TAU[m]!r}" for m in ["A", "A_CV", "C", "C_CV", "T"]) + f"; COMBO default (fitted here on dev) τ {TAU['D']:.6f}.")
    say("- Dev set = the frozen euv_extra dev rows (541, same folds); dev OOF predictions from the frozen fold models reproduce the frozen dev log-loss for "
        "A, A_CV, C, C_CV and COMBO-T exactly, and the COMBO-T τ.")
    say(f"- Label code (first M1+ from the region in (t, t+24 h]) vs stored true_alarm, mismatches per set: {lab_mis}.")
    say("- Set sizes: " + ", ".join(f"{NAME[k]} {len(c)} (true {int(c.true_alarm.sum())}, false {int((c.true_alarm == 0).sum())}, HARPs {c.harpnum.nunique()})"
                                   for k, c in D.items()) + ".\n")
    Y = {k: (c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()) for k, c in D.items()}
    GR = {k: [np.where(h == v)[0] for v in np.unique(h)] for k, (_, _, h) in Y.items()}

    def counts(k, keep):
        y, w, _ = Y[k]; tk, fr, pr = op_stats(y, w, keep)
        return dict(true_kept=f"{int((keep & (y == 1)).sum())}/{int(y.sum())}", false_removed=f"{int((~keep & (y == 0)).sum())}/{int((y == 0).sum())}",
                    precision=(keep & (y == 1)).sum() / keep.sum() if keep.any() else np.nan, true_kept_w=tk, false_removed_w=fr, precision_w=pr)

    # ---------------------------------------------------------------- Part 0 disclosure numbers
    say("## Part 0 disclosure numbers (C+ rule), reproduced\n")
    rows = []
    for k in SETS:
        kp = KEEP[k]["C_CV"] | D[k].anyCplus24.to_numpy()
        rows.append(dict(set=NAME[k], rule="C+", **counts(k, kp))); rows.append(dict(set=NAME[k], rule="Model C", **counts(k, KEEP[k]["C"])))
    say(md(pd.DataFrame(rows)))
    s = lambda rule, ks, y1: sum(int(((KEEP[k]["C_CV"] | D[k].anyCplus24.to_numpy()) if rule == "C+" else KEEP[k]["C"])[Y[k][0] == y1].sum()
                                     if y1 == 1 else (~((KEEP[k]["C_CV"] | D[k].anyCplus24.to_numpy()) if rule == "C+" else KEEP[k]["C"]))[Y[k][0] == 0].sum())
                                 for k in ks)
    rej = {k: (Y[k][0] == 1) & ~KEEP[k]["C_CV"] for k in SETS}
    n_rej, n_rej_c = sum(int(v.sum()) for v in rej.values()), sum(int((v & D[k].anyC24.to_numpy()).sum()) for k, v in rej.items())
    diff_mx = sum(int(((KEEP[k]["C_CV"] | D[k].anyC24.to_numpy()) != (KEEP[k]["C_CV"] | D[k].anyCplus24.to_numpy())).sum()) for k in SETS)
    say(f"Sums over the later sets (2021-26 combined): C+ {s('C+', LATER, 1)}/160 true kept, {s('C+', LATER, 0)}/831 false removed; Model C "
        f"{s('C', LATER, 1)}/160, {s('C', LATER, 0)}/831. C_CV-rejected true alarms over all 5 sets: {n_rej}, of which {n_rej_c} had >= 1 C-class flare in "
        f"(t-24 h, t); dev: {int(rej['dev'].sum())} ({int((rej['dev'] & D['dev'].anyC24.to_numpy()).sum())}). Including M/X (C+ vs C-protected) changes "
        f"{diff_mx} of {sum(len(c) for c in D.values())} alarms.\n")
    for lab, repo, chat in [("dev C+ true kept", s("C+", ["dev"], 1), 91), ("dev C+ false removed", s("C+", ["dev"], 0), 179),
                            ("2021-26 C+ true kept", s("C+", LATER, 1), 146), ("2021-26 C+ false removed", s("C+", LATER, 0), 282),
                            ("2021-26 Model C true kept", s("C", LATER, 1), 150), ("2021-26 Model C false removed", s("C", LATER, 0), 199),
                            ("2025-26 C+ true kept", s("C+", ["2025-26"], 1), 52), ("2025-26 C+ false removed", s("C+", ["2025-26"], 0), 125),
                            ("2025-26 Model C true kept", s("C", ["2025-26"], 1), 54), ("2025-26 Model C false removed", s("C", ["2025-26"], 0), 87),
                            ("C_CV-rejected true", n_rej, 44), ("... with C-class flare", n_rej_c, 24), ("M/X changes", diff_mx, 1),
                            ("dev rejected", int(rej["dev"].sum()), 12), ("dev rejected with C", int((rej["dev"] & D["dev"].anyC24.to_numpy()).sum()), 7)]:
        chk("Part 0", lab, repo, chat, None)
    say(statement("Part 0"))

    # ---------------------------------------------------------------- 1a matched retention
    say(f"## 1a. Matched retention, C vs C_CV\n\n**{LAB}.** Weighted false removed at the highest threshold keeping >= target weighted true (threshold "
        "chosen on each set — descriptive). Difference = C_CV − C; 95% CI from paired HARP resamples (2,000, seed 0; thresholds re-chosen in each resample). "
        "Simple counts at the chosen thresholds.\n")

    def fr_at(p, y, w, tgt):
        if y.sum() == 0 or (y == 0).sum() == 0:
            return np.nan
        k = p >= tau_keep(p, y, w, keep=tgt); return (w * (1 - y) * ~k).sum() / (w * (1 - y)).sum()
    rows = []; CH1A = {("2025-26", 0.80): (0.553, 0.485, -0.068, -0.291, 0.398), ("2025-26", 0.85): (0.452, 0.393), ("2025-26", 0.88): (0.452, 0.355, -0.097, -0.293, 0.323),
                        ("2025-26", 0.90): (0.440, 0.355), ("2025-26", 0.95): (0.200, 0.330, 0.131, -0.229, 0.223),
                        ("extra", 0.80): (0.55, 0.66, 11, -9, 45), ("extra", 0.88): (0.27, 0.35, 7, -11, 49), ("extra", 0.95): (0.11, 0.18, 8, -12, 43),
                        ("2022", 0.80): (0.48, 0.81, 33, -12, 57), ("2022", 0.88): (0.31, 0.53, 22, -20, 56), ("2022", 0.95): (0.24, 0.23, -2, -24, 43)}
    for k in SETS:
        y, w, _ = Y[k]; C = choices(len(GR[k]), 2000, 0)
        for tgt in (0.80, 0.85, 0.88, 0.90, 0.95):
            pc, pv = P[k]["C"], P[k]["C_CV"]; tc_, tv = tau_keep(pc, y, w, keep=tgt), tau_keep(pv, y, w, keep=tgt)
            fc, fv = fr_at(pc, y, w, tgt), fr_at(pv, y, w, tgt); B = []
            for row in C:
                ix = np.concatenate([GR[k][j] for j in row]); B.append(fr_at(pv[ix], y[ix], w[ix], tgt) - fr_at(pc[ix], y[ix], w[ix], tgt))
            lo, hi = pct(B); kc, kv = pc >= tc_, pv >= tv
            rows.append(dict(set=NAME[k], target=tgt, tau_C=tc_, tau_C_CV=tv, fr_w_C=fc, fr_w_C_CV=fv, diff=fv - fc, CI_lo=lo, CI_hi=hi,
                             C_true_kept=f"{int((kc & (y == 1)).sum())}/{int(y.sum())}", C_false_removed=f"{int((~kc & (y == 0)).sum())}/{int((y == 0).sum())}",
                             C_CV_true_kept=f"{int((kv & (y == 1)).sum())}/{int(y.sum())}", C_CV_false_removed=f"{int((~kv & (y == 0)).sum())}/{int((y == 0).sum())}"))
            ch = CH1A.get((k, tgt))
            if ch:
                pts = k != "2025-26"; nd = 2 if pts else 3
                chk("1a", f"{k} {tgt} C", fc, ch[0], nd); chk("1a", f"{k} {tgt} C_CV", fv, ch[1], nd)
                if len(ch) > 2:
                    sc_ = 100 if pts else 1; nd2 = 0 if pts else 3
                    chk("1a", f"{k} {tgt} diff", (fv - fc) * sc_, ch[2], nd2); chk("1a", f"{k} {tgt} CI lo", lo * sc_, ch[3], nd2); chk("1a", f"{k} {tgt} CI hi", hi * sc_, ch[4], nd2)
    say(md(pd.DataFrame(rows), 3)); say(statement("1a"))

    # ---------------------------------------------------------------- 1b
    say(f"## 1b. Sign of the log(1+R) coefficient in the frozen fold models\n\n**{LAB}.** Standardized coefficients (per 1 SD, training-fold scaler).\n")
    rows = []
    for m, chat in [("C", [-0.198, -0.326, -0.185, -0.261, -0.321]), ("C_CV", [0.146, -0.144, 0.178, -0.006, 0.027]), ("T", None)]:
        co = [mm.coef_[0][cols.index("logR")] for _, mm, cols in MOD[m]]
        rows.append(dict(model={"T": "COMBO-T"}.get(m, m), **{f"fold{k}": v for k, v in enumerate(co)}, negative=f"{sum(v < 0 for v in co)}/5"))
        if chat:
            for kk, (a, b) in enumerate(zip(co, chat)):
                chk("1b", f"{m} fold{kk}", a, b, 3)
    say(md(pd.DataFrame(rows), 3)); say(statement("1b"))

    # ---------------------------------------------------------------- 1c
    say(f"## 1c. Rejected true alarms and prior flares\n\n**{LAB}.** C-class = 1e-6 <= flux < 1e-5; C1.0+ includes M/X; prior window = start in "
        "(t − 24 h, t); hours to M1+ = to the first M1+ start from the region in (t, t + 24 h] (the label flare). Frozen τ (exact).\n")
    rows, lst = [], []
    for k in SETS:
        c, y = D[k], Y[k][0]
        for g, msk in [("true rejected by C_CV", (y == 1) & ~KEEP[k]["C_CV"]), ("true kept by C_CV", (y == 1) & KEEP[k]["C_CV"]),
                       ("false removed by C_CV", (y == 0) & ~KEEP[k]["C_CV"]), ("false kept by C_CV", (y == 0) & KEEP[k]["C_CV"]),
                       ("true rejected by COMBO-T", (y == 1) & ~KEEP[k]["T"])]:
            s_ = c[msk]
            rows.append(dict(set=NAME[k], group=g, n=len(s_), HARPs=s_.harpnum.nunique(), with_C_class=int(s_.anyC24.sum()), with_C1plus=int(s_.anyCplus24.sum()),
                             with_MX=int(s_.anyMX24.sum()), median_h_to_M1=s_.h_to_M1.median() if y[msk].any() else np.nan,
                             median_p=np.median(P[k]["T" if "COMBO" in g else "C_CV"][msk]) if msk.any() else np.nan))
        for g, m in [("C_CV", "C_CV"), ("COMBO-T", "T")]:
            for i in np.where((y == 1) & ~KEEP[k][m])[0]:
                e = c.iloc[i]; lst.append(dict(rejected_by=g, set=NAME[k], eid=e.eid, p=P[k][m][i], h_to_M1=e.h_to_M1, flares_C1plus_prior_24h=e.flares24 or "none"))
    R = pd.DataFrame(rows); say(md(R, 3))
    A_ = R.groupby("group")[["n", "with_C_class", "with_C1plus", "with_MX"]].sum()
    allc = pd.concat([D[k].assign(set=k, p_CCV=P[k]["C_CV"], p_T=P[k]["T"], kCCV=KEEP[k]["C_CV"], kT=KEEP[k]["T"]) for k in SETS], ignore_index=True)
    tr_rej, tr_kept = allc[(allc.true_alarm == 1) & ~allc.kCCV], allc[(allc.true_alarm == 1) & allc.kCCV]
    fr_, fk_ = allc[(allc.true_alarm == 0) & ~allc.kCCV], allc[(allc.true_alarm == 0) & allc.kCCV]; trT = allc[(allc.true_alarm == 1) & ~allc.kT]
    say("Sums over the five sets (descriptive): " + "; ".join(f"{g}: {int(r.n)} (C-class {int(r.with_C_class)}, C1.0+ {int(r.with_C1plus)}, M/X {int(r.with_MX)})" for g, r in A_.iterrows())
        + f". HARPs among C_CV-rejected true: {tr_rej.harpnum.nunique()}; among COMBO-T-rejected true: {trT.harpnum.nunique()}.")
    say(f"Median hours to first M1+: C_CV-rejected with a C-class flare {tr_rej[tr_rej.anyC24].h_to_M1.median():.2f} (n {int(tr_rej.anyC24.sum())}); "
        f"rejected without {tr_rej[~tr_rej.anyC24].h_to_M1.median():.2f} (n {int((~tr_rej.anyC24).sum())}); true kept {tr_kept.h_to_M1.median():.2f} (n {len(tr_kept)}); "
        f"COMBO-T-rejected {trT.h_to_M1.median():.2f} (n {len(trT)}), median COMBO-T chance {100 * trT.p_T.median():.2f}%.")
    pc_ = lambda s_: 100 * s_.anyMX24.mean()
    say(f"Any M/X in (t − 24 h, t): true rejected {pc_(tr_rej):.1f}%, true kept {pc_(tr_kept):.1f}%, false kept {pc_(fk_):.1f}%, false removed {pc_(fr_):.1f}%.\n")
    for k, chat in zip(SETS, [(12, 7), (6, 3), (5, 2), (6, 2), (15, 10)]):
        r_ = R[(R.set == NAME[k]) & (R.group == "true rejected by C_CV")].iloc[0]
        chk("1c", f"{k} C_CV-rejected true", int(r_.n), chat[0], None); chk("1c", f"{k} ... with C-class", int(r_.with_C_class), chat[1], None)
    for lab, repo, chat, nd in [("HARPs C_CV-rejected", tr_rej.harpnum.nunique(), 32, None), ("median h rejected with C", tr_rej[tr_rej.anyC24].h_to_M1.median(), 10.7, 1),
                                ("median h rejected without C", tr_rej[~tr_rej.anyC24].h_to_M1.median(), 15.5, 1), ("median h true kept", tr_kept.h_to_M1.median(), 9.3, 1),
                                ("false removed with C", int(fr_.anyC24.sum()), 201, None), ("false removed n", len(fr_), 662, None),
                                ("false kept with C", int(fk_.anyC24.sum()), 449, None), ("false kept n", len(fk_), 614, None),
                                ("true kept with C", int(tr_kept.anyC24.sum()), 183, None), ("true kept n", len(tr_kept), 212, None),
                                ("M/X % true rejected", pc_(tr_rej), 5, 0), ("M/X % true kept", pc_(tr_kept), 47, 0), ("M/X % false kept", pc_(fk_), 21, 0),
                                ("M/X % false removed", pc_(fr_), 0, 0), ("COMBO-T rejected true", len(trT), 44, None), ("COMBO-T HARPs", trT.harpnum.nunique(), 30, None),
                                ("COMBO-T rejected with C1.0+", int(trT.anyCplus24.sum()), 22, None), ("COMBO-T median chance %", 100 * trT.p_T.median(), 6.0, 1),
                                ("COMBO-T median h to M1+", trT.h_to_M1.median(), 13.1, 1)]:
        chk("1c", lab, repo, chat, nd)
    for k, chat in zip(SETS, [12, 4, 6, 6, 16]):
        chk("1c", f"{k} COMBO-T rejected", int(((Y[k][0] == 1) & ~KEEP[k]["T"]).sum()), chat, None)
    say("Per-episode list of rejected true alarms (flares C1.0+ from the same region with start in (t − 24 h, t); p = predicted chance of the rejecting model):\n")
    say(md(pd.DataFrame(lst), 3)); say(statement("1c"))

    # ---------------------------------------------------------------- 1d
    say(f"## 1d. C-class flare count in (t − 24 h, t) vs CV_box\n\n**{LAB}.** Spearman ρ; C-class only (1e-6 <= flux < 1e-5).\n")
    rows = []
    for k in SETS:
        r_, p_ = spearmanr(D[k].nC24, D[k].primary_CV_box); rows.append(dict(set=NAME[k], n=len(D[k]), rho=r_, p=p_))
    for lab, s_ in [("pooled (all 5 sets)", allc), ("pooled, true only", allc[allc.true_alarm == 1]), ("pooled, false only", allc[allc.true_alarm == 0])]:
        r_, p_ = spearmanr(s_.nC24, s_.primary_CV_box); rows.append(dict(set=lab, n=len(s_), rho=r_, p=p_))
    T1 = pd.DataFrame(rows); say(md(T1, 3))
    for (lab, chat) in zip(T1.set, [0.658, 0.587, 0.439, 0.535, 0.530, 0.567, 0.309, 0.560]):
        chk("1d", f"rho {lab}", T1.set_index("set").loc[lab, "rho"], chat, 3)
    rows = []
    for lo_, hi_, bl in BINS:
        for y1, nm in [(0, "false"), (1, "true")]:
            s_ = allc[(allc.nC24 >= lo_) & (allc.nC24 <= hi_) & (allc.true_alarm == y1)]
            rows.append(dict(C_count_bin=bl, group=nm, n=len(s_), median_CV_box=s_.primary_CV_box.median()))
    T2 = pd.DataFrame(rows); say("Median CV_box by C-count bin (pooled over the 5 sets):\n"); say(md(T2, 3))
    for (bl, nm), chat in zip([(b[2], g) for g in ["false", "true"] for b in BINS], [0.056, 0.110, 0.152, 0.189, 0.286, 0.111, 0.237, 0.251, 0.243, 0.337]):
        chk("1d", f"median {nm} bin {bl}", T2[(T2.C_count_bin == bl) & (T2.group == nm)].median_CV_box.iloc[0], chat, 3)
    say(statement("1d"))

    # ---------------------------------------------------------------- 1e
    say(f"## 1e. Rule comparisons\n\n**{LAB}.** Frozen models at their exact frozen τ. Table rule and C-level choice use dev only.\n")
    TB = {}
    for lo_, hi_, bl in BINS:
        r_ = np.sort(dev[(dev.true_alarm == 1) & (dev.nC24 >= lo_) & (dev.nC24 <= hi_)].primary_CV_box.to_numpy())
        TB[bl] = r_[int(np.floor(0.12 * len(r_)))] if len(r_) else np.nan
    binof = lambda n: next(b for lo_, hi_, b in BINS if lo_ <= n <= hi_)

    def rules(k):
        c = D[k]; kc = KEEP[k]
        out = {"gate only": np.ones(len(c), bool), "Model A": kc["A"], "Model C": kc["C"], "A+CV": kc["A_CV"], "C+CV (C_CV)": kc["C_CV"],
               "C-flare rule alone": c.anyC24.to_numpy(), "C-protected (C-class only)": kc["C_CV"] | c.anyC24.to_numpy(),
               "C+ rule (C1.0+ incl. M/X)": kc["C_CV"] | c.anyCplus24.to_numpy()}
        for L in LEVELS:
            out[f"C-level sweep C{L}"] = kc["C_CV"] | (c.maxCclass24.to_numpy() >= L * 1e-6 - 1e-18)
        out["table rule"] = c.primary_CV_box.to_numpy() >= np.array([TB[binof(n)] for n in c.nC24])
        return out
    RU = {k: rules(k) for k in SETS}
    yd1 = Y["dev"][0]; cdev = int((KEEP["dev"]["C"] & (yd1 == 1)).sum())
    cand = [(L, int((RU["dev"][f"C-level sweep C{L}"] & (yd1 == 1)).sum()), int((~RU["dev"][f"C-level sweep C{L}"] & (yd1 == 0)).sum())) for L in LEVELS]
    ok_ = [x for x in cand if x[1] >= cdev]; chosen = max(ok_, key=lambda x: (x[2], -x[0]))[0] if ok_ else None
    say(f"Table-rule dev cutoffs (sorted dev true CV_box r, cutoff r[floor(0.12 n)]): " + ", ".join(f"{b} {v:.3f}" for b, v in TB.items()) + ".")
    say(f"C-level sweep dev choice (max false removed with dev true kept >= Model C's {cdev}/96): **C{chosen}** "
        f"(dev candidates level/true kept/false removed: {cand}).\n")
    for b, chat in zip(TB, [0.065, 0.081, 0.196, 0.085, 0.194]):
        chk("1e", f"table cutoff {b}", TB[b], chat, 3)
    chk("1e", "sweep chosen level", chosen, 2.0, 1)
    rows = []
    for k in SETS:
        for nm, kp in RU[k].items():
            rows.append(dict(set=NAME[k], rule=nm, **counts(k, kp)))
    say(md(pd.DataFrame(rows), 3))
    sums = lambda nm, ks: (sum(int((RU[k][nm] & (Y[k][0] == 1)).sum()) for k in ks), sum(int((~RU[k][nm] & (Y[k][0] == 0)).sum()) for k in ks))
    rows = [dict(rule=nm, **dict(zip(["true_kept_of_160", "false_removed_of_831"], sums(nm, LATER))),
                 **dict(zip(["all5_true_kept_of_256", "all5_false_removed_of_1276"], sums(nm, SETS)))) for nm in RU["dev"]]
    say("Sums over sets (simple counts; 2021-26 = the four later sets; all5 includes dev):\n"); say(md(pd.DataFrame(rows)))
    for nm, chat in [("Model C", (150, 199)), ("C+CV (C_CV)", (128, 444)), ("A+CV", (125, 492)), ("C-flare rule alone", (130, 386)),
                     ("C-protected (C-class only)", (145, 282)), ("C+ rule (C1.0+ incl. M/X)", (146, 282)), ("table rule", (109, 404))]:
        a, b = sums(nm, LATER); chk("1e", f"2021-26 {nm} true", a, chat[0], None); chk("1e", f"2021-26 {nm} false", b, chat[1], None)
    for nm, chat in [("C-flare rule alone", (77, 240)), ("C-protected (C-class only)", (91, 179)), ("C+ rule (C1.0+ incl. M/X)", (91, 179)),
                     ("table rule", (87, 188)), ("Model A", (87, 70))]:
        a, b = sums(nm, ["dev"]); chk("1e", f"dev {nm} true", a, chat[0], None); chk("1e", f"dev {nm} false", b, chat[1], None)
    for L, chat in zip(LEVELS, [(236, 461), (231, 513), (227, 549), (226, 592), (221, 617), (220, 635), (217, 646), (215, 658)]):
        a, b = sums(f"C-level sweep C{L}", SETS); chk("1e", f"sweep C{L} true", a, chat[0], None); chk("1e", f"sweep C{L} false", b, chat[1], None)
    a, b = sums("C+CV (C_CV)", SETS); chk("1e", "sweep none true", a, 212, None); chk("1e", "sweep none false", b, 662, None)
    # C+ vs Model C paired differences (weighted points; HARP bootstrap 2,000, seed 0)
    jobs = {k: ("op", dict(y=Y[k][0], w=Y[k][1], kept=[KEEP[k]["C"], RU[k]["C+ rule (C1.0+ incl. M/X)"]], groups=GR[k]), 2000, 0) for k in SETS}
    with ProcessPoolExecutor(W) as pool:
        BO = boot_many(jobs, pool)
    rows = []
    for k in SETS:
        b = np.array(BO[k], float); c0, c1 = counts(k, KEEP[k]["C"]), counts(k, RU[k]["C+ rule (C1.0+ incl. M/X)"])
        rows.append(dict(set=NAME[k], D_true_pts=100 * (c1["true_kept_w"] - c0["true_kept_w"]), D_true_CI="[%+.1f, %+.1f]" % tuple(100 * np.array(pct(b[:, 1, 0] - b[:, 0, 0]))),
                         D_false_pts=100 * (c1["false_removed_w"] - c0["false_removed_w"]), D_false_CI="[%+.1f, %+.1f]" % tuple(100 * np.array(pct(b[:, 1, 1] - b[:, 0, 1])))))
    say("C+ rule minus Model C (weighted points; paired HARP bootstrap 2,000, seed 0; post-hoc — these sets cannot confirm the rule):\n")
    say(md(pd.DataFrame(rows), 1)); say(statement("1e"))

    # ---------------------------------------------------------------- 1f
    say(f"## 1f. COMBO default, the 90-configuration dev grid, COMBO-T on later sets\n\n**{LAB}.** prot = 1 if the region's max flare flux (any class) with "
        "start in (t − W, t) >= L; interaction = prot × log10 CV_box; features = Model C columns + log10 CV_box + prot [+ interaction]; Step 6 settings with "
        "LogisticRegression C as listed; τ = highest dev OOF threshold keeping >= 88% weighted true. Sorted by weighted false removed (desc), then log-loss.\n")
    say(md(G, 4))
    say(f"Grid top = frozen COMBO-T (W 12, C2.0, no interaction, C 0.3; τ and log-loss identical to data/combo_t/thresholds.json): {grid_ok}. "
        f"COMBO default (W 24, C1.0, interaction, C 1) dev τ {TAU['D']:.4f}.\n")
    for lab, repo, chat, nd in [("top tau", top.tau, 0.0792, 4), ("top fr_w", top.false_removed_w, 0.5735, 4), ("top tk_w", top.true_kept_w, 0.8840, 4),
                                ("top LL", top.LL, 0.3139, 4), ("default tau", TAU["D"], 0.0642, 4)]:
        chk("1f", lab, repo, chat, nd)
    g2 = G.set_index(["W_h", "L", "interaction", "C"])
    chk("1f", "W12 C2 inter C0.3 fr_w", g2.loc[(12, "C2.0", "yes", 0.3), "false_removed_w"], 0.5718, 4)
    chk("1f", "W24 C5 inter C0.3 fr_w", g2.loc[(24, "C5.0", "yes", 0.3), "false_removed_w"], 0.5533, 4)
    chk("1f", "rank 2 = W12 C2 inter C0.3", tuple(G.iloc[1][["W_h", "L", "interaction", "C"]]) == (12, "C2.0", "yes", 0.3), True, None)
    chk("1f", "rank 3 = W24 C5 inter C0.3", tuple(G.iloc[2][["W_h", "L", "interaction", "C"]]) == (24, "C5.0", "yes", 0.3), True, None)
    rows = []
    for k in SETS:
        y, w, _ = Y[k]
        for m, nm in [("C", "Model C"), ("D", "COMBO default"), ("T", "COMBO-T")]:
            rows.append(dict(set=NAME[k], model=nm, **counts(k, KEEP[k][m]), AUC_w=roc_auc_score(y, P[k][m], sample_weight=w), AUC=roc_auc_score(y, P[k][m]),
                             LL_w=wlogloss(y, P[k][m], w)))
    say(md(pd.DataFrame(rows), 4))
    yy, ww = np.concatenate([Y[k][0] for k in LATER]), np.concatenate([Y[k][1] for k in LATER])
    rows = []
    for m, nm, chat in [("T", "COMBO-T", (128, 477, 0.768, 0.3657)), ("D", "COMBO default", (142, 324, 0.755, 0.3756)), ("C", "Model C", (150, 199, 0.750, 0.3768))]:
        pp = np.concatenate([P[k][m] for k in LATER]); kk = np.concatenate([KEEP[k][m] for k in LATER])
        r_ = dict(model=nm, true_kept=int((kk & (yy == 1)).sum()), false_removed=int((~kk & (yy == 0)).sum()), AUC_unweighted=roc_auc_score(yy, pp), LL_w_set_HARP=wlogloss(yy, pp, ww))
        rows.append(r_)
        for lab, a, b, nd in [("true kept", r_["true_kept"], chat[0], None), ("false removed", r_["false_removed"], chat[1], None), ("AUC", r_["AUC_unweighted"], chat[2], 3), ("LL", r_["LL_w_set_HARP"], chat[3], 4)]:
            chk("1f", f"2021-26 {nm} {lab}", a, b, nd)
    say("2021-26 pooled (the four later sets; log-loss weighted 1/n per (set, HARP); AUC unweighted; descriptive):\n"); say(md(pd.DataFrame(rows), 4))
    for k, chat in zip(LATER, [(40, 138), (26, 63), (22, 66), (40, 210)]):
        y = Y[k][0]; chk("1f", f"COMBO-T {k} true", int((KEEP[k]["T"] & (y == 1)).sum()), chat[0], None); chk("1f", f"COMBO-T {k} false", int((~KEEP[k]["T"] & (y == 0)).sum()), chat[1], None)
    rows = []
    for m, nm, chat in [("T", "COMBO-T", [(183, 5), (639, 83), (99, 38), (70, 34)]), ("D", "COMBO default", [(274, 12), (538, 74), (104, 37), (75, 37)])]:
        for scope in LATER + ["2021-26 pooled"]:
            ks = LATER if scope == "2021-26 pooled" else [scope]
            pp = np.concatenate([P[k][m] for k in ks]); yv = np.concatenate([Y[k][0] for k in ks])
            for (lo_, hi_, tn), ch in zip(TIERS, chat):
                s_ = (pp >= lo_) & (pp < hi_)
                rows.append(dict(model=nm, set=NAME.get(scope, scope), tier=tn, n=int(s_.sum()), true=int(yv[s_].sum()),
                                 mean_predicted=pp[s_].mean() if s_.any() else np.nan, observed_rate=yv[s_].mean() if s_.any() else np.nan))
                if scope == "2021-26 pooled":
                    chk("1f", f"{nm} tier {tn} n", int(s_.sum()), ch[0], None); chk("1f", f"{nm} tier {tn} true", int(yv[s_].sum()), ch[1], None)
    say("Reliability tiers (<5%, 5-15%, 15-30%, >=30%):\n"); say(md(pd.DataFrame(rows), 4))
    rows = []
    for k in SETS:
        rows.append(dict(set=NAME[k], rule="COMBO-T + C+ override", **counts(k, KEEP[k]["T"] | D[k].anyCplus24.to_numpy())))
    say(md(pd.DataFrame(rows), 3))
    ov = lambda ks: (sum(int(((KEEP[k]["T"] | D[k].anyCplus24.to_numpy()) & (Y[k][0] == 1)).sum()) for k in ks),
                     sum(int((~(KEEP[k]["T"] | D[k].anyCplus24.to_numpy()) & (Y[k][0] == 0)).sum()) for k in ks))
    for lab, ks, chat in [("dev", ["dev"], (90, 198)), ("2021-26", LATER, (144, 318)), ("2025-26", ["2025-26"], (51, 141))]:
        a, b = ov(ks); chk("1f", f"override {lab} true", a, chat[0], None); chk("1f", f"override {lab} false", b, chat[1], None)
    say(f"COMBO-T + C+ override sums: dev {ov(['dev'])}, 2021-26 {ov(LATER)} (true kept, false removed).\n"); say(statement("1f"))

    # ---------------------------------------------------------------- 1g
    say(f"## 1g. Walk-forward recalibration\n\n**{LAB}.** τ re-set on the three 2021-24 sets pooled (weights 1/n per HARP within each set), applied once to "
        "2025-26 (56 true / 322 false).\n")
    y3, w3 = np.concatenate([Y[k][0] for k in Y2124]), np.concatenate([Y[k][1] for k in Y2124]); rows = []
    CH1G = {"C": [(0.074, 48, 153), (0.067, 52, 122), (0.060, 54, 63)], "D": [(0.072, 48, 152), (0.057, 52, 130), (0.046, 53, 115)],
            "T": [(0.073, 43, 190), (0.061, 48, 142), (0.056, 50, 130)]}
    for m, nm in [("C", "Model C"), ("D", "COMBO default"), ("T", "COMBO-T")]:
        p3 = np.concatenate([P[k][m] for k in Y2124])
        for tgt, ch in zip((0.88, 0.90, 0.95), CH1G[m]):
            tau = tau_keep(p3, y3, w3, keep=tgt); kk = P["2025-26"][m] >= tau
            rows.append(dict(model=nm, target=tgt, tau=tau, **counts("2025-26", kk)))
            y = Y["2025-26"][0]; chk("1g", f"{nm} {tgt} tau", tau, ch[0], 3)
            chk("1g", f"{nm} {tgt} true", int((kk & (y == 1)).sum()), ch[1], None); chk("1g", f"{nm} {tgt} false", int((~kk & (y == 0)).sum()), ch[2], None)
    say(md(pd.DataFrame(rows), 4)); say(statement("1g"))

    # ---------------------------------------------------------------- 1h
    say(f"## 1h. Literature-style metrics on 2025-26\n\n**{LAB}.**\n")
    c26 = D["2025-26"]; tw = pd.read_csv("data/euv_confirm/twins_le2.csv"); v = c26.set_index("eid").primary_CV_box
    xt, xf = tw.true_eid.map(v).to_numpy(), tw.false_eid.map(v).to_numpy()
    Bu = [med_ratio(xt[ix], xf[ix], "ratio") for ix in choices(len(xt), 2000, 0)]; lo, hi = pct(Bu)
    wd_, wl_ = wilcoxon(xt, xf).pvalue, wilcoxon(np.log10(xt / xf)).pvalue; sg = binomtest(int((xt > xf).sum()), len(xt), 0.5).pvalue
    say(f"- CV_box twins (TEST 1 stored pairs, {len(xt)}): ratio {med_ratio(xt, xf, 'ratio'):.4f}; unclustered pair-bootstrap 95% CI [{lo:.2f}, {hi:.2f}] (2,000, seed 0); "
        f"Wilcoxon signed-rank p (differences) {wd_:.1e}, (log ratios) {wl_:.1e}; sign test two-sided p {sg:.1e} ({int((xt > xf).sum())}/{len(xt)}).")
    chk("1h", "unclustered CI lo", lo, 1.63, 2); chk("1h", "unclustered CI hi", hi, 8.04, 2); chk("1h", "Wilcoxon p (differences)", float(f"{wd_:.1e}"), 1.5e-6, None)
    chk("1h", "sign p", float(f"{sg:.1e}"), 9.0e-5, None); chk("1h", "39/50", int((xt > xf).sum()), 39, None)
    y = Y["2025-26"][0]; rows = []
    for nm, sc, ch in [("A", P["2025-26"]["A"], (0.756, 0.424, 68, 75)), ("C", P["2025-26"]["C"], (0.777, 0.437, 80, 63)),
                       ("C_CV", P["2025-26"]["C_CV"], (0.781, 0.491, 64, 85)), ("CV_box alone", c26.primary_CV_box.to_numpy(), (0.753, 0.396, None, None))]:
        fpr, tpr, th = roc_curve(y, sc); i = int(np.argmax(tpr - fpr))
        rows.append(dict(model=nm, AUC=roc_auc_score(y, sc), max_TSS=tpr[i] - fpr[i], threshold=th[i], true_kept_pct=100 * tpr[i], false_removed_pct=100 * (1 - fpr[i])))
        chk("1h", f"{nm} AUC", roc_auc_score(y, sc), ch[0], 3); chk("1h", f"{nm} TSS", tpr[i] - fpr[i], ch[1], 3)
        if ch[2] is not None:
            chk("1h", f"{nm} kept %", 100 * tpr[i], ch[2], 0); chk("1h", f"{nm} removed %", 100 * (1 - fpr[i]), ch[3], 0)
    say("\nMax-TSS, unweighted — **threshold tuned on test set — optimistic**:\n"); say(md(pd.DataFrame(rows), 3))
    kc = KEEP["2025-26"]["C_CV"]; prec, gate = (kc & (y == 1)).sum() / kc.sum(), y.mean()
    say(f"Frozen C_CV precision (simple) {prec:.3f} vs gate {gate:.3f}.\n")
    chk("1h", "C_CV precision", prec, 0.244, 3); chk("1h", "gate precision", gate, 0.148, 3); say(statement("1h"))

    # ---------------------------------------------------------------- 1i
    say(f"## 1i. Excess area (brightness above the 24-h mean)\n\n**{LAB}.** Excess area = trapezoid ∫ max(box/mean − 1, 0) dt (hours) over the valid_primary "
        "frames; |·| area = ∫ |box/mean − 1| dt; raw area = ∫ box dt; mean = mean of box over the same frames.\n")

    def areas(eid):
        s = pd.read_csv(f"data/euv_confirm/series/{eid}.csv", parse_dates=["t_obs"], float_precision="round_trip"); s = s[s.valid_primary].sort_values("t_obs")
        th_ = (s.t_obs - s.t_obs.iloc[0]).dt.total_seconds().to_numpy() / 3600; b = s.box.to_numpy(); r_ = b / b.mean() - 1
        return np.trapezoid(np.maximum(r_, 0), th_), np.trapezoid(np.abs(r_), th_), np.trapezoid(b, th_)
    PAIRS = [("twin_pair_24h / magnetic_vs_aia94_twin_pair", "13299_20250529T1459", "13891_20251018T2059", (1.059, 0.114)),
             ("twin_gif_1_p10", "14117_20251206T1159", "13726_20250905T0959", (0.991, 1.396)), ("twin_gif_2_p30", "13574_20250806T2159", "14825_20260627T0659", (1.865, 0.815)),
             ("twin_gif_3_p50", "13708_20250830T1359", "12889_20250313T0659", (0.612, 0.607)), ("twin_gif_4_p70", "13574_20250803T0959", "14284_20260123T0959", (0.953, 0.307)),
             ("twin_gif_5_p90", "14117_20251208T2259", "14765_20260616T0259", (4.256, 0.398))]
    rows = []
    for nm, a, b, ch in PAIRS:
        ea, eb = areas(a), areas(b)
        rows.append(dict(pair=nm, true_eid=a, false_eid=b, excess_true=ea[0], excess_false=eb[0], abs_true=ea[1], abs_false=eb[1], raw_true=ea[2], raw_false=eb[2],
                         CV_box_true=v.get(a, np.nan), CV_box_false=v.get(b, np.nan)))
        chk("1i", f"{nm} excess true", ea[0], ch[0], 3); chk("1i", f"{nm} excess false", eb[0], ch[1], 3)
    say(md(pd.DataFrame(rows), 3))
    le2 = pd.read_csv("data/euv_confirm/cohort_le2.csv", usecols=["harpnum", "t"], parse_dates=["t"]); le2["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(le2.harpnum, le2.t)]
    rr = pd.DataFrame([json.load(open(p)) for p in __import__("glob").glob("data/euv_confirm/results/*.json")])[["eid", "primary_fill", "primary_CV_box"]]
    rr[["primary_fill", "primary_CV_box"]] = rr[["primary_fill", "primary_CV_box"]].apply(pd.to_numeric, errors="coerce"); le2 = le2.merge(rr, on="eid", how="left")
    ar = pd.DataFrame([dict(eid=e, **dict(zip(["excess", "absarea", "raw"], areas(e)))) for e in le2.eid]); le2 = le2.merge(ar, on="eid")
    rows = []
    for lab, s_ in [("2025-26 evaluable (378; fill >= 80%)", le2[le2.eid.isin(c26.eid)]), ("all le2 with CV_box > 0 (chat set, no fill rule)", le2[le2.primary_CV_box > 0])]:
        for col, chat in [("excess", 0.934), ("absarea", 0.936)]:
            r_, p_ = spearmanr(s_[col], s_.primary_CV_box); rows.append(dict(set=lab, n=len(s_), area=col, rho=r_, p=p_))
            if "chat" in lab:
                chk("1i", f"rho {col} (n {len(s_)})", r_, chat, 3)
    say("Spearman ρ with CV_box:\n"); say(md(pd.DataFrame(rows), 3)); chk("1i", "chat set n", int((le2.primary_CV_box > 0).sum()), 387, None); say(statement("1i"))
    say("## Mismatch summary\n")
    for it, (n, bad) in MIS.items():
        say(f"- {it}: {n - len(bad)}/{n} match" + (f"; mismatches: {len(bad)}" if bad else ""))
    os.makedirs("docs", exist_ok=True); open("docs/posthoc_2026-09-28.md", "w").write("\n".join(OUT) + "\n")
    print("mismatch summary: " + "; ".join(f"{it} {n - len(bad)}/{n}" for it, (n, bad) in MIS.items()))
    for it, (n, bad) in MIS.items():
        for b in bad:
            print(f"  {it} MISMATCH {b}")
    print(f"wrote docs/posthoc_2026-09-28.md; wall {time.time() - t00:.1f} s")
