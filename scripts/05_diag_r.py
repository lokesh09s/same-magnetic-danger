"""R1-R4 reproduction runs (diagnostic; dev period only; decisions.md 2026-09-22). Main pipeline and gate unchanged.
R1 = D7/D8 with the exact 12-min SHARP record at each sample time; R2 = R1 + NCEI flare locations;
R4 = R2 + TOTBSQ/TOTFZ/EPSZ from SWAN-SF (13 features, primary); R4-cgem = R2 + the 3 from cgem.lorentz masked.
Usage: python diag_r.py"""
import os, tarfile, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, drms
from astropy.time import Time
from joblib import Parallel, delayed
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from diag_d7_catalogue import report

src = open("scripts/05_diag_d7.py").read()
exec(compile(src[:src.index("# ---------------------------------------------------------------- positives")], "d7", "exec"))
# now defined: F, LO, HI, SEED, NP, REPEATS, SVM, raw, elig, m1
region_harps = {}
for h, g in raw.groupby("harpnum"):
    for ar in set().union(*g["ars"]):
        region_harps.setdefault(ar, []).append(h)
KEYS = "HARPNUM,T_REC,NOAA_ARS,QUALITY,LON_FWT," + ",".join(x.upper() for x in F)
SLOT = pd.Timedelta("12min")


def slot(t_utc):
    """Nearest T_REC on the 12-min TAI grid to a UTC time; returned as a T_REC string."""
    tai = pd.Timestamp(Time(t_utc).tai.datetime).round(SLOT)
    return tai.strftime("%Y.%m.%d_%H:%M:%S_TAI")


def trec_utc(s):
    return pd.Timestamp(Time(s[:-4].replace("_", " ").replace(".", "-", 2), scale="tai").utc.datetime)


def retry(f, *a):
    for k in range(6):
        try:
            return f(*a)
        except Exception as err:
            print(f"retry {k + 1}: {err!r}", flush=True); time.sleep(20)
    raise RuntimeError(a)


# ---------------------------------------------------------------- 12-min SHARP records at sample time and at peak
fl = m1.dropna(subset=["peak"]).copy()
fl["ts"] = fl["peak"] - pd.Timedelta(hours=24)
fl = fl[(fl.ts >= LO) & (fl.ts <= HI)].reset_index(drop=True)
fl["s_sample"], fl["s_peak"] = fl.ts.map(slot), fl.peak.map(slot)
need = sorted({(h, s) for _, f in fl.iterrows() for h in region_harps.get(int(f.noaa_ar), [])
               for s in (f.s_sample, f.s_peak)})
C12 = "data/diag/r_sharp12.csv"
if not os.path.exists(C12):
    by = pd.DataFrame(need, columns=["h", "s"]).groupby("h").s.apply(list)
    q = lambda h: drms.Client().query(f"hmi.sharp_cea_720s[{h}][{','.join(by[h])}]", key=KEYS)
    with ThreadPoolExecutor(6) as ex:
        pd.concat(list(ex.map(lambda h: retry(q, h), by.index))).to_csv(C12, index=False)
r12 = pd.read_csv(C12, dtype={"NOAA_ARS": str})
r12.columns = [c.lower() for c in r12.columns]
r12["ars"] = r12.noaa_ars.fillna("").apply(lambda v: frozenset(int(x) for x in v.split(",") if x.strip().isdigit()))
rec = {(int(x.harpnum), x.t_rec): x for x in r12.itertuples()}

ngdc = report("data/ngdc")
ngdc_lon = {(d, s): lon for d, s, lon in zip(ngdc.date, ngdc.start, ngdc.lon) if lon is not None and lon == lon}


def positives(use_ngdc):
    pos, n_rec = [], 0
    for _, f in fl.iterrows():
        loc_ok_ngdc = use_ngdc and abs(ngdc_lon.get((f.start.normalize(), f.start.strftime("%H%M")), 999)) <= 68
        for h in sorted(region_harps.get(int(f.noaa_ar), [])):
            pk = rec.get((h, f.s_peak))
            proxy_ok = pk is not None and abs(pk.lon_fwt) <= 68
            if not (proxy_ok or loc_ok_ngdc):
                continue
            x = rec.get((h, f.s_sample))
            if x is None or not (x.quality <= 65536 and abs(x.lon_fwt) <= 68 and int(f.noaa_ar) in x.ars
                                 and all(pd.notna(getattr(x, c)) for c in F)):
                continue
            pos.append(dict(harpnum=h, t_rec=x.t_rec, flare=f.start, ngdc_only=not proxy_ok, **{c: getattr(x, c) for c in F}))
            break
    return pd.DataFrame(pos)


# ---------------------------------------------------------------- extra features: SWAN-SF and cgem.lorentz
m1_by_ar = {ar: np.sort(g["start"].values) for ar, g in m1.groupby("noaa_ar")}


def no_m1_next24(row):
    t0, t1 = np.datetime64(row["t"]), np.datetime64(row["t"] + pd.Timedelta(hours=24))
    return not any(((v > t0) & (v <= t1)).any() for ar in row["ars"] for v in [m1_by_ar.get(ar, np.array([], "datetime64[ns]"))])


