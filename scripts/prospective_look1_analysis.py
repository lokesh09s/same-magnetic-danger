"""LOOK 1 (EARLY) — compute, label-blind size rule, the single analysis run, and reproduction checks (code by Claude Code (AI)).
Registrations: daff479 (Look 1 early) with 2f62f88, eb3e7d5, bb8a137, d2ed360, 9a88d70/e17a8a3, 46207c7/b2ca7ac, 8aa1797/784b1a8, b480d22,
5a6d106 (dependence-free secondary DROPPED from Look 1). Open choices D1-D10: LOOK1_ANALYSIS_DECISIONS.md.
Only registered code is used: imported, or lifted verbatim where it exists only inline (each lifted block names its source lines).
Usage (repo root, .venv/bin/python), in this order:
  RUN_BY=<Lokesh|Kyros> python prospective_look1_analysis.py compute    8. label-blind: CV_box, CV6, BF(a), MR per Look 1 episode
  RUN_BY=<Lokesh|Kyros> python prospective_look1_analysis.py sizerule   9. label-blind size rule (once; nothing else may read labels first)
  RUN_BY=<Lokesh|Kyros> CONFIRM="run the prospective test once" python prospective_look1_analysis.py analysis  10. ONCE
  Reproduction checks (no prospective data): python prospective_look1_reproduce.py > prospective_look1_reproduce.log"""
import glob, hashlib, json, os, re, subprocess, sys, time, warnings
from datetime import datetime, timezone
import numpy as np, pandas as pd

ROOT, COH, LABF = "data/prospective_look1", "data/prospective_look1/cohort_le2.csv", "data/labelled_20260817_20260904.csv"
RUNLOG, AMEND, MIN_N = "prospective_look1_early.log", "daff479", 60
LO, HI = "2026-08-15", "2026-09-05 23:59"                     # SWPC window for Look 1 history features (only starts < t are used)
MR_RAW = ["data/raw_sharp_20260801_20260817.csv", "data/raw_sharp_20260817_20260901.csv", "data/raw_sharp_20260901_20260904.csv"]
MR_EXT = [p.replace("raw_sharp_", "raw_sharp_extra_") for p in MR_RAW]   # D6: the 2025-26 chunk supplies pre-08-17 window rows
MODEL_HASH_FILES = {"data/euv_extra/model_hashes.json": "d939ab6b530150fd0aef6842672c3410637b87a5d5f048cdcaa2484144f2e987",
                    "data/combo_t/model_hashes.json": "473e3eb7c475e1562022a4d1b0d7fa5a5ba7de555b73bd9098ebc617a14cf846"}
TIERS = [(0, 0.05, "<5%"), (0.05, 0.15, "5-15%"), (0.15, 0.30, "15-30%"), (0.30, 1.01, ">30%")]   # = posthoc_2026_09_28.TIERS
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
eid_of = lambda h, t: f"{h}_{t:%Y%m%dT%H%M}"
warnings.filterwarnings("ignore")


# ------------------------------------------------------------------ loaders (no label column unless the caller asks for it)
def load_cv(root, cohort, usecols=None):
    """= euv_confirm_tests.conf_cohort lines 19-23 (cohort + results merge, default float parser, cohort order kept), path as a parameter;
    the spatial R4a merge (line 24) is left out (not a Look 1 output). usecols=["harpnum", "t"] gives the label-blind version."""
    c = pd.read_csv(cohort, parse_dates=["t"]) if usecols is None else pd.read_csv(cohort, usecols=usecols, parse_dates=["t"])
    c["t"] = pd.to_datetime(c["t"])                             # no-op on a parsed column; keeps an EMPTY cohort's t a datetime
    c["eid"] = pd.Series([eid_of(h, t) for h, t in zip(c.harpnum, c.t)], index=c.index, dtype="str")   # pandas default text dtype, also when empty
    num = ["primary_fill", "primary_CV_box"]
    js = glob.glob(f"{root}/results/*.json")
    r = pd.DataFrame([json.load(open(p)) for p in js])[["eid"] + num] if js else pd.DataFrame(columns=["eid"] + num)
    r[num] = r[num].apply(pd.to_numeric, errors="coerce").astype(float); r["eid"] = r["eid"].astype("str")
    return c.merge(r, on="eid", how="left")


primary = lambda c: c[(c.primary_fill >= 0.80) & c.primary_CV_box.notna()].reset_index(drop=True)   # euv_confirm_tests.py:61


