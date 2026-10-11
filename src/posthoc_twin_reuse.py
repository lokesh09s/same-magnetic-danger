"""Post-hoc twin-interval check under region reuse (decisions.md 2026-09-30, 7c9b7bb). POST-HOC diagnostic on the 50 TEST 1 pairs (ae1b174).
Step 1 reproduces TEST 1 (pairs resampled by true HARP); then (a) by false HARP, (b) two-way (true x false HARP weights), (c) by linked
groups (connected components of the HARP-pair graph). Statistic: median true CV_box / median false CV_box; 2,000 resamples, seed 0.
Usage: python posthoc_twin_reuse.py"""
import sys, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from phase_f import ratio_jobs, boot_many, pct, med_ratio, W
from euv_confirm_tests import conf_cohort

NB, SEED = 2000, 0


def components(th, fh):
    """union-find over HARPs; edges = pairs. -> component label per pair, components ordered by their smallest HARP."""
    parent = {}
    find = lambda a: a if parent.setdefault(a, a) == a else parent.__setitem__(a, find(parent[a])) or parent[a]
    for a, b in zip(th, fh):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    root = np.array([find(a) for a in th])
    members = {}
    for a in set(th) | set(fh):
        members.setdefault(find(a), set()).add(a)
    order = sorted(members, key=lambda r: min(members[r]))
    return np.array([order.index(r) for r in root]), [sorted(members[r]) for r in order]


def summ(B):
    B = np.asarray(B, float); ok = np.isfinite(B)
    lo, hi = pct(B[ok]); return lo, hi, float(np.mean(B[ok] <= 1)), int((~ok).sum())


if __name__ == "__main__":
    t0 = time.time(); pd.set_option("display.width", 250)
    le2 = conf_cohort("le2"); assert len(le2) == 387
    c1 = le2[(le2.primary_fill >= 0.80) & le2.primary_CV_box.notna()].reset_index(drop=True); assert len(c1) == 378   # TEST 1 set
    tw = pd.read_csv("data/euv_confirm/twins_le2.csv"); assert len(tw) == 50
    v = c1.set_index("eid").primary_CV_box
    xt, xf = tw.true_eid.map(v).to_numpy(float), tw.false_eid.map(v).to_numpy(float)
    assert np.isfinite(xt).all() and np.isfinite(xf).all()
    th, fh = tw.true_harp.to_numpy(), tw.false_harp.to_numpy()
    grp = lambda keys: [np.where(keys == k)[0] for k in pd.unique(keys)]          # order of first appearance
    pool = ProcessPoolExecutor(W)
    # ---- Step 1: TEST 1 with the existing code (STOP on mismatch)
    e, j = ratio_jobs("TEST 1", c1, "primary_CV_box", "ratio", tw)
    B1 = boot_many({"s1": j[("TEST 1", "tw")]}, pool)["s1"]
    lo1, hi1, le1, un1 = summ(B1)
    if (round(e["ratio_twins"], 4), round(lo1, 4), round(hi1, 4), e["pairs"]) != (3.2624, 1.2956, 9.4887, 50):
        print(f"STOP: TEST 1 not reproduced: {e['ratio_twins']:.4f} [{lo1:.4f}, {hi1:.4f}], {e['pairs']} pairs"); sys.exit(1)
    print(f"Step 1: TEST 1 reproduced exactly with the existing code: ratio {e['ratio_twins']:.4f} [{lo1:.4f}, {hi1:.4f}], {e['pairs']} pairs "
          f"(pairs resampled by true HARP; 2,000, seed 0)")
    point = med_ratio(xt, xf, "ratio"); assert point == e["ratio_twins"]
    # ---- (a) false HARP, (c) linked groups
    comp, members = components(th, fh)
    B = boot_many({"a": ("ratio_pairs", dict(xt=xt, xf=xf, mode="ratio", groups=grp(fh)), NB, SEED),
                   "c": ("ratio_pairs", dict(xt=xt, xf=xf, mode="ratio", groups=grp(comp)), NB, SEED)}, pool)
    pool.shutdown()
    # ---- (b) two-way: counts a_i (true HARPs) x b_j (false HARPs); weighted medians = medians of values repeated by weight
    T_, F_ = pd.unique(th), pd.unique(fh); ti, fi = pd.Index(T_).get_indexer(th), pd.Index(F_).get_indexer(fh)
    rng = np.random.RandomState(SEED); Bb, skipped = [], 0
    for _ in range(NB):
        a = np.bincount(rng.choice(len(T_), len(T_), replace=True), minlength=len(T_))
        b = np.bincount(rng.choice(len(F_), len(F_), replace=True), minlength=len(F_))
        w = a[ti] * b[fi]
        if w.sum() == 0:
            skipped += 1; continue
        Bb.append(np.median(np.repeat(xt, w)) / np.median(np.repeat(xf, w)))
    rows = []
    for name, clusters, BB, skip in [("Step 1 flaring side only (true HARP; TEST 1)", f"{len(T_)} true HARPs", B1, 0),
                                     ("(a) non-flaring side only (false HARP)", f"{len(F_)} false HARPs", B["a"], 0),
                                     ("(b) both sides (two-way, weights a_i * b_j)", f"{len(T_)} true x {len(F_)} false HARPs", Bb, skipped),
                                     ("(c) linked groups (connected components)", f"{len(members)} components", B["c"], 0)]:
        lo, hi, le, un = summ(BB)
        rows.append({"interval": name, "clusters": clusters, "ratio": f"{point:.4f}", "95% CI": f"[{lo:.4f}, {hi:.4f}]", "share ratio <= 1": f"{le:.4f}",
                     "resamples used": len(BB) - un, "skipped (zero weight)": skip, "undefined (non-finite)": un})
    T = pd.DataFrame(rows)
    both = sorted(int(x) for x in set(th) & set(fh))
    print(f"\nPOST-HOC (7c9b7bb): 50 TEST 1 pairs; median true CV_box / median false CV_box; 2,000 resamples, seed 0; percentile 95% CI")
    print(T.to_string(index=False))
    print(f"\ndistinct HARPs: true {len(T_)}, false {len(F_)}, on both sides {len(both)} {both}, total {len(set(th) | set(fh))}")
    sizes = [dict(component=k + 1, HARPs=len(m), pairs=int((comp == k).sum()), members=" ".join(map(str, m))) for k, m in enumerate(members)]
    print(f"components: {len(members)}; sizes (HARPs / pairs), ordered by smallest HARP:")
    print(pd.DataFrame(sizes).to_string(index=False))
    print(f"\nwall {time.time() - t0:.1f} s, workers {W}")
