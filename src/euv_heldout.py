"""HELD-OUT EUV TESTS (decisions.md 2026-09-25 pre-registration f3d6489; ΔCV design 3283478 item 1h).
compute: test-year EUV values with the dev code (euv_full.compute_episode, euv_spatial.spatial_episode), 9 workers.
test:    run ONCE -- a. ΔCV (PRIMARY, S1, S2); b. R4a (primary, sensitivity) + operating-point test; c. R4c; d. Spearman.
Usage: python euv_heldout.py compute | test"""
import glob, json, os, sys, time, warnings
import numpy as np, pandas as pd

T, D = "data/euv_test", "data/euv_full"
W = os.cpu_count() - 1
warnings.filterwarnings("ignore")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)


def test_episode(ep):
    from euv_full import compute_episode
    from euv_spatial import spatial_episode
    h, e = ep["harpnum"], ep["eid"]; t0 = time.time(); err = ""
    try:
        if not os.path.exists(f"{T}/results/{e}.json"):
            r = compute_episode(ep, f"{T}/hmi/{h}", f"{T}/aia/{h}", f"{T}/series")
            json.dump({k: str(v) for k, v in r.items()}, open(f"{T}/results/{e}.json", "w"))       # same format as dev
        for d, v in [("spatial", "valid_primary"), ("spatial_nf", "valid_sens")]:
            if not os.path.exists(f"{T}/{d}/{e}.json"):
                spatial_episode(ep, f"{T}/{d}", v, root=T)
    except Exception as x:
        err = repr(x)
    return e, round(time.time() - t0, 1), err


