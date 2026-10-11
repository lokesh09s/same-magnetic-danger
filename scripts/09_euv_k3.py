"""EXPLORATORY (decisions.md 2026-09-26, ae24e98): temporal contrast K3 = log10(median kappa_box LATE / EARLY), LATE =
pairs with t_obs > t - 3 h. From the stored Phase X pairs files (no image reprocessing). DEV 2010-2019 ONLY.
Usage: python euv_k3.py compute | eval"""
import glob, json, os, sys, time
import numpy as np, pandas as pd

R, OUT = "data/euv_full", "data/euv_full/k3"


def k3(pairs_csv, t):
    p = pd.read_csv(pairs_csv, usecols=["t_obs", "kappa_box"], parse_dates=["t_obs"])
    p = p[np.isfinite(p.kappa_box)]
    late, early = p[p.t_obs > t - pd.Timedelta("3h")], p[p.t_obs <= t - pd.Timedelta("3h")]
    ml = late.kappa_box.median() if len(late) else np.nan; me = early.kappa_box.median() if len(early) else np.nan
    ok = len(late) >= 5 and np.isfinite(ml) and np.isfinite(me) and ml > 0 and me > 0
    return len(late), len(early), float(np.log10(ml / me)) if ok else np.nan


if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    os.makedirs(OUT, exist_ok=True)
    c = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"], usecols=["harpnum", "t"])     # no label column read
    c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
    rows = []
    for e in c.itertuples():
        r = dict(eid=e.eid)
        for tag, d in [("", "spatial"), ("_nf", "spatial_nf")]:
            f = f"{R}/{d}/{e.eid}_pairs.csv"
            r[f"n_late{tag}"], r[f"n_early{tag}"], r[f"K3{tag}"] = k3(f, e.t) if os.path.exists(f) else (np.nan, np.nan, np.nan)
        rows.append(r)
    K = pd.DataFrame(rows); K.to_csv(f"{OUT}/k3_values.csv", index=False)
    rs = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")])
    rs = rs[rs.eid.notna()][["eid", "primary_fill", "sens_fill"]]; rs[["primary_fill", "sens_fill"]] = rs[["primary_fill", "sens_fill"]].apply(pd.to_numeric, errors="coerce")
    K = K.merge(rs, on="eid", how="left"); P, S = K.primary_fill >= 0.8, K.sens_fill >= 0.8
    print(f"LABEL-BLIND REPORT (no labels read): {len(K)} dev episodes, pairs files for {int(K.n_late.notna().sum())}")
    for tag, m, lab in [("", P, "primary 80% set"), ("_nf", S, "flare-excluded 80% set")]:
        x = K.loc[m, f"K3{tag}"]; nl = K.loc[m, f"n_late{tag}"]
        print(f"K3{tag} on the {lab} ({int(m.sum())}): defined {int(x.notna().sum())}, excluded {int(x.isna().sum())} "
              f"(LATE < 5 pairs: {int((nl < 5).sum())}); LATE pairs median {nl.median():.0f}, min {nl.min():.0f}, max {nl.max():.0f}")
        q = np.nanpercentile(x, [0, 5, 25, 50, 75, 95, 100])
        print("   K3 percentiles 0/5/25/50/75/95/100: " + " / ".join(f"{v:.4f}" for v in q))

