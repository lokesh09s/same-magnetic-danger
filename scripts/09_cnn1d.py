"""Candidate #28 SMALL 1D-CNN ON THE 94 A LIGHT CURVE (CNN1D) -- decisions.md 2026-09-30 (fdf044d, amendment 8630b46). EXPLORATORY (dev).
Everything is #27 (minirocket.py, unchanged and imported) except the curve model:
  Conv1d(1,8,7,same) -> ReLU -> MaxPool1d(2) -> Conv1d(8,16,5,same) -> ReLU -> global average pool -> Dropout(0.3) -> Linear(16,1) -> sigmoid
  (737 parameters); weighted BCE (sum w*l / sum w, episode weights), Adam lr 1e-3 weight_decay 1e-3, batch 32, max 200 epochs,
  early stopping on 20% of the training HARPs (GroupShuffleSplit, run seed), patience 20, best weights restored; no refit, no search.
Usage: python cnn1d.py step1 <scratch dir outside the repo>   label-blind checks + crash test on SYNTHETIC labels (scratch deleted)
       python cnn1d.py step2                                  dev evaluation E1-E5, run once (reads the real labels)"""
import copy, hashlib, json, os, shutil, sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from minirocket import base_frame, build_curves, logit, wll, CCV, CLIP, SEED, E4_SEEDS, NSLOT, OUT as MR_OUT

OUT = "data/cnn1d"
MAX_EPOCHS, PATIENCE, BATCH, LR_, WD, VAL = 200, 20, 32, 1e-3, 1e-3, 0.2
warnings.filterwarnings("ignore")
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def make_net():
    import torch.nn as nn
    return nn.Sequential(nn.Conv1d(1, 8, 7, padding="same"), nn.ReLU(), nn.MaxPool1d(2), nn.Conv1d(8, 16, 5, padding="same"), nn.ReLU(),
                         nn.AdaptiveAvgPool1d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(16, 1))


def _det(seed):
    import torch
    torch.manual_seed(seed); np.random.seed(seed); torch.use_deterministic_algorithms(True); torch.set_num_threads(1)


def _wbce(net, X, y, w):
    """weighted BCE sum(w*l)/sum(w) in eval mode (float64 on the logits)."""
    import torch
    net.eval()
    with torch.no_grad():
        z = net(X).squeeze(1).double()
    l = torch.nn.functional.binary_cross_entropy_with_logits(z, y.double(), reduction="none")
    return float((w.double() * l).sum() / w.double().sum())


def fit_curve(X, y, w, h, seed):
    """Train one network on 80% of the training HARPs, early-stop on the other 20%. -> dict(state, best_epoch, epochs, train_loss, val_loss)."""
    import torch
    from sklearn.model_selection import GroupShuffleSplit
    _det(seed)
    itr, iva = next(GroupShuffleSplit(n_splits=1, test_size=VAL, random_state=seed).split(X, y, h))
    T = lambda a: torch.as_tensor(np.ascontiguousarray(a), dtype=torch.float32)
    Xtr, ytr, wtr, Xva, yva, wva = T(X[itr]), T(y[itr]), T(w[itr]), T(X[iva]), T(y[iva]), T(w[iva])
    net = make_net(); opt = torch.optim.Adam(net.parameters(), lr=LR_, weight_decay=WD)
    gen = torch.Generator().manual_seed(seed)
    best, best_state, best_epoch, wait, epoch = np.inf, None, 0, 0, 0
    for epoch in range(1, MAX_EPOCHS + 1):
        net.train()
        for b in torch.randperm(len(itr), generator=gen).split(BATCH):
            opt.zero_grad()
            l = torch.nn.functional.binary_cross_entropy_with_logits(net(Xtr[b]).squeeze(1), ytr[b], reduction="none")
            ((wtr[b] * l).sum() / wtr[b].sum()).backward(); opt.step()
        v = _wbce(net, Xva, yva, wva)
        if v < best:
            best, best_state, best_epoch, wait = v, copy.deepcopy(net.state_dict()), epoch, 0
        else:
            wait += 1
            if wait >= PATIENCE:
                break
    net.load_state_dict(best_state)
    return dict(state=best_state, best_epoch=best_epoch, epochs=epoch, train_loss=_wbce(net, Xtr, ytr, wtr), val_loss=best)


