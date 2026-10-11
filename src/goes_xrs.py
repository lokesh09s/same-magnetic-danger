"""GOES XRS 1-8 A daily maximum (1-minute science data, NOAA primary satellite) for the days
whose SWPC event report is empty ('NO EVENT REPORTS.').  Decision E (user, 2026-09-21):
    max >= M1 -> day MISSING for labels
    max >= C1 -> day INCOMPLETE for flare history
  with M1 = 1.0e-5, C1 = 1.0e-6 W/m^2 in true (science) flux -- decision K2
    otherwise              -> genuine zero

Primary satellite: NCEI "GOES 1-15 XRS Science-Quality Data Readme", Appendix A, Table 11
("Primary and Secondary GOES Satellites for XRS from 1986 through January 2025"):
  https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/science/xrs/GOES_1-15_XRS_Science-Quality_Data_Readme.pdf
Only the PRIMARY column changes are needed; transcribed for our range (secondary-only rows omitted).
Data: 1-minute averaged science files (xrsf-l2-avg1m_science), variable xrsb_flux (1-8 A),
      only minutes with xrsb_flag == 0 (good_data) are used.
"""
import os, re, sys, urllib.request
import numpy as np, pandas as pd, xarray as xr

# Table 11, transcribed as (switch time UTC, primary, secondary) for our range.
# A blank cell in the table means "no change"; here every row carries the full state.
# None = no secondary satellite.
TABLE11 = [("2009-12-01 00:00", 14, None), ("2010-09-01 00:00", 14, 15), ("2010-10-28 00:00", 15, None),
           ("2011-09-01 00:00", 15, 14),   ("2012-10-23 16:00", 14, 15), ("2012-11-19 16:31", 15, 14),
           ("2015-01-26 16:01", 15, 13),   ("2015-05-21 18:00", 14, 13), ("2015-06-09 16:25", 15, 13),
           ("2016-05-03 13:00", 13, 14),   ("2016-05-12 17:30", 14, 13), ("2016-05-16 17:00", 14, 15),
           ("2016-06-09 17:30", 15, 13),   ("2017-02-07 00:00", 16, 15), ("2018-06-01 00:00", 16, 17),
           ("2023-01-10 00:00", 16, 18),   ("2025-04-07 00:00", 18, 19)]
TABLE11 = [(pd.Timestamp(t), p, q) for t, p, q in TABLE11]
PRIMARY = [(t, p) for t, p, _ in TABLE11]

BASE = {13: "https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/science/xrs/goes13/xrsf-l2-avg1m_science/",
        14: "https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/science/xrs/goes14/xrsf-l2-avg1m_science/",
        15: "https://www.ncei.noaa.gov/data/goes-space-environment-monitor/access/science/xrs/goes15/xrsf-l2-avg1m_science/",
        16: "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes16/l2/data/xrsf-l2-avg1m_science/",
        17: "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes17/l2/data/xrsf-l2-avg1m_science/",
        18: "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes18/l2/data/xrsf-l2-avg1m_science/",
        19: "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes19/l2/data/xrsf-l2-avg1m_science/"}
CACHE = "data/goes_xrs"
# Decision K2 (user, 2026-09-21; supersedes K): labels are on the TRUE irradiance scale, the same scale
# as the GOES science data, so the class boundaries apply directly: M1 = 1.0e-5, C1 = 1.0e-6, all years.
M1, C1 = 1.0e-5, 1.0e-6


def segments(day):
    """[(start, end, primary, secondary), ...] covering [day, day+1d), split at any Table 11 switch."""
    lo, hi = day, day + pd.Timedelta(days=1)
    cuts = [lo] + [t for t, _, _ in TABLE11 if lo < t < hi] + [hi]
    state = lambda t: [(p, q) for u, p, q in TABLE11 if u <= t][-1]
    return [(a, b, *state(a)) for a, b in zip(cuts[:-1], cuts[1:])]


_listing = {}
def file_url(sat, day):
    """Resolve the daily file (version suffix varies) from the month's directory listing."""
    d = f"{BASE[sat]}{day:%Y}/{day:%m}/"
    if d not in _listing:
        try:
            _listing[d] = urllib.request.urlopen(d, timeout=60).read().decode()
        except Exception:
            _listing[d] = ""
    m = re.findall(rf'sci_xrsf-l2-avg1m_g{sat}_d{day:%Y%m%d}_v[\d-]+\.nc', _listing[d])
    return (d + sorted(set(m))[-1]) if m else None     # newest version if several