if __name__ == "__main__" and sys.argv[1:] == ["eval"]:
    from concurrent.futures import ProcessPoolExecutor
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    from euv_spatial import cv_fit
    from phase_f import load_base, prep, boot_many, wlogloss, pct, A_COLS, W
    t00 = time.time(); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); fmt = lambda v: f"{v:.4f}"
    dv = load_base().merge(pd.read_csv(f"{OUT}/k3_values.csv")[["eid", "K3", "K3_nf"]], on="eid", how="left")

    def jobs_for(name, c, base, full):
        pA, pE = cv_fit(c, base), cv_fit(c, full); y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
        groups = [np.where(h == v)[0] for v in np.unique(h)]
        est = dict(test=name, n=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(groups),
                   logloss_base=wlogloss(y, pA, w), logloss_full=wlogloss(y, pE, w),
                   AUC_base=roc_auc_score(y, pA, sample_weight=w), AUC_full=roc_auc_score(y, pE, sample_weight=w))
        est["delta"] = est["logloss_base"] - est["logloss_full"]
        return est, {name: ("dll", dict(y=y, w=w, pA=pA, pE=pE, groups=groups), 10000, 20260921)}

    def evaluate(specs, pool):
        ests, jobs = [], {}
        for s in specs:
            e, j = jobs_for(*s); ests.append(e); jobs.update(j)
        B = boot_many(jobs, pool)
        for e in ests:
            e["CI_lo"], e["CI_hi"] = pct(B[e["test"]])
        return pd.DataFrame(ests)

    with ProcessPoolExecutor(W) as pool:
        px = pd.read_csv(f"{R}/spatial/eval_compare.csv", float_precision="round_trip").set_index("candidate").loc["R4a"]
        ck = evaluate([("check A vs A+R4a (Phase X 541)", prep(dv, dv.P & dv.R4a.notna()), A_COLS, A_COLS + ["R4a"])], pool).iloc[0]
        assert ck.n == 541 and ck.delta == px.delta_A_minus_Aplus and ck.CI_lo == px.CI_lo and ck.CI_hi == px.CI_hi \
            and ck.AUC_base == px.AUC_A and ck.AUC_full == px.AUC_A_plus, "Phase X R4a not reproduced"
        print(f"check: A vs A + R4a on the Phase X 541 set reproduces Phase X exactly (delta {ck.delta:.4f} "
              f"[{ck.CI_lo:.4f}, {ck.CI_hi:.4f}], AUC {ck.AUC_base:.4f} -> {ck.AUC_full:.4f})")
        mP = dv.P & dv.K3.notna() & dv.R4a.notna(); mS = dv.S & dv.K3_nf.notna() & dv.R4a_nf.notna()
        print(f"sets: PRIMARY {int(mP.sum())} of {int(dv.P.sum())} primary 80% (excluded label-blind {int((dv.P & ~mP).sum())}); "
              f"s2 {int(mS.sum())} of {int(dv.S.sum())} sens 80% (excluded {int((dv.S & ~mS).sum())})")
        cP, cS = prep(dv, mP), prep(dv, mS)
        T = evaluate([("PRIMARY A+R4a vs A+R4a+K3", cP, A_COLS + ["R4a"], A_COLS + ["R4a", "K3"]),
                      ("s1 A vs A+K3", cP, A_COLS, A_COLS + ["K3"]),
                      ("s2 A+R4a_nf vs A+R4a_nf+K3_nf", cS, A_COLS + ["R4a_nf"], A_COLS + ["R4a_nf", "K3_nf"])], pool)
    print("\ndev 2010-2019, internal 5-fold CV, EXPLORATORY; delta = LL(base) - LL(base + x), + = helps; HARP bootstrap 10,000, seed 20260921")
    print(T.to_string(index=False, float_format=fmt))
    r = T.iloc[0]; el = r.delta > 0 and r.CI_lo > 0 and r.AUC_full > r.AUC_base
    print(f"pre-stated reading (mechanical, PRIMARY): delta {r.delta:+.4f} [{r.CI_lo:+.4f}, {r.CI_hi:+.4f}], AUC {r.AUC_base:.4f} -> "
          f"{r.AUC_full:.4f} -> \"{'ELIGIBLE for independent confirmation' if el else 'NOT ELIGIBLE'}\"")
    lead = pd.read_csv(f"{R}/step6/explore_2_timing.csv")[["eid", "lead_h"]]
    t = dv[(dv.true_alarm == 1) & mP].merge(lead, on="eid", how="left")
    a, b = t[(t.lead_h > 0) & (t.lead_h <= 6)], t[(t.lead_h > 6) & (t.lead_h <= 24)]
    print(f"\ns3 true episodes (PRIMARY set, lead from the step 6 diagnostic): lead (0, 6] h n {len(a)}, median K3 {a.K3.median():.4f}; "
          f"lead (6, 24] h n {len(b)}, median K3 {b.K3.median():.4f}; no lead {int(t.lead_h.isna().sum())}")
    rows = []
    for v in ["n_C", "n_M", "n_X", "score", "R4a"]:
        rr, p = spearmanr(cP.K3, cP[v]); rows.append(dict(variable=v, n=len(cP), rho=rr, p=p))
    S4 = pd.DataFrame(rows)
    print("\ns4 Spearman rho of K3 (PRIMARY set)"); print(S4.to_string(index=False, formatters={"rho": "{:.4f}".format, "p": "{:.2e}".format}))
    T.to_csv(f"{OUT}/eval.csv", index=False); S4.to_csv(f"{OUT}/spearman.csv", index=False)
    print(f"\nwall {time.time() - t00:.1f} s, workers {W}")
