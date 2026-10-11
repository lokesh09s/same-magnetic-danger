"""Look 1 (early) coverage check — METADATA ONLY (decided by: user, 2026-10-09; code by Claude Code (AI)).
SHARP: JSOC jsoc_info op=rs_summary returns only a record COUNT per queried slot (no keyword values, no HARPNUM, nothing saved).
SWPC: NCEI directory listings (file names only; no report is downloaded). GOES XRS: NCEI directory listings (file names only).
Usage: python prospective_look1_coverage.py > prospective_look1_coverage.log
       python prospective_look1_coverage.py hourly >> prospective_look1_coverage.log   (every hourly slot 2026-08-17 00:00 .. 2026-09-03 23:00 TAI)"""
import json, re, sys, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

START, TODAY = date(2026, 8, 17), date(2026, 10, 9)
JSOC = "http://jsoc.stanford.edu/cgi-bin/ajax/jsoc_info?"
SWPC = "https://www.ngdc.noaa.gov/stp/space-weather/swpc-products/daily_reports/solar_event_reports/{y}/{m:02d}/"
GOES = "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes{s}/l2/data/xrsf-l2-avg1m_science/{y}/{m:02d}/"


def get(url):
    return urllib.request.urlopen(url, timeout=120).read().decode()


def sharp_count(trec):
    """Number of hmi.sharp_cea_720s records at one T_REC slot (count only)."""
    q = urllib.parse.urlencode({"ds": f"hmi.sharp_cea_720s[][{trec}]", "op": "rs_summary"})
    r = json.loads(get(JSOC + q))
    return int(r.get("count", 0))


def months():
    d = START.replace(day=1)
    while d <= TODAY:
        yield d.year, d.month
        d = (d + timedelta(days=32)).replace(day=1)


def listed_days(url_tpl, pat, **kw):
    days = set()
    for y, m in months():
        try:
            html = get(url_tpl.format(y=y, m=m, **kw))
        except Exception as e:
            print(f"  listing unavailable {url_tpl.format(y=y, m=m, **kw)}: {e.__class__.__name__}")
            continue
        days |= {datetime.strptime(s, "%Y%m%d").date() for s in re.findall(pat, html)}
    return days


if __name__ == "__main__" and sys.argv[1:] == ["hourly"]:
    print(f"\nHOURLY SHARP CHECK (count only), run by Claude Code at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC: 2026-08-17 00:00 .. 2026-09-03 23:00 TAI")
    h, end, counts = datetime(2026, 8, 17), datetime(2026, 9, 3, 23), {}
    while h <= end:
        counts[h] = sharp_count(f"{h:%Y.%m.%d_%H}:00_TAI")
        h += timedelta(hours=1)
    missing = [k for k, n in counts.items() if n == 0]
    print(f"slots {len(counts)}; with >= 1 record {len(counts) - len(missing)}; with 0 records {len(missing)}")
    print("records per slot: min", min(counts.values()), "median", sorted(counts.values())[len(counts) // 2], "max", max(counts.values()))
    print("slots with 0 records:", [f"{k:%Y-%m-%d %H}:00" for k in missing] or "none")
    sys.exit(0)

if __name__ == "__main__":
    print(f"LOOK 1 (EARLY) COVERAGE CHECK — metadata only; run by Claude Code at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    # SHARP: daily slots at 00:00 TAI, then hourly on the last day that has records
    daily = {}
    d = START
    while d <= TODAY:
        daily[d] = sharp_count(f"{d:%Y.%m.%d}_00:00_TAI")
        d += timedelta(days=1)
    with_recs = [d for d, n in daily.items() if n > 0]
    print("SHARP hmi.sharp_cea_720s, daily 00:00 TAI slots with >= 1 record:",
          f"{with_recs[0]} .. {with_recs[-1]}" if with_recs else "none", f"({len(with_recs)} of {len(daily)} days)")
    gaps = [d for d in daily if with_recs and with_recs[0] <= d <= with_recs[-1] and daily[d] == 0]
    print("  days inside that span with 0 records at 00:00 TAI:", gaps or "none")
    if with_recs:
        last = with_recs[-1]
        hourly = {h: sharp_count(f"{last:%Y.%m.%d}_{h:02d}:00_TAI") for h in range(24)}
        nxt = last + timedelta(days=1)
        hourly_next = {h: sharp_count(f"{nxt:%Y.%m.%d}_{h:02d}:00_TAI") for h in range(24)}
        print(f"  hourly record counts {last}: " + " ".join(f"{h:02d}:{n}" for h, n in hourly.items()))
        print(f"  hourly record counts {nxt}: " + " ".join(f"{h:02d}:{n}" for h, n in hourly_next.items()))
    # SWPC daily event reports
    sw = listed_days(SWPC, r"(\d{8})events\.txt")
    sw_span = sorted(x for x in sw if x >= START - timedelta(days=2))
    print("SWPC daily event reports listed (NCEI):", f"{sw_span[0]} .. {sw_span[-1]}" if sw_span else "none")
    if sw_span:
        miss = [sw_span[0] + timedelta(days=i) for i in range((sw_span[-1] - sw_span[0]).days + 1)
                if sw_span[0] + timedelta(days=i) not in sw]
        print("  missing days inside that span:", miss or "none")
    # GOES XRS 1-min science files
    for s in (18, 19):
        g = sorted(x for x in listed_days(GOES, rf"sci_xrsf-l2-avg1m_g{s}_d(\d{{8}})_v[\d-]+\.nc", s=s) if x >= START)
        miss = [g[0] + timedelta(days=i) for i in range((g[-1] - g[0]).days + 1) if g[0] + timedelta(days=i) not in g] if g else []
        print(f"GOES-{s} XRS avg1m science daily files listed:", f"{g[0]} .. {g[-1]}" if g else "none",
              "| missing inside span:", miss or "none")
