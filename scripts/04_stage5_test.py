"""STAGE 5 -- held-out test, per frozen/frozen_spec.json.  RUN ONCE in mode 'test'.
Mode 'dryrun' exercises identical code on a DEV stand-in (2014, dev HARPs) to remove coding errors; its outputs go to
/tmp and are not test results.
Usage: python stage5_test.py dryrun|test"""
import hashlib, json, sys
import numpy as np, pandas as pd, joblib
from sklearn.metrics import roc_auc_score
import cohort, swpc

MODE = sys.argv[1]
assert MODE in ("dryrun", "test")
OUT = "data/stage5" if MODE == "test" else "/tmp/stage5_dryrun"
import os; os.makedirs(OUT, exist_ok=True)
SPEC = json.load(open("frozen/frozen_spec.json"))
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
SEED, GATE_BOOT, DELTA_BOOT = 20260921, 1000, 10000

# ---------------------------------------------------------------- integrity
assert H("frozen/frozen_spec.json") == "1d20506849930dd52f7f77333f44e4f458a65d9946cb0007a1c603816785368d", "spec changed"
assert H(SPEC["data"]["labelled_file"]) == SPEC["data"]["labelled_sha256"], "labelled file changed"
assert H("frozen/split.csv") == SPEC["data"]["split_sha256"], "split changed"
assert H("src/cohort.py") == SPEC["cohort"]["code_sha256"], "cohort.py changed"
for f, v in SPEC["gate"]["fold_models"].items():
    assert H(v["path"]) == v["sha256"], f"gate {f} changed"
for k, v in SPEC["models"]["fold_models"].items():
    assert H(f"data/stage4/models/{k}.joblib") == v, f"model {k} changed"
print("integrity: all frozen hashes verified")

F, THR, CAL = SPEC["gate"]["features"], SPEC["gate"]["threshold"], SPEC["matched_pairs"]["caliper"]
split = pd.read_csv("frozen/split.csv")
lab = pd.read_csv(SPEC["data"]["labelled_file"], parse_dates=["t_rec_utc"], low_memory=False)
if MODE == "test":
    harps = set(split.loc[split["set"] == "test", "harpnum"])
    PERIODS = {"primary (2021, 2023, 2024)": [2021, 2023, 2024], "sensitivity (2021-2024, 2022 included)": [2021, 2022, 2023, 2024]}
else:
    harps = set(split.loc[split["set"].isin(["train", "val"]), "harpnum"])
    PERIODS = {"DRYRUN primary (2014)": [2014], "DRYRUN sensitivity (2013-2014)": [2013, 2014]}
lab = lab[lab["harpnum"].isin(harps)]
lab = lab[lab["t_rec_utc"].dt.year.isin(sorted(set(sum(PERIODS.values(), []))) )].reset_index(drop=True)
print(f"mode {MODE}: {len(lab)} rows, {lab['harpnum'].nunique()} HARPs, years {sorted(lab['t_rec_utc'].dt.year.unique())}")

# ---------------------------------------------------------------- gate scores: mean of 5 fold models
unscorable = lab[F].isna().any(axis=1)
print(f"unscorable rows (missing gate feature): {int(unscorable.sum())} "
      f"(positive {int(lab.loc[unscorable, 'flared_M1_next_24h'].sum())}) -- excluded")
lab = lab[~unscorable].reset_index(drop=True)
X = lab[F].to_numpy(float)
dv = np.zeros(len(lab))
for f, v in SPEC["gate"]["fold_models"].items():
    g = joblib.load(v["path"]); dv += g["model"].decision_function((X - g["median"]) / g["sd"])
lab["score"] = dv / len(SPEC["gate"]["fold_models"])
AB = {m: [joblib.load(f"data/stage4/models/{m}_fold{f}.joblib") for f in range(5)] for m in "AB"}


def prob(c, m):
    return np.mean([d["model"].predict_proba(d["scaler"].transform(c[d["cols"]]))[:, 1] for d in AB[m]], axis=0)


def contingency(y, a):
    tp, fn = int((a & (y == 1)).sum()), int((~a & (y == 1)).sum())
    fp, tn = int((a & (y == 0)).sum()), int((~a & (y == 0)).sum())
    tpr = tp / (tp + fn) if tp + fn else np.nan; fpr = fp / (fp + tn) if fp + tn else np.nan
    hss = 2 * (tp * tn - fn * fp) / ((tp + fn) * (fn + tn) + (tp + fp) * (fp + tn)) if (tp + fn) and (fn + tn) else np.nan
    return dict(TSS=tpr - fpr, HSS=hss, FAR=fp / (tp + fp) if tp + fp else np.nan, TPR=tpr, FPR=fpr,
                TP=tp, FN=fn, FP=fp, TN=tn)