def predict_curve(m, X):
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    net = make_net(); net.load_state_dict(m["state"]); net.eval()
    with torch.no_grad():
        return torch.sigmoid(net(torch.as_tensor(np.ascontiguousarray(X), dtype=torch.float32)).squeeze(1)).double().numpy()


def outer_fold(job):
    """= minirocket.outer_fold with the CNN as the curve model: (a) inner OOF scores, (b) stacker, (c) outer network -> fold-k predictions."""
    from threadpoolctl import threadpool_limits
    from sklearn.model_selection import GroupKFold
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from stage4_models import LR
    k, seed, X, y, w, h, fold, CC, keep_models = job
    t0 = time.time()
    with threadpool_limits(1):
        iO, iT = np.where(fold != k)[0], np.where(fold == k)[0]
        s_in, inner = np.full(len(iO), np.nan), []
        for tr, te in GroupKFold(n_splits=5).split(iO, y[iO], h[iO]):
            m = fit_curve(X[iO[tr]], y[iO[tr]], w[iO[tr]], h[iO[tr]], seed); s_in[te] = predict_curve(m, X[iO[te]])
            inner.append({q: m[q] for q in ("best_epoch", "epochs", "train_loss", "val_loss")})
        Z = np.column_stack([CC[iO], logit(s_in)])
        sc = StandardScaler().fit(Z); st = LogisticRegression(**LR).fit(sc.transform(Z), y[iO], sample_weight=w[iO])
        m = fit_curve(X[iO], y[iO], w[iO], h[iO], seed)
        sT = predict_curve(m, X[iT])
        pT = st.predict_proba(sc.transform(np.column_stack([CC[iT], logit(sT)])))[:, 1]
    out = dict(k=k, seed=seed, idx=iT, p=pT, curve=sT, secs=time.time() - t0, inner=inner,
               outer={q: m[q] for q in ("best_epoch", "epochs", "train_loss", "val_loss")},
               stacker_coef=dict(zip(CCV + ["logit_curve"], st.coef_[0])))
    if keep_models:
        out["models"] = dict(state=m["state"], stack_scaler=sc, stacker=st)
    return out


def run_pipeline(c, X, y, seeds, keep_seed=None, workers=None):
    """= minirocket.run_pipeline with this module's outer_fold."""
    from phase_f import W
    w, h, fold, CC = c.weight.to_numpy(), c.harpnum.to_numpy(), c.fold.to_numpy(), c[CCV].to_numpy(float)
    jobs = [(k, s, X, y, w, h, fold, CC, s == keep_seed) for s in seeds for k in range(5)]
    res = {s: dict(p=np.full(len(c), np.nan), curve=np.full(len(c), np.nan), folds=[]) for s in seeds}
    with ProcessPoolExecutor(workers or W) as pool:
        for r in pool.map(outer_fold, jobs):
            R = res[r["seed"]]; R["p"][r["idx"]] = r["p"]; R["curve"][r["idx"]] = r["curve"]; R["folds"].append(r)
    for s, R in res.items():
        assert np.isfinite(R["p"]).all() and np.isfinite(R["curve"]).all(), f"seed {s}: missing OOF predictions"
        R["folds"].sort(key=lambda r: r["k"])
    return res