def load_minutes(sat, day):
    """Good-quality 1-minute xrsb_flux for one satellite-day, or None if no file."""
    os.makedirs(CACHE, exist_ok=True)
    path = f"{CACHE}/g{sat}_{day:%Y%m%d}.nc"
    if not os.path.exists(path):
        url = file_url(sat, day)
        if url is None:
            return None
        urllib.request.urlretrieve(url, path)
    with xr.open_dataset(path) as ds:
        s = pd.Series(ds["xrsb_flux"].values, index=pd.to_datetime(ds["time"].values))
        good = ds["xrsb_flag"].values == 0
    return s[good & np.isfinite(s.values)]


def day_max(day):
    """Daily max of good 1-8 A flux: primary minutes, gaps filled with secondary good minutes
    (decisions H, I).  A minute is taken from the secondary only if the primary has no good value
    for it, so no minute is counted twice."""
    s, used, n_primary = day_minutes(day)
    return {"day": day, "sats": "/".join(used), "primary_minutes": n_primary,
            "good_minutes": len(s), "coverage": len(s) / 1440,
            "xrsb_max": float(s.max()) if len(s) else np.nan}


def day_minutes(day):
    """(combined good 1-minute flux series, satellites used, primary minute count) for one day."""
    parts, used = [], []
    n_primary = 0
    for a, b, prim, sec in segments(day):
        p = load_minutes(prim, day)
        p = p[(p.index >= a) & (p.index < b)] if p is not None else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        n_primary += len(p)
        seg = p
        if sec is not None:
            q = load_minutes(sec, day)
            if q is not None:
                q = q[(q.index >= a) & (q.index < b)]
                q = q[~q.index.floor("min").isin(p.index.floor("min"))]      # only fill gaps
                seg = pd.concat([p, q])
        used.append(f"{prim}+{sec}" if sec else f"{prim}")
        parts.append(seg)
    return pd.concat(parts).sort_index(), used, n_primary


def classify(mx, coverage):
    """Decisions E, H, I."""
    if np.isnan(mx):
        return "missing_nodata"                        # H: neither satellite has data
    if mx >= M1:
        return "missing_M1"                            # E
    if mx >= C1:
        return "incomplete_C1"                         # E
    if coverage < 0.90:
        return "missing_lowcov"                        # I: quiet, but too little of the day seen
    return "genuine_zero"


MERGE_GAP = pd.Timedelta(minutes=5)


def peaks(s):
    """M1+ peaks in a 1-minute true-flux series: runs of minutes >= M1, runs <= MERGE_GAP apart merged,
    peak = the run's max.  Shared by completeness_check.py and audit_2018_2020.py."""
    above = s[s >= M1]
    if above.empty:
        return []
    runs, cur = [], [above.index[0]]
    for t in above.index[1:]:
        if t - cur[-1] <= MERGE_GAP:
            cur.append(t)
        else:
            runs.append(cur); cur = [t]
    runs.append(cur)
    out = []
    for r in runs:
        seg = s[r[0]:r[-1]]
        out.append({"goes_peak": seg.idxmax(), "goes_flux_true": float(seg.max()),
                    "true_class": xrs_class(seg.max())})
    return out


def xrs_class(f):
    for letter, lo in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6)):
        if f >= lo:
            return f"{letter}{f / lo:.1f}"
    return f"{f:.1e}"


if __name__ == "__main__":
    import glob
    empty = sorted(pd.Timestamp(f.split("/")[-1][:8]) for f in glob.glob("data/swpc_events/*events.txt")
                   if "NO EVENT REPORTS" in open(f, encoding="latin-1").read())
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:      # ponytail: 8 parallel downloads, polite to NCEI
        rows = list(ex.map(day_max, empty))
    t = pd.DataFrame(rows)
    t["status"] = [classify(m, c) for m, c in zip(t["xrsb_max"], t["coverage"])]
    t.to_csv("data/goes_empty_days.csv", index=False)
    print(f"{len(t)} empty-report days classified -> data/goes_empty_days.csv")
