"""Path A follow-up (decisions.md 2026-09-22): FAR/precision CIs (HEK vs K2, 2021-24), the 34 phantom alarms,
and a 3-case evidence pack. Reuses diag_patha.py outputs; frozen files untouched."""
import json, os
import numpy as np, pandas as pd
import astropy.units as u
from sunpy.net import Fido, attrs as a
import swpc

os.makedirs("data/pathA/evidence", exist_ok=True)
SPEC = json.load(open("frozen/frozen_spec.json")); THR = SPEC["gate"]["threshold"]
exec(open("scripts/05_diag_patha.py").read().split("# ---------------------------------------------------------------- episodes")[0]
     .split("rows = []")[0])                                   # rebuild lab/dev/test exactly as Path A (no metrics rerun)


def far_prec(y, a):
    tp, fp = int((a & (y == 1)).sum()), int((a & (y == 0)).sum())
    return (fp / (tp + fp), tp / (tp + fp)) if tp + fp else (np.nan, np.nan)


# ---------------------------------------------------------------- (2) CIs, 2,000 HARP resamples, seed 0
out = []
h = test.harpnum.to_numpy(); al = test.score.to_numpy() >= THR
lv = {"hour": (h, al, test.y_HEK.to_numpy(), test.y_K2.to_numpy())}
r = pd.DataFrame({"h": h, "a": al, "yH": test.y_HEK, "yK": test.y_K2}).groupby("h").max()
lv["region"] = (r.index.to_numpy(), r.a.to_numpy(), r.yH.to_numpy(), r.yK.to_numpy())
for level, (hh, aa, yH, yK) in lv.items():
    keys = np.unique(hh); grp = {k: np.where(hh == k)[0] for k in keys}
    rng = np.random.RandomState(0); B = []
    for _ in range(2000):
        ix = np.concatenate([grp[k] for k in rng.choice(keys, len(keys), replace=True)])
        fH, pH = far_prec(yH[ix], aa[ix]); fK, pK = far_prec(yK[ix], aa[ix])
        B.append((fH, fK, fH - fK, pH, pK, pH - pK))
    B = np.array(B); B = B[np.isfinite(B).all(axis=1)]
    fH, pH = far_prec(yH, aa); fK, pK = far_prec(yK, aa)
    for j, (name, val) in enumerate([("FAR HEK", fH), ("FAR K2", fK), ("FAR HEK-K2", fH - fK),
                                     ("precision HEK", pH), ("precision K2", pK), ("precision HEK-K2", pH - pK)]):
        lo, hi = np.percentile(B[:, j], [2.5, 97.5])
        out.append(dict(level=level, quantity=name, value=round(val, 4), ci_lo=round(lo, 4), ci_hi=round(hi, 4),
                        resamples_used=len(B), alarms=int(aa.sum()), units=len(keys)))
ci = pd.DataFrame(out); ci.to_csv("data/pathA/far_precision_ci_2021_24.csv", index=False)
print(ci.to_string(index=False))

