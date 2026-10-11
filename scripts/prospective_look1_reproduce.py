"""Reproduction checks for prospective_look1_analysis.py (code by Claude Code (AI)). NO PROSPECTIVE DATA: only data/euv_confirm (2025-26,
already analysed; every SWPC window ends at 2026-08-16 23:59, before the prospective reports) and dev 2010-19 files.
Each check runs the SAME functions the Look 1 run uses and compares them with logged values (file:line given).
Usage: python prospective_look1_reproduce.py > prospective_look1_reproduce.log"""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import prospective_look1_analysis as A

RES = []


def check(name, ok, detail):
    RES.append(bool(ok)); print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}", flush=True)


if __name__ == "__main__":
    t0 = time.time()
    from phase_f import W, load_base, prep, wlogloss, tau_keep
    from euv_f2_replication import twins
    import euv_confirm_tests as ect
    pool = ProcessPoolExecutor(W)
    rt = lambda p: pd.read_csv(p, float_precision="round_trip")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("REPRODUCTION CHECKS for prospective_look1_analysis.py — no prospective data; 2025-26 (data/euv_confirm) and dev 2010-19 only")
    print(f"code under test: prospective_look1_analysis.py sha256 {A.H('prospective_look1_analysis.py')}; this script sha256 "
          f"{A.H('prospective_look1_reproduce.py')}; git HEAD {head}")
    print(f"closure sha256 {A.closure_hash()[0]}  (local modules used by the analysis + frozen/frozen_spec.json; the gate requires this line)")

    # ---- 1. TEST 1 (ae1b174): loader, size-rule count, twins, PRIMARY, s1, reading, sign tests, 08-17/18 no-op
    T = "data/euv_confirm"; COH = f"{T}/cohort_le2.csv"
    c = A.load_cv(T, COH)
    ref = ect.conf_cohort("le2").drop(columns="R4a")
    try:
        pd.testing.assert_frame_equal(c, ref); same = True
    except AssertionError:
        same = False
    check("loader = euv_confirm_tests.conf_cohort('le2') (minus R4a)", same, f"{len(c)} rows")
    cb = A.load_cv(T, COH, usecols=["harpnum", "t"])
    n_blind = int(((cb.primary_fill >= 0.80) & cb.primary_CV_box.notna()).sum())
    check("label-blind size-rule count (usecols harpnum, t)", n_blind == 378, f"{n_blind} (euv_confirm_tests.log:2: 378)")
    c1 = A.primary(c)
    check("PRIMARY set", (len(c1), int(c1.true_alarm.sum()), int((c1.true_alarm == 0).sum()), c1.harpnum.nunique()) == (378, 56, 322, 101),
          f"{len(c1)} episodes, true {int(c1.true_alarm.sum())}, false {int((c1.true_alarm == 0).sum())}, HARPs {c1.harpnum.nunique()}")
    tw, nt = twins(c1); st = rt(f"{T}/twins_le2.csv")
    check("twins = stored data/euv_confirm/twins_le2.csv", len(tw) == 50 and nt == 56 and (tw[["true_eid", "false_eid", "true_harp", "false_harp", "group"]]
          .reset_index(drop=True).equals(st[["true_eid", "false_eid", "true_harp", "false_harp", "group"]])) and np.allclose(tw.score_diff, st.score_diff, rtol=0, atol=1e-15),
          f"{len(tw)} pairs of {nt} true; max |score diff| {tw.score_diff.abs().max():.4f}; groups {tw.group.value_counts().to_dict()}")
    R1 = rt(f"{T}/test1_ratios.csv")
    P = A.ratio("PRIMARY", c1, "primary_CV_box", tw, pool); r0 = R1.iloc[0]
    exact = all(P[k] == r0[k] for k in ["ratio_twins", "tw_CI_lo", "tw_CI_hi", "twin_med_true", "twin_med_false", "pairs"]) and P["all_CI"] == r0.all_CI
    check("PRIMARY ratio and CI (full precision = test1_ratios.csv row 0)", exact,
          f"{P['ratio_twins']:.4f} [{P['tw_CI_lo']:.4f}, {P['tw_CI_hi']:.4f}], {P['pairs']} pairs (euv_confirm_tests.log:10: 3.2624 [1.2956, 9.4887])")
    Pf = A.ratio("PRIMARY", c1, "primary_CV_box", tw, pool, all_=False)
    check("Look 1 path ratio(all_=False) = reproduced PRIMARY; no all-episode values kept",
          all(Pf[k] == P[k] for k in ["ratio_twins", "tw_CI_lo", "tw_CI_hi", "pairs", "twin_med_true", "twin_med_false"]) and "ratio_all" not in Pf and "all_CI" not in Pf,
          f"{Pf['ratio_twins']:.4f} [{Pf['tw_CI_lo']:.4f}, {Pf['tw_CI_hi']:.4f}]")
    tz = pd.Series(pd.to_datetime(["2026-08-16 23:59:23", "2026-08-17 12:59:23", "2026-08-18 23:59:23", "2026-08-19 12:59:23"]))
    mu, mt = A.drop_days(tz, "UTC")[0].tolist(), A.drop_days(tz, "TAI")[0].tolist()
    check("D3a clocks at the boundaries (t = 08-16 23:59:23, 08-17 12:59:23, 08-18 23:59:23, 08-19 12:59:23 UTC)",
          mu == [False, True, True, False] and mt == [True, True, False, False], f"UTC drops {mu}; TAI drops {mt}")
    check("PRIMARY mechanical reading", A.reading(P) == "REPLICATED", f"'{A.reading(P)}' (euv_confirm_tests.log:10: REPLICATED)")
    tw_h = twins(c1, by_group=True)[0]; S1 = A.ratio("s1", c1, "primary_CV_box", tw_h, pool); r1 = R1.iloc[1]
    check("history-matched twins (full precision = test1_ratios.csv row 1)",
          all(S1[k] == r1[k] for k in ["ratio_twins", "tw_CI_lo", "tw_CI_hi", "twin_med_true", "twin_med_false", "pairs"]),
          f"{S1['ratio_twins']:.4f} [{S1['tw_CI_lo']:.4f}, {S1['tw_CI_hi']:.4f}], {S1['pairs']} pairs (euv_confirm_tests.log:6: 2.8174 [1.0169, 6.8227], 47)")
    s_a, s_b = A.sign(c1, "primary_CV_box", tw), A.sign(c1, "primary_CV_box", tw_h)
    check("sign test, PRIMARY pairs", (s_a["true_higher"], s_a["ties"], s_a["pairs"]) == (39, 0, 50) and abs(s_a["sign_p"] - 9.021490107130603e-05) < 1e-15,
          f"{s_a['true_higher']}/{s_a['pairs']}, ties {s_a['ties']}, p {s_a['sign_p']:.6g} (sensitivity_combined.log:16: 39, 0, 0.0001)")
    check("sign test, history-matched pairs", (s_b["true_higher"], s_b["ties"], s_b["pairs"]) == (35, 0, 47) and abs(s_b["sign_p"] - 0.00108853820647425) < 1e-15,
          f"{s_b['true_higher']}/{s_b['pairs']}, ties {s_b['ties']}, p {s_b['sign_p']:.6g} (sensitivity_combined.log:21: 35, 0, 0.0011)")
    day = c1.t.dt.strftime("%Y-%m-%d"); c1x = c1[~day.isin(["2026-08-17", "2026-08-18"])].reset_index(drop=True)
    X = A.ratio("excl", c1x, "primary_CV_box", twins(c1x)[0], pool)
    check("08-17/18 secondary is a no-op on 2025-26 (= PRIMARY exactly)", len(c1x) == 378 and all(X[k] == P[k] for k in ["ratio_twins", "tw_CI_lo", "tw_CI_hi", "pairs"]),
          f"{len(c1x)} episodes; {X['ratio_twins']:.4f} [{X['tw_CI_lo']:.4f}, {X['tw_CI_hi']:.4f}]")

    # ---- 2. region reuse (7c9b7bb): printed table, HARP counts and components = posthoc_twin_reuse.log lines 3-16
    _, text = A.reuse(c1, tw, pool, "POST-HOC (7c9b7bb): 50 TEST 1 pairs; median true CV_box / median false CV_box; 2,000 resamples, seed 0; percentile 95% CI")
    log = open("posthoc_twin_reuse.log").read().splitlines()[2:16]
    check("region reuse output = posthoc_twin_reuse.log lines 3-16 (byte-identical)", text == log,
          "intervals (a) [1.4764, 8.9395], (b) [0.8632, 12.2290], (c) [0.6812, 18.8683]; HARPs 18/41/8/51; 4 components" if text == log else
          "first difference: " + next((f"line {i + 3}: {a!r} vs {b!r}" for i, (a, b) in enumerate(zip(text, log)) if a != b), f"lengths {len(text)} vs {len(log)}"))

    # ---- 3. frozen models, COMBO-T outputs, C+ and the shared bootstrap machinery on 2025-26 (SWPC windows end 2026-08-16 23:59)
    hs, TH, M, TT, MT = A.frozen()
    check("frozen thresholds are the exact values (784b1a8)", TH["C"]["tau"] == 0.06256983158392139 and TH["C_CV"]["tau"] == 0.06893616544608924 and TT["tau"] == 0.07921511827656076,
          f"tau_C {TH['C']['tau']!r}, tau_C_CV {TH['C_CV']['tau']!r}, tau_COMBO-T {TT['tau']!r}; {len(hs)} euv_extra files hash-verified")
    e = A.evaluable(c, "2024-12-27", "2026-08-16 23:59")
    check("COMBO-T / C+ evaluable set", (len(e), e.harpnum.nunique()) == (378, 101), f"{len(e)} episodes, {e.harpnum.nunique()} HARPs (retest_checks: 378 / 101)")
    F = A.filter_outputs(e, TH, M, TT, MT, pool, machinery=True); K = F["counts"]
    F0 = A.filter_outputs(e, TH, M, TT, MT, pool)              # the Look 1 path (no C_CV machinery)
    same = F0["comboT_dll"] == F["comboT_dll"] and F0["comboT_D"] == F["comboT_D"] and all(F0["counts"][k] == F["counts"][k] for k in ["C", "T", "Cp"]) and \
        all(np.array_equal(F0["cplus_D"][k], F["cplus_D"][k]) for k in F["cplus_D"]) and "C_CV" not in F0["counts"] and "machinery" not in F0
    check("Look 1 path filter_outputs(machinery=False) = reproduced path for COMBO-T and C+; no C_CV results kept", same, "identical")
    mc = rt(f"{T}/retest_models.csv").set_index("model")
    for m_, k_ in [("C", "C"), ("C_CV", "C_CV")]:
        ok = K[k_]["true_kept"] == mc.loc[m_, "true_kept"] and K[k_]["false_removed"] == mc.loc[m_, "false_removed"] and \
            K[k_]["true_kept_w"] == mc.loc[m_, "true_kept_w"] and K[k_]["false_removed_w"] == mc.loc[m_, "false_removed_w"] and F["LL"][k_] == mc.loc[m_, "logloss"]
        check(f"Model {m_} at frozen tau (= retest_models.csv, full precision)", ok, f"true kept {K[k_]['true_kept']}, false removed {K[k_]['false_removed']}, "
              f"w {K[k_]['true_kept_w']:.4f} / {K[k_]['false_removed_w']:.4f}, LL {F['LL'][k_]:.4f}")
    cm_ = rt(f"{T}/retest_comparisons.csv").set_index("comparison").loc["C vs C_CV"]; mm = F["machinery"]
    ok = all(mm[k] == cm_[k] for k in ["D_false_pts", "D_false_lo", "D_false_hi", "D_true_pts", "D_true_lo", "D_true_hi", "resamples_used"]) and \
        (mm["dll"], mm["dll_lo"], mm["dll_hi"]) == (cm_.dlogloss, cm_.dlogloss_lo, cm_.dlogloss_hi)
    check("bootstrap machinery: C vs C_CV (= retest_comparisons.csv, full precision; used for COMBO-T outputs 1 and 3)", ok,
          f"dLL {mm['dll']:.4f} [{mm['dll_lo']:.4f}, {mm['dll_hi']:.4f}]; D_false {mm['D_false_pts']:+.4f} [{mm['D_false_lo']:+.4f}, {mm['D_false_hi']:+.4f}]; "
          f"D_true {mm['D_true_pts']:+.4f} [{mm['D_true_lo']:+.4f}, {mm['D_true_hi']:+.4f}] (euv_confirm_filter_retest.log:14)")
    ok = (K["T"]["true_kept"], K["T"]["false_removed"], round(K["T"]["true_kept_w"], 4), round(K["T"]["false_removed_w"], 4), round(F["LL"]["T"], 4)) == \
        ("40/56", "210/322", 0.7820, 0.6278, 0.3602)
    check("COMBO-T on 2025-26 (docs/posthoc_2026-09-28.md:486)", ok, f"true kept {K['T']['true_kept']}, false removed {K['T']['false_removed']}, "
          f"w {K['T']['true_kept_w']:.4f} / {K['T']['false_removed_w']:.4f}, LL {F['LL']['T']:.4f}")
    tiers = [(r.tier, r.n, r.true, round(r.mean_predicted, 4), round(r.observed_rate, 4)) for r in F["tiers"].itertuples()]
    want = [("<5%", 102, 0, 0.0385, 0.0), ("5-15%", 225, 31, 0.0818, 0.1378), ("15-30%", 35, 15, 0.1885, 0.4286), (">30%", 16, 10, 0.6339, 0.625)]
    check("COMBO-T reliability tiers (docs/posthoc_2026-09-28.md:512-515)", tiers == want, f"{tiers}")
    rej = sorted(e.eid[(e.true_alarm == 1).to_numpy() & (F["pT"] < TT["tau"])])
    check("COMBO-T rejected true alarms (docs/posthoc_2026-09-28.md:109: 16)", len(rej) == 16, f"{len(rej)}: {rej[:3]} ...")
    cp = F["cplus_D"]; ok = (K["Cp"]["true_kept"], K["Cp"]["false_removed"], round(K["Cp"]["true_kept_w"], 4), round(K["Cp"]["false_removed_w"], 4)) == ("52/56", "125/322", 0.9129, 0.3891) \
        and f"{cp['D_true_pts']:.1f} [{cp['D_true_CI'][0]:+.1f}, {cp['D_true_CI'][1]:+.1f}]" == "-1.3 [-3.7, +0.0]" \
        and f"{cp['D_false_pts']:.1f} [{cp['D_false_CI'][0]:+.1f}, {cp['D_false_CI'][1]:+.1f}]" == "7.9 [+0.7, +15.5]"
    check("C+ rule on 2025-26 (docs/posthoc_2026-09-28.md:26, 367)", ok, f"true kept {K['Cp']['true_kept']}, false removed {K['Cp']['false_removed']}, "
          f"w {K['Cp']['true_kept_w']:.4f} / {K['Cp']['false_removed_w']:.4f}; D_true {cp['D_true_pts']:.1f} [{cp['D_true_CI'][0]:+.1f}, {cp['D_true_CI'][1]:+.1f}], "
          f"D_false {cp['D_false_pts']:.1f} [{cp['D_false_CI'][0]:+.1f}, {cp['D_false_CI'][1]:+.1f}]")
    from posthoc_2026_09_28 import oof, flare_features, WIN
    from euv_confirm_tests import log_r
    dv = load_base(); cd = prep(dv, dv.P & np.isfinite(dv.primary_CV_box) & (dv.primary_CV_box > 0))
    cd["logR"] = log_r(cd, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59")); cd["log10_CV_box"] = np.log10(cd.primary_CV_box)
    cd = cd.merge(flare_features(cd, *WIN["dev"]), on="eid", how="left", validate="one_to_one"); cd["prot12"] = cd.prot_12_2
    pT = oof(MT, cd); yd, wd = cd.true_alarm.to_numpy(), cd.weight.to_numpy()
    check("COMBO-T frozen dev OOF (combo_t_freeze.log:6; thresholds.json)", wlogloss(yd, pT, wd) == TT["dev_oof_logloss"] and tau_keep(pT, yd, wd) == TT["tau"],
          f"LL {wlogloss(yd, pT, wd)!r} (frozen {TT['dev_oof_logloss']!r}); tau {tau_keep(pT, yd, wd)!r}")

    # ---- 4. CV6 and BF(a): registered never to be computed on 2025-26 (decisions.md:5198) -> dev only
    import prospective_measures as pm
    dvv, nv = rt("data/prospective/dev_values.csv"), rt("data/prospective/noise_values.csv")
    deps = pm.dev_eps().set_index("eid")
    for eid in ["71_20100630T0359", "6975_20170329T1559"]:
        x = deps.loc[eid]
        r = A.bf_cv6(dict(eid=eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai, primary_fill=float(x.primary_fill)), "data/euv_full")
        w6, wb = dvv.set_index("eid").loc[eid, "CV6"], nv.set_index("eid").loc[eid, "BF_a"]
        check(f"CV6 and BF(a) recomputed for dev {eid}", r["CV6"] == w6 and r["BF_a"] == wb and r["block_k"] == 5 and r["box_diff"] < 1e-9,
              f"CV6 {r['CV6']!r} (stored {w6!r}); BF(a) {r['BF_a']!r} (stored {wb!r}); k {r['block_k']}; box diff {r['box_diff']:.1e}")
    dv2 = load_base().merge(nv[["eid", "BF_a"]], on="eid", how="left").merge(dvv[["eid", "CV6"]], on="eid", how="left")
    dv2["CV_box"] = np.where(dv2.P & (dv2.primary_CV_box > 0), dv2.primary_CV_box, np.nan)
    tw6 = pd.read_csv("data/euv_full/step6/twins_PRIMARY.csv")
    for name, col, want in [("BF(a)", "BF_a", "81, 1.2125 [1.1048, 1.3194]"), ("CV6", "CV6", "69, 2.1261 [1.2479, 3.3090]"), ("CV_box", "CV_box", "81, 1.9661 [1.4737, 3.1731]")]:
        e_ = A.ratio(name, dv2.assign(**{col: dv2[col].where(dv2[col] > 0)}), col, tw6, pool)
        got = f"{e_['pairs']}, {e_['ratio_twins']:.4f} [{e_['tw_CI_lo']:.4f}, {e_['tw_CI_hi']:.4f}]"
        check(f"dev twins ratio {name} (prospective_step2.log)", got == want, f"{got} (logged {want})")

    # ---- 5. MR: registered never to be computed on 2025-26 (decisions.md:6025) -> dev only
    import mag_restless as m, chunks
    eps = m.load_episodes()
    raw_f = [p for a, p in chunks.files("raw_sharp") if a < m.DEV_END]; ext_f = [p for a, p in chunks.files("raw_sharp_extra") if a < m.DEV_END]
    s_ref, i_ref = m.load_sharp(set(eps.harpnum)); s_new, i_new = A.load_sharp_files(raw_f, ext_f, set(eps.harpnum))
    check("MR SHARP loader = mag_restless.load_sharp (dev)", s_new.equals(s_ref) and i_new == i_ref, f"{len(s_new)} records, {s_new.HARPNUM.nunique()} HARPs; {i_new}")
    mr, _, _ = A.mr_rows(eps, raw_f, ext_f)
    ref = rt("data/mag_restless/dev_mr.csv"); cols = [k for k in ref.columns if k in mr.columns]
    buf = io.StringIO(); mr[cols].to_csv(buf, index=False); buf.seek(0); mine = pd.read_csv(buf, float_precision="round_trip")
    try:
        pd.testing.assert_frame_equal(mine, ref[cols]); same = True
    except AssertionError as err:
        same = False; print(str(err)[:400])
    check("MR per episode (dev 547) = data/mag_restless/dev_mr.csv", same and len(cols) == len(ref.columns), f"{len(mine)} episodes, {len(cols)} of {len(ref.columns)} columns compared")
    dm = load_base().merge(ref[["eid", "MR"]], on="eid", how="left", validate="1:1")
    cm = prep(dm, dm.P & np.isfinite(dm.primary_CV_box) & (dm.primary_CV_box > 0)); cm["MR10"] = 10 ** cm.MR
    e1 = A.ratio("MR T_a", cm, "MR10", twins(cm)[0], pool)
    got = f"{e1['pairs']}, {e1['ratio_twins']:.4f} [{e1['tw_CI_lo']:.4f}, {e1['tw_CI_hi']:.4f}]"
    check("dev MR magnetic twins E1 T_a (mag_restless_eval.log:8)", got == "81, 1.0814 [0.9193, 1.3109]", f"{got} (logged 81, 1.0814 [0.9193, 1.3109])")
    # ---- 6. end-to-end smoke tests on SYNTHETIC random labels (standing rule: never real labels shuffled): 2025-26 keys, scores, flare
    #         history and real CV_box results (label-free); synthetic CV6, BF(a), MR; scratch dirs outside the repo
    full = pd.read_csv(COH)
    keys = full.apply(lambda r: f"{r.harpnum}_{pd.Timestamp(r.t):%Y%m%dT%H%M}", axis=1)
    SCR = lambda: (lambda msg: None)

    def build(n, clock):
        A.D3_CLOCK = clock
        tmp = tempfile.mkdtemp(prefix=f"look1_smoke_{n}_"); root = f"{tmp}/root"; os.makedirs(f"{root}/results")
        rng = np.random.RandomState(20261009 + n)
        sub = full[keys.isin(set(c1.eid))].head(n) if n < 387 else full.copy()
        sub = sub.assign(true_alarm=(rng.rand(len(sub)) < 0.15).astype(int), delayed=0, delayed_followup_incomplete=0)
        coh = f"{root}/cohort_le2.csv"; sub.to_csv(coh, index=False)
        ids = [f"{h}_{pd.Timestamp(t):%Y%m%dT%H%M}" for h, t in zip(sub.harpnum, sub.t)]
        for i_ in ids:
            if os.path.exists(f"{T}/results/{i_}.json"):
                shutil.copy(f"{T}/results/{i_}.json", f"{root}/results/{i_}.json")
        cv6 = rng.lognormal(-2.5, 0.8, len(ids)); cv6[::7] = np.nan
        pd.DataFrame(dict(eid=ids, CV6=cv6, fill6=1.0, CV6_undefined=np.where(np.isnan(cv6), "fill6", ""), BF_a=rng.uniform(0.2, 0.6, len(ids)),
                          BF_a_kept_frac=1.0, BF_a_undefined="", block_k=5, box_diff=0.0)).to_csv(f"{root}/measures.csv", index=False)
        pd.DataFrame(dict(eid=ids, MR=rng.normal(-1.45, 0.2, len(ids)), reason_MR="")).to_csv(f"{root}/mr.csv", index=False)
        json.dump(dict(hashes=A.key_hashes(root, coh)), open(f"{root}/compute_done.json", "w"))
        runlog = f"{tmp}/run.log"
        return tmp, root, coh, runlog, (lambda msg, rl=runlog: open(rl, "a").write(msg + "\n"))

    def refused(f_, *args):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                f_(*args)
            return False
        except SystemExit:
            return True
    WIN2526 = ("2024-12-27", "2026-08-16 23:59")
    for n, clock in [(0, "TAI"), (1, "UTC"), (12, "TAI"), (59, "TAI"), (387, "UTC")]:
        tmp, root, coh, runlog, lr = build(n, clock); ok, why = True, ""
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                A.sizerule_step(root, coh, runlog, lr)
                small = json.load(open(f"{root}/sizerule.json"))["too_small"]
                A.run_analysis(root, coh, *WIN2526, runlog, lr)
            rep, log_ = open(f"{root}/analysis_report.txt").read(), open(runlog).read()
            prs = json.load(open(f"{root}/analysis_primary.json"))["PRIMARY"]["pairs"]
            hit = [w_ for w_ in A.STOP_WORDS if w_ in rep]
            if small and hit:
                ok, why = False, f"reading words under TOO SMALL: {hit}"
            if not small and not any(f"READING: {r_}" in rep for r_ in ["REPLICATED", "DIRECTION CONSISTENT, NOT CONFIRMED", "NOT REPLICATED"]):
                ok, why = False, "no PRIMARY reading although the size rule passed"
            if not ("ANALYSIS START" in log_ and "ANALYSIS DONE" in log_ and f"D3 clock {clock}" in log_):
                ok, why = False, "START/DONE/clock missing from the run log"
            if not (refused(A.run_analysis, root, coh, *WIN2526, runlog, lr) and refused(A.sizerule_step, root, coh, runlog, lr)
                    and refused(A.compute_step, root, coh, "unused", lr)):
                ok, why = False, "a second analysis, size rule or compute was not refused"
        except Exception as x:
            ok, why = False, f"crashed: {type(x).__name__}: {str(x)[:200]}"
        check(f"smoke test, synthetic labels, {n} episodes, D3 clock {clock}", ok, why or f"too_small={small}, PRIMARY pairs {prs}; completed; "
              + ("no reading wording anywhere" if small else "PRIMARY reading printed") + "; second analysis / size rule / compute refused")
        shutil.rmtree(tmp)
    # failure after labels: FAILED logged, registered results kept, re-run refused
    tmp, root, coh, runlog, lr = build(40, "TAI"); real_reuse = A.reuse
    A.reuse = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("injected"))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            A.sizerule_step(root, coh, runlog, lr)
            A.run_analysis(root, coh, *WIN2526, runlog, lr)
        ok, why = False, "the injected failure did not propagate"
    except RuntimeError:
        log_ = open(runlog).read()
        ok = "ANALYSIS FAILED" in log_ and os.path.exists(f"{root}/analysis_results.json") and refused(A.run_analysis, root, coh, *WIN2526, runlog, lr)
        why = "" if ok else "FAILED line, saved results or refusal missing"
    finally:
        A.reuse = real_reuse
    check("failure after labels (injected in the post-hoc block)", ok, why or "ANALYSIS FAILED logged (no values); registered results already saved; re-run refused")
    shutil.rmtree(tmp)
    # label-free refusals leave no marker; marker-only and START-only both refuse
    tmp, root, coh, runlog, lr = build(12, "TAI")
    with contextlib.redirect_stdout(io.StringIO()):
        A.sizerule_step(root, coh, runlog, lr)
    sr = json.load(open(f"{root}/sizerule.json")); sr["too_small"] = not sr["too_small"]; json.dump(sr, open(f"{root}/sizerule.json", "w"))
    r1 = refused(A.run_analysis, root, coh, *WIN2526, runlog, lr) and not os.path.exists(f"{root}/analysis_done.json") and \
        "ANALYSIS START" not in (open(runlog).read() if os.path.exists(runlog) else "")
    sr["too_small"] = not sr["too_small"]; json.dump(sr, open(f"{root}/sizerule.json", "w"))
    A.D3_CLOCK = None; r2 = refused(A.run_analysis, root, coh, *WIN2526, runlog, lr) and not os.path.exists(f"{root}/analysis_done.json"); A.D3_CLOCK = "TAI"
    open(f"{root}/analysis_done.json", "w").write("{}"); r3 = refused(A.run_analysis, root, coh, *WIN2526, runlog, lr); os.remove(f"{root}/analysis_done.json")
    open(runlog, "a").write("x | ANALYSIS START: test\n"); r4 = refused(A.run_analysis, root, coh, *WIN2526, runlog, lr)
    check("label-free refusals: inconsistent sizerule.json and undecided D3 leave no marker; marker-only and START-only both refuse",
          r1 and r2 and r3 and r4, f"inconsistent sizerule {r1}, D3 undecided {r2}, marker only {r3}, START only {r4}")
    shutil.rmtree(tmp)
    lr0 = lambda msg: None
    g = [refused(A.run_analysis, A.ROOT, A.COH, A.LO, A.HI, A.RUNLOG, lr0), refused(A.sizerule_step, A.ROOT, A.COH, A.RUNLOG, lr0),
         refused(A.compute_step, A.ROOT, A.COH, A.LABF, lr0)]
    check("direct calls on the real Look 1 folder are refused without the student gate (nothing read)", all(g), f"analysis/sizerule/compute refused: {g}")
    pool.shutdown()
    print(f"\nRESULT: {sum(RES)} of {len(RES)} checks PASS" + ("" if all(RES) else " — FAILURES ABOVE") + f"; wall {(time.time() - t0) / 60:.1f} min, workers {W}")
    sys.exit(0 if all(RES) else 1)
