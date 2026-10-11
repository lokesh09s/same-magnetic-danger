"""The monthly chunk list, shared by run_all.py and every report that reads chunk files.
Reports must read exactly these files -- a glob would also pick up ad-hoc test runs
(e.g. data/labelled_20100501_20100801.csv) and double-count them."""
from datetime import date

import os
# Default = the 2010-2024 dataset.  CHUNK_RANGE="2025-01-01,2026-08-17" selects the confirmation set's chunks.
RANGE = tuple(os.environ["CHUNK_RANGE"].split(",")) if os.environ.get("CHUNK_RANGE") else ("2010-05-01", "2025-01-01")


def months(start=RANGE[0], end=RANGE[1]):
    """[(chunk_start, chunk_end), ...] month boundaries, half-open."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out, cur = [], s
    while cur < e:
        nxt = date(cur.year + cur.month // 12, cur.month % 12 + 1, 1)
        out.append((cur.isoformat(), min(nxt, e).isoformat()))
        cur = nxt
    return out


def files(kind):
    """kind = 'raw_sharp', 'labelled' or 'labels_hek/labelled' -> [(chunk_start, path), ...]."""
    return [(a, f"data/{kind}_{a}_{b}.csv".replace("-", "")) for a, b in months()]
