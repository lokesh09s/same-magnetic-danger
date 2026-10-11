"""SWPC flare catalogue from HEK, shared by build_dataset.py and checks.py."""
import re
import numpy as np, pandas as pd
from sunpy.net import Fido, attrs as a

LETTER = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}


def parse_goes(s):
    """'M1.5' -> ('M', 1.5e-5).  Unparseable -> (None, nan)."""
    m = re.match(r"^([ABCMX])([\d.]*)$", str(s).strip())
    if not m:
        return None, np.nan
    return m.group(1), LETTER[m.group(1)] * (float(m.group(2)) if m.group(2) else 1.0)


def fetch(lo, hi, verbose=True):
    """SWPC flares with start time in [lo, hi]. Returns (all_flares, m1_plus)."""
    res = Fido.search(a.Time(lo, hi), a.hek.EventType("FL"), a.hek.FRM.Name == "SWPC")["hek"]
    if len(res) == 0 or "event_starttime" not in res.colnames:
        # solar minimum: HEK can legitimately return no SWPC flares for a whole month
        empty = pd.DataFrame(columns=["start", "noaa_ar", "goes_class", "cls", "flux"])
        if verbose:
            print("flares retrieved: 0  (no SWPC events in window)")
        return empty, empty
    st = res["event_starttime"]
    fl = pd.DataFrame({
        "start": pd.to_datetime(np.asarray(st.to_datetime() if hasattr(st, "to_datetime") else st)),
        "noaa_ar": pd.to_numeric(pd.Series(np.asarray(res["ar_noaanum"])), errors="coerce"),
        "goes_class": pd.Series(np.asarray(res["fl_goescls"])).astype(str).str.strip(),
    })
    n0 = len(fl)
    fl = fl.drop_duplicates(subset=["start", "noaa_ar", "goes_class"])
    n_dup = n0 - len(fl)
    fl[["cls", "flux"]] = fl["goes_class"].apply(lambda s: pd.Series(parse_goes(s)))
    # ar_noaanum <= 0 or NaN means the region is UNKNOWN, not region zero.  HEK reports 0
    # for whole years (e.g. 2022).  Joining those would match no HARP and silently emit
    # false-negative labels, so they are dropped from the join and counted instead.
    fl = fl.dropna(subset=["flux"])
    unknown = fl["noaa_ar"].isna() | (fl["noaa_ar"] <= 0)
    n_unknown = int(unknown.sum())
    n_unknown_m1 = int((unknown & (fl["flux"] >= 1e-5)).sum())   # M1+ only, for the join report
    fl = fl[~unknown]
    fl["noaa_ar"] = fl["noaa_ar"].astype(int)
    m1 = fl[fl["flux"] >= 1e-5].copy()
    m1.attrs["n_unknown_m1"] = n_unknown_m1   # M1+ flares that could not be joined at all          # M1.0 and above, parsed numerically here, not catalogue-side
    if verbose:
        print(f"flares retrieved: {n0}")
        print(f"duplicates removed: {n_dup}  (on start_time, noaa_ar, goes_class)")
        print(f"parsed & AR-matched: {len(fl)};  M1+ retained: {len(m1)}")
        print(f"flares with UNKNOWN region (ar_noaanum <= 0 or NaN), not joined: {n_unknown}  (of which M1+: {n_unknown_m1})")
        print("class counts:", fl["cls"].value_counts().to_dict())
    return fl, m1


def fetch_raw_m1(lo, hi):
    """M1+ flares from HEK/SWPC INCLUDING unknown-region ones. Cross-checks only."""
    return fetch_raw(lo, hi, min_flux=1e-5)


def fetch_raw(lo, hi, min_flux=0.0):
    """HEK/SWPC flares INCLUDING unknown-region ones (noaa_ar may be 0 or NaN).
    For cross-checks only -- never use this for labelling."""
    res = Fido.search(a.Time(lo, hi), a.hek.EventType("FL"), a.hek.FRM.Name == "SWPC")["hek"]
    if len(res) == 0 or "event_starttime" not in res.colnames:
        return pd.DataFrame(columns=["start", "noaa_ar", "goes_class", "flux"])
    st = res["event_starttime"]
    fl = pd.DataFrame({
        "start": pd.to_datetime(np.asarray(st.to_datetime() if hasattr(st, "to_datetime") else st)),
        "noaa_ar": pd.to_numeric(pd.Series(np.asarray(res["ar_noaanum"])), errors="coerce"),
        "goes_class": pd.Series(np.asarray(res["fl_goescls"])).astype(str).str.strip(),
    }).drop_duplicates(subset=["start", "noaa_ar", "goes_class"])
    fl["flux"] = fl["goes_class"].apply(lambda c: parse_goes(c)[1])
    return fl[fl["flux"] >= min_flux].reset_index(drop=True)
