"""EUV pilot downloads (decisions: EUV PILOT DOWNLOAD).  JSOC export only (the approved fallback is not implemented here).
Items per episode: 1 = hmi.sharp_720s magnetogram + bitmap at t; 2 = AIA 94 A 12-min (t-24h, t]; 3 = AIA 1600 A 12-min
(t-24h, t]; 4 = AIA 94 A 12-s (t-6h, t] (cost test; files may be deleted after processing -- manifest keeps the record).
AIA: im_patch tracked cutouts, box = HARP bounding box (from item 1's WCS) + 50 arcsec margin, reference time t.
Resumable: an item whose files are already listed in the manifest with a matching SHA-256 is skipped.
Usage: python euv_download.py <item> [HARP ...]      item in 1 2 3 4 all"""
import hashlib, os, re, sys, time, glob
import numpy as np, pandas as pd, drms
from astropy.io import fits

EMAIL = "YOUR_EMAIL_HERE"                      # supplied by the user for JSOC exports
ROOT, MARGIN = "data/euv_pilot", 50.0
EP = pd.read_csv("data/euv_pilot_episodes.csv", parse_dates=["t"])
_lab = pd.read_csv("data/labelled_20100501_20250101.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"],
                   parse_dates=["t_rec_utc"], low_memory=False)
EP = EP.merge(_lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], validate="one_to_one")
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
MAN = f"{ROOT}/manifest.csv"
LOG = f"{ROOT}/download_log.csv"


def box_from_item1(h):
    """HARP bounding box (helioprojective arcsec) from the item-1 magnetogram WCS, + margin."""
    import sunpy.map
    f = sorted(glob.glob(f"{ROOT}/{h}/1/*magnetogram*.fits"))[0]
    m = sunpy.map.Map(f)
    bl, tr = m.bottom_left_coord, m.top_right_coord
    x0, x1 = sorted([bl.Tx.to_value("arcsec"), tr.Tx.to_value("arcsec")])
    y0, y1 = sorted([bl.Ty.to_value("arcsec"), tr.Ty.to_value("arcsec")])
    return dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, width=(x1 - x0) + 2 * MARGIN, height=(y1 - y0) + 2 * MARGIN)


def spec(item, e):
    t = e["t"]
    if item == 1:                                   # the episode row's own T_REC (the record at t)
        return f"hmi.sharp_720s[{e['harpnum']}][{e['t_rec_tai']}]{{magnetogram,bitmap}}", None
    b = box_from_item1(e["harpnum"])
    im = {"im_patch": {"t_ref": t.strftime("%Y-%m-%dT%H:%M:%S"), "t": 0, "r": 0, "c": 0, "locunits": "arcsec",
                       "boxunits": "arcsec", "x": round(b["x"], 1), "y": round(b["y"], 1),
                       "width": round(b["width"], 1), "height": round(b["height"], 1)}}
    fmt = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")
    if item == 2:
        return f"aia.lev1_euv_12s[{fmt(t - pd.Timedelta(hours=24) + pd.Timedelta(minutes=12))}-{fmt(t)}@12m][94]{{image}}", im
    if item == 3:
        return f"aia.lev1_uv_24s[{fmt(t - pd.Timedelta(hours=24) + pd.Timedelta(minutes=12))}-{fmt(t)}@12m][1600]{{image}}", im
    if item == 4:
        return f"aia.lev1_euv_12s[{fmt(t - pd.Timedelta(hours=6) + pd.Timedelta(seconds=12))}-{fmt(t)}][94]{{image}}", im


def append(path, df):
    (pd.concat([pd.read_csv(path), df]) if os.path.exists(path) else df).to_csv(path, index=False)


def manifest_rows(item, h, files, source="JSOC export"):
    rows = []
    for f in files:
        hd = fits.getheader(f, 1) if len(fits.open(f)) > 1 else fits.getheader(f, 0)
        rows.append({"harpnum": h, "item": item, "file": f, "T_OBS": hd.get("T_OBS", hd.get("DATE-OBS")),
                     "wavelength": hd.get("WAVELNTH", "HMI 6173"), "exposure": hd.get("EXPTIME"),
                     "source": source, "size": os.path.getsize(f), "sha256": H(f)})
    return rows


def done(item, h):
    if not os.path.exists(MAN):
        return False
    m = pd.read_csv(MAN)
    m = m[(m["item"] == item) & (m["harpnum"] == h)]
    return len(m) > 0 and all(os.path.exists(f) and H(f) == s for f, s in zip(m["file"], m["sha256"]))


