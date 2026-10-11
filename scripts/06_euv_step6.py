"""STEP 6 (decisions.md 2026-09-24 pre-registration). DEV 2010-2019 ONLY -- internal cross-validation, NOT a held-out test.
A = score + n_C + n_M + n_X; E94 = A + dCV_94. Stage 4 folds (fixed column), estimator and scaling; weights 1/n per HARP of
the analysis set. Sets: PRIMARY, S1 (flare-excluded), S2 (primary minus coverage-flagged), S3 (S1 + 2 h after P2 end).
Outputs: data/euv_full/step6/ only. Usage: python euv_step6.py"""
import glob, json, os
import numpy as np, pandas as pd, joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy.stats import wilcoxon
import swpc
from euv_pilot import flare_excluded
from euv_dctrl import summarise
from stage4_models import wlogloss, LR, A_COLS, SEED, K

R, OUT, NBOOT, FILL = "data/euv_full", "data/euv_full/step6", 10000, 0.80
CALIPER = json.load(open("frozen/frozen_spec.json"))["matched_pairs"]["caliper"]
os.makedirs(f"{OUT}/models", exist_ok=True)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)

coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
assert len(coh) == 547 and coh.t.dt.year.max() <= 2019
coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
res = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")]).drop(columns=["harpnum", "t"])
NUM = ["frames", "primary_fill", "sens_fill", "primary_dCV", "sens_dCV", "max_frac_outside_valid"]
res[NUM] = res[NUM].apply(pd.to_numeric, errors="coerce")          # stored as str (json default=str); str(float) round-trips
coh = coh.merge(res, on="eid", how="left")


# ---------------------------------------------------------------- S3 recompute from stored series (no image processing)
def series_versions(e):
    s = pd.read_csv(f"{R}/series/{e.eid}.csv", parse_dates=["t_obs"], float_precision="round_trip")
    t = pd.Timestamp(e.t); lo = t - pd.Timedelta("24h")
    slots = pd.date_range(lo + pd.Timedelta("12min"), t, freq="12min").to_numpy()
    ev, _ = swpc.load(t - pd.Timedelta("2D"), t)
    if len(ev):                                                # empty load has object columns; nothing to shift
        ev = ev.assign(end=ev["end"] + pd.Timedelta("2h"))
    post, _, _, _ = flare_excluded(s.t_obs, ev, {int(x) for x in str(e.noaa_ars).split(",") if x.strip()})
    out = dict(eid=e.eid, s3_extra_frames=int((s.valid_sens & post).sum()))
    for ver, valid in [("chk_primary", s.valid_primary), ("chk_sens", s.valid_sens), ("s3", s.valid_sens & ~post)]:
        tv = s.t_obs[valid].to_numpy()
        out[f"{ver}_fill"] = round(float(np.mean([len(tv) > 0 and np.abs(tv - sl).min() <= np.timedelta64(6, "m")
                                                  for sl in slots])), 4)
        out[f"{ver}_dCV"] = summarise(s.assign(valid=valid), None, None, None, ver)["dCV"] if valid.sum() >= 3 else np.nan
    return out, s


s3rows, frames = [], []
for e in coh[coh.frames.notna()].itertuples():
    o, s = series_versions(e); s3rows.append(o); frames.append(s[["q_ok", "exp_ok", "flare"]])
coh = coh.merge(pd.DataFrame(s3rows), on="eid", how="left")
for v in ["primary", "sens"]:                                  # pre-registered check: stored values reproduced
    m = coh.frames.notna()
    assert (coh.loc[m, f"chk_{v}_fill"] - coh.loc[m, f"{v}_fill"]).abs().max() < 1e-9, f"{v} fill not reproduced"
    assert (coh.loc[m, f"chk_{v}_dCV"] - coh.loc[m, f"{v}_dCV"]).abs().max() < 1e-9, f"{v} dCV not reproduced"
    assert (coh.loc[m, f"chk_{v}_dCV"].isna() == coh.loc[m, f"{v}_dCV"].isna()).all(), f"{v} dCV NaN pattern differs"
print(f"check: stored primary/sens dCV and fill reproduced from series for {int(coh.frames.notna().sum())} episodes (|diff| < 1e-9)")


