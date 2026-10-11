"""EXPLORATORY — parasitic-polarity "dots" near the PIL (decisions.md 2026-09-27, dc080a8). DEV 2010-2019 (candidate #23).
Label-blind feature from the alarm-time LoS magnetogram; outputs in data/dots/ only; at most 4 workers.
Usage: python euv_dots.py selftest | compute | eval"""
import json, os, sys, time, warnings
import numpy as np, pandas as pd

OUT, WORKERS = "data/dots", 4
warnings.filterwarnings("ignore")


def dots(B_raw, mm_px):
    """-> (N_dots, Phi_dots [Mx]). Components per sign (decisions.md dc080a8, clarification 1)."""
    from scipy import ndimage
    from euv_pilot import pil_mask
    B = np.nan_to_num(np.asarray(B_raw, float))
    bg = np.sign(ndimage.gaussian_filter(B, 5.0 / mm_px))
    pil = pil_mask(B); s8 = np.ones((3, 3), int); n, phi = 0, 0.0
    for sgn in (1, -1):
        lab, k = ndimage.label(sgn * B >= 100, structure=s8)
        for i, sl in enumerate(ndimage.find_objects(lab), 1):
            m = lab[sl] == i; npx = int(m.sum()); area = npx * mm_px ** 2
            if not 1 <= area <= 20:
                continue
            b, g = B[sl][m], bg[sl][m]
            if np.mean((g != 0) & (np.sign(b) == -g)) < 0.9:
                continue
            cy, cx = ndimage.center_of_mass(m)
            if pil[sl[0].start + int(round(cy)), sl[1].start + int(round(cx))]:
                n += 1; phi += float(np.abs(b).sum() * (mm_px * 1e8) ** 2)
    return n, phi


def synthetic(patch_px, where):
    B = np.full((200, 200), 50.0); B[60:140, 40:100] = 800.0; B[60:140, 100:160] = -800.0      # bipole, PIL at x = 100
    s = int(round(np.sqrt(patch_px)))
    if where == "pil":
        y0, x0 = 100 - s // 2, 92 - s // 2                        # inside the positive block, ~8 px from the PIL
    else:
        y0, x0 = 20, 20                                           # weak +50 G surround, far from the PIL
    B[y0:y0 + s, x0:x0 + s] = -800.0
    return B, s * s


def episode_dots(args):
    import sunpy.map
    from euv_full import hmi_files
    eid, h, trec = args
    m, _ = hmi_files(f"data/euv_full/hmi/{h}", trec)
    if not m:
        return eid, np.nan, np.nan, np.nan
    mag = sunpy.map.Map(m)
    mm = float(mag.meta["cdelt1"]) * float(mag.meta["rsun_ref"]) / float(mag.meta["rsun_obs"]) / 1e6
    n, phi = dots(mag.data, mm)
    return eid, n, phi, mm


if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    mm = 0.362; px5, px30 = round(5 / mm ** 2), round(30 / mm ** 2)
    Ba, na = synthetic(px5, "pil"); Bb, nb = synthetic(px5, "far"); Bc, nc = synthetic(px30, "pil")
    ra, rb, rc = dots(Ba, mm)[0], dots(Bb, mm)[0], dots(Bc, mm)[0]
    assert ra == 1, f"(a) {ra}"; assert rb == 0, f"(b) {rb}"; assert rc == 0, f"(c) {rc}"
    assert dots(Ba, mm) == dots(Ba, mm), "(d) not deterministic"
    print(f"selftest passed: (a) {na * mm ** 2:.1f} Mm^2 patch in PIL zone -> 1; (b) same patch far from PIL -> 0; "
          f"(c) {nc * mm ** 2:.1f} Mm^2 patch -> 0; (d) deterministic")