def fetch(item, e):
    h = int(e["harpnum"]); d = f"{ROOT}/{h}/{item}"; os.makedirs(d, exist_ok=True)
    if done(item, h):
        print(f"HARP {h} item {item}: present and verified, skipped"); return
    ds, proc = spec(item, e)
    c = drms.Client(email=EMAIL)
    t0 = time.time()
    note = ""
    method = os.environ.get("JSOC_METHOD", "url")      # "url-tar": whole request as one tar (download-speed test)
    reuse = os.environ.get("JSOC_REQUEST_ID")          # finished request to re-download (no new export)
    try:
        if reuse:
            raise drms.DrmsExportError(f"reuse ({reuse})")
        r = c.export(ds, method=method, protocol="fits", process=proc) if proc else c.export(ds, method=method, protocol="fits")
        if r.status == 7:                               # drms returns (not raises) status 7 on submit
            raise drms.DrmsExportError(r._d.get("error", ""))
    except drms.DrmsExportError as err:                 # JSOC allows 1 pending request per address: attach to it
        rid = re.search(r"\((JSOC_\d{8}_\d+)\)", str(err))
        if not rid:
            raise
        r = c.export_from_id(rid.group(1)); note = f"attached to {rid.group(1)} (submitted earlier)"
        print(f"HARP {h} item {item}: {note}", flush=True)
    while True:                                         # ride out transient network timeouts while JSOC prepares
        try:
            r.wait(sleep=30, timeout=6 * 3600); break
        except (TimeoutError, ConnectionError, OSError) as err:
            print(f"wait: {err!r}; retrying", flush=True); time.sleep(60)
    if not r.has_succeeded():
        raise RuntimeError(f"export failed: {r.status} {ds}")
    t_ready = time.time()
    for p in glob.glob(f"{d}/*.part"):                  # interrupted transfers
        os.remove(p)
    urls = r.urls
    if method == "url-tar":                             # one archive: download, unpack the FITS, delete the tar
        import tarfile
        for k in range(5):
            try:
                got = r.download(d, timeout=600); break
            except (TimeoutError, ConnectionError, OSError) as err:
                print(f"tar attempt {k + 1}: {err!r}", flush=True); time.sleep(30)
        else:
            raise RuntimeError("tar download failed 5 times")
        for tp in glob.glob(f"{d}/*.tar"):
            with tarfile.open(tp) as tf:
                for m in tf.getmembers():
                    if m.isfile() and m.name.endswith(".fits"):
                        m.name = os.path.basename(m.name); tf.extract(m, d)
            os.remove(tp)
        urls = urls.iloc[:0]
    for i, fn in enumerate(urls["filename"]):           # per file: skip present, retry transient stalls
        if os.path.exists(f"{d}/{fn}"):
            continue
        for k in range(5):
            try:
                r.download(d, index=i, timeout=120); break
            except (TimeoutError, ConnectionError, OSError) as err:
                print(f"file {i} attempt {k + 1}: {err!r}", flush=True); time.sleep(30)
        else:
            raise RuntimeError(f"file {fn} failed 5 times")
    dt = time.time() - t0
    files = sorted(glob.glob(f"{d}/*.fits"))  # ponytail: drms "download" paths unreliable; item dir holds only this export
    rows = manifest_rows(item, h, files)
    append(MAN, pd.DataFrame(rows))
    log = pd.DataFrame([{"harpnum": h, "item": item, "spec": ds, "files": len(files),
                         "bytes": sum(r_["size"] for r_ in rows), "wall_s": round(dt, 1), "request_id": r.id,
                         "note": (note + f" method={method}; prep_s={t_ready - t0:.0f}; download_s={time.time() - t_ready:.0f}").strip()}])
    append(LOG, log)
    print(f"HARP {h} item {item}: {len(files)} files, {sum(r_['size'] for r_ in rows)/1e6:.1f} MB, {dt:.0f} s")


if __name__ == "__main__":
    items = [1, 2, 3, 4] if sys.argv[1] == "all" else [int(sys.argv[1])]
    harps = [int(x) for x in sys.argv[2:]] or list(EP["harpnum"])
    for _, e in EP[EP["harpnum"].isin(harps)].iterrows():
        for it in items:
            fetch(it, e)