def evaluate(c, res, synthetic=False):
    """E1-E4 exactly as minirocket.evaluate (same computations; the MiniRocket-only lines replaced by E5)."""
    from sklearn.metrics import roc_auc_score
    from scipy.stats import binomtest, spearmanr
    from phase_f import tau_keep, op_stats, boot_many, ratio_jobs, pct, W, NB_D, SEED_D, NB_R, SEED_R
    from euv_heldout import fit_folds
    from euv_f2_replication import twins
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    groups = [np.where(h == v)[0] for v in np.unique(h)]
    _, pB = fit_folds(c, CCV)
    _, pV = fit_folds(c, ["log10_CV_box"])
    R = res[SEED]; pS = R["p"]
    jobs = {("dll", s): ("dll", dict(y=y, w=w, pA=pB, pE=res[s]["p"], groups=groups), NB_D, SEED_D) for s in res}
    kept, e2 = [], []
    for keep in (0.88, 0.95):
        tB, tS = tau_keep(pB, y, w, keep), tau_keep(pS, y, w, keep); kB, kS = pB >= tB, pS >= tS; kept += [kB, kS]
        e2.append((keep, tB, tS, op_stats(y, w, kB), op_stats(y, w, kS), (int((kB & (y == 1)).sum()), int((~kB & (y == 0)).sum())),
                   (int((kS & (y == 1)).sum()), int((~kS & (y == 0)).sum()))))
    jobs["E2"] = ("op", dict(y=y, w=w, kept=kept, groups=groups), NB_R, SEED_R)
    cc = c.assign(curve=R["curve"]); T = {"T_a": twins(cc)[0], "T_b": twins(cc, by_group=True)[0]}; e3 = []
    for tn, tw in T.items():
        e, j = ratio_jobs(f"curve {tn}", cc, "curve", "ratio", tw); jobs.update(j)
        v = cc.set_index("eid").curve; xt, xf = tw.true_eid.map(v), tw.false_eid.map(v)
        up, dn = int((xt > xf).sum()), int((xt < xf).sum())
        e.update(twins=tn, true_higher=up, false_higher=dn, ties=len(tw) - up - dn, sign_p=binomtest(up, up + dn, 0.5).pvalue if up + dn else np.nan)
        e3.append(e)
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    rho = {v: spearmanr(R["curve"], c[v]) for v in ["log10_CV_box", "n_C", "logR", "score"]}
    auc = lambda p: roc_auc_score(y, p, sample_weight=w)
    L = []                                                              # report lines; printed only for real labels
    pr = L.append
    f4 = lambda v: f"{v:.4f}"
    llB = wll(y, pB, w)
    pr(f"\n== E1 PRIMARY (CNN seed {SEED}): Δ = LL(C_CV) − LL(C_CV + curve) (+ = curve helps); HARP bootstrap {NB_D}, seed {SEED_D}")
    lo, hi = pct(B[("dll", SEED)]); d1 = llB - wll(y, pS, w)
    pr(f"  LL(C_CV) {llB:.4f}, LL(C_CV + curve) {wll(y, pS, w):.4f}; Δ {d1:+.4f} [{lo:+.4f}, {hi:+.4f}]; weighted AUC {auc(pB):.4f} -> {auc(pS):.4f}")
    co = pd.DataFrame([dict(fold=r["k"], **r["stacker_coef"]) for r in R["folds"]])
    pr("  stacker coefficients per outer fold (per 1 SD, training-fold StandardScaler):")
    pr(co.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    op = np.array(B["E2"], float)
    pr(f"\n== E2 MATCHED RETENTION: dev OOF tau per model (tau_keep); weighted; paired HARP bootstrap {NB_R}, seed {SEED_R}")
    for i, (keep, tB, tS, sB, sS, nB, nS) in enumerate(e2):
        d = op[:, 2 * i + 1, 1] - op[:, 2 * i, 1]
        pr(f"  target {keep:.2f}: C_CV tau {tB:.6f} true kept {nB[0]}/{int(y.sum())} ({sB[0]:.4f} w), false removed {nB[1]}/{int((y == 0).sum())} "
           f"({sB[1]:.4f} w) | C_CV + curve tau {tS:.6f} true kept {nS[0]}/{int(y.sum())} ({sS[0]:.4f} w), false removed {nS[1]}/{int((y == 0).sum())} ({sS[1]:.4f} w)")
        pr(f"     false removed (C_CV + curve − C_CV): {(sS[1] - sB[1]) * 100:+.2f} points [{np.nanpercentile(d, 2.5) * 100:+.2f}, {np.nanpercentile(d, 97.5) * 100:+.2f}]")
    pr("\n== E3 DESCRIPTIVE")
    pr(f"  curve-score-only OOF weighted AUC {auc(R['curve']):.4f}; CV_box-only OOF weighted AUC (fit_folds on log10_CV_box) {auc(pV):.4f}")
    R3 = pd.DataFrame(e3); R3["tw_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "tw")]) for m in R3.measure]; R3["all_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "all")]) for m in R3.measure]
    pr(f"  curve-score twins (T_a = twins(c), T_b = twins(c, by_group=True); ratio_jobs mode 'ratio' on the OOF curve score; CI pairs by true HARP {NB_R}, seed {SEED_R})")
    pr(R3[["twins", "pairs", "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI", "true_higher", "false_higher", "ties", "sign_p", "ratio_all", "all_CI"]]
       .to_string(index=False, float_format=f4))
    for v, (r_, p_) in rho.items():
        pr(f"  Spearman rho(curve score, {v}) = {r_:.4f} (p {p_:.2e}, n {len(c)})")
    pr(f"\n== E4 STABILITY: E1 with CNN seed in {E4_SEEDS} (the seed drives initialisation, batch order, dropout and the 20% split; primary stays {SEED})")
    for s in [SEED] + E4_SEEDS:
        lo_, hi_ = pct(B[("dll", s)]); d = llB - wll(y, res[s]["p"], w)
        pr(f"  seed {s}: LL(C_CV + curve) {wll(y, res[s]['p'], w):.4f}; Δ {d:+.4f} [{lo_:+.4f}, {hi_:+.4f}]; AUC {auc(res[s]['p']):.4f}")
    pr(f"\n== E5 TRAINING (descriptive; seed {SEED}): weighted BCE at the restored best epoch, eval mode; train = the 80% fitted part, val = the 20% early-stopping part")
    pr(pd.DataFrame([dict(outer_fold=r["k"], **r["outer"]) for r in R["folds"]]).to_string(index=False, float_format=f4))
    allb = [r["outer"]["best_epoch"] for r in R["folds"]] + [x["best_epoch"] for r in R["folds"] for x in r["inner"]]
    pr(f"  mean best epoch over all 30 networks (5 outer + 25 inner): {np.mean(allb):.2f} (min {min(allb)}, max {max(allb)}); "
       f"networks stopped by patience: {sum(x['epochs'] < MAX_EPOCHS for r in R['folds'] for x in [r['outer']] + r['inner'])}/30")
    n200 = sum(b == MAX_EPOCHS for b in allb)                           # user decision before Step 2: > half of 30 -> limitation
    pr(f"  networks with best epoch = {MAX_EPOCHS}: {n200}/30 -> "
       + ("LIMITATION: \"possibly under-trained (epoch cap binding)\" (pre-stated; no rerun, reading unchanged)" if n200 > 15 else
          "epoch cap not binding in more than half of the networks (pre-stated rule)"))
    q = d1 > 0 and (e2[0][4][1] - e2[0][3][1]) > 0
    reading = "QUALIFIES FOR A HELD-OUT TEST (dev only; not confirmation)" if q else "NOT ELIGIBLE"
    pr(f"\nQUALIFICATION RULE (pre-stated, mechanical): E1 Δ {d1:+.4f} > 0 is {d1 > 0}; E2 (88%) {(e2[0][4][1] - e2[0][3][1]) * 100:+.2f} points > 0 is "
       f"{(e2[0][4][1] - e2[0][3][1]) > 0} -> \"{reading}\"")
    if synthetic:
        print(f"E1-E5 code paths ran on the synthetic predictions, including the report ({len(L)} lines built, not printed); values not reported")
        return dict(qualifies=q, tau88=tau_keep(pS, y, w, 0.88), pS=pS)
    print("\n".join(L))
    return dict(qualifies=q, tau88=tau_keep(pS, y, w, 0.88), pS=pS)