# ---------------------------------------------------------------- (3) the 34 phantom alarms
ep = pd.read_csv("data/diag/patha_episodes.csv", parse_dates=["t"])
ph = ep[(ep.period == "2021-2024") & (ep.true_HEK == 0) & (ep.true_K2 == 1)].copy()
k2i = k2.set_index(["harpnum", "t_rec_utc"])
ph["noaa_ars"] = [k2i.loc[(x.harpnum, x.t), "noaa_ars"] for x in ph.itertuples()]
fl, _ = swpc.load(ph.t.min() - pd.Timedelta("1D"), ph.t.max() + pd.Timedelta("2D"))
m1 = fl[fl.flux >= 1e-5]
rows = []
for x in ph.itertuples():
    ars = {int(v) for v in str(x.noaa_ars).split(",") if v.strip().isdigit()}
    f = m1[m1.noaa_ar.isin(ars) & (m1.start > x.t) & (m1.start <= x.t + pd.Timedelta("24h"))].sort_values("start")
    first = f.iloc[0]
    q = Fido.search(a.Time(first.start - pd.Timedelta("10min"), first.start + pd.Timedelta("10min")),
                    a.hek.EventType("FL"), a.hek.FRM.Name == "SWPC")["hek"]
    hk = [(str(e["event_starttime"]), str(e["fl_goescls"]).strip(), e["ar_noaanum"]) for e in q]
    rows.append(dict(harpnum=x.harpnum, noaa_ars=x.noaa_ars, alarm_t_utc=x.t, year=x.year,
                     swpc_m1_in_24h=len(f), first_swpc_start=first.start, first_swpc_peak=first.peak,
                     first_swpc_class_K2=first.goes_class, first_swpc_class_reported=first.get("goes_class_reported", ""),
                     first_swpc_region=int(first.noaa_ar), first_swpc_obs=first.obs,
                     hek_events_within_10min=len(hk),
                     hek_ar_noaanum=";".join(str(v[2]) for v in hk), hek_class=";".join(v[1] for v in hk),
                     hek_start=";".join(v[0] for v in hk)))
pl = pd.DataFrame(rows); pl.to_csv("data/pathA/phantoms_2021_24.csv", index=False)
print(f"\nphantoms: {len(pl)}; per year {pl.year.value_counts().sort_index().to_dict()}")
print("HEK ar_noaanum of the matched HEK events:", pl.hek_ar_noaanum.value_counts().to_dict())
print(pl[["harpnum", "noaa_ars", "alarm_t_utc", "first_swpc_start", "first_swpc_class_K2", "first_swpc_region",
          "hek_ar_noaanum", "hek_class"]].to_string(index=False))

# ---------------------------------------------------------------- (4) evidence pack: first 3 phantoms of 2023
raw = pd.read_csv("data/raw_sharp_20100501_20250101.csv", dtype={"NOAA_ARS": str, "T_REC": str}, low_memory=False)
for x in pl[pl.year == 2023].sort_values("alarm_t_utc").head(3).itertuples():
    d = f"data/pathA/evidence/HARP{x.harpnum}_{x.alarm_t_utc:%Y%m%dT%H%M}"; os.makedirs(d, exist_ok=True)
    q = Fido.search(a.Time(x.first_swpc_start - pd.Timedelta("10min"), x.first_swpc_start + pd.Timedelta("10min")),
                    a.hek.EventType("FL"), a.hek.FRM.Name == "SWPC")["hek"]
    keep = [c for c in q.colnames if c.startswith(("hpc_", "hgs_", "hgc_", "hrc_", "event_coord", "ar_", "fl_", "event_",
                                                    "frm_", "obs_", "kb_archivid"))]
    q[keep].to_pandas().to_csv(f"{d}/hek_record.csv", index=False)
    day = pd.Timestamp(x.first_swpc_start).normalize()
    lines = open(f"data/swpc_events/{day:%Y%m%d}events.txt").read().splitlines()
    hhmm = f"{x.first_swpc_start:%H%M}"
    with open(f"{d}/swpc_report_line.txt", "w") as fo:
        fo.write(f"# source: data/swpc_events/{day:%Y%m%d}events.txt (NCEI SWPC original daily event report)\n")
        fo.write("\n".join(L for L in lines if L.startswith("#") and "Event" in L) + "\n")
        fo.write("\n".join(L for L in lines if " XRA " in f" {L} " and hhmm in L[:20]) + "\n")
    t_tai = k2i.loc[(x.harpnum, x.alarm_t_utc), "t_rec_tai"] if "t_rec_tai" in k2i else None
    raw[(raw.HARPNUM == x.harpnum) & (raw.T_REC == t_tai)].to_csv(f"{d}/sharp_record_at_alarm.csv", index=False)
    print(f"evidence: {d}  (HEK rows {len(q)}, SWPC lines written, SHARP rows "
          f"{int(((raw.HARPNUM == x.harpnum) & (raw.T_REC == t_tai)).sum())})")