def episodes(cohort, labf):
    """= prospective_look1.episodes (label-blind): harpnum, t, noaa_ars, t_rec_tai, eid."""
    e = pd.read_csv(cohort, usecols=["harpnum", "t", "noaa_ars"], parse_dates=["t"])
    e["eid"] = pd.Series([eid_of(h, t) for h, t in zip(e.harpnum, e.t)], index=e.index, dtype="str")
    lab = pd.read_csv(labf, usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"], low_memory=False)
    e = e.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert e.t_rec_tai.notna().all()
    return e.sort_values(["harpnum", "t"]).reset_index(drop=True)


# ------------------------------------------------------------------ per-episode measures (label-blind)
def cv_episode(args):
    """= euv_confirm.confirm_episode (euv_confirm.py:113-126) without the spatial lines, root passed explicitly (spawn-safe)."""
    ep, root = args
    from euv_full import compute_episode
    h, e = ep["harpnum"], ep["eid"]; err = ""
    try:
        if not os.path.exists(f"{root}/results/{e}.json"):
            r = compute_episode(ep, f"{root}/hmi/{h}", f"{root}/aia/{h}", f"{root}/series")
            json.dump({k: str(v) for k, v in r.items()}, open(f"{root}/results/{e}.json", "w"))
    except Exception as x:
        err = repr(x)
    return e, err


def bf_cv6(ep, root):
    """CV6 = prospective_measures.cv6 on the stack's series (prospective_measures.episode:85); BF(a) = prospective_measures.py:172
    `k = int(round(2.4 / cdelt)); bf(blocks(V, shape, k), primary_fill)`. Nothing is written."""
    import prospective_measures as pm
    pm.R = root
    s, V, _, _, box_diff, cdelt, shape = pm.stack(ep)
    k = int(round(2.4 / cdelt)); Ba, kfa, whya = pm.bf(pm.blocks(V, shape, k), ep["primary_fill"])
    c6, f6 = pm.cv6(s, pd.Timestamp(ep["t"]))
    return dict(eid=ep["eid"], CV6=c6, fill6=f6, CV6_undefined="" if np.isfinite(c6) else "fill6", BF_a=Ba, BF_a_kept_frac=kfa,
                BF_a_undefined=whya, block_k=k, box_diff=box_diff)


def load_sharp_files(raw_f, ext_f, harps):
    """= mag_restless.load_sharp (mag_restless.py:38-59) with the chunk-file lists as parameters; body verbatim."""
    from astropy.time import Time
    import mag_restless as m
    raw = pd.concat([pd.read_csv(p, usecols=["HARPNUM", "T_REC", "QUALITY", "LON_FWT"] + m.P[:2] + m.OTHER, dtype={"T_REC": str})
                     for p in raw_f], ignore_index=True)
    ext = pd.concat([pd.read_csv(p, usecols=["HARPNUM", "T_REC", "TOTUSJZ"], dtype={"T_REC": str}) for p in ext_f], ignore_index=True)
    raw, ext = raw[raw.HARPNUM.isin(harps)], ext[ext.HARPNUM.isin(harps)]
    k = ["HARPNUM", "T_REC"]
    info = dict(raw_files=len(raw_f), extra_files=len(ext_f), raw_rows=len(raw), extra_rows=len(ext),
                raw_dup_keys=int(raw.duplicated(k).sum()), raw_dup_identical=int(raw.duplicated().sum()),
                extra_dup_keys=int(ext.duplicated(k).sum()), extra_dup_identical=int(ext.duplicated().sum()))
    raw, ext = raw.drop_duplicates(k), ext.drop_duplicates(k)
    d = raw.merge(ext, on=k, how="left", indicator=True)
    info["raw_without_extra"] = int((d._merge == "left_only").sum()); d = d.drop(columns="_merge")
    d["QUALITY"] = pd.to_numeric(d.QUALITY, errors="raise").astype(np.int64)
    u = pd.unique(d.T_REC)
    utc = pd.to_datetime(Time([s.replace("_TAI", "").replace(".", "-", 2).replace("_", " ") for s in u],
                              format="iso", scale="tai").utc.isot)
    d["t_utc"] = d.T_REC.map(dict(zip(u, utc)))
    d["tai_hour"] = d.T_REC.str[11:13].astype(int)
    return d.sort_values(["HARPNUM", "t_utc"]).reset_index(drop=True), info


def mr_rows(eps, raw_f, ext_f):
    """= mag_restless.compute (mag_restless.py:162-171) with the episode list and chunk files as parameters; per episode mag_restless.episode."""
    import mag_restless as m, swpc
    sharp, info = load_sharp_files(raw_f, ext_f, set(eps.harpnum))
    by = {h: g.reset_index(drop=True) for h, g in sharp.groupby("HARPNUM")}
    empty = sharp.iloc[:0]; rows = []
    for e in eps.itertuples():
        ev, _ = swpc.load(e.t - pd.Timedelta("2D"), e.t)
        rows.append(m.episode(e, by.get(e.harpnum, empty), ev))
    return pd.DataFrame(rows), sharp, info


# ------------------------------------------------------------------ statistics (registered code)
def ratio(label, cset, col, tw, pool, all_=True):
    """= euv_confirm_tests.ratio_block with the measure column as a parameter (phase_f.ratio_jobs + boot_many + pct; median true / median
    false; twins CI = pairs resampled by true HARP, 2,000, seed 0). D10: 0 pairs -> undefined, no bootstrap (sensitivity_combined.py:90).
    all_=False (Look 1): the all-episode ratio (TEST 1 s2; not registered for Look 1) is dropped and its bootstrap is not run."""
    from phase_f import ratio_jobs, boot_many, pct
    if len(tw) == 0:
        return dict(measure=label, pairs=0, ratio_twins=np.nan, tw_CI_lo=np.nan, tw_CI_hi=np.nan, note="undefined (0 pairs)")
    e, j = ratio_jobs(label, cset, col, "ratio", tw)
    if not all_:                                                # ratio_jobs computes the all-episode point estimates; drop them
        j = {k: v for k, v in j.items() if k[1] == "tw"}
        for k in ["n", "n_true", "n_false", "med_true", "med_false", "ratio_all"]:
            e.pop(k, None)
    if e["pairs"] == 0:
        return dict(e, tw_CI_lo=np.nan, tw_CI_hi=np.nan, note="undefined (0 pairs)")
    B = boot_many(j, pool)
    if all_:
        e["all_CI"] = "[%.4f, %.4f]" % pct(B[(label, "all")])
    e["tw_CI_lo"], e["tw_CI_hi"] = pct(B[(label, "tw")])
    return e


def reading(e):
    """euv_confirm_tests.py:66-67 logic with the registered prospective wording (2f62f88 / daff479); NaN -> 'NOT REPLICATED' (D10)."""
    r, lo = e.get("ratio_twins", np.nan), e.get("tw_CI_lo", np.nan)
    return "REPLICATED" if r > 1 and lo > 1 else "DIRECTION CONSISTENT, NOT CONFIRMED" if r > 1 else "NOT REPLICATED"


def sign(cset, col, tw):
    """= sensitivity_combined.py:92-96 (pairs with both values; ties excluded; two-sided binomial)."""
    from scipy.stats import binomtest
    if len(tw) == 0:
        return dict(pairs=0, true_higher=0, ties=0, sign_p=np.nan)
    v = cset.set_index("eid")[col]; p = tw.assign(xt=tw.true_eid.map(v), xf=tw.false_eid.map(v)).dropna(subset=["xt", "xf"])
    hi_, ties = int((p.xt > p.xf).sum()), int((p.xt == p.xf).sum())
    return dict(pairs=len(p), true_higher=hi_, ties=ties,
                sign_p=binomtest(hi_, len(p) - ties, 0.5, alternative="two-sided").pvalue if len(p) - ties else np.nan)


def reuse(c1, tw, pool, header, first_row="Step 1 flaring side only (true HARP; TEST 1)"):
    """= posthoc_twin_reuse.py:40-85 (POST-HOC region-reuse diagnostics), moved into a function; prints the same table.
    The Step 1 row is the TEST 1 code path on the same pairs (posthoc_twin_reuse.py:47-49)."""
    from phase_f import ratio_jobs, boot_many, med_ratio
    from posthoc_twin_reuse import components, summ, NB, SEED
    v = c1.set_index("eid").primary_CV_box
    xt, xf = tw.true_eid.map(v).to_numpy(float), tw.false_eid.map(v).to_numpy(float)
    assert np.isfinite(xt).all() and np.isfinite(xf).all()
    th, fh = tw.true_harp.to_numpy(), tw.false_harp.to_numpy()
    grp = lambda keys: [np.where(keys == k)[0] for k in pd.unique(keys)]
    e, j = ratio_jobs("TEST 1", c1, "primary_CV_box", "ratio", tw)
    B1 = boot_many({"s1": j[("TEST 1", "tw")]}, pool)["s1"]
    point = med_ratio(xt, xf, "ratio"); assert point == e["ratio_twins"]
    comp, members = components(th, fh)
    B = boot_many({"a": ("ratio_pairs", dict(xt=xt, xf=xf, mode="ratio", groups=grp(fh)), NB, SEED),
                   "c": ("ratio_pairs", dict(xt=xt, xf=xf, mode="ratio", groups=grp(comp)), NB, SEED)}, pool)
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
    for name, clusters, BB, skip in [(first_row, f"{len(T_)} true HARPs", B1, 0),
                                     ("(a) non-flaring side only (false HARP)", f"{len(F_)} false HARPs", B["a"], 0),
                                     ("(b) both sides (two-way, weights a_i * b_j)", f"{len(T_)} true x {len(F_)} false HARPs", Bb, skipped),
                                     ("(c) linked groups (connected components)", f"{len(members)} components", B["c"], 0)]:
        lo, hi, le, un = summ(BB)
        rows.append({"interval": name, "clusters": clusters, "ratio": f"{point:.4f}", "95% CI": f"[{lo:.4f}, {hi:.4f}]", "share ratio <= 1": f"{le:.4f}",
                     "resamples used": len(BB) - un, "skipped (zero weight)": skip, "undefined (non-finite)": un})
    T = pd.DataFrame(rows)
    both = sorted(int(x) for x in set(th) & set(fh))
    sizes = [dict(component=k + 1, HARPs=len(m), pairs=int((comp == k).sum()), members=" ".join(map(str, m))) for k, m in enumerate(members)]
    text = [header, *T.to_string(index=False).splitlines(), "",
            f"distinct HARPs: true {len(T_)}, false {len(F_)}, on both sides {len(both)} {both}, total {len(set(th) | set(fh))}",
            f"components: {len(members)}; sizes (HARPs / pairs), ordered by smallest HARP:", *pd.DataFrame(sizes).to_string(index=False).splitlines()]
    return T, text


# ------------------------------------------------------------------ frozen models, COMBO-T and C+
def frozen():
    """= euv_confirm_retest.load_models (hash-verified euv_extra A, A_CV, C, C_CV) + the COMBO-T loading of posthoc_2026_09_28.load_all."""
    import joblib
    from euv_confirm_retest import load_models
    for f, h in MODEL_HASH_FILES.items():                     # the hash lists themselves, pinned 2026-10-10
        if H(f) != h:
            sys.exit(f"Refusing to run: {f} changed")
    hs, TH, M = load_models()
    ht = json.load(open("data/combo_t/model_hashes.json"))
    if not all(H(f) == h for f, h in ht.items()):
        sys.exit("Refusing to run: COMBO-T files changed")
    TT = json.load(open("data/combo_t/thresholds.json"))
    MT = [(lambda d: (d["scaler"], d["model"], d["cols"]))(joblib.load(f"data/combo_t/models/COMBO_T_fold{k}.joblib")) for k in range(5)]
    return hs, TH, M, TT, MT


def evaluable(c, lo, hi):
    """= euv_confirm_retest.evaluable / descriptive_aia94.load_set (fill >= 0.80, CV_box finite and > 0, log10 CV_box, logR =
    euv_confirm_tests.log_r, weights 1/n per HARP within the set) + posthoc_2026_09_28.flare_features (prot12 = prot_12_2, anyCplus24)."""
    from euv_confirm_tests import log_r
    from posthoc_2026_09_28 import flare_features
    e = c[(c.primary_fill >= 0.80) & np.isfinite(c.primary_CV_box) & (c.primary_CV_box > 0)].reset_index(drop=True)
    if len(e) == 0:
        return e                                                # no evaluable episode: callers report it; nothing else runs
    e["log10_CV_box"] = np.log10(e.primary_CV_box)
    e["logR"] = log_r(e, pd.Timestamp(lo), pd.Timestamp(hi))
    e["weight"] = 1 / e.groupby("harpnum").harpnum.transform("size")
    e = e.merge(flare_features(e, lo, hi), on="eid", how="left", validate="one_to_one")
    e["prot12"] = e.prot_12_2
    return e


def counts(y, w, keep):
    """= posthoc_2026_09_28 counts() (simple and weighted)."""
    from phase_f import op_stats
    tk, fr, pr = op_stats(y, w, keep)
    return dict(true_kept=f"{int((keep & (y == 1)).sum())}/{int(y.sum())}", false_removed=f"{int((~keep & (y == 0)).sum())}/{int((y == 0).sum())}",
                true_kept_w=tk, false_removed_w=fr)


def filter_outputs(e, TH, M, TT, MT, pool, machinery=False):
    """COMBO-T outputs 1-3 (9a88d70) and C+ (8aa1797/784b1a8) on the evaluable set, plus the C vs C_CV machinery numbers (reproduction only).
    Bootstraps: dll = euv_confirm_retest.py:88-89 (10,000, seed 20260921); op = euv_confirm_retest.py:87 (2,000, seed 0) with the joint
    finite mask of :96-97 for COMBO-T (D7); C+ D intervals = posthoc_2026_09_28.py:367-374 (pct per difference) (D8)."""
    from euv_confirm_retest import pred
    from phase_f import boot_many, pct, wlogloss
    y, w, h = e.true_alarm.to_numpy(), e.weight.to_numpy(), e.harpnum.to_numpy(); groups = [np.where(h == v)[0] for v in np.unique(h)]
    pC, pCV, pT = pred(M["C"], e), pred(M["C_CV"], e), pred(MT, e)
    kC, kCV, kT = pC >= TH["C"]["tau"], pCV >= TH["C_CV"]["tau"], pT >= TT["tau"]
    kCp = kCV | e.anyCplus24.to_numpy()                         # C+ = C_CV keeps OR a C1.0+ start in (t-24h, t) (8aa1797)
    names = ["C", "T", "Cp"] + (["C_CV"] if machinery else [])  # resample draws do not depend on the kept list (phase_f.choices)
    kv = dict(C=kC, T=kT, Cp=kCp, C_CV=kCV)
    jobs = {"dT": ("dll", dict(y=y, w=w, pA=pC, pE=pT, groups=groups), 10000, 20260921),
            "op": ("op", dict(y=y, w=w, kept=[kv[n_] for n_ in names], groups=groups), 2000, 0)}
    if machinery:                                               # reproduction only: C vs C_CV (euv_confirm_filter_retest.log:14)
        jobs["dCV"] = ("dll", dict(y=y, w=w, pA=pC, pE=pCV, groups=groups), 10000, 20260921)
    B = boot_many(jobs, pool)
    op = np.array(B["op"], float)                               # resamples x names x (true kept, false removed, precision)
    ix = {n_: i for i, n_ in enumerate(names)}
    K = {n_: counts(y, w, kv[n_]) for n_ in names}

    def joint(ib, ia, name):                                    # euv_confirm_retest.py:93-97 (ib, ia = indices into names)
        dfb, dtb = op[:, ib, 1] - op[:, ia, 1], op[:, ib, 0] - op[:, ia, 0]; ok = np.isfinite(dfb) & np.isfinite(dtb)
        (fl, fh), (tl, th) = (np.percentile(dfb[ok], [2.5, 97.5]), np.percentile(dtb[ok], [2.5, 97.5])) if ok.any() else ((np.nan,) * 2, (np.nan,) * 2)
        a, b = K["C"], K[name]
        return dict(D_false_pts=100 * (b["false_removed_w"] - a["false_removed_w"]), D_false_lo=100 * fl, D_false_hi=100 * fh,
                    D_true_pts=100 * (b["true_kept_w"] - a["true_kept_w"]), D_true_lo=100 * tl, D_true_hi=100 * th, resamples_used=int(ok.sum()))
    tiers = []
    for lo_, hi_, tn in TIERS:                                  # posthoc_2026_09_28.py:416-419 (unweighted; D7)
        s_ = (pT >= lo_) & (pT < hi_)
        tiers.append(dict(tier=tn, n=int(s_.sum()), true=int(y[s_].sum()), mean_predicted=pT[s_].mean() if s_.any() else np.nan,
                          observed_rate=y[s_].mean() if s_.any() else np.nan))
    dT = wlogloss(y, pC, w) - wlogloss(y, pT, w)
    cp_t = 100 * np.array(pct(op[:, ix["Cp"], 0] - op[:, ix["C"], 0])); cp_f = 100 * np.array(pct(op[:, ix["Cp"], 1] - op[:, ix["C"], 1]))
    out = dict(n=len(e), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(groups), counts=K, pC=pC, pT=pT,
               LL=dict(C=wlogloss(y, pC, w), T=wlogloss(y, pT, w)),
               comboT_dll=dict(delta=dT, lo=pct(B["dT"])[0], hi=pct(B["dT"])[1]), comboT_D=joint(ix["T"], ix["C"], "T"), tiers=pd.DataFrame(tiers),
               cplus_D=dict(D_true_pts=100 * (K["Cp"]["true_kept_w"] - K["C"]["true_kept_w"]), D_true_CI=cp_t,
                            D_false_pts=100 * (K["Cp"]["false_removed_w"] - K["C"]["false_removed_w"]), D_false_CI=cp_f))
    if machinery:
        out["LL"]["C_CV"] = wlogloss(y, pCV, w)
        out["machinery"] = dict(dll=wlogloss(y, pC, w) - wlogloss(y, pCV, w), dll_lo=pct(B["dCV"])[0], dll_hi=pct(B["dCV"])[1],
                                **joint(ix["C_CV"], ix["C"], "C_CV"))
    return out


# ------------------------------------------------------------------ run control (order, run-once, logging)
D3_CLOCK = "TAI"          # D3a: "on 2026-08-17/18" = the TAI (T_REC) date of t (= cohort UTC t + 37 s). Decided by the user 2026-10-10.
REPRO_LOG = "prospective_look1_reproduce.log"
_GATED = False


def drop_days(t, clock):
    """b480d22 item 2: True for episodes whose t is on 2026-08-17 or 2026-08-18 on the chosen clock (cohort t is UTC = TAI - 37 s)."""
    d = (t + (pd.Timedelta("37s") if clock == "TAI" else pd.Timedelta(0))).dt.strftime("%Y-%m-%d")
    return d.isin(["2026-08-17", "2026-08-18"]), d


def closure_hash():
    """sha256 over the per-file sha256 of every local module the analysis uses, plus frozen/frozen_spec.json (caliper)."""
    files = local_closure("prospective_look1_analysis") + ["frozen/frozen_spec.json"]
    return hashlib.sha256("".join(f"{f}:{H(f)}\n" for f in files).encode()).hexdigest(), files


def guard_real(root, runlog):
    """The real Look 1 folder may only be used through the student command line (gate), with the real run log."""
    if os.path.abspath(root) == os.path.abspath(ROOT) and (not _GATED or os.path.abspath(runlog) != os.path.abspath(RUNLOG)):
        sys.exit("Refusing to run: data/prospective_look1 can only be used through the student command line (RUN_BY, gate).")
CONFIRM = "run the prospective test once"
STOP_WORDS = ["REPLICATED", "CONFIRMED", "BETTER PROBABILITIES", "NOT SHOWN", "READING:"]   # must not appear when TOO SMALL (D2)
f4 = lambda v: f"{v:.4f}" if v is not None and np.isfinite(v) else "nan"


def local_closure(start):
    """Local modules imported (at any depth, incl. inside functions) by `start` — the code the gate requires to be committed and unchanged."""
    import ast
    local = {f[:-3] for f in os.listdir(".") if f.endswith(".py")}
    seen, todo = set(), [start]
    while todo:
        m_ = todo.pop()
        if m_ in seen:
            continue
        seen.add(m_)
        for n in ast.walk(ast.parse(open(m_ + ".py").read())):
            if isinstance(n, ast.Import):
                todo += [a.name.split(".")[0] for a in n.names if a.name.split(".")[0] in local]
            elif isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in local:
                todo.append(n.module.split(".")[0])
    return sorted(f"{m_}.py" for m_ in seen)


def gate():
    """Student-run steps only: RUN_BY exact; daff479 in history; this script and every local module it uses committed and unchanged."""
    global _GATED
    who = os.environ.get("RUN_BY", "")
    if who not in ("Lokesh", "Kyros"):
        sys.exit('Refusing to run: RUN_BY must be exactly "Lokesh" or "Kyros".')
    if sys.flags.optimize:
        sys.exit("Refusing to run under python -O / PYTHONOPTIMIZE: integrity checks would be skipped.")
    if os.path.abspath(os.getcwd()) != os.path.dirname(os.path.abspath(__file__)):
        sys.exit("Refusing to run: run from the project folder that holds this script.")
    if subprocess.run(["git", "merge-base", "--is-ancestor", AMEND, "HEAD"]).returncode != 0:
        sys.exit(f"Refusing to run: the Look 1 amendment ({AMEND}) is not in this checkout.")
    ch, files = closure_hash()
    files = files + [REPRO_LOG]
    dirty = subprocess.run(["git", "status", "--porcelain", "--"] + files, capture_output=True, text=True).stdout.strip()
    untracked = [f for f in files if subprocess.run(["git", "ls-files", "--error-unmatch", f], capture_output=True).returncode != 0]
    if dirty or untracked:
        sys.exit(f"Refusing to run: code not committed or changed since the commit: {dirty.splitlines() + untracked}")
    txt = open(REPRO_LOG).read()
    if f"closure sha256 {ch}" not in txt or not re.search(r"RESULT: (\d+) of \1 checks PASS", txt):
        sys.exit("Refusing to run: this code is not the code that passed the committed reproduction checks (prospective_look1_reproduce.log).")
    _GATED = True
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    me = H(__file__)[:12]

    def logrun(msg):
        print(msg, flush=True)
        open(RUNLOG, "a").write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC | run by {who} | HEAD {head} | script {me} | "
                                f"{' '.join(sys.argv[1:])} | {msg}\n")
    return logrun


