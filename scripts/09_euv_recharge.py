"""EXPLORATORY — RECHARGE vs CLUSTERING (decisions.md 2026-09-27, 1d7d117). DEV 2010-2019 ONLY. No images, no JSOC.
C = A + log(1+R) vs C_S = C + S_last (log10 peak flux of the region's most recent C1+ flare in (t-48h, t); floor -6)."""
import time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
import swpc
from euv_heldout import fit_folds
from phase_f import boot_many, pct, wlogloss, A_COLS, W

if __name__ == "__main__":
    t00 = time.time(); pd.set_option("display.width", 250)
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
    assert len(coh) == 547 and coh.t.max() < pd.Timestamp("2020-01-01")
    fl, _ = swpc.fetch(pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59"), verbose=False)
    c1 = fl[fl.flux >= 1e-6]
    by_ar = {int(a): g[["start", "flux"]].sort_values("start") for a, g in c1.groupby("noaa_ar")}
    by_all = {int(a): g[["start", "cls"]] for a, g in fl.groupby("noaa_ar")}
    logR, S, real, cnt = [], [], [], []
    for e in coh.itertuples():
        ar = [int(a) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()]
        w = pd.concat([g[(g.start > e.t - pd.Timedelta("48h")) & (g.start < e.t)] for a in ar if (g := by_ar.get(a)) is not None] or
                      [pd.DataFrame(columns=["start", "flux"])])
        if len(w):
            last = w.start.max(); R = (e.t - last) / pd.Timedelta("1h"); s = float(np.log10(w.loc[w.start == last, "flux"].max())); real.append(True)
        else:
            R, s = 48.0, -6.0; real.append(False)
        logR.append(float(np.log1p(min(R, 48.0)))); S.append(s)
        prev = [g[(g.start >= e.t - pd.Timedelta("48h")) & (g.start < e.t)] for a in ar if (g := by_all.get(a)) is not None]
        p = pd.concat(prev).drop_duplicates() if prev else pd.DataFrame(columns=["start", "cls"])
        cnt.append({k: int((p.cls == k).sum()) for k in "CMX"})
    coh["logR"], coh["S_last"], real = logR, S, np.array(real)
    cnt = pd.DataFrame(cnt)
    assert ((coh.logR < np.log1p(48)).to_numpy() == real).all(), "(R < 48) <=> real flare violated"
    assert all((cnt[k].to_numpy() == coh[f"n_{k}"].to_numpy()).all() for k in "CMX"), "join does not reproduce n_C, n_M, n_X"
    mC, pC = fit_folds(coh, A_COLS + ["logR"]); mS, pS = fit_folds(coh, A_COLS + ["logR", "S_last"])
    y, w, h = coh.true_alarm.to_numpy(), coh.weight.to_numpy(), coh.harpnum.to_numpy()
    llC, llS = wlogloss(y, pC, w), wlogloss(y, pS, w)
    assert round(llC, 4) == 0.3356, f"LL(C) {llC} does not reproduce Step B dev 0.3356"
    print("EXPLORATORY (dev 2010-2019 only; nothing claimed as confirmed)")
    print(f"checks: (R < 48) <=> real last flare for all {len(coh)} episodes; event join reproduces n_C, n_M, n_X; LL(C) {llC:.4f} = Step B dev 0.3356")
    with ProcessPoolExecutor(W) as pool:
        B = boot_many({"d": ("dll", dict(y=y, w=w, pA=pC, pE=pS, groups=[np.where(h == v)[0] for v in np.unique(h)]), 10000, 20260921)}, pool)["d"]
    lo, hi = pct(B); d = llC - llS
    print(f"\nDelta = LL(C) - LL(C_S) (+ = S_last helps): {d:.4f} [{lo:.4f}, {hi:.4f}] (HARP bootstrap 10,000, seed 20260921); "
          f"LL(C) {llC:.4f}, LL(C_S) {llS:.4f}; weighted AUC C {roc_auc_score(y, pC, sample_weight=w):.4f}, C_S {roc_auc_score(y, pS, sample_weight=w):.4f}")
    co = pd.DataFrame([dict(fold=k, **{f"std_{c}": b for c, b in zip(cols, m.coef_[0])}) for k, (sc, m, cols) in enumerate(mS)])
    print("\nC_S coefficients per fold (per 1 SD, training-fold StandardScaler)")
    print(co.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    sg = np.sign(co.std_S_last).astype(int); neg, pos = int((sg < 0).sum()), int((sg > 0).sum())
    print(f"S_last coefficient signs: {sg.tolist()} (negative {neg}/5, positive {pos}/5)")
    print(f"\ndescriptive: episodes at the floor (no C1+ in (t-48h, t)): {int((~real).sum())} of {len(coh)}")
    for v in ["n_M", "n_X", "logR"]:
        r, p = spearmanr(coh.S_last, coh[v]); print(f"  Spearman rho(S_last, {v}) = {r:.4f} (p {p:.2e}, n {len(coh)})")
    ok = d > 0 and lo > 0
    reading = "RECHARGE SUPPORTED" if ok and neg >= 4 else "CLUSTERING SUPPORTED" if ok and pos >= 4 else "NO DETECTABLE EFFECT"
    print(f"\nPRE-STATED READING (mechanical): Delta {d:+.4f}, CI lower {lo:+.4f}, negative folds {neg}/5 -> \"{reading}\"")
    print(f"wall {time.time() - t00:.1f} s, workers {W}")
