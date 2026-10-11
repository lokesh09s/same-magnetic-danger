"""HELD-OUT REPLICATION OF F2 (decisions.md 2026-09-26; added after the held-out R4a result 7438177). Run ONCE.
Primary: CV_box, magnetic twins (step 6 twins code) on the test primary 80% set; secondary: twins within flare-history
group; CV_PIL / CV_ctrl descriptive; dev secondary reference EXPLORATORY."""
import glob, json, os, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from phase_f import ratio_jobs, boot_many, pct, load_base, W

SEED, CAL = 20260921, json.load(open("frozen/frozen_spec.json"))["matched_pairs"]["caliper"]
OUT = "data/euv_test/f2_replication"
CV = [("CV_box", "primary_CV_box"), ("CV_PIL", "primary_CV_PIL"), ("CV_ctrl", "primary_CV_ctrl")]


def hist_group(c):
    return np.where(c.n_M + c.n_X >= 1, "JUST-FLARED", np.where(c.n_C + c.n_M + c.n_X == 0, "QUIET-NOW", "C-only"))


def twins(c, by_group=False):
    """= euv_step6.twins matching (seeded order, greedy nearest on gate score, different HARP, no reuse, caliper);
    by_group: the false twin must share the true episode's flare-history group."""
    c = c.reset_index(drop=True).assign(grp=hist_group(c.reset_index(drop=True)))
    rng = np.random.RandomState(SEED)
    tru = c[c.true_alarm == 1].iloc[rng.permutation((c.true_alarm == 1).sum())]
    fal = c[c.true_alarm == 0].copy()
    used, pairs = set(), []
    for _, e in tru.iterrows():
        cand = fal[(fal.harpnum != e.harpnum) & ~fal.index.isin(used)]
        if by_group:
            cand = cand[cand.grp == e.grp]
        dist = (cand.score - e.score).abs()
        if len(dist) and dist.min() <= CAL:
            j = dist.idxmin(); used.add(j)
            pairs.append(dict(true_eid=e.eid, false_eid=fal.loc[j, "eid"], true_harp=e.harpnum, false_harp=fal.loc[j, "harpnum"],
                              group=e.grp, score_diff=e.score - fal.loc[j, "score"]))
    return pd.DataFrame(pairs), int((c.true_alarm == 1).sum())


def run(label, c, tw, pool):
    ests, jobs = [], {}
    for name, col in CV:
        e, j = ratio_jobs(f"{label} | {name}", c, col, "ratio", tw); ests.append(e); jobs.update(j)
    B = boot_many(jobs, pool)
    for e in ests:
        k = e["measure"]; e["all_CI_lo"], e["all_CI_hi"] = pct(B[(k, "all")]); e["tw_CI_lo"], e["tw_CI_hi"] = pct(B[(k, "tw")])
    return pd.DataFrame(ests)


if __name__ == "__main__":
    t0 = time.time(); os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    fmt = lambda v: f"{v:.4f}"
    print(f"HELD-OUT REPLICATION OF F2 (added after 7438177); workers {W}")
    # ---- dev (checks + EXPLORATORY reference)
    dv = load_base()
    s6 = pd.read_csv("data/euv_full/step6/twins_PRIMARY.csv")
    p6, _ = twins(dv[dv.P & dv.primary_dCV.notna()])
    assert len(p6) == len(s6) and (p6.true_eid.values == s6.true_eid.values).all() and (p6.false_eid.values == s6.false_eid.values).all()
    f2 = pd.read_csv("data/phase_f/F2_ratios.csv", float_precision="round_trip").set_index("measure")
    with ProcessPoolExecutor(W) as pool:
        chk = run("dev", dv[dv.P], s6, pool).set_index("measure")
        for name, _ in CV:
            a, b = chk.loc[f"dev | {name}"], f2.loc[name]
            assert all(abs(a[k] - b[k]) < 1e-9 for k in ["med_true", "med_false", "ratio_all", "ratio_twins", "twin_med_true", "twin_med_false"])
            assert "[%.4f, %.4f]" % (a.all_CI_lo, a.all_CI_hi) == b.all_CI and "[%.4f, %.4f]" % (a.tw_CI_lo, a.tw_CI_hi) == b.twins_CI
        print("checks: twins code reproduces the 81 step 6 pairs; ratio code reproduces the committed F2 rows for CV_box, CV_PIL, CV_ctrl")
        # ---- test
        tc = pd.read_csv("data/stage5/cohort_test_primary.csv", parse_dates=["t"])
        tc["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(tc.harpnum, tc.t)]
        num = ["primary_fill"] + [col for _, col in CV]
        rs = pd.DataFrame([json.load(open(p)) for p in glob.glob("data/euv_test/results/*.json")])[["eid"] + num]
        rs[num] = rs[num].apply(pd.to_numeric, errors="coerce")
        tc = tc.merge(rs, on="eid", how="left")
        ts = tc[(tc.primary_fill >= 0.80) & tc.primary_CV_box.notna()].reset_index(drop=True)
        print(f"test set: {len(ts)} episodes (true {int(ts.true_alarm.sum())}, false {int((ts.true_alarm == 0).sum())}, "
              f"HARPs {ts.harpnum.nunique()}); CV_PIL/CV_ctrl undefined: {int(ts.primary_CV_PIL.isna().sum())}/{int(ts.primary_CV_ctrl.isna().sum())}")
        tw1, nt = twins(ts); tw2, _ = twins(ts, by_group=True); dtw2, dnt = twins(dv[dv.P], by_group=True)
        for lab, tw, n in [("test primary twins", tw1, nt), ("test history-group twins", tw2, nt), ("dev history-group twins", dtw2, dnt)]:
            print(f"{lab}: {len(tw)} pairs of {n} true episodes; max |score diff| {tw.score_diff.abs().max():.4f}; "
                  f"by group {tw.group.value_counts().to_dict()}")
        tw1.to_csv(f"{OUT}/twins_test_primary.csv", index=False); tw2.to_csv(f"{OUT}/twins_test_history.csv", index=False)
        dtw2.to_csv(f"{OUT}/twins_dev_history.csv", index=False)
        R1 = run("TEST primary twins", ts, tw1, pool)
        R2 = run("TEST history-group twins (secondary)", ts, tw2, pool)
        R3 = run("DEV history-group twins (EXPLORATORY reference)", dv[dv.P], dtw2, pool)
    T = pd.concat([R1, R2, R3]); T.to_csv(f"{OUT}/ratios.csv", index=False)
    cols = ["measure", "n", "n_true", "n_false", "med_true", "med_false", "ratio_all", "all_CI_lo", "all_CI_hi", "pairs",
            "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI_lo", "tw_CI_hi"]
    print("\nratio = median(true) / median(false); all-episodes CI: HARP bootstrap 2,000, seed 0; twins CI: pairs resampled by true HARP, 2,000, seed 0")
    print(T[cols].to_string(index=False, float_format=fmt))
    r = R1.set_index("measure").loc["TEST primary twins | CV_box"]
    reading = ("REPLICATED" if r.ratio_twins > 1 and r.tw_CI_lo > 1 else
               "direction consistent, not confirmed" if r.ratio_twins > 1 else "NOT REPLICATED")
    print(f"\npre-stated reading (mechanical; primary = TEST primary twins, CV_box): ratio {r.ratio_twins:.4f} "
          f"[{r.tw_CI_lo:.4f}, {r.tw_CI_hi:.4f}] -> \"{reading}\"")
    print(f"wall {time.time() - t0:.1f} s")