def freeze(c, res, tau88, pS, root):
    """5 outer-fold pipelines (network state_dict + scaler/stacker), tau, dev rows; never overwrite. -> {file: sha256}."""
    import joblib, torch
    md = f"{root}/models"; os.makedirs(md, exist_ok=False); hashes = {}
    for r in res[SEED]["folds"]:
        fn = f"{md}/CNN1D_fold{r['k']}.pt"; torch.save(r["models"]["state"], fn); hashes[fn] = H(fn)
        fn = f"{md}/CNN1D_stack_fold{r['k']}.joblib"; joblib.dump({q: r["models"][q] for q in ("stack_scaler", "stacker")}, fn); hashes[fn] = H(fn)
    fn = f"{root}/thresholds.json"
    json.dump(dict(C_CV_cnn=dict(tau=tau88, seed=SEED, cols=CCV + ["logit_curve"], clip=CLIP)), open(fn, "x"), indent=1); hashes[fn] = H(fn)
    fn = f"{root}/dev_rows_CNN1D.csv"; assert not os.path.exists(fn)
    c[["eid", "harpnum", "t", "fold", "weight"]].assign(p_oof=pS).to_csv(fn, index=False); hashes[fn] = H(fn)
    json.dump(hashes, open(f"{root}/model_hashes.json", "x"), indent=1)
    return hashes