POOL = elig[elig.apply(no_m1_next24, axis=1)]
P2 = positives(True)
harps_all = set(POOL.harpnum) | set(P2.harpnum)
SW = "data/diag/r_swansf.csv"
if not os.path.exists(SW):
    parts = []
    with tarfile.open("data/swansf/SWAN.tar.gz") as tf:
        for m in tf:
            n = m.name.rsplit("/", 1)[-1]
            if m.isfile() and n.endswith(".csv") and n[:-4].isdigit() and int(n[:-4]) in harps_all:
                d = pd.read_csv(tf.extractfile(m), sep="\t", usecols=["Timestamp", "TOTBSQ", "TOTFZ", "EPSZ"])
                parts.append(d.assign(harpnum=int(n[:-4])))
    sw = pd.concat(parts).drop_duplicates(["harpnum", "Timestamp"])
    sw["t_rec"] = pd.to_datetime(sw.Timestamp).dt.strftime("%Y.%m.%d_%H:%M:%S_TAI")
    sw[["harpnum", "t_rec", "TOTBSQ", "TOTFZ", "EPSZ"]].to_csv(SW, index=False)
CG = "data/diag/r_cgem.csv"
if not os.path.exists(CG):
    want = pd.concat([POOL[["harpnum", "t_rec"]], P2[["harpnum", "t_rec"]]]).drop_duplicates()
    by = want.groupby("harpnum").t_rec.apply(list)

    def q(h):                                          # hourly pool: one @1h range per HARP; 12-min positives: short list
        ts = sorted(by[h]); hourly = [t for t in ts if t[14:19] == "00:00"]; other = [t for t in ts if t not in set(hourly)]
        sets = ([f"{hourly[0][:-4]}-{hourly[-1][:-4]}@1h"] if hourly else []) + \
               [",".join(other[i:i + 50]) for i in range(0, len(other), 50)]
        out = [drms.Client().query(f"cgem.lorentz[{h}][{x}]", key="HARPNUM,T_REC,TOTBSQ1,TOTFZ1,EPSZ1") for x in sets]
        r = pd.concat(out)
        return r[r.T_REC.isin(set(ts))]
    with ThreadPoolExecutor(6) as ex:
        pd.concat(list(ex.map(lambda h: retry(q, h), by.index))).to_csv(CG, index=False)
EXTRA = {"swan": pd.read_csv(SW).rename(columns=str.lower),
         "cgem": pd.read_csv(CG).rename(columns={"HARPNUM": "harpnum", "T_REC": "t_rec", "TOTBSQ1": "totbsq",
                                                 "TOTFZ1": "totfz", "EPSZ1": "epsz"})}
F3 = ["totbsq", "totfz", "epsz"]


# ---------------------------------------------------------------- catalogue and 1,000 splits x 2 class weights
def build(pos, extra=None):
    pool = POOL.drop(columns=[c for c in F3 if c in POOL], errors="ignore")
    feats = F
    if extra is not None:
        e = EXTRA[extra][["harpnum", "t_rec"] + F3]
        pos = pos.merge(e, on=["harpnum", "t_rec"], how="left").dropna(subset=F3)
        pool = pool.merge(e, on=["harpnum", "t_rec"], how="left").dropna(subset=F3)
        feats = F + F3
    pool = pool[~pool.set_index(["harpnum", "t_rec"]).index.isin(pos.set_index(["harpnum", "t_rec"]).index)]
    P = len(pos); N = int(round(NP * P))
    neg = pool.sample(n=N, replace=False, random_state=SEED)
    cat = pd.concat([pos.assign(y=1), neg.assign(y=0)], ignore_index=True)
    X = cat[feats].to_numpy(float); X = (X - np.median(X, axis=0)) / X.std(axis=0)
    return X, cat.y.to_numpy(), P, N, len(pool), cat


def split(X, y, i, ratio):
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.30, stratify=y, random_state=SEED + i)
    pred = SVC(**{**SVM, "class_weight": {1: ratio, 0: 1.0}}).fit(Xtr, ytr).decision_function(Xte) >= 0
    return [int((pred & (yte == 1)).sum()), int((~pred & (yte == 1)).sum()),
            int((pred & (yte == 0)).sum()), int((~pred & (yte == 0)).sum())]


TARGET = {2.0: (0.562, 0.658), 15.0: (0.722, 0.800)}
P1 = positives(False)
runs = {"R1": (P1, None), "R2": (P2, None), "R4 (SWAN-SF, primary)": (P2, "swan"),
        "R4-cgem (masked; failed magnitude validation TOTBSQ, TOTFZ; rho >= 0.978)": (P2, "cgem")}
print(f"flares in period with a peak: {len(fl)}; R1 positives {len(P1)}; R2 positives {len(P2)} "
      f"(NCEI-location admissions {int(P2.ngdc_only.sum())})")
out = []
for name, (pos, extra) in runs.items():
    X, y, P, N, npool, cat = build(pos, extra)
    for ratio in (2.0, 15.0):
        c = np.array(Parallel(n_jobs=3)(delayed(split)(X, y, i, ratio) for i in range(REPEATS)), float)
        TP, FN, FP, TN = c.T
        tss, rec_, fpr = TP / (TP + FN) - FP / (FP + TN), TP / (TP + FN), FP / (FP + TN)
        prec = np.where(TP + FP > 0, TP / np.maximum(TP + FP, 1), np.nan)
        lo, hi = TARGET[ratio]
        f = lambda v: f"{np.nanmean(v):.3f} ± {np.nanstd(v, ddof=1):.3f}"
        out.append({"run": name, "C1/C2": ratio, "P": P, "N": N, "neg pool": npool, "TSS": f(tss), "recall": f(rec_),
                    "precision": f(prec), "FPR": f(fpr), "prec undefined": int(np.isnan(prec).sum()),
                    "target": f"{lo}–{hi}", "TSS in target": bool(lo <= tss.mean() <= hi)})
        print(out[-1], flush=True)
t = pd.DataFrame(out); t.to_csv("data/diag/r_runs.csv", index=False)
print(t.to_string(index=False))