if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    from concurrent.futures import ProcessPoolExecutor
    os.makedirs(OUT, exist_ok=True); t0 = time.time()
    c = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t"], parse_dates=["t"])     # no label column read
    dv = pd.read_csv("data/stage2/oof_scores_dev.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"])
    c = c.merge(dv, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one")
    assert len(c) == 547 and c.t_rec_tai.notna().all()
    c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
    with ProcessPoolExecutor(WORKERS) as pool:
        r = pd.DataFrame(list(pool.map(episode_dots, list(zip(c.eid, c.harpnum, c.t_rec_tai)), chunksize=8)),
                         columns=["eid", "N_dots", "Phi_dots_Mx", "mm_px"])
    r.to_csv(f"{OUT}/dev_dots.csv", index=False); x = r.N_dots.dropna()
    print(f"LABEL-BLIND REPORT (no labels read): {len(r)} dev episodes; missing magnetogram {int(r.N_dots.isna().sum())} (excluded label-blind)")
    print(f"N_dots: median {x.median():.0f}, IQR [{x.quantile(.25):.0f}, {x.quantile(.75):.0f}], max {x.max():.0f}; zero in {100 * (x == 0).mean():.1f}% "
          f"({int((x == 0).sum())}/{len(x)}); Phi_dots median {r.Phi_dots_Mx.median():.3e} Mx; wall {time.time() - t0:.1f} s, workers {WORKERS}")

if __name__ == "__main__" and sys.argv[1:] == ["eval"]:
    import glob
    from concurrent.futures import ProcessPoolExecutor
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    from euv_heldout import fit_folds
    from phase_f import boot_many, pct, wlogloss, ratio_jobs, A_COLS
    t0 = time.time(); pd.set_option("display.width", 250)
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    coh = coh.merge(pd.read_csv(f"{OUT}/dev_dots.csv"), on="eid", how="left")
    assert coh.N_dots.notna().all(), "missing magnetogram in the dev cohort"
    coh["log1p_dots"] = np.log1p(coh.N_dots)
    mA, pA = fit_folds(coh, A_COLS); mD, pD = fit_folds(coh, A_COLS + ["log1p_dots"])
    assert np.abs(pA - coh.p_A).max() < 1e-12, "A does not reproduce Stage 4 p_A"
    y, w, h = coh.true_alarm.to_numpy(), coh.weight.to_numpy(), coh.harpnum.to_numpy()
    rs = pd.DataFrame([json.load(open(p)) for p in glob.glob("data/euv_full/results/*.json")])
    rs = rs[rs.eid.notna()][["eid", "primary_CV_box"]]; rs["primary_CV_box"] = pd.to_numeric(rs.primary_CV_box, errors="coerce")
    coh = coh.merge(rs, on="eid", how="left"); coh["log10_CV_box"] = np.where(coh.primary_CV_box > 0, np.log10(coh.primary_CV_box), np.nan)
    with ProcessPoolExecutor(WORKERS) as pool:
        B = boot_many({"d": ("dll", dict(y=y, w=w, pA=pA, pE=pD, groups=[np.where(h == v)[0] for v in np.unique(h)]), 10000, 20260921)}, pool)["d"]
        tw = pd.read_csv("data/euv_full/step6/twins_PRIMARY.csv")
        e, j = ratio_jobs("N_dots | 81 gate-score twins", coh, "N_dots", "ratio", tw); RB = boot_many(j, pool)
    lo, hi = pct(B); llA, llD = wlogloss(y, pA, w), wlogloss(y, pD, w); d = llA - llD
    aA, aD = roc_auc_score(y, pA, sample_weight=w), roc_auc_score(y, pD, sample_weight=w)
    print("EXPLORATORY (dev 2010-2019 only); check: A reproduces Stage 4 p_A (max |diff| < 1e-12)")
    print(f"\nA vs A + log(1+N_dots), dev 547 (true {int(y.sum())}, false {int((y == 0).sum())}, HARPs {len(np.unique(h))}): LL(A) {llA:.4f}, "
          f"LL(A+dots) {llD:.4f}, delta {d:+.4f} [{lo:+.4f}, {hi:+.4f}] (HARP bootstrap 10,000, seed 20260921); AUC {aA:.4f} -> {aD:.4f}")
    co = [m.coef_[0][-1] for _, m, _ in mD]
    print(f"log(1+N_dots) coefficient per fold (per 1 SD): {[round(v, 4) for v in co]}; signs {np.sign(co).astype(int).tolist()}")
    print("\ndescriptive Spearman rho of log(1+N_dots):")
    for v in ["score", "n_C", "n_M", "log10_CV_box"]:
        mm = coh[v].notna(); r, p = spearmanr(coh.loc[mm, "log1p_dots"], coh.loc[mm, v])
        print(f"  {v:13s} rho {r:+.4f} (p {p:.2e}, n {int(mm.sum())})")
    print(f"\nN_dots twins ratio (81 gate-score twins; F2 code; median true / median false; 2,000, seed 0): "
          f"all {e['ratio_all']:.4f} {'[%.4f, %.4f]' % pct(RB[(e['measure'], 'all')])} (medians {e['med_true']:.1f} / {e['med_false']:.1f}); "
          f"twins {e['ratio_twins']:.4f} {'[%.4f, %.4f]' % pct(RB[(e['measure'], 'tw')])} (medians {e['twin_med_true']:.1f} / {e['twin_med_false']:.1f}, {e['pairs']} pairs)")
    el = d > 0 and lo > 0 and aD > aA
    print(f"\nPRE-STATED READING (mechanical): delta {d:+.4f}, CI lower {lo:+.4f}, AUC {aA:.4f} -> {aD:.4f} -> "
          f"\"{'ELIGIBLE FOR FOLLOW-UP' if el else 'NOT ELIGIBLE'}\"")
    print(f"wall {time.time() - t0:.1f} s, workers {WORKERS}")
