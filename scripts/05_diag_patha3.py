"""Path A consistency checks (decisions.md 2026-09-22): region flips, FAR/precision by test-year set,
HEK ar_noaanum = 0 per year, and the 4 'no HEK event' phantoms. Descriptive; frozen files untouched."""
import json, os
import numpy as np, pandas as pd
from sunpy.net import Fido, attrs as a
import flares

os.makedirs("data/pathA", exist_ok=True)
SPEC = json.load(open("frozen/frozen_spec.json")); THR = SPEC["gate"]["threshold"]
exec(open("scripts/05_diag_patha.py").read().split("# ------------------------------- episodes")[0].split("rows = []")[0])
ep = pd.read_csv("data/diag/patha_episodes.csv", parse_dates=["t"])
ph = ep[(ep.period == "2021-2024") & (ep.true_HEK == 0) & (ep.true_K2 == 1)]
test["alarm"] = test.score.to_numpy() >= THR

# ---------------------------------------------------------------- (1) region flips
r = test.groupby("harpnum").agg(alarm=("alarm", "max"), yH=("y_HEK", "max"), yK=("y_K2", "max"))
flip = r[(r.alarm) & (r.yH == 0) & (r.yK == 1)].index
rows = []
for h in flip:
    d = test[test.harpnum == h]
    ah = d[d.alarm]
    eh = ep[(ep.period == "2021-2024") & (ep.harpnum == h)]
    n_ph = int(((eh.true_HEK == 0) & (eh.true_K2 == 1)).sum())
    pos_alarm = int((ah.y_K2 == 1).sum())
    if n_ph:
        why = "phantom episode (first evaluable hour)"
    elif pos_alarm:
        why = "later alarm hour, K2-positive, not an episode t"
    else:
        why = "K2-positive rows only outside alarm hours"
    rows.append(dict(harpnum=h, noaa_ars=d.noaa_ars.iloc[0], alarm_hours=len(ah), rows=len(d),
                     K2_pos_rows=int((d.y_K2 == 1).sum()), K2_pos_alarm_hours=pos_alarm,
                     HEK_pos_rows=int((d.y_HEK == 1).sum()), episodes=len(eh), phantom_episodes=n_ph, reason=why))
fl_df = pd.DataFrame(rows).sort_values("harpnum")
fl_df.to_csv("data/pathA/region_flips_2021_24.csv", index=False)
print(f"alarmed regions {int(r.alarm.sum())}; flips (HEK false -> K2 true) {len(fl_df)}; "
      f"phantom episodes span {ph.harpnum.nunique()} HARPs")
print(fl_df.reason.value_counts().to_dict())
print(fl_df.to_string(index=False))


# ---------------------------------------------------------------- (2) FAR / precision by test-year set
def far_prec(y, al):
    tp, fp = int((al & (y == 1)).sum()), int((al & (y == 0)).sum())
    return (fp / (tp + fp), tp / (tp + fp)) if tp + fp else (np.nan, np.nan)


out = []
for tag, yrs in [("primary 2021/2023/2024", [2021, 2023, 2024]), ("2022 only", [2022])]:
    d = test[test.t_rec_utc.dt.year.isin(yrs)]
    lv = {"hour": (d.harpnum.to_numpy(), d.alarm.to_numpy(), d.y_HEK.to_numpy(), d.y_K2.to_numpy())}
    g = d.groupby("harpnum").agg(a=("alarm", "max"), yH=("y_HEK", "max"), yK=("y_K2", "max"))
    lv["region"] = (g.index.to_numpy(), g.a.to_numpy(), g.yH.to_numpy(), g.yK.to_numpy())
    for level, (hh, al, yH, yK) in lv.items():
        keys = np.unique(hh); grp = {k: np.where(hh == k)[0] for k in keys}
        rng = np.random.RandomState(0); B = []
        for _ in range(2000):
            ix = np.concatenate([grp[k] for k in rng.choice(keys, len(keys), replace=True)])
            fH, pH = far_prec(yH[ix], al[ix]); fK, pK = far_prec(yK[ix], al[ix])
            B.append((fH, fK, fH - fK, pH, pK, pH - pK))
        B = np.array(B); B = B[np.isfinite(B).all(axis=1)]
        fH, pH = far_prec(yH, al); fK, pK = far_prec(yK, al)
        for j, (name, val) in enumerate([("FAR HEK", fH), ("FAR K2", fK), ("FAR HEK-K2", fH - fK),
                                         ("precision HEK", pH), ("precision K2", pK), ("precision HEK-K2", pH - pK)]):
            lo, hi = np.percentile(B[:, j], [2.5, 97.5])
            out.append(dict(years=tag, level=level, quantity=name, value=round(val, 4), ci_lo=round(lo, 4),
                            ci_hi=round(hi, 4), resamples_used=len(B), alarms=int(al.sum()), units=len(keys)))
t2 = pd.DataFrame(out); t2.to_csv("data/pathA/far_precision_ci_by_years.csv", index=False)
print("\n" + t2.to_string(index=False))

# ---------------------------------------------------------------- (3) HEK M1+ with ar_noaanum = 0, per year
rows = []
for y in range(2019, 2025):
    f = flares.fetch_raw_m1(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"))
    ar = pd.to_numeric(f.noaa_ar, errors="coerce")
    z = int(((ar <= 0) | ar.isna()).sum())
    rows.append(dict(year=y, hek_M1plus=len(f), ar_zero_or_missing=z, fraction=round(z / len(f), 4) if len(f) else np.nan))
t3 = pd.DataFrame(rows); t3.to_csv("data/pathA/hek_ar_zero_by_year.csv", index=False)
print("\nHEK M1+ events (classes as reported, no scale conversion) with ar_noaanum <= 0 or missing:")
print(t3.to_string(index=False))

# ---------------------------------------------------------------- (4) the 4 'no HEK event' phantoms
pl = pd.read_csv("data/pathA/phantoms_2021_24.csv", parse_dates=["alarm_t_utc", "first_swpc_start", "first_swpc_peak"])
miss = pl[pl.hek_events_within_10min == 0]
rows = []
for x in miss.itertuples():
    for anchor, tt in [("SWPC start", x.first_swpc_start), ("SWPC peak", x.first_swpc_peak)]:
        q = Fido.search(a.Time(tt - pd.Timedelta("60min"), tt + pd.Timedelta("60min")),
                        a.hek.EventType("FL"), a.hek.FRM.Name == "SWPC")["hek"]
        for e in q:
            rows.append(dict(harpnum=x.harpnum, alarm_t_utc=x.alarm_t_utc, anchor=anchor, anchor_time=tt,
                             hek_start=str(e["event_starttime"]), hek_peak=str(e["event_peaktime"]),
                             hek_class=str(e["fl_goescls"]).strip(), ar_noaanum=e["ar_noaanum"],
                             hpc_x=e["hpc_x"], hpc_y=e["hpc_y"], frm=str(e["frm_name"])))
        if not len(q):
            rows.append(dict(harpnum=x.harpnum, alarm_t_utc=x.alarm_t_utc, anchor=anchor, anchor_time=tt,
                             hek_start="NONE FOUND", hek_peak="", hek_class="", ar_noaanum=np.nan, hpc_x=np.nan,
                             hpc_y=np.nan, frm=""))
t4 = pd.DataFrame(rows).drop_duplicates(); t4.to_csv("data/pathA/no_hek_phantoms_pm60min.csv", index=False)
print(f"\n'no HEK event' phantoms: {len(miss)}; HEK rows found within +-60 min:")
print(t4.to_string(index=False))