if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from euv_test_download import episodes_test
    for d in ["series", "results", "spatial", "spatial_nf", "logs"]:
        os.makedirs(f"{T}/{d}", exist_ok=True)
    eps = episodes_test(); t0 = time.time(); log = f"{T}/logs/compute.log"; errs = []
    jobs = [dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai, noaa_ars=str(x.noaa_ars)) for x in eps.itertuples()]
    open(log, "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} compute start: {len(jobs)} episodes, workers {W}\n")
    with ProcessPoolExecutor(W) as pool:
        futs = [pool.submit(test_episode, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            e, s, err = f.result()
            if err:
                errs.append((e, err)); open(log, "a").write(f"ERROR {e}: {err}\n")
            if i % 25 == 0 or i == len(jobs):
                open(log, "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(jobs)} episodes, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    open(log, "a").write(f"compute done: {len(jobs)} episodes, {len(errs)} errors, wall {(time.time() - t0) / 3600:.2f} h, workers {W}\n")
    pd.DataFrame(errs, columns=["eid", "error"]).to_csv(f"{T}/compute_errors.csv", index=False)


# ================================================================ step 3: held-out tests (run ONCE)
def fit_folds(c, cols):
    """= euv_spatial.cv_fit (step 6 settings), also returning the 5 fold models."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from stage4_models import LR, K
    y, w, f = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.fold.to_numpy()
    p, ms = np.empty(len(c)), []
    for k in range(K):
        tr, te = f != k, f == k
        sc = StandardScaler().fit(c.loc[tr, cols])
        m = LogisticRegression(**LR).fit(sc.transform(c.loc[tr, cols]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]; ms.append((sc, m, cols))
    return ms, p


def predict(ms, c):
    return np.mean([m.predict_proba(sc.transform(c[cols]))[:, 1] for sc, m, cols in ms], axis=0)


def test_set(tc, mask):
    c = tc[mask].reset_index(drop=True).copy()
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
    return c


if __name__ == "__main__" and sys.argv[1:] == ["test"]:
    import joblib
    from concurrent.futures import ProcessPoolExecutor
    from sklearn.metrics import roc_auc_score
    from scipy.stats import spearmanr
    from phase_f import load_base, prep, boot_many, pct, op_stats, tau_keep, wlogloss, A_COLS
    t00 = time.time()
    # ---- test cohort + test EUV values
    tc = pd.read_csv("data/stage5/cohort_test_primary.csv", parse_dates=["t"])
    assert len(tc) == 313 and set(tc.t.dt.year) <= {2021, 2023, 2024}
    tc["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(tc.harpnum, tc.t)]
    num = ["primary_fill", "sens_fill", "primary_dCV", "sens_dCV", "max_frac_outside_valid"]
    rs = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{T}/results/*.json")])[["eid"] + num]
    rs[num] = rs[num].apply(pd.to_numeric, errors="coerce")
    sp = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{T}/spatial/*.json")])[["eid", "R4a", "R4c", "max_frame_mean_diff"]]
    nf = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{T}/spatial_nf/*.json")])[["eid", "R4a", "max_frame_mean_diff"]]
    assert (sp.max_frame_mean_diff < 1e-9).all() and (nf.max_frame_mean_diff < 1e-9).all()
    tc = tc.merge(rs, on="eid", how="left").merge(sp.drop(columns="max_frame_mean_diff"), on="eid", how="left") \
           .merge(nf.drop(columns="max_frame_mean_diff").rename(columns={"R4a": "R4a_nf"}), on="eid", how="left")
    tP, tS = tc.primary_fill >= 0.80, tc.sens_fill >= 0.80
    # ---- dev sets and fold models (checks: reproduce committed dev results)
    dv = load_base()
    dres = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{D}/results/*.json")])[["eid", "max_frac_outside_valid"]]
    dres["max_frac_outside_valid"] = pd.to_numeric(dres.max_frac_outside_valid, errors="coerce"); dv = dv.merge(dres, on="eid", how="left")
    s6 = pd.read_csv(f"{D}/step6/compare.csv").set_index("set")
    px = pd.read_csv(f"{D}/spatial/eval_compare.csv").set_index("candidate")
    nfc = pd.read_csv(f"{D}/spatial_nf/eval_nf_compare.csv")
    opd = pd.read_csv(f"{D}/spatial_nf/oppoint_dev.csv", float_precision="round_trip").set_index("model")
    f7 = pd.read_csv("data/phase_f/F7_summary.csv", float_precision="round_trip").set_index("candidate")

    def dev_models(mask, extra):
        c = prep(dv, mask); ma, pa = fit_folds(c, A_COLS); me, pe = fit_folds(c, A_COLS + extra)
        y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
        return c, ma, me, wlogloss(y, pa, w), wlogloss(y, pe, w), pa, pe
    saved = lambda tag: [(lambda d: (d["scaler"], d["model"], d["cols"]))(joblib.load(f"{D}/step6/models/{tag}_fold{k}.joblib")) for k in range(5)]
    M = {}
    for name, mask, dcol, tag in [("PRIMARY", dv.P & dv.primary_dCV.notna(), "primary_dCV", "PRIMARY"),
                                  ("S1", dv.S & dv.sens_dCV.notna(), "sens_dCV", "S1_flare_excluded")]:
        c, ma, me, la, le, _, _ = dev_models(mask, [dcol])
        sa, se = saved(f"{tag}_A"), saved(f"{tag}_E94")
        assert all(np.array_equal(a[1].coef_, b[1].coef_) and np.array_equal(a[1].intercept_, b[1].intercept_) for a, b in zip(ma, sa))
        assert all(np.array_equal(a[1].coef_, b[1].coef_) and np.array_equal(a[1].intercept_, b[1].intercept_) for a, b in zip(me, se))
        M[name] = (sa, se, dcol)
    c, ma, me, la, le, _, _ = dev_models(dv.P & dv.primary_dCV.notna() & ~(dv.max_frac_outside_valid > 0), ["primary_dCV"])
    assert abs(la - s6.loc["S2_primary_no_overhang", "logloss_A"]) < 1e-12 and abs(le - s6.loc["S2_primary_no_overhang", "logloss_E94"]) < 1e-12
    M["S2"] = (ma, me, "primary_dCV")
    c541, ma541, me_r4a, la, le, pa541, pe_r4a = dev_models(dv.P & dv.R4a.notna(), ["R4a"])
    assert abs(la - px.loc["R4a", "logloss_A"]) < 1e-12 and abs(le - px.loc["R4a", "logloss_A_plus"]) < 1e-12
    _, _, me_r4c, _, le_c, _, pe_r4c = dev_models(dv.P & dv.R4c.notna(), ["R4c"])
    assert abs(le_c - px.loc["R4c", "logloss_A_plus"]) < 1e-12
    c528, ma528, me_a528, la8, le8, pa528, pe_a528 = dev_models(dv.S & dv.R4a_nf.notna(), ["R4a"])
    _, _, me_nf528, _, lenf, _, pe_nf528 = dev_models(dv.S & dv.R4a_nf.notna(), ["R4a_nf"])
    assert abs(la8 - nfc.logloss_A[0]) < 1e-12 and abs(le8 - nfc.logloss_A_plus[0]) < 1e-12 and abs(lenf - nfc.logloss_A_plus[1]) < 1e-12
    y8, w8 = c528.true_alarm.to_numpy(), c528.weight.to_numpy(); y1, w1 = c541.true_alarm.to_numpy(), c541.weight.to_numpy()
    TAU = {"A528": tau_keep(pa528, y8, w8), "A+R4a": tau_keep(pe_a528, y8, w8), "A+R4a_nf": tau_keep(pe_nf528, y8, w8),
           "A541": tau_keep(pa541, y1, w1), "A+R4c": tau_keep(pe_r4c, y1, w1)}
    assert TAU["A528"] == opd.loc["A", "tau"] and TAU["A+R4a"] == opd.loc["A+R4a", "tau"] and TAU["A+R4a_nf"] == opd.loc["A+R4a_nf", "tau"]
    assert TAU["A541"] == f7.loc["R4c", "tau_A"] and TAU["A+R4c"] == f7.loc["R4c", "tau_Ax"]
    print("checks: dev fold models reproduce step 6 (saved PRIMARY/S1 models identical; S2 log-losses), Phase X R4a/R4c, "
          "the R4a flare check; frozen tau reproduced exactly: " + ", ".join(f"{k} {v:.6f}" for k, v in TAU.items()))
    print(f"test frame-mean checks (spatial vs series): max |diff| {max(sp.max_frame_mean_diff.max(), nf.max_frame_mean_diff.max()):.1e}")

    pool = ProcessPoolExecutor(W)

    def delta_test(name, c, ma, me, col_map=None):
        cc = c.copy()
        if col_map:
            for dst, src in col_map.items():
                cc[dst] = cc[src]
        pA, pE = predict(ma, cc), predict(me, cc)
        y, w, h = cc.true_alarm.to_numpy(), cc.weight.to_numpy(), cc.harpnum.to_numpy()
        groups = [np.where(h == v)[0] for v in np.unique(h)]
        B = boot_many({"d": ("dll", dict(y=y, w=w, pA=pA, pE=pE, groups=groups), 10000, 20260921)}, pool)["d"]
        lo, hi = pct(B); la, le = wlogloss(y, pA, w), wlogloss(y, pE, w)
        return dict(test=name, n=len(cc), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(groups), logloss_A=la, logloss_Ax=le,
                    delta=la - le, CI_lo=lo, CI_hi=hi, AUC_A=roc_auc_score(y, pA, sample_weight=w), AUC_Ax=roc_auc_score(y, pE, sample_weight=w)), pA, pE

    def op_test(name, c, pA, pE, tA, tE):
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
        kA, kE = pA >= tA, pE >= tE; groups = [np.where(h == v)[0] for v in np.unique(h)]
        B = np.array(boot_many({"o": ("op", dict(y=y, w=w, kept=[kA, kE], groups=groups), 2000, 0)}, pool)["o"], float)
        rows = []
        for mi, (lab, k, tau) in enumerate([("A", kA, tA), (name, kE, tE)]):
            tk, fr, pr = op_stats(y, w, k)
            rows.append(dict(model=lab, tau=tau, kept=int(k.sum()), true_kept_n=f"{int((k & (y == 1)).sum())}/{int(y.sum())}",
                             true_kept=tk, true_kept_CI="[%.4f, %.4f]" % pct(B[:, mi, 0]),
                             false_removed_n=f"{int((~k & (y == 0)).sum())}/{int((y == 0).sum())}", false_removed=fr,
                             false_removed_CI="[%.4f, %.4f]" % pct(B[:, mi, 1]), precision=pr, precision_CI="[%.4f, %.4f]" % pct(B[:, mi, 2]),
                             FAR=1 - pr, FAR_CI="[%.4f, %.4f]" % tuple(1 - np.array(pct(B[:, mi, 2]))[::-1])))
        d_fr = rows[1]["false_removed"] - rows[0]["false_removed"]; d_tk = rows[1]["true_kept"] - rows[0]["true_kept"]
        cfr, ctk = pct(B[:, 1, 1] - B[:, 0, 1]), pct(B[:, 1, 0] - B[:, 0, 0])
        return pd.DataFrame(rows), dict(test=name, n=len(c), d_false_removed=d_fr, d_fr_CI_lo=cfr[0], d_fr_CI_hi=cfr[1],
                                        d_true_kept=d_tk, d_tk_CI_lo=ctk[0], d_tk_CI_hi=ctk[1],
                                        d_fr_count=int((~kE & (y == 0)).sum()) - int((~kA & (y == 0)).sum()),
                                        d_tk_count=int((kE & (y == 1)).sum()) - int((kA & (y == 1)).sum()))

    def counts(mask, col):
        s = tc[mask]; u = tc[mask & tc[col].isna()] if col else tc.iloc[:0]
        return f"fill>=80%: {int(mask.sum())} (true {int(s.true_alarm.sum())} / false {int((s.true_alarm == 0).sum())})" + \
               (f"; excluded label-blind (undefined {col}): {len(u)} {u.eid.tolist()}" if col else "")

    out = {}
    fmt = lambda v: f"{v:.4f}"
    # ---- a. ΔCV (3283478 item 1h)
    print("\n=== a. ΔCV HELD-OUT TEST (3283478 item 1h): 2021/2023/2024, single-region T2 cohort; test prediction = mean of 5 dev fold models;"
          " delta = LL(A) - LL(E94), + = EUV helps; HARP bootstrap 10,000, seed 20260921")
    print("  primary:", counts(tP, "primary_dCV")); print("  S1     :", counts(tS, "sens_dCV"))
    rows = []
    for name, mask in [("PRIMARY", tP & tc.primary_dCV.notna()), ("S1", tS & tc.sens_dCV.notna()),
                       ("S2", tP & tc.primary_dCV.notna() & ~(tc.max_frac_outside_valid > 0))]:
        ma, me, dcol = M[name]; c = test_set(tc, mask)
        r, _, _ = delta_test(name, c, ma, me, {"dCV": dcol} if name != "S2" else {"primary_dCV": "primary_dCV"}); rows.append(r)
    print(f"  S2 excluded for overhang: {int((tP & tc.primary_dCV.notna() & (tc.max_frac_outside_valid > 0)).sum())}")
    out["a"] = pd.DataFrame(rows); print(out["a"].to_string(index=False, float_format=fmt))
    # ---- b. R4a
    print("\n=== b. R4a HELD-OUT TEST (f3d6489). PRIMARY A vs A+R4a (dev 541 models); SENSITIVITY A vs A+R4a_nf (dev 528 models)")
    print("  R4a primary:", counts(tP, "R4a")); print("  R4a_nf     :", counts(tS, "R4a_nf"))
    cP, cN = test_set(tc, tP & tc.R4a.notna()), test_set(tc, tS & tc.R4a_nf.notna())
    rP, _, _ = delta_test("PRIMARY A vs A+R4a", cP, ma541, me_r4a)
    rN, _, _ = delta_test("SENSITIVITY A vs A+R4a_nf", cN, ma528, me_nf528)
    out["b"] = pd.DataFrame([rP, rN]); print(out["b"].to_string(index=False, float_format=fmt))
    reading = ("adds information on held-out years" if rP["delta"] > 0 and rP["CI_lo"] > 0 else
               "direction consistent, not confirmed" if rP["delta"] > 0 else "not confirmed")
    print(f"  pre-stated reading (mechanical): PRIMARY delta {rP['delta']:.4f} [{rP['CI_lo']:.4f}, {rP['CI_hi']:.4f}] -> \"{reading}\"")
    print("\n  OPERATING-POINT TEST: frozen dev tau (528-set models), no re-tuning; weighted %, counts; HARP bootstrap 2,000, seed 0")
    op1, d1 = op_test("A+R4a", cP, predict(ma528, cP), predict(me_a528, cP), TAU["A528"], TAU["A+R4a"])
    op2, d2 = op_test("A+R4a_nf", cN, predict(ma528, cN), predict(me_nf528, cN), TAU["A528"], TAU["A+R4a_nf"])
    for lab, o in [("test R4a primary set", op1), ("test R4a_nf set", op2)]:
        print(f"  [{lab}]"); print(o.to_string(index=False, float_format=fmt))
    out["b_op"] = pd.concat([op1.assign(set="R4a primary"), op2.assign(set="R4a_nf")]); out["b_opd"] = pd.DataFrame([d1, d2])
    print(out["b_opd"].to_string(index=False, float_format=fmt))
    op_read = d1["d_false_removed"] > 0 and d1["d_fr_CI_lo"] > 0 and d1["d_true_kept"] >= -0.10
    print(f"  pre-stated reading (mechanical, A+R4a vs A): false-removed diff {d1['d_false_removed']:+.4f} [{d1['d_fr_CI_lo']:+.4f}, "
          f"{d1['d_fr_CI_hi']:+.4f}], true-kept diff {d1['d_true_kept']:+.4f} -> "
          f"{'removes more false alarms on held-out years' if op_read else 'condition not met'}")
    # ---- c. R4c secondary
    print("\n=== c. R4c SECONDARY (cannot upgrade the conclusion): A vs A+R4c (dev 541 models)")
    print("  R4c primary:", counts(tP, "R4c"))
    cC = test_set(tc, tP & tc.R4c.notna())
    rC, pAc, pEc = delta_test("A vs A+R4c", cC, ma541, me_r4c)
    out["c"] = pd.DataFrame([rC]); print(out["c"].to_string(index=False, float_format=fmt))
    op3, d3 = op_test("A+R4c", cC, pAc, pEc, TAU["A541"], TAU["A+R4c"])
    print(op3.to_string(index=False, float_format=fmt)); print(pd.DataFrame([d3]).to_string(index=False, float_format=fmt))
    out["c_op"] = op3; out["c_opd"] = pd.DataFrame([d3])
    # ---- d. descriptive
    r, p = spearmanr(cP.R4a, cP.n_C)
    print(f"\n=== d. DESCRIPTIVE: Spearman rho(R4a, n_C) on the test R4a primary set = {r:.4f} (p {p:.2e}, n {len(cP)})")
    pool.shutdown()
    os.makedirs(f"{T}/heldout", exist_ok=True)
    for k, v in out.items():
        v.to_csv(f"{T}/heldout/{k}.csv", index=False)
    print(f"\nwall {time.time() - t00:.1f} s, workers {W}")
