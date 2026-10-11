"""R5-R7 reproduction runs (decisions.md 2026-09-29, d34431f). DIAGNOSTIC; dev period 2010-05-01 ... 2014-05-31 only; gate, frozen files,
split, cohorts and existing results unchanged. R2 construction = diag_r.py's own code (run up to its TARGET line; local caches only).
Step 1: R2 rerun must reproduce data/diag/r_runs.csv exactly (else STOP). R5 penalty placement; R6 20 negative draws x 200 splits; R7 both.
Usage: python diag_r5_r7.py"""
import os, sys, time
import numpy as np, pandas as pd
from joblib import Parallel, delayed

t00 = time.time()
_src = open("scripts/05_diag_r.py").read()
exec(compile(_src[:_src.index("TARGET = ")], "diag_r", "exec"))   # defines F, SEED, NP, REPEATS, SVM, POOL, P2, F3, build, split, SVC, train_test_split
TARGET = {2.0: (0.562, 0.658), 15.0: (0.722, 0.800)}
NJ = os.cpu_count() - 1
DRAWS, SPLITS_PER_DRAW = 20, 200


def split_r5(X, y, i, ratio):
    """= diag_r.split, but C = 4 on the flare class: class_weight {1: 1.0, 0: 1/ratio}."""
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.30, stratify=y, random_state=SEED + i)
    pred = SVC(**{**SVM, "C": 4.0, "class_weight": {1: 1.0, 0: 1.0 / ratio}}).fit(Xtr, ytr).decision_function(Xte) >= 0
    return [int((pred & (yte == 1)).sum()), int((~pred & (yte == 1)).sum()),
            int((pred & (yte == 0)).sum()), int((~pred & (yte == 0)).sum())]


def build_seed(pos, seed):
    """= diag_r.build(pos) (extra=None), with the negative draw's random_state = seed."""
    pool = POOL.drop(columns=[c for c in F3 if c in POOL], errors="ignore")
    pool = pool[~pool.set_index(["harpnum", "t_rec"]).index.isin(pos.set_index(["harpnum", "t_rec"]).index)]
    P = len(pos); N = int(round(NP * P))
    neg = pool.sample(n=N, replace=False, random_state=seed)
    cat = pd.concat([pos.assign(y=1), neg.assign(y=0)], ignore_index=True)
    X = cat[F].to_numpy(float); X = (X - np.median(X, axis=0)) / X.std(axis=0)
    return X, cat.y.to_numpy(), P, N, len(pool), cat


def summ(c):
    """per-row summary exactly as diag_r.py"""
    TP, FN, FP, TN = np.asarray(c, float).T
    tss, rec_, fpr = TP / (TP + FN) - FP / (FP + TN), TP / (TP + FN), FP / (FP + TN)
    prec = np.where(TP + FP > 0, TP / np.maximum(TP + FP, 1), np.nan)
    f = lambda v: f"{np.nanmean(v):.3f} ± {np.nanstd(v, ddof=1):.3f}"
    return tss, {"TSS": f(tss), "recall": f(rec_), "precision": f(prec), "FPR": f(fpr), "prec undefined": int(np.isnan(prec).sum())}


def run_splits(fn, X, y, idx, ratio):
    return Parallel(n_jobs=NJ)(delayed(fn)(X, y, i, ratio) for i in idx)


# ---------------------------------------------------------------- Step 1: R2 reproduction check (STOP on mismatch)
X, y, P, N, npool, cat = build(P2)
Xs, ys, *_ = build_seed(P2, SEED)
assert np.array_equal(X, Xs) and np.array_equal(y, ys), "build_seed(P2, SEED) does not reproduce diag_r.build(P2)"
ref = pd.read_csv("data/diag/r_runs.csv"); ref = ref[ref.run == "R2"].set_index("C1/C2")
bad = []
for ratio in (2.0, 15.0):
    _, s = summ(run_splits(split, X, y, range(REPEATS), ratio)); r = ref.loc[ratio]
    got = {"P": P, "N": N, "neg pool": npool, **s}
    bad += [f"C1/C2 {ratio} {k}: rerun {got[k]} vs recorded {r[k]}" for k in got if got[k] != r[k]]
t1 = time.time()
if bad:
    print("STOP: R2 rerun does not reproduce data/diag/r_runs.csv:\n  " + "\n  ".join(bad)); sys.exit(1)
print(f"Step 1: R2 rerun reproduces data/diag/r_runs.csv exactly (P {P}, N {N}, neg pool {npool}; TSS {ref.loc[2.0, 'TSS']} / {ref.loc[15.0, 'TSS']}; "
      f"recall, precision, FPR identical); build_seed(P2, SEED) == build(P2); {t1 - t00:.0f} s", flush=True)

# ---------------------------------------------------------------- Step 2: R5, R6, R7
rows = []


def row(run, ratio, P, N, npool, counts, draw_tss=None):
    tss, s = summ(counts); lo, hi = TARGET[ratio]
    r = {"run": run, "C1/C2": ratio, "P": P, "N": N, "neg pool": npool, **s, "target": f"{lo}–{hi}", "TSS in target": bool(lo <= tss.mean() <= hi),
         "splits": len(counts)}
    if draw_tss is not None:
        m = np.array([t.mean() for t in draw_tss])
        r.update({"draw min": f"{m.min():.3f}", "draw median": f"{np.median(m):.3f}", "draw max": f"{m.max():.3f}",
                  "draws in target": f"{int(((m >= lo) & (m <= hi)).sum())}/{len(m)}", "draw means": "; ".join(f"{v:.3f}" for v in m)})
    print(r, flush=True); rows.append(r)


for ratio in (2.0, 15.0):
    row("R5 (C_pos = 4, C_neg = 4/ratio)", ratio, P, N, npool, run_splits(split_r5, X, y, range(REPEATS), ratio))
t2 = time.time()
DRAW = [build_seed(P2, SEED + 1000 + j) for j in range(DRAWS)]
assert all((d[2], d[3], d[4]) == (P, N, npool) for d in DRAW)
for run, fn in [("R6 (20 negative draws, R2 penalty)", split), ("R7 (20 negative draws, C_pos = 4, C_neg = 4/ratio)", split_r5)]:
    for ratio in (2.0, 15.0):
        flat = Parallel(n_jobs=NJ)(delayed(fn)(d[0], d[1], i, ratio) for d in DRAW for i in range(SPLITS_PER_DRAW))
        per = [flat[j * SPLITS_PER_DRAW:(j + 1) * SPLITS_PER_DRAW] for j in range(DRAWS)]
        row(run, ratio, P, N, npool, flat, [summ(c)[0] for c in per])
t3 = time.time()
T = pd.DataFrame(rows); T.to_csv("data/diag/r5_r7.csv", index=False)
print(T.drop(columns=["draw means"]).to_string(index=False))
print(f"\nruntime: total {(t3 - t00) / 60:.1f} min (Step 1 R2 rerun {(t1 - t00) / 60:.1f}; R5 {(t2 - t1) / 60:.1f}; R6 + R7 {(t3 - t2) / 60:.1f}); "
      f"workers {NJ}")
