"""Decision O: fetch the Bobra & Couvidat (2015) SHARP keywords missing from the original query,
for the SAME record sets (one per monthly chunk), keywords only.  Resumable: a chunk whose file exists
is skipped.  Original raw files are never modified -- extras go to data/raw_sharp_extra_<chunk>.csv.

Available as JSOC keywords (queried here): TOTUSJZ, MEANPOT, SHRGT45 (in B&C's 13-feature SVM set) and
MEANGAM, MEANGBT, MEANGBZ, MEANGBH, MEANJZH, MEANJZD, MEANALP (B&C "Discarded").
NOT keywords in hmi.sharp_cea_720s or hmi.sharp_720s (checked 2026-09-21): TOTBSQ, TOTFZ, EPSZ, TOTFX,
TOTFY, EPSX, EPSY -- the Lorentz-force parameters.  Not fetched; see decisions.md.
"""
import os, sys, time
import drms
from chunks import months

EXTRA = ["TOTUSJZ", "MEANPOT", "SHRGT45",
         "MEANGAM", "MEANGBT", "MEANGBZ", "MEANGBH", "MEANJZH", "MEANJZD", "MEANALP"]
KEYS = ["HARPNUM", "T_REC"] + EXTRA
jsoc = lambda d: d.replace("-", ".") + "_TAI"

c = drms.Client()
ch = months(*sys.argv[1:3]) if len(sys.argv) >= 3 else months()
_ov = os.environ.get("JSOC_END_OVERRIDE", "")                  # same final-chunk override as build_dataset.py
for i, (a, b) in enumerate(ch, 1):
    out = f"data/raw_sharp_extra_{a}_{b}.csv".replace("-", "")
    if os.path.exists(out):
        continue
    end = _ov.split("|")[1] if _ov and _ov.split("|")[0] == b else jsoc(b)
    qs = f"hmi.sharp_cea_720s[][{jsoc(a)}-{end}@1h]"           # identical record set to build_dataset.py
    for attempt in range(1, 6):
        try:
            r = c.query(qs, key=",".join(KEYS))
            break
        except Exception as e:                                  # JSOC timeouts / resets
            print(f"  {a}: attempt {attempt} failed: {type(e).__name__}", flush=True)
            if attempt == 5:
                sys.exit(f"chunk {a} failed; re-run to resume")
            time.sleep(60 * attempt)
    r.to_csv(out + ".tmp", index=False)
    os.replace(out + ".tmp", out)                               # never leave a half-written chunk
    print(f"[{i}/{len(ch)}] {a}  {len(r)} rows", flush=True)
print("done")