def verify(c, X, p_oof, root):
    """Reload each fold's frozen pipeline from disk and predict that fold's dev episodes. -> max |diff| vs the in-run OOF predictions."""
    import joblib, torch
    from threadpoolctl import threadpool_limits
    fold, CC, p = c.fold.to_numpy(), c[CCV].to_numpy(float), np.full(len(c), np.nan)
    with threadpool_limits(1):
        for k in range(5):
            st, iT = joblib.load(f"{root}/models/CNN1D_stack_fold{k}.joblib"), np.where(fold == k)[0]
            s = predict_curve(dict(state=torch.load(f"{root}/models/CNN1D_fold{k}.pt")), X[iT])
            p[iT] = st["stacker"].predict_proba(st["stack_scaler"].transform(np.column_stack([CC[iT], logit(s)])))[:, 1]
    return float(np.max(np.abs(p - p_oof)))


def curves_checked(c):
    """#27's curve file, its sha256, and exact equality with a fresh rebuild."""
    fn = f"{MR_OUT}/curves.csv"
    X, info = build_curves(c)
    stored = pd.read_csv(fn, float_precision="round_trip")
    assert (info.reason == "").all() and (stored.eid.to_numpy() == c.eid.to_numpy()).all()
    assert np.array_equal(stored[[f"s{i:03d}" for i in range(NSLOT)]].to_numpy(), X[:, 0]), "curves differ from #27's file; STOP"
    return X, H(fn)