# ---------------------------------------------------------------- models
def cv_fit(c, cols, tag=None):
    y, w, f = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.fold.to_numpy()
    p = np.empty(len(c))
    for k in range(K):
        tr, te = f != k, f == k
        sc = StandardScaler().fit(c.loc[tr, cols])
        m = LogisticRegression(**LR).fit(sc.transform(c.loc[tr, cols]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]
        if tag:
            joblib.dump({"scaler": sc, "model": m, "cols": cols}, f"{OUT}/models/{tag}_fold{k}.joblib")
    return p


pA0 = cv_fit(coh, A_COLS)                                      # pre-registered check: Stage 4 A reproduced with the fold column
assert np.abs(pA0 - coh.p_A).max() < 1e-9, "Stage 4 p_A not reproduced"
print(f"check: Stage 4 model A reproduced on 547 episodes with the stored fold column (max |diff| {np.abs(pA0 - coh.p_A).max():.1e})")


def analysis_set(mask):
    c = coh[mask].reset_index(drop=True).copy()
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
    return c


def compare(c, dcol, name, save=False):
    c = c.assign(dCV=c[dcol]); assert c.dCV.notna().all()
    pA = cv_fit(c, A_COLS, f"{name}_A" if save else None)
    pE = cv_fit(c, A_COLS + ["dCV"], f"{name}_E94" if save else None)
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    harps = np.unique(h); idx_of = {x: np.where(h == x)[0] for x in harps}
    rng, d = np.random.RandomState(SEED), []
    for _ in range(NBOOT):
        ix = np.concatenate([idx_of[x] for x in rng.choice(harps, len(harps), replace=True)])
        d.append(wlogloss(y[ix], pA[ix], w[ix]) - wlogloss(y[ix], pE[ix], w[ix]))
    lo, hi = np.percentile(d, [2.5, 97.5])
    llA, llE = wlogloss(y, pA, w), wlogloss(y, pE, w)
    c[["eid", "harpnum", "fold", "true_alarm", "weight", "dCV"]].assign(p_A=pA, p_E94=pE).to_csv(f"{OUT}/oof_{name}.csv", index=False)
    return dict(set=name, episodes=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(harps),
                weighted_true=round(float(np.sum(w * y)), 2), weight_sum=round(float(w.sum()), 2),
                logloss_A=llA, logloss_E94=llE, delta_A_minus_E94=llA - llE, CI_lo=lo, CI_hi=hi,
                AUC_A=roc_auc_score(y, pA, sample_weight=w), AUC_E94=roc_auc_score(y, pE, sample_weight=w))


def twins(c, dcol, name):
    """Stage 4 code path (stage4_models.py), dCV instead of the slopes; 10,000 resamples."""
    rng = np.random.RandomState(SEED)
    tru = c[c.true_alarm == 1].iloc[rng.permutation((c.true_alarm == 1).sum())]
    fal = c[c.true_alarm == 0].copy()
    used, pairs = set(), []
    for _, e in tru.iterrows():
        cand = fal[(fal.harpnum != e.harpnum) & ~fal.index.isin(used)]
        dist = (cand.score - e.score).abs()
        if len(dist) and dist.min() <= CALIPER:
            j = dist.idxmin(); used.add(j)
            pairs.append(dict(true_eid=e.eid, false_eid=fal.loc[j, "eid"], true_harp=e.harpnum, false_harp=fal.loc[j, "harpnum"],
                              false_delayed=int(fal.loc[j, "delayed"]), score_diff=e.score - fal.loc[j, "score"],
                              d_dCV=e[dcol] - fal.loc[j, dcol]))
    pr = pd.DataFrame(pairs); pr.to_csv(f"{OUT}/twins_{name}.csv", index=False)
    g = {x: np.where(pr.true_harp.to_numpy() == x)[0] for x in pr.true_harp.unique()}; keys = np.array(list(g))
    v = pr.d_dCV.to_numpy(); bm, bd = [], []
    for _ in range(NBOOT):
        s = v[np.concatenate([g[x] for x in rng.choice(keys, len(keys), replace=True)])]
        bm.append(s.mean()); bd.append(np.median(s))
    return dict(set=name, true_episodes=len(tru), pairs=len(pr), unmatched=len(tru) - len(pr), true_HARPs=len(keys),
                false_delayed=int(pr.false_delayed.sum()), max_abs_score_diff=pr.score_diff.abs().max(),
                mean=v.mean(), mean_CI_lo=np.percentile(bm, 2.5), mean_CI_hi=np.percentile(bm, 97.5),
                median=np.median(v), median_CI_lo=np.percentile(bd, 2.5), median_CI_hi=np.percentile(bd, 97.5),
                frac_true_higher=float((v > 0).mean()), wilcoxon_p=wilcoxon(v).pvalue)


pairs0 = pd.read_csv("data/stage4/matched_pairs_dev.csv")     # check: the twins code reproduces the Stage 4 pairs on 547
chk = twins(coh, "score", "check_stage4")
p0 = pd.read_csv(f"{OUT}/twins_check_stage4.csv"); os.remove(f"{OUT}/twins_check_stage4.csv")
assert chk["pairs"] == len(pairs0) and (p0.true_harp.values == pairs0.true_harp.values).all() \
       and (p0.false_harp.values == pairs0.false_harp.values).all() and np.allclose(p0.score_diff, pairs0.score_diff, atol=1e-12)
print(f"check: twins code reproduces the {len(pairs0)} Stage 4 score-matched pairs")

sets = {"PRIMARY": (coh.primary_fill >= FILL, "primary_dCV"),
        "S1_flare_excluded": (coh.sens_fill >= FILL, "sens_dCV"),
        "S2_primary_no_overhang": ((coh.primary_fill >= FILL) & ~(coh.max_frac_outside_valid > 0), "primary_dCV"),
        "S3_flare_plus_2h": (coh.s3_fill >= FILL, "s3_dCV")}
sets = {k: ((m & coh[d].notna()).fillna(False), d) for k, (m, d) in sets.items()}   # + defined dCV (decisions.md 85d20b4)
print("fill >= 80% but dCV undefined (excluded):", coh.loc[(coh.primary_fill >= FILL) & coh.primary_dCV.isna(), "eid"].tolist())
cmp_rows, twin_rows = [], []
for name, (m, dcol) in sets.items():
    c = analysis_set(m)
    cmp_rows.append(compare(c, dcol, name, save=name in ("PRIMARY", "S1_flare_excluded")))
    if name in ("PRIMARY", "S1_flare_excluded"):
        twin_rows.append(twins(c, dcol, name))
T = pd.DataFrame(cmp_rows); W = pd.DataFrame(twin_rows)
T.to_csv(f"{OUT}/compare.csv", index=False); W.to_csv(f"{OUT}/twins_summary.csv", index=False)
print("\n(b, c) E94 vs A -- dev 2010-2019, internal 5-fold CV (NOT a held-out test); delta = LL(A) - LL(E94), + = EUV helps; "
      f"HARP bootstrap {NBOOT}, seed {SEED}")
print(T.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print(f"\n(d) magnetic twins (gate score, caliper {CALIPER:.4f}, Stage 4 procedure); paired dCV difference true - false; "
      f"CIs: HARP bootstrap clustered by true HARP, {NBOOT}")
print(W.T.to_string(header=False, float_format=lambda v: f"{v:.4f}"))

# ---------------------------------------------------------------- (e) descriptive
coh["group"] = np.where(coh.true_alarm == 1, "true", np.where(coh.delayed == 1, "delayed", "other false"))
D = []
for name, (m, dcol) in list(sets.items())[:2]:
    c = coh[m]
    for grp in ["true", "delayed", "other false"]:
        x = c.loc[c.group == grp, dcol]
        D.append(dict(set=name, group=grp, n=len(x), median=x.median(), Q1=x.quantile(.25), Q3=x.quantile(.75)))
D = pd.DataFrame(D); D.to_csv(f"{OUT}/descriptive.csv", index=False)
print("\n(e) DESCRIPTIVE dCV by group (unweighted episodes; no test)")
print(D.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

# ---------------------------------------------------------------- (c) S3 counts, (f) frame counts
s3 = coh[sets["S3_flare_plus_2h"][0]]
print(f"\n(c) S3 valid at 80%: {len(s3)} of 547 (true {int(s3.true_alarm.sum())}/98, false {int((s3.true_alarm == 0).sum())}/449); "
      f"frames removed by the +2 h extension beyond S1 (all 546 episodes): {int(coh.s3_extra_frames.sum())}")
F = pd.concat(frames); ex = ~F.exp_ok
fc = {"exposure-rule frames": int(ex.sum()), "of which QUALITY != 0": int((ex & ~F.q_ok).sum()),
      "of which QUALITY == 0": int((ex & F.q_ok).sum()), "inside P2 flare interval, any QUALITY": int((ex & F.flare).sum()),
      "inside P2 flare interval, QUALITY == 0": int((ex & F.flare & F.q_ok).sum()), "frames total": len(F),
      "frames in P2 flare intervals (any QUALITY)": int(F.flare.sum())}
print("\n(f) frame counts (recomputed from series; 2026-09-24 item 1c)"); [print(f"  {k}: {v}") for k, v in fc.items()]

# ---------------------------------------------------------------- (g) pre-stated reading, applied mechanically
p, s1 = T.set_index("set").loc["PRIMARY"], T.set_index("set").loc["S1_flare_excluded"]
ok = p.delta_A_minus_E94 > 0 and p.CI_lo > 0 and s1.delta_A_minus_E94 > 0
reading = "EUV adds information" if ok else "no detectable improvement"
print(f"\n(g) pre-stated rule: PRIMARY delta > 0 and 95% CI excludes 0 and S1 delta > 0 -> {ok} -> \"{reading}\"")
json.dump(dict(reading=reading, frame_counts=fc, s3_valid=len(s3), s3_true=int(s3.true_alarm.sum())),
          open(f"{OUT}/step6_result.json", "w"), default=float, indent=1)
