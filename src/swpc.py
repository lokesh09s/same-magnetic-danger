"""Flare catalogue from NOAA SWPC's ORIGINAL daily event reports (the catalogue HEK copies).

Source: https://www.ngdc.noaa.gov/stp/space-weather/swpc-products/daily_reports/solar_event_reports/
        YYYY/MM/YYYYMMDDevents.txt   ("Edited Events"), cached under data/swpc_events/.
Used for ALL years 2010-2024 -- never switched per year (decided by user, 2026-09-21).

Rules, each applied identically to every year:
  * only XRA lines (GOES 1-8 A X-ray events) are flares
  * begin time = the event's Begin column on that report's date, UTC
  * region: SWPC writes Reg# as 4 digits; rule is  reg < 10000 -> reg + 10000,  nothing else.
    blank Reg# = UNKNOWN region: kept in the catalogue, never joined (same rule as before)
  * dedup on (begin time, GOES class): SWPC can list one flare from two GOES satellites
    (e.g. G16 and G18); one physical flare must count once.
"""
import os, calendar, urllib.request, urllib.error
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from flares import parse_goes

URL = ("https://www.ngdc.noaa.gov/stp/space-weather/swpc-products/daily_reports/"
       "solar_event_reports/{y}/{m:02d}/{y}{m:02d}{d:02d}events.txt")
CACHE = "data/swpc_events"
MISSING = f"{CACHE}/_missing_days.txt"      # days the archive has no report for (404)


def _path(day):
    return f"{CACHE}/{day:%Y%m%d}events.txt"