def boot_ci(groups, stat, n):
    keys = np.array(list(groups)); rng = np.random.RandomState(SEED); v = []
    for _ in range(n):
        ix = np.concatenate([groups[k] for k in rng.choice(keys, len(keys), replace=True)])
        x = stat(ix)
        if np.isfinite(x):
            v.append(x)
    return np.percentile(v, [2.5, 97.5]), len(v)


def gate_metrics(d):
    y, s, h = d["flared_M1_next_24h"].to_numpy(), d["score"].to_numpy(), d["harpnum"].to_numpy()
    out = {}
    # hour level
    grp = {x: np.where(h == x)[0] for x in np.unique(h)}
    for thr, tag in [(THR, "frozen"), (0.0, "zero")]:
        m = contingency(y, s >= thr)
        ci, n = boot_ci(grp, lambda ix: contingency(y[ix], s[ix] >= thr)["TSS"], GATE_BOOT)
        out[f"hour_{tag}"] = {**m, "TSS_CI": ci, "boot_used": n}
    # region level: one entry per HARP
    r = pd.DataFrame({"h": h, "y": y, "s": s}).groupby("h").agg(y=("y", "max"), s=("s", "max"))
    ry, rs = r["y"].to_numpy(), r["s"].to_numpy(); rgrp = {i: np.array([i]) for i in range(len(r))}
    for thr, tag in [(THR, "frozen"), (0.0, "zero")]:
        m = contingency(ry, rs >= thr)
        ci, n = boot_ci(rgrp, lambda ix: contingency(ry[ix], rs[ix] >= thr)["TSS"], GATE_BOOT)
        out[f"region_{tag}"] = {**m, "TSS_CI": ci, "boot_used": n}
    return out


def wll(y, p, w):
    p = np.clip(p, 1e-15, 1 - 1e-15); return float(np.sum(w * -(y * np.log(p) + (1 - y) * np.log(1 - p))) / np.sum(w))


def ab(c, label):
    y, w, h = c["true_alarm"].to_numpy(), c["weight"].to_numpy(), c["harpnum"].to_numpy()
    pA, pB = prob(c, "A"), prob(c, "B")
    grp = {x: np.where(h == x)[0] for x in np.unique(h)}
    ok = 0 < y.sum() < len(y)
    ci, n = boot_ci(grp, lambda ix: wll(y[ix], pA[ix], w[ix]) - wll(y[ix], pB[ix], w[ix]), DELTA_BOOT)
    return {"cohort": label, "episodes": len(c), "true": int(y.sum()), "HARPs": len(grp),
            "true_HARPs": len(set(h[y == 1])), "weighted_true": float((w * y).sum()), "weight_sum": float(w.sum()),
            "logloss_A": wll(y, pA, w), "logloss_B": wll(y, pB, w), "delta_A_minus_B": wll(y, pA, w) - wll(y, pB, w),
            "delta_CI_lo": ci[0], "delta_CI_hi": ci[1], "boot_used": n,
            "AUC_A": roc_auc_score(y, pA, sample_weight=w) if ok else np.nan,
            "AUC_B": roc_auc_score(y, pB, sample_weight=w) if ok else np.nan}, pA, pB


SUBSETS = {"single": lambda d: d["noaa_ar_count"] == 1, "<=2": lambda d: d["noaa_ar_count"] <= 2,
           "all": lambda d: d["noaa_ar_count"] > 0}