def step1(scratch):
    import torch
    t0 = time.time()
    scratch = os.path.abspath(scratch); repo = os.path.abspath(".")
    assert not (scratch + os.sep).startswith(repo + os.sep), "the scratch folder must be outside the repository"
    print("CANDIDATE #28 CNN1D — STEP 1, LABEL-BLIND + SYNTHETIC CRASH TEST (EXPLORATORY (dev)); decisions.md fdf044d + 8630b46")
    print(f"torch {torch.__version__}; parameters {sum(p.numel() for p in make_net().parameters())} "
          f"{[tuple(p.shape) for p in make_net().parameters()]}")
    c = base_frame()
    X, hsh = curves_checked(c)
    print(f"curve file {MR_OUT}/curves.csv sha256 {hsh}; identical to a fresh minirocket.build_curves rebuild for all {len(c)} episodes; no label column read")
    y = np.random.RandomState(12345).binomial(1, 96 / 541, len(c))
    print(f"\n== CRASH TEST, SYNTHETIC LABELS: numpy RandomState(12345).binomial(1, 96/541, 541) -> {int(y.sum())} ones; no real label read; "
          f"C_CV reproduction check skipped; freeze/reload in a scratch folder outside the repository, deleted afterwards")
    t1 = time.time()
    res = run_pipeline(c, X, y, [SEED] + E4_SEEDS, keep_seed=SEED)
    t2 = time.time()
    fs = [r for R in res.values() for r in R["folds"]]
    print(f"full nested pipeline ran for {len(res)} seeds x 5 outer folds ({len(fs) * 6} networks); OOF predictions finite for all 541 in every seed")
    print(f"wall for the pipeline {t2 - t1:.1f} s ({(t2 - t1) / 60:.1f} min); per outer fold task median {np.median([r['secs'] for r in fs]):.1f} s")
    out = evaluate(c.assign(true_alarm=y), res, synthetic=True)
    root = os.path.join(scratch, "cnn1d_freeze_test"); os.makedirs(root)
    hs = freeze(c, res, out["tau88"], out["pS"], root)
    d = verify(c, X, res[SEED]["p"], root)
    shutil.rmtree(root)
    print(f"freeze wrote {len(hs)} hashed files to the scratch folder; reload check max abs difference {d!r}; scratch folder deleted: {not os.path.exists(root)}")
    print(f"\nwall total {time.time() - t0:.1f} s")


def step2():
    from phase_f import tau_keep, wlogloss
    from euv_heldout import fit_folds
    t0 = time.time()
    print("CANDIDATE #28 CNN1D — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md fdf044d + 8630b46")
    c = base_frame()
    lab = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t", "true_alarm"], parse_dates=["t"])
    lab["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(lab.harpnum, lab.t)]
    c = c.merge(lab[["eid", "true_alarm"]], on="eid", how="left", validate="1:1")
    y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
    TX = json.load(open("data/euv_extra/thresholds.json"))["C_CV"]
    _, pB = fit_folds(c, CCV)
    assert wlogloss(y, pB, w) == TX["dev_oof_logloss"] and tau_keep(pB, y, w) == TX["tau"], "C_CV does not reproduce the frozen euv_extra C_CV; STOP"
    print(f"checks: C_CV OOF reproduces the frozen euv_extra C_CV exactly (LL {TX['dev_oof_logloss']:.10f}, tau {TX['tau']:.10f}); "
          f"episodes {len(c)} (true {int(y.sum())}, false {int((y == 0).sum())}), HARPs {c.harpnum.nunique()}")
    X, hsh = curves_checked(c)
    print(f"check: curve file {MR_OUT}/curves.csv sha256 {hsh}, identical to a fresh rebuild")
    t1 = time.time()
    res = run_pipeline(c, X, y, [SEED] + E4_SEEDS, keep_seed=SEED)
    print(f"pipeline wall {time.time() - t1:.1f} s")
    out = evaluate(c, res)
    if out["qualifies"]:                                                # freeze BEFORE any held-out step (b1fbd2e item 3), then reload check (bf2dbc4)
        hashes = freeze(c, res, out["tau88"], out["pS"], OUT)
        print(f"\nFROZEN (before any held-out computation): 5 outer-fold pipelines (network + stacker), tau (dev OOF, 88%) {out['tau88']:.10f}")
        for fn, hh in hashes.items():
            print(f"  sha256 {hh}  {fn}")
        d = verify(c, X, res[SEED]["p"], OUT)
        print(f"RELOAD CHECK: frozen models reloaded from disk reproduce the dev outer-OOF predictions: max abs difference {d!r}")
        if d != 0:
            print("NOT IDENTICAL -> STOP"); sys.exit(1)
    print(f"\nwall total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    if sys.argv[1:2] == ["step1"] and len(sys.argv) == 3:
        step1(sys.argv[2])
    elif sys.argv[1:] == ["step2"]:
        step2()
    else:
        sys.exit(__doc__)