def download(day):
    """Cache one day's report. Returns 'ok', 'cached' or 'missing'."""
    if os.path.exists(_path(day)):
        return "cached"
    try:
        with urllib.request.urlopen(URL.format(y=day.year, m=day.month, d=day.day), timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "missing"
        raise
    open(_path(day), "wb").write(data)
    return "ok"


def download_range(lo, hi, workers=8):
    """Cache every daily report in [lo, hi]; record 404 days in MISSING. Returns missing days."""
    os.makedirs(CACHE, exist_ok=True)
    days = list(pd.date_range(pd.Timestamp(lo).normalize(), pd.Timestamp(hi).normalize(), freq="D"))
    with ThreadPoolExecutor(workers) as ex:       # ponytail: 8 threads, polite to NCEI; raise if slow
        status = list(ex.map(download, days))
    missing = [d for d, s in zip(days, status) if s == "missing"]
    known = set(open(MISSING).read().split()) if os.path.exists(MISSING) else set()
    open(MISSING, "w").write("\n".join(sorted(known | {f"{d:%Y-%m-%d}" for d in missing})) + "\n")
    return missing


def missing_days():
    """Days the archive has no report for at all (404). Currently none in 2010-04-29..2025-01-02."""
    return {d for d in open(MISSING).read().split() if d} if os.path.exists(MISSING) else set()


GOES_TABLE = "data/goes_empty_days.csv"     # written by goes_xrs.py


def _goes_status():
    """{day: status} for every empty-report day, from the GOES XRS rules (decisions E, H, I)."""
    if not os.path.exists(GOES_TABLE):
        raise SystemExit(f"{GOES_TABLE} missing -- run goes_xrs.py first. Refusing to treat empty "
                         "SWPC reports as confident zeros.")
    t = pd.read_csv(GOES_TABLE)
    return dict(zip(t["day"].str[:10], t["status"]))


MISSING_STATUSES = ("missing_M1", "missing_nodata", "missing_lowcov")


def label_missing_days():
    """MISSING for labels: 404 days + empty reports that are M1 (E), have no GOES data (H),
    or are quiet on < 90% coverage (I)."""
    return missing_days() | {d for d, s in _goes_status().items() if s in MISSING_STATUSES}


def history_incomplete_days():
    """INCOMPLETE for history: every label-missing day, plus empty reports that reach C1 (E)."""
    return label_missing_days() | {d for d, s in _goes_status().items() if s == "incomplete_C1"}


def to_noaa(reg):
    """The single region-conversion rule."""
    return reg + 10000 if reg < 10000 else reg


# Decision K2 (user, 2026-09-21; supersedes K): everything on the TRUE irradiance scale, per NOAA/NCEI.
# GOES-13/14/15 operational fluxes carried SWPC's 0.7 scaling (NCEI readme sec. 3.1), so they are
# DIVIDED by 0.7; GOES-16+ fluxes are already true irradiance and are used as reported.
TRUE_SCALE_SATS = {"G16", "G17", "G18", "G19"}
OLD_SCALE_SATS = {"G13", "G14", "G15"}
SCALE = 0.7
# Primary pipeline = K2.  FLARE_SCALE=K reproduces the superseded old-scale labels for the diagnostic ablation.
FLARE_SCALE = os.environ.get("FLARE_SCALE", "K2")
assert FLARE_SCALE in ("K2", "K"), FLARE_SCALE

# XRA events SWPC attributes to SDO (5 in 2010-2024, none M1+): neither K nor K2 covers them and
# no source gives their scale.  Kept AS REPORTED and counted as scale_unverified (me, 2026-09-21).
UNVERIFIED_SCALE_OBS = {"SDO"}
SCALE = 0.7


def class_of(flux):
    """GOES letter class of a flux, e.g. 9.8e-6 -> 'C'."""
    for letter, lo in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
        if flux >= lo:
            return letter
    return "A"


# SWPC's own reports contain a few impossible times (3 XRA lines in 2010-2024, all B-class, all 2020,
# e.g. 2020-04-09 Begin '0091' with Max 0932).  An event with a bad begin time is skipped; a bad peak
# time is set missing.  Neither is guessed.  Counted here (me, 2026-09-21).
BAD_TIMES = {"begin": 0, "peak": 0}


def _valid_hhmm(t):
    return len(t) == 4 and t.isdigit() and int(t[:2]) < 24 and int(t[2:]) < 60


def parse_day(day):
    """All XRA events in one cached daily report -> list of dicts (flux on the TRUE scale, K2)."""
    out = []
    if not os.path.exists(_path(day)):
        return out
    for line in open(_path(day), encoding="latin-1"):
        if line.startswith(("#", ":")) or " XRA " not in line:
            continue
        tok = line.replace("+", " ").split()
        i = tok.index("XRA")
        begin = "".join(ch for ch in tok[1] if ch.isdigit())      # strip B/U/A qualifiers
        peak = "".join(ch for ch in tok[2] if ch.isdigit())
        endt = "".join(ch for ch in tok[3] if ch.isdigit())
        if not _valid_hhmm(begin):
            BAD_TIMES["begin"] += 1                                 # missing (////) or garbled, e.g. '0091'
            continue
        if len(peak) == 4 and not _valid_hhmm(peak):
            BAD_TIMES["peak"] += 1
            peak = ""
        cls = tok[i + 2] if len(tok) > i + 2 else ""
        letter, flux_rep = parse_goes(cls)
        if letter is None:
            continue
        obs = tok[i - 2] if i >= 2 else ""
        if FLARE_SCALE == "K":                                     # DIAGNOSTIC ONLY (ablation D2/D6)
            flux = flux_rep * SCALE if obs in TRUE_SCALE_SATS else flux_rep
        elif obs in OLD_SCALE_SATS:
            # K2: remove SWPC's 0.7 -> true flux.  Exact decimal division: binary floating point gives
            # e.g. X1.4 / 0.7 = 1.9999999999999998e-04 instead of 2.0e-04 (also X2.8, X5.6), so exact
            # class values could land just below a boundary.  Decimal keeps them exact.
            flux = float(Decimal(repr(flux_rep)) / Decimal("0.7"))
        elif obs in TRUE_SCALE_SATS or obs in UNVERIFIED_SCALE_OBS:
            flux = flux_rep
        else:
            raise ValueError(f"{day:%Y-%m-%d}: XRA event from unknown satellite {obs!r}: {line.strip()}")
        rest = tok[i + 3:]                                          # [flux] [Reg#]
        reg = next((int(t) for t in rest[1:] if t.isdigit()), None)
        t0 = pd.Timestamp(f"{day:%Y-%m-%d} {begin[:2]}:{begin[2:]}")
        tp = pd.Timestamp(f"{day:%Y-%m-%d} {peak[:2]}:{peak[2:]}") if len(peak) == 4 else pd.NaT
        if tp is not pd.NaT and tp < t0:
            tp += pd.Timedelta(days=1)                              # peak after midnight
        # end time (EUV pilot, decision P2); impossible or missing -> NaT; after midnight -> next day
        te = pd.Timestamp(f"{day:%Y-%m-%d} {endt[:2]}:{endt[2:]}") if _valid_hhmm(endt) else pd.NaT
        if te is not pd.NaT and te < t0:
            te += pd.Timedelta(days=1)
        out.append({"start": t0, "peak": tp, "end": te,
                    "goes_class": cls, "flux_reported": flux_rep,   # as SWPC printed it
                    "flux": flux, "cls": class_of(flux),            # harmonised, true scale (K2)
                    "noaa_ar": to_noaa(reg) if reg is not None else pd.NA, "obs": obs})
    return out


def load(lo, hi):
    """All XRA flares with begin in [lo, hi], deduplicated. Returns (flares, n_duplicates)."""
    days = pd.date_range(pd.Timestamp(lo).normalize(), pd.Timestamp(hi).normalize(), freq="D")
    rows = [e for d in days for e in parse_day(d)]
    fl = pd.DataFrame(rows, columns=["start", "peak", "end", "goes_class", "flux_reported", "flux", "cls",
                                     "noaa_ar", "obs"])
    fl = fl[(fl["start"] >= pd.Timestamp(lo)) & (fl["start"] <= pd.Timestamp(hi))]
    n0 = len(fl)
    # dedup on (begin, REPORTED class); if one copy has a region and the other doesn't, keep the region
    fl = (fl.sort_values("noaa_ar", na_position="last")
            .drop_duplicates(subset=["start", "goes_class"]).sort_values("start"))
    return fl.reset_index(drop=True), n0 - len(fl)


def fetch(lo, hi, verbose=True):
    """Same interface as flares.fetch: (joinable flares, joinable M1+), unknown M1+ on attrs."""
    fl, n_dup = load(lo, hi)
    unknown = fl["noaa_ar"].isna()
    n_unknown_m1 = int((unknown & (fl["flux"] >= 1e-5)).sum())
    fl = fl[~unknown].copy()
    fl["noaa_ar"] = fl["noaa_ar"].astype(int)
    m1 = fl[fl["flux"] >= 1e-5].copy()
    m1.attrs["n_unknown_m1"] = n_unknown_m1
    if verbose:
        miss = sorted(d for d in missing_days()
                      if pd.Timestamp(lo).normalize() <= pd.Timestamp(d) <= pd.Timestamp(hi))
        print(f"source: SWPC original event reports ({CACHE})")
        print(f"flares (XRA) in window: {len(fl) + int(unknown.sum())}")
        print(f"duplicates removed: {n_dup}  (on begin time, GOES class)")
        print(f"UNKNOWN region (blank Reg#), not joined: {int(unknown.sum())}  (of which M1+: {n_unknown_m1})")
        print(f"joinable: {len(fl)};  M1+ retained: {len(m1)}")
        print(f"days with no SWPC report in window: {len(miss)} {miss[:5]}")
        print("class counts:", fl["cls"].value_counts().to_dict())
    return fl, m1


def conversion_report(lo, hi):
    """Decision K2 audit: events whose letter class changed under the /0.7 conversion."""
    fl, _ = load(lo, hi)
    conv = fl[fl["obs"].isin(OLD_SCALE_SATS)]
    rep_cls = conv["goes_class"].str[0]
    changed = conv[rep_cls != conv["cls"]]
    return {"events": len(fl), "converted_div0.7": len(conv), "class_changed": len(changed),
            "C_to_M": int(((rep_cls == "C") & (conv["cls"] == "M")).sum()),
            "M_to_X": int(((rep_cls == "M") & (conv["cls"] == "X")).sum()),
            "B_to_C": int(((rep_cls == "B") & (conv["cls"] == "C")).sum()),
            "A_to_B": int(((rep_cls == "A") & (conv["cls"] == "B")).sum()),
            "scale_unverified": int(fl["obs"].isin(UNVERIFIED_SCALE_OBS).sum()),
            "M1plus_reported": int((fl["flux_reported"] >= 1e-5).sum()),
            "M1plus_harmonised": int((fl["flux"] >= 1e-5).sum())}