def hash_lines(paths, runlog=RUNLOG):
    for p in paths:
        if os.path.isfile(p):
            open(runlog, "a").write(f"    sha256 {H(p)}  {os.path.getsize(p):>11,d} B  {p}\n")


def key_hashes(root, coh):
    """Hashes of the cohort file and the compute outputs the size rule and the analysis read (fixed once compute succeeds)."""
    ps = [coh, f"{root}/measures.csv", f"{root}/mr.csv"] + sorted(glob.glob(f"{root}/results/*.json"))
    return {p: H(p) for p in ps if os.path.isfile(p)}


started = lambda runlog: os.path.exists(runlog) and "ANALYSIS START" in open(runlog).read()


def show(e):
    return (f"{e.get('pairs', 0)} pairs; median true {f4(e.get('twin_med_true', np.nan))}, median false {f4(e.get('twin_med_false', np.nan))}; "
            f"ratio {f4(e.get('ratio_twins', np.nan))} [{f4(e.get('tw_CI_lo', np.nan))}, {f4(e.get('tw_CI_hi', np.nan))}]" + (f" ({e['note']})" if e.get("note") else ""))


def compute_step(root, coh, labf, logrun):
    """Step 8, label-blind. Resumable (existing results are kept) until the size rule has run; then it refuses."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from phase_f import W
    guard_real(root, RUNLOG)
    if os.path.exists(f"{root}/sizerule.json") or os.path.exists(f"{root}/analysis_done.json") or started(RUNLOG):
        sys.exit("Refusing to run: the size rule or the analysis has already run; compute outputs are fixed.")
    if os.path.exists(f"{root}/compute_done.json"):
        os.remove(f"{root}/compute_done.json")                  # a new compute must succeed again before the size rule
    t0 = time.time()
    for d in ["series", "results"]:
        os.makedirs(f"{root}/{d}", exist_ok=True)
    eps = episodes(coh, labf)
    jobs = [(dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai, noaa_ars=str(x.noaa_ars)), root)
            for x in eps.itertuples() if os.path.isdir(f"{root}/aia/{int(x.harpnum)}")]
    errs = []
    with ProcessPoolExecutor(W) as pool:
        for f in as_completed([pool.submit(cv_episode, j) for j in jobs]):
            e_, err = f.result()
            if err:
                errs.append((e_, err))
    c = load_cv(root, coh, usecols=["harpnum", "t"])
    fill = dict(zip(c.eid, c.primary_fill)); rows = []
    for x in eps.itertuples():                                   # BF(a), CV6 (sequential; prospective_measures.R is a module global)
        if os.path.exists(f"{root}/series/{x.eid}.csv"):
            rows.append(bf_cv6(dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai, primary_fill=fill.get(x.eid, np.nan)), root))
        else:
            rows.append(dict(eid=x.eid, CV6=np.nan, CV6_undefined="no series", BF_a=np.nan, BF_a_undefined="no series"))
    meas = pd.DataFrame(rows, columns=list(dict.fromkeys(["eid", "CV6", "fill6", "CV6_undefined", "BF_a", "BF_a_kept_frac", "BF_a_undefined",
                                                           "block_k", "box_diff"])))
    meas.to_csv(f"{root}/measures.csv", index=False)
    mr, _, info = mr_rows(eps.assign(fold=-1, in541=False), MR_RAW, MR_EXT) if len(eps) else (pd.DataFrame(columns=["eid", "MR", "reason_MR"]), None, {})
    mr.to_csv(f"{root}/mr.csv", index=False)
    bad_k = int((meas.block_k.dropna() != 5).sum()); bad_box = int((meas.box_diff.fillna(0) >= 1e-9).sum())
    d1 = int(((c.primary_fill >= 0.80) & c.primary_CV_box.notna()).sum())
    logrun(f"COMPUTE (label-blind): episodes {len(eps)}; with AIA {len(jobs)}; CV_box compute errors {len(errs)} {errs[:3]}; "
           f"CV_box defined (fill >= 80%) {d1}; CV6 defined {int(meas.CV6.notna().sum())} {meas.CV6_undefined[meas.CV6.isna()].value_counts().to_dict()}; "
           f"BF(a) defined {int(meas.BF_a.notna().sum())} {meas.BF_a_undefined[meas.BF_a.isna()].value_counts().to_dict()}; block k != 5: {bad_k}; "
           f"box-mean check |diff| >= 1e-9: {bad_box}; MR defined {int(mr.MR.notna().sum())} {mr.reason_MR[mr.MR.isna()].value_counts().to_dict()}; "
           f"SHARP for MR {info}; wall {(time.time() - t0) / 60:.1f} min")
    if bad_box or bad_k or errs:
        logrun("STOP: a registered check failed (box-mean |diff| >= 1e-9 (bb8a137), block size != 5, or a compute error). "
               "compute_done.json NOT written; do not run the size rule; tell Claude Code.")
        sys.exit(1)
    kh = key_hashes(root, coh)
    json.dump(dict(hashes=kh, time_utc=f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}"), open(f"{root}/compute_done.json", "w"), indent=1)
    hash_lines(list(kh) + [f"{root}/compute_done.json"])


def sizerule_step(root, coh, runlog, logrun):
    """Step 9, label-blind, once: only after a successful compute, only before any analysis start."""
    guard_real(root, runlog)
    if os.path.exists(f"{root}/sizerule.json"):
        sys.exit("Refusing to run: the size rule has already been applied.")
    if os.path.exists(f"{root}/analysis_done.json") or started(runlog):
        sys.exit("Refusing to run: the analysis has already started.")
    if not os.path.exists(f"{root}/compute_done.json") or json.load(open(f"{root}/compute_done.json"))["hashes"] != key_hashes(root, coh):
        sys.exit("Refusing to run: compute has not finished successfully, or its outputs changed since (compute_done.json).")
    c = load_cv(root, coh, usecols=["harpnum", "t"])            # label-blind: no true_alarm / delayed column is read
    n = int(((c.primary_fill >= 0.80) & c.primary_CV_box.notna()).sum()); small = n < MIN_N
    json.dump(dict(n_cv_box_defined=n, n_episodes=len(c), too_small=small, rule="fewer than 60 episodes with CV_box defined (fill >= 80%)",
                   time_utc=f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}", run_by=os.environ.get("RUN_BY", "")),
              open(f"{root}/sizerule.json", "w"), indent=1)
    logrun(f"SIZE RULE (label-blind; 2f62f88, b480d22 item 3): {n} of {len(c)} episodes have CV_box defined (fill >= 80%) -> "
           + ('"TOO SMALL — DESCRIPTIVE ONLY": numbers given, no reading; the PRIMARY runs ONCE on the Look 2 set (b480d22 item 4)' if small
              else "at least 60: the PRIMARY gets its registered mechanical reading"))
    hash_lines([f"{root}/sizerule.json"], runlog)


def run_analysis(root, coh, lo, hi, runlog, logrun):
    """Step 10, RUN ONCE. Label-free checks first; then an exclusive marker and an 'ANALYSIS START' log line; then labels are read."""
    import swpc
    from concurrent.futures import ProcessPoolExecutor
    from phase_f import W
    from euv_f2_replication import twins
    # ---- label-free pre-checks (a failure here does NOT use up Look 1)
    guard_real(root, runlog)
    real = os.path.abspath(root) == os.path.abspath(ROOT)
    if D3_CLOCK not in ("UTC", "TAI"):
        sys.exit("Refusing to run: the D3a clock (UTC or TAI) has not been decided.")
    if real and subprocess.run(["git", "log", "--all", "--grep", "Look 1 ANALYSIS START", "--oneline"], capture_output=True, text=True).stdout.strip():
        sys.exit("Refusing to run: a 'Look 1 ANALYSIS START' commit already exists.")
    if os.path.exists(f"{root}/analysis_done.json") or started(runlog):
        sys.exit("Refusing to run: Look 1 runs once only (marker or 'ANALYSIS START' in the run log).")
    if not os.path.exists(f"{root}/sizerule.json"):
        sys.exit("Refusing to run: run the size rule first.")
    SR = json.load(open(f"{root}/sizerule.json"))
    if SR["too_small"] != (SR["n_cv_box_defined"] < MIN_N):
        sys.exit("Refusing to run: sizerule.json is inconsistent.")
    if not os.path.exists(f"{root}/compute_done.json") or json.load(open(f"{root}/compute_done.json"))["hashes"] != key_hashes(root, coh):
        sys.exit("Refusing to run: the cohort or the compute outputs changed since compute_done.json.")
    need = {"harpnum", "t", "score", "n_C", "n_M", "n_X", "noaa_ars", "true_alarm", "delayed"}
    if not need <= set(pd.read_csv(coh, nrows=0).columns):     # column names only (label-free)
        sys.exit(f"Refusing to run: cohort columns missing: {sorted(need - set(pd.read_csv(coh, nrows=0).columns))}")
    import scipy.stats, posthoc_2026_09_28, posthoc_twin_reuse      # noqa: F401 — import everything before the marker
    from euv_confirm_tests import log_r                              # noqa: F401
    cb = load_cv(root, coh, usecols=["harpnum", "t"])
    if int(((cb.primary_fill >= 0.80) & cb.primary_CV_box.notna()).sum()) != SR["n_cv_box_defined"]:
        sys.exit("Refusing to run: the label-blind recount differs from sizerule.json.")
    meas = pd.read_csv(f"{root}/measures.csv", float_precision="round_trip", dtype={"eid": "str", "CV6_undefined": "str"})
    mr = pd.read_csv(f"{root}/mr.csv", float_precision="round_trip", dtype={"eid": "str", "reason_MR": "str"})
    assert {"eid", "CV6", "CV6_undefined", "BF_a"} <= set(meas.columns) and {"eid", "MR", "reason_MR"} <= set(mr.columns)
    hs, TH, M, TT, MT = frozen()                                 # all frozen-file hash checks
    known404 = swpc.missing_days()
    gap = [f"{d:%Y-%m-%d}" for d in pd.date_range(pd.Timestamp(lo).normalize(), pd.Timestamp(hi).normalize())
           if not os.path.exists(f"data/swpc_events/{d:%Y%m%d}events.txt") and f"{d:%Y-%m-%d}" not in known404]
    if gap:
        sys.exit(f"Refusing to run: SWPC reports missing for {gap}.")
    small = SR["too_small"]
    # ---- run-once marker (exclusive create) and START line, then labels
    fd = os.open(f"{root}/analysis_done.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps(dict(started_utc=f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}", run_by=os.environ.get("RUN_BY", ""),
                                 script_sha256=H(__file__), confirm=os.environ.get("CONFIRM", ""))).encode()); os.close(fd)
    logrun(f"ANALYSIS START: labels are read from here on (sizerule.json sha256 {H(f'{root}/sizerule.json')[:12]}; cohort sha256 {H(coh)[:12]}; "
           f"script {H(__file__)[:12]}; D3 clock {D3_CLOCK})")
    if real:                                                    # durable trace in git BEFORE any label is read
        add = subprocess.run(["git", "add", "-f", RUNLOG], capture_output=True)
        com = subprocess.run(["git", "commit", "-q", "-m", f"Look 1 ANALYSIS START: run by {os.environ.get('RUN_BY', '')}, "
                              f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC (run log committed before any label is read)", "--", RUNLOG], capture_output=True)
        if add.returncode or com.returncode:
            logrun("ANALYSIS STOPPED BEFORE ANY LABEL WAS READ: the git commit of the START record failed; tell Claude Code")
            sys.exit(1)
    rep = f"{root}/analysis_report.txt"

    def say(line):                                              # written and flushed line by line
        print(line, flush=True)
        with open(rep, "a") as fh:
            fh.write(line + "\n")
    pool = ProcessPoolExecutor(W)
    try:
        t0 = time.time()
        c = load_cv(root, coh)                                  # labels from here on
        c1 = primary(c)
        if len(c1) != SR["n_cv_box_defined"]:
            raise RuntimeError("size-rule count differs")
        D = "DESCRIPTIVE ONLY (TOO SMALL), no reading" if small else None
        say(f"LOOK 1 (EARLY), t in [2026-08-17 00:00 TAI, 2026-09-03 23:00 TAI] — reported separately from the 2025-26 confirmation set and never pooled (daff479).")
        say(f"Size rule (label-blind): {SR['n_cv_box_defined']} of {SR['n_episodes']} episodes with CV_box defined (fill >= 80%) -> "
            + ("TOO SMALL — DESCRIPTIVE ONLY. All numbers below are descriptive and carry no reading; the PRIMARY runs ONCE on the Look 2 set, "
               "not before 2027-03-15 (b480d22 item 4)." if small else "at least 60: the PRIMARY gets its registered mechanical reading."))
        say("Twins CIs: percentile 95%, pairs resampled by true HARP, 2,000 resamples, seed 0 (phase_f.ratio_jobs / boot_many; TEST 1 code ae1b174). "
            "Dependence-free CV_box twins SECONDARY (5a6d106): DROPPED from Look 1 (daff479), not computed.")
        say(f"PRIMARY set: {len(c1)} episodes (true {int(c1.true_alarm.sum())}, false {int((c1.true_alarm == 0).sum())}; delayed {int(c1.delayed.sum())} "
            f"counted as false), HARPs {c1.harpnum.nunique()}")
        tw = twins(c1)[0]; tw_h = twins(c1, by_group=True)[0]
        P = ratio("PRIMARY CV_box twins", c1, "primary_CV_box", tw, pool, all_=False)
        say(f"PRIMARY (pre-registered{', descriptive only' if small else ''}): CV_box magnetic twins: {show(P)}; "
            f"max |score diff| {f4(tw.score_diff.abs().max()) if len(tw) else 'nan'}")
        if small:
            say(f"  PRIMARY: {D}")
        else:
            say(f"  READING: {reading(P)}")
            if not np.isfinite(P.get("ratio_twins", np.nan)):
                say("  FLAG (D10): the PRIMARY ratio is undefined; the registered reading has no undefined case; the TEST 1 code gives NOT REPLICATED.")
                logrun("FLAG (D10): PRIMARY ratio undefined; reading 'NOT REPLICATED' by the TEST 1 code")
        json.dump(dict(PRIMARY=P, reading=None if small else reading(P), sizerule=SR), open(f"{root}/analysis_primary.json", "w"), indent=1,
                  default=lambda v: v.tolist() if hasattr(v, "tolist") else str(v))
        cm = c1.merge(meas[["eid", "CV6", "BF_a"]], on="eid", how="left").merge(mr[["eid", "MR"]], on="eid", how="left")
        for col in ["CV6", "BF_a"]:
            cm[col] = cm[col].where(cm[col] > 0)                # D4: as prospective Step 2 (prospective_measures.py:338)
        cm["MR10"] = 10 ** cm.MR                                # MR on the linear scale (mag_restless step2 E1)
        say(f"SECONDARIES (pre-registered; {'DESCRIPTIVE ONLY (TOO SMALL)' if small else 'cannot change the PRIMARY reading'}); "
            "sign test two-sided, ties excluded (D5):")
        S = {}
        for name, col in [("CV_box", "primary_CV_box"), ("CV6", "CV6"), ("BF(a)", "BF_a")]:
            for tn, t_ in [("magnetic twins", tw), ("magnetic + flare-history twins", tw_h)]:
                e = P if (col == "primary_CV_box" and tn == "magnetic twins") else ratio(f"{name} {tn}", cm, col, t_, pool, all_=False)
                S[f"{name} | {tn}"] = dict(e, **{f"sign_{k}": v for k, v in sign(cm, col, t_).items()})
                say(f"  {name} | {tn}: {show(e)}; true > false {S[f'{name} | {tn}']['sign_true_higher']} of {S[f'{name} | {tn}']['sign_pairs']} "
                    f"(ties {S[f'{name} | {tn}']['sign_ties']}), sign-test p {f4(S[f'{name} | {tn}']['sign_sign_p'])}")
        c6 = c[["eid", "true_alarm"]].merge(meas[["eid", "CV6", "CV6_undefined"]], on="eid", how="left")
        c6["why"] = np.where(c6.CV6.isna(), c6.CV6_undefined.fillna("no value"), np.where(c6.CV6 <= 0, "<= 0", ""))
        u6 = lambda d: {g: int(((d.why != "") & (d.true_alarm == g)).sum()) for g in (1, 0)}
        p6 = c6[c6.eid.isin(c1.eid)]
        say(f"  CV6 undefined by true/false (313c1c0): all {len(c6)} episodes: true {u6(c6)[1]}, false {u6(c6)[0]} "
            f"{c6.why[c6.why != ''].value_counts().to_dict()}; PRIMARY set: true {u6(p6)[1]}, false {u6(p6)[0]}")
        drop, day = drop_days(c1.t, D3_CLOCK)
        c1x = c1[~drop].reset_index(drop=True)
        X = ratio("PRIMARY without 2026-08-17/18", c1x, "primary_CV_box", twins(c1x)[0], pool, all_=False)
        say(f"  PRIMARY without episodes on 2026-08-17/18 ({D3_CLOCK} date of t; removed {day[drop].value_counts().sort_index().to_dict()}; "
            f"twins re-matched; b480d22 item 2, D3): {len(c1x)} episodes; {show(X)}; " + (f"{D}" if small else f"READING: {reading(X)}"))
        M_ = ratio("MR magnetic twins", cm, "MR10", tw, pool, all_=False)
        mall = c[["eid", "true_alarm"]].merge(mr[["eid", "MR"]], on="eid", how="left")
        und = lambda d: f"true {int((d.MR.isna() & (d.true_alarm == 1)).sum())}, false {int((d.MR.isna() & (d.true_alarm == 0)).sum())}"
        say(f"  MR twins ratio median(10^MR true) / median(10^MR false), reported only (46207c7, b2ca7ac): {show(M_)}; MR undefined: "
            f"all {len(mall)} episodes {und(mall)}; PRIMARY set {und(cm)}")
        e = evaluable(c, lo, hi); F = filter_outputs(e, TH, M, TT, MT, pool) if len(e) else None
        if F:
            say(f"COMBO-T and C+ ({'DESCRIPTIVE ONLY (TOO SMALL)' if small else 'secondary'}; set fill >= 80%, CV_box > 0, weights 1/n per HARP): "
                f"{F['n']} episodes (true {F['true']}, false {F['false']}), HARPs {F['HARPs']}; label code vs stored true_alarm mismatches "
                f"{int((e.pos.to_numpy() != e.true_alarm.to_numpy()).sum())}; frozen hashes verified ({len(hs)} euv_extra files + COMBO-T)")
            d = F["comboT_dll"]
            say(f"  COMBO-T (1) delta log-loss LL(Model C) - LL(COMBO-T) = {f4(d['delta'])} [{f4(d['lo'])}, {f4(d['hi'])}] (HARP bootstrap 10,000, "
                f"seed 20260921)" + (" — descriptive only" if small else f"; descriptive reading: {'BETTER PROBABILITIES' if d['lo'] > 0 else 'NOT SHOWN'}"))
            say("  COMBO-T (2) reliability (unweighted):\n" + "\n".join("    " + l for l in F["tiers"].to_string(index=False, float_format=f4).splitlines()))
            D_ = F["comboT_D"]; K = F["counts"]
            say(f"  COMBO-T (3) at tau: COMBO-T true kept {K['T']['true_kept']}, false removed {K['T']['false_removed']}; Model C {K['C']['true_kept']}, "
                f"{K['C']['false_removed']}; D_true {D_['D_true_pts']:+.2f} pts [{D_['D_true_lo']:+.2f}, {D_['D_true_hi']:+.2f}], D_false {D_['D_false_pts']:+.2f} "
                f"[{D_['D_false_lo']:+.2f}, {D_['D_false_hi']:+.2f}] (paired HARP bootstrap 2,000, seed 0; resamples used {D_['resamples_used']})")
            cp = F["cplus_D"]
            say(f"  C+ rule, descriptive only, no reading (8aa1797; exact thresholds 784b1a8): C+ true kept {K['Cp']['true_kept']}, false removed "
                f"{K['Cp']['false_removed']}; D_true {cp['D_true_pts']:+.1f} pts [{cp['D_true_CI'][0]:+.1f}, {cp['D_true_CI'][1]:+.1f}], D_false "
                f"{cp['D_false_pts']:+.1f} [{cp['D_false_CI'][0]:+.1f}, {cp['D_false_CI'][1]:+.1f}] (C+ minus Model C; paired HARP bootstrap 2,000, seed 0)")
        else:
            say("COMBO-T and C+: no evaluable episode (fill >= 80% and CV_box > 0)")
        for name, t_ in [("twins_primary", tw), ("twins_history", tw_h)]:
            t_.to_csv(f"{root}/{name}.csv", index=False)
        res = dict(sizerule=SR, PRIMARY=P, reading=None if small else reading(P), secondaries=S, excl_0817_0818=X, MR=M_, D3_clock=D3_CLOCK,
                   comboT=None if not F else dict(dll=F["comboT_dll"], D=F["comboT_D"], counts={k: F["counts"][k] for k in ["C", "T"]},
                                                  tiers=F["tiers"].to_dict("records")),
                   cplus=None if not F else dict(counts=F["counts"]["Cp"], D=F["cplus_D"]))
        json.dump(res, open(f"{root}/analysis_results.json", "w"), indent=1, default=lambda v: v.tolist() if hasattr(v, "tolist") else str(v))
        if len(tw) >= 2:
            _, rtext = reuse(c1, tw, pool, f"POST-HOC region-reuse diagnostics on the {len(tw)} Look 1 PRIMARY pairs (same code as posthoc_twin_reuse.py; "
                             "2,000 resamples, seed 0; percentile 95% CI; D9)", first_row="Look 1 PRIMARY flaring side (true HARP)")
            for l in rtext:
                say(l)
        else:
            say("POST-HOC region-reuse diagnostics: skipped (fewer than 2 pairs; D9)")
        if small:
            hit = [w_ for w_ in STOP_WORDS if w_ in open(rep).read()]
            if hit:
                raise RuntimeError(f"reading wording printed under TOO SMALL: {hit}")
        logrun(f"ANALYSIS DONE (run once): report {rep}; wall {(time.time() - t0) / 60:.1f} min")
        hash_lines([rep, f"{root}/analysis_primary.json", f"{root}/analysis_results.json", f"{root}/twins_primary.csv", f"{root}/twins_history.csv"], runlog)
    except BaseException as x:
        logrun(f"ANALYSIS FAILED after labels were read: {type(x).__name__} (no values logged); Look 1 is used up; report what exists")
        raise
    finally:
        pool.shutdown()


if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    compute_step(ROOT, COH, LABF, gate())
elif __name__ == "__main__" and sys.argv[1:] == ["sizerule"]:
    sizerule_step(ROOT, COH, RUNLOG, gate())
elif __name__ == "__main__" and sys.argv[1:] == ["analysis"]:
    lr = gate()
    if os.environ.get("CONFIRM", "") != CONFIRM:
        sys.exit(f'Refusing to run: set CONFIRM="{CONFIRM}" (the students\' registered command).')
    run_analysis(ROOT, COH, LO, HI, RUNLOG, lr)
elif __name__ == "__main__":
    sys.exit(__doc__)