gate_rows, coh_rows, ab_rows = [], [], []
missing = swpc.label_missing_days()
primary_key = list(PERIODS)[0]
for pname, years in PERIODS.items():
    for sname, sf in SUBSETS.items():
        d = lab[lab["t_rec_utc"].dt.year.isin(years)]
        d = d[sf(d)]
        gm = gate_metrics(d)
        for lvl, m in gm.items():
            gate_rows.append({"period": pname, "subset": sname, "level_threshold": lvl, "rows_or_HARPs":
                              m["TP"] + m["FN"] + m["FP"] + m["TN"], "positives": m["TP"] + m["FN"],
                              **{k: m[k] for k in ["TSS", "HSS", "FAR", "TPR", "FPR"]},
                              "TSS_CI_lo": m["TSS_CI"][0], "TSS_CI_hi": m["TSS_CI"][1], "boot_used": m["boot_used"]})
        # cohort: alarms restricted to the evaluation years; trend windows use every labelled row of the HARP
        full = pd.read_csv(SPEC["data"]["labelled_file"], parse_dates=["t_rec_utc"], low_memory=False) \
            if sname == "single" and pname == primary_key else full
        hl = full[full["harpnum"].isin(set(d["harpnum"]))]
        c, x, eps = cohort.build(d[["harpnum", "t_rec_utc", "score"]].merge(
            d.drop(columns="score"), on=["harpnum", "t_rec_utc"]), hl, THR, missing)
        coh_rows.append({"period": pname, "subset": sname, "episodes_T1": len(eps), "alarm_HARPs": eps["harpnum"].nunique(),
                         "excluded_episodes": len(x), "excl_reasons": x["reason"].value_counts().to_dict(),
                         "eligible_episodes": len(c), "true": int(c["true_alarm"].sum()) if len(c) else 0,
                         "false": int((c["true_alarm"] == 0).sum()) if len(c) else 0,
                         "delayed": int(c["delayed"].sum()) if len(c) else 0,
                         "regions": c["harpnum"].nunique() if len(c) else 0,
                         "regions_with_true": c.loc[c["true_alarm"] == 1, "harpnum"].nunique() if len(c) else 0,
                         "weighted_true": float((c["weight"] * c["true_alarm"]).sum()) if len(c) else 0.0})
        if not len(c):
            continue
        r, pA, pB = ab(c, "all eligible episodes (T2)")
        ab_rows.append({"period": pname, "subset": sname, **r})
        first = c[c["first_eligible"]].copy(); first["weight"] = 1.0
        r1, _, _ = ab(first.reset_index(drop=True), "first eligible episode per region")
        ab_rows.append({"period": pname, "subset": sname, **r1})
        if pname == primary_key and sname == "single":
            c.assign(p_A=pA, p_B=pB).to_csv(f"{OUT}/cohort_test_primary.csv", index=False)
            # score-matched pairs, frozen dev caliper
            rng = np.random.RandomState(SEED)
            tru = c[c["true_alarm"] == 1].iloc[rng.permutation((c["true_alarm"] == 1).sum())]
            fal = c[c["true_alarm"] == 0]; used, pairs = set(), []
            for _, e in tru.iterrows():
                cand = fal[(fal["harpnum"] != e["harpnum"]) & ~fal.index.isin(used)]
                dist = (cand["score"] - e["score"]).abs()
                if len(dist) and dist.min() <= CAL:
                    j = dist.idxmin(); used.add(j)
                    pairs.append({"true_harp": e["harpnum"], "score_diff": e["score"] - fal.loc[j, "score"],
                                  **{f"d_{s}": e[s] - fal.loc[j, s] for s in ["rel_slope_usflux", "rel_slope_totusjh"]}})
            pr = pd.DataFrame(pairs); pr.to_csv(f"{OUT}/matched_pairs_test.csv", index=False)
            pair_rows = [{"caliper": CAL, "pairs": len(pr), "true_episodes": len(tru), "unmatched": len(tru) - len(pr),
                          "max_abs_score_diff": pr["score_diff"].abs().max() if len(pr) else np.nan,
                          "true_HARPs": pr["true_harp"].nunique() if len(pr) else 0}]
            if len(pr):
                g = {k: np.where(pr["true_harp"].to_numpy() == k)[0] for k in pr["true_harp"].unique()}
                for s in ["rel_slope_usflux", "rel_slope_totusjh"]:
                    v = pr[f"d_{s}"].to_numpy()
                    ci, _ = boot_ci(g, lambda ix: v[ix].mean(), 1000)
                    pair_rows.append({"slope": s, "mean_diff": v.mean(), "median_diff": np.median(v),
                                      "CI_lo": ci[0], "CI_hi": ci[1]})
            grpn = np.where(c["true_alarm"] == 1, "true", np.where(c["delayed"] == 1, "delayed", "other false"))
            desc = []
            for name in ["true", "delayed", "other false"]:
                cc = c[grpn == name]
                if len(cc):
                    desc.append({"group": name, "episodes": len(cc), "HARPs": cc["harpnum"].nunique(),
                                 "weight": cc["weight"].sum(),
                                 **{f"{s}_wmean": np.average(cc[s], weights=cc["weight"]) for s in
                                    ["score", "n_C", "n_M", "n_X", "rel_slope_usflux", "rel_slope_totusjh"]},
                                 **{f"{s}_median": cc[s].median() for s in ["rel_slope_usflux", "rel_slope_totusjh"]}})
        print(f"  done: {pname} / {sname}", flush=True)

pd.set_option("display.width", 250)
fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else v
for name, rows in [("GATE", gate_rows), ("COHORT SIZES", coh_rows), ("MODELS A vs B", ab_rows)]:
    t = pd.DataFrame(rows); t.to_csv(f"{OUT}/{name.split()[0].lower()}_{name.split()[-1].lower()}.csv", index=False)
    print(f"\n{name}"); print(t.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print("\nMATCHED PAIRS (primary, single-region)"); print(pd.DataFrame(pair_rows).to_string(index=False, float_format=lambda v: f"{v:.4g}"))
pd.DataFrame(pair_rows).to_csv(f"{OUT}/pairs_summary.csv", index=False)
print("\nDELAYED vs TRUE (primary, single-region; descriptive)"); print(pd.DataFrame(desc).to_string(index=False, float_format=lambda v: f"{v:.4g}"))
pd.DataFrame(desc).to_csv(f"{OUT}/delayed_descriptive.csv", index=False)
