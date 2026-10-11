"""FULL EUV STUDY, 94 A only (decisions.md 2026-09-23 amendment). Outputs only under data/euv_full/.
Usage: python euv_full.py hmi_check | dryrun | hmi | run | counts"""
import glob, hashlib, io, json, os, socket, sys, tarfile, time, urllib.request
socket.setdefaulttimeout(120)
import numpy as np, pandas as pd, sunpy.map, drms, astropy.units as u
from astropy.io import fits
from euv_download import EMAIL
from euv_pilot import pil_mask, ar_mask

R = "data/euv_full"
for sub in ["dryrun", "hmi", "aia", "series", "results", "logs"]:
    os.makedirs(f"{R}/{sub}", exist_ok=True)
MARGIN = 50.0


def log(msg, f="logs/run.log"):
    print(msg, flush=True)
    with open(f"{R}/{f}", "a") as fh:
        fh.write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M:%S} {msg}\n")


# ---------------------------------------------------------------- HMI masks: direct access (url_quick, as-is) + keyword header
def hmi_direct(harp, trec, dest, keys):
    """download magnetogram+bitmap as-is; rebuild headers from a keyword query (keys = header keys of the exported files).
    Returns (magnetogram path, bitmap path, seconds)."""
    t0 = time.time(); os.makedirs(dest, exist_ok=True)
    c = drms.Client(email=EMAIL)
    ds = f"hmi.sharp_720s[{harp}][{trec}]"
    r = c.export(ds + "{magnetogram,bitmap}", method="url_quick", protocol="as-is")
    if r.status != 0 or not len(r.urls):
        raise RuntimeError(f"url_quick failed {ds}: status {r.status}")
    kw = c.query(ds, key=",".join(keys)).iloc[0]
    out = {}
    for _, u_ in r.urls.iterrows():
        seg = u_.filename.replace(".fits", "")
        raw = urllib.request.urlopen(u_.url).read()
        with fits.open(io.BytesIO(raw)) as hd:
            hdu = hd[1] if len(hd) > 1 else hd[0]
            data = hdu.data.astype(np.float64) if seg == "magnetogram" else hdu.data
        h = fits.Header()
        for k in keys:
            v = kw.get(k)
            if v is None or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and v.strip() == ""):
                continue
            v = v.item() if hasattr(v, "item") else v
            if isinstance(v, str):
                v = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in v)   # version strings contain newlines
            h[k] = v
        p = f"{dest}/hmi.sharp_720s.{harp}.{trec.replace('.', '').replace(':', '')}.{seg}.fits"
        fits.PrimaryHDU(data=data, header=h).writeto(p + ".tmp", overwrite=True); os.replace(p + ".tmp", p)
        out[seg] = p
    return out["magnetogram"], out["bitmap"], time.time() - t0


WCS_KEYS = None


def header_keys(ref_file):
    h = fits.getheader(ref_file, 1) if len(fits.open(ref_file)) > 1 else fits.getheader(ref_file)
    skip = {"SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND", "XTENSION", "PCOUNT", "GCOUNT", "TFIELDS",
            "ZIMAGE", "ZBITPIX", "ZNAXIS", "ZNAXIS1", "ZNAXIS2", "ZTILE1", "ZTILE2", "ZCMPTYPE", "ZNAME1", "ZVAL1",
            "ZNAME2", "ZVAL2", "ZSIMPLE", "ZQUANTIZ", "ZDITHER0", "BLANK", "BZERO", "BSCALE", "CHECKSUM", "DATASUM",
            "COMMENT", "HISTORY", ""}
    return [k for k in h.keys() if k not in skip and not k.startswith(("TTYPE", "TFORM", "ZHECKSUM", "ZDATASUM"))]


def hmi_check():
    """step 2a: direct access vs the pilot's exported files, 3 pilot records."""
    from euv_download import EP
    from euv_dctrl import samples, hmi_to_frame
    rows = []
    ref0 = glob.glob("data/euv_pilot/4231/1/*magnetogram*.fits")[0]
    keys = header_keys(ref0)
    exp = pd.read_csv("data/euv_pilot/download_log.csv"); exp = exp[exp["item"] == 1].set_index("harpnum").wall_s
    for e in EP.itertuples():
        h = int(e.harpnum)
        m_old = sunpy.map.Map(glob.glob(f"data/euv_pilot/{h}/1/*magnetogram*.fits")[0])
        b_old = fits.open(glob.glob(f"data/euv_pilot/{h}/1/*bitmap*.fits")[0])[-1].data
        mp, bp, dt = hmi_direct(h, e.t_rec_tai, f"{R}/dryrun/hmi_direct/{h}", keys)
        m_new = sunpy.map.Map(mp); b_new = fits.getdata(bp)
        a, b = m_old.data.astype(float), m_new.data.astype(float)
        fin = np.isfinite(a) & np.isfinite(b)
        S_old, *_ = samples(m_old.data, b_old); S_new, *_ = samples(m_new.data, b_new)
        aia = sunpy.map.Map(sorted(glob.glob(f"data/euv_pilot/{h}/2/*.fits"))[-1])
        idx_old, idx_new = hmi_to_frame(m_old, aia), hmi_to_frame(m_new, aia)
        rows.append(dict(harpnum=h, shape_equal=a.shape == b.shape, nan_pattern_equal=bool((np.isnan(a) == np.isnan(b)).all()),
                         max_abs_diff_finite=float(np.nanmax(np.abs(a[fin] - b[fin]))) if fin.any() else np.nan,
                         bitmap_equal=bool((np.asarray(b_old) == np.asarray(b_new)).all()),
                         pil_diff_px=int((pil_mask(m_old.data) != pil_mask(m_new.data)).sum()),
                         ar_diff_px=int((ar_mask(m_old.data) != ar_mask(m_new.data)).sum()),
                         dctrl_samples_equal=all(np.array_equal(S_old[k], S_new[k]) for k in S_old),
                         aia_mapping_equal=bool(np.array_equal(idx_old, idx_new)),
                         direct_s=round(dt, 1), export_wall_s=float(exp.get(h, np.nan))))
    df = pd.DataFrame(rows)
    df["PASS"] = (df.shape_equal & df.nan_pattern_equal & (df.max_abs_diff_finite == 0) & df.bitmap_equal
                  & (df.pil_diff_px == 0) & (df.ar_diff_px == 0))
    df.to_csv(f"{R}/dryrun/hmi_direct_check.csv", index=False)
    pd.set_option("display.width", 250); log("\n" + df.to_string(index=False), "logs/dryrun.log")
    json.dump({"keys": keys}, open(f"{R}/hmi_header_keys.json", "w"))
    return bool(df.PASS.all())



# ================================================================ episodes and exports
def episodes(pilot=False):
    lab = pd.read_csv("data/labelled_20100501_20250101.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"],
                      parse_dates=["t_rec_utc"], low_memory=False)
    if pilot:
        from euv_download import EP
        e = EP[["harpnum", "t", "t_rec_tai", "noaa_ars"]].copy()
    else:
        c = pd.read_csv("data/stage3/cohort_dev.csv", parse_dates=["t"])
        e = c[["harpnum", "t", "noaa_ars"]].merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"],
                                                     how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert e.t_rec_tai.notna().all()
    e["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(e.harpnum, e.t)]
    return e.sort_values(["harpnum", "t"]).reset_index(drop=True)


def unpack(dest):
    nb = 0
    for tp in glob.glob(f"{dest}/*.tar"):
        nb += os.path.getsize(tp)
        with tarfile.open(tp) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith(".fits"):
                    m.name = os.path.basename(m.name); tf.extract(m, dest)
        os.remove(tp)
    return nb


def submit(ds, proc=None, tries=3):
    """submit one url-tar export (one pending at a time); retries with backoff; returns ExportRequest."""
    c = drms.Client(email=EMAIL)
    for k in range(tries):
        try:
            r = c.export(ds, method="url-tar", protocol="fits", process=proc) if proc else c.export(ds, method="url-tar", protocol="fits")
            if r.status == 7:
                raise RuntimeError(f"status 7: {r._d.get('error')}")
            return r
        except Exception as err:
            log(f"submit retry {k + 1}/{tries}: {err!r}"); time.sleep(60 * (k + 1))
    raise RuntimeError(f"submit failed: {ds}")


def wait(r):
    t0 = time.time()
    while True:
        try:
            r.wait(sleep=20, timeout=6 * 3600); break
        except (TimeoutError, ConnectionError, OSError) as err:
            log(f"wait retry: {err!r}"); time.sleep(60)
    if not r.has_succeeded():
        raise RuntimeError(f"export failed status {r.status}")
    return time.time() - t0


def download(r, dest):
    t0 = time.time(); os.makedirs(dest, exist_ok=True)
    for p in glob.glob(f"{dest}/*.tar*"):
        os.remove(p)
    for k in range(5):
        try:
            r.download(dest, timeout=900); break
        except (TimeoutError, ConnectionError, OSError) as err:
            log(f"tar retry {k + 1}: {err!r}"); time.sleep(30 * (k + 1))
    else:
        raise RuntimeError("tar download failed")
    return unpack(dest), time.time() - t0


def hmi_ds(h, eps):
    return f"hmi.sharp_720s[{h}][{','.join(eps.t_rec_tai)}]{{magnetogram,bitmap}}"


def hmi_files(dest, trec):
    tag = trec.replace(".", "").replace(":", "")
    m = glob.glob(f"{dest}/hmi.sharp_720s.*.{tag}.magnetogram.fits"); b = glob.glob(f"{dest}/hmi.sharp_720s.*.{tag}.bitmap.fits")
    if m and b:
        return m[0], b[0]
    found = {}                                          # JSOC sometimes names files by record number: match the header
    for f in glob.glob(f"{dest}/hmi.sharp_720s.*.fits"):
        seg = "magnetogram" if f.endswith("magnetogram.fits") else "bitmap" if f.endswith("bitmap.fits") else None
        if seg and str(fits.getheader(f, 1).get("T_REC", ""))[:19] == trec[:19]:
            found[seg] = f
    return (found["magnetogram"], found["bitmap"]) if len(found) == 2 else (None, None)


def aia_spec(h, eps, hmi_dir):
    """one tracked 94 A cutout export per HARP covering all its windows (decisions.md implementation details)."""
    ext, cen = [], None
    for e in eps.itertuples():
        mag = sunpy.map.Map(hmi_files(hmi_dir, e.t_rec_tai)[0])
        bl, tr = mag.bottom_left_coord, mag.top_right_coord
        x0, x1 = sorted([bl.Tx.to_value("arcsec"), tr.Tx.to_value("arcsec")]); y0, y1 = sorted([bl.Ty.to_value("arcsec"), tr.Ty.to_value("arcsec")])
        ext.append((x1 - x0, y1 - y0)); cen = ((x0 + x1) / 2, (y0 + y1) / 2)     # last = latest episode (sorted by t)
    t_ref = eps.t.max(); t_first = eps.t.min()
    im = {"im_patch": {"t_ref": t_ref.strftime("%Y-%m-%dT%H:%M:%S"), "t": 0, "r": 0, "c": 0, "locunits": "arcsec",
                       "boxunits": "arcsec", "x": round(cen[0], 1), "y": round(cen[1], 1),
                       "width": round(max(w for w, _ in ext) + 2 * MARGIN, 1), "height": round(max(v for _, v in ext) + 2 * MARGIN, 1)}}
    fmt = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"aia.lev1_euv_12s[{fmt(t_first - pd.Timedelta(hours=24) + pd.Timedelta(minutes=12))}-{fmt(t_ref)}@12m][94]{{image}}", im


def expected_frames(eps):
    return len(pd.date_range(eps.t.min() - pd.Timedelta("24h") + pd.Timedelta("12min"), eps.t.max(), freq="12min"))


def trec_of(p):
    """AIA T_REC from the file name, e.g. aia.lev1_euv_12s.2014-06-11T131125Z.94.image.fits -> 2014-06-11 13:11:25"""
    return pd.to_datetime(os.path.basename(p).split(".")[2], format="%Y-%m-%dT%H%M%SZ")


def valid_fits(p):
    try:
        if os.path.getsize(p) < 2880:
            return False
        h = fits.getheader(p, 1) if len(fits.open(p)) > 1 else fits.getheader(p)
        return "T_REC" in h or "T_OBS" in h
    except Exception:
        return False


# ================================================================ per-episode computation (both versions)
def compute_episode(ep, hmi_dir, aia_dir, series_dir):
    """ep: dict(eid, harpnum, t, t_rec_tai, noaa_ars). Same D-CTRL computation as euv_dctrl.run (cutout); returns results
    for PRIMARY (flare frames kept) and SENSITIVITY (flare frames excluded, P2 amended)."""
    import swpc
    from astropy.time import Time
    from aiapy.calibrate import update_pointing
    from aiapy.calibrate.utils import get_pointing_table
    from euv_run import register_cutout
    from euv_dctrl import samples, hmi_to_frame, frame_means, summarise
    from euv_pilot import flare_excluded, SAT_DN
    t = pd.Timestamp(ep["t"])
    mp, bp = hmi_files(hmi_dir, ep["t_rec_tai"])
    mag = sunpy.map.Map(mp); bitmap = fits.open(bp)[-1].data
    S, short, n = samples(mag.data, bitmap)
    lo = t - pd.Timedelta("24h")
    paths = sorted(p for p in glob.glob(f"{aia_dir}/*.fits")
                   if lo < trec_of(p) <= t)
    ptab = get_pointing_table("JSOC", time_range=(Time(t - pd.Timedelta("26h")), Time(t + pd.Timedelta("2h"))))
    rows = []
    for f in paths:
        m = sunpy.map.Map(f)
        q, exp = int(m.meta.get("quality", 0)), m.exposure_time.to_value("s")
        raw = m.data.astype(float)
        if exp <= 0:
            raw[:] = np.nan; exp = 1.0
        nsat = int((raw > SAT_DN).sum())
        raw[raw > SAT_DN] = np.nan
        pt_ok = True
        try:
            m = update_pointing(m, pointing_table=ptab)
        except IndexError:
            pass
        except TypeError:                               # SAT_ROT missing in the header: keep header pointing (counted)
            pt_ok = False
        r = register_cutout(sunpy.map.Map(raw / exp, m.meta))
        idx = hmi_to_frame(mag, r)
        rows.append(dict(t_obs=pd.Timestamp(m.meta["t_obs"].rstrip("Z")), t_rec=trec_of(f),
                         quality=q, exptime=exp, sat_px=nsat, sat_flag=nsat > 0, pointing_updated=pt_ok, frac_outside=float((idx < 0).mean()),
                         **frame_means(r.data, idx, S)))
    s = pd.DataFrame(rows)
    ev, _ = swpc.load(t - pd.Timedelta("2D"), t)
    regions = {int(x) for x in str(ep["noaa_ars"]).split(",") if x.strip()}
    flare, na, nb, _ = flare_excluded(s.t_obs, ev, regions)
    med = s.loc[(s.quality == 0) & (s.exptime > 0), "exptime"].median()
    s["q_ok"], s["exp_ok"], s["flare"] = s.quality == 0, s.exptime >= 0.5 * med, flare
    s["valid_primary"] = s.q_ok & s.exp_ok & s.box.notna()
    s["valid_sens"] = s.valid_primary & ~s.flare
    s.to_csv(f"{series_dir}/{ep['eid']}.csv", index=False)
    slots = pd.date_range(lo + pd.Timedelta("12min"), t, freq="12min").to_numpy()
    out = dict(eid=ep["eid"], harpnum=ep["harpnum"], t=t, frames=len(s), n_pix=n, ctrl_short=short,
               excl_quality=int((~s.q_ok).sum()), excl_exposure=int((~s.exp_ok).sum()), excl_flare=int(s.flare.sum()),
               excl_flare_P2a=na, excl_flare_P2b=nb, sat_flagged_frames=int(s.sat_flag.sum()), sat_pixels=int(s.sat_px.sum()),
               frames_no_satrot=int((~s.pointing_updated).sum()), frames_no_satrot_q_ok=int((~s.pointing_updated & s.q_ok).sum()),
               max_frac_outside_valid=float(s.loc[s.valid_primary, "frac_outside"].max()) if s.valid_primary.any() else np.nan)
    for ver, col in [("primary", "valid_primary"), ("sens", "valid_sens")]:
        v = s[s[col]]; tv = v.t_obs.to_numpy()
        fill = np.mean([len(tv) > 0 and np.abs(tv - sl).min() <= np.timedelta64(6, "m") for sl in slots])
        r_ = summarise(s.assign(valid=s[col]), S, short, n, ver) if len(v) >= 3 else {}
        out.update({f"{ver}_valid_frames": len(v), f"{ver}_fill": round(float(fill), 4),
                    **{f"{ver}_{k}": r_.get(k, np.nan) for k in ("dCV", "dCV_sd", "CV_PIL", "CV_ctrl", "CV_box", "dCV_far")}})
    return out


# ================================================================ driver (dry run and full run)
def run_pipeline(eps, root, workers=8, progress_every=7200, compute=True):
    import threading
    from concurrent.futures import ProcessPoolExecutor
    for sub in ["hmi", "aia", "series", "results"]:
        os.makedirs(f"{root}/{sub}", exist_ok=True)
    elog = f"{root}/exports.csv"; flog = f"{root}/failed.csv"
    pool = ProcessPoolExecutor(workers) if compute else None                  # compute=False: download only
    futs = {}; threads = []; t_start = time.time(); last_prog = time.time()
    lock = threading.Lock()

    def rec(row, path):
        with lock:
            pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)

    def dispatch(h, g):
        if not compute:
            return
        for e in g.itertuples():
            if os.path.exists(f"{root}/results/{e.eid}.json"):
                continue
            ep = dict(eid=e.eid, harpnum=int(e.harpnum), t=str(e.t), t_rec_tai=e.t_rec_tai, noaa_ars=str(e.noaa_ars))
            futs[e.eid] = pool.submit(compute_episode, ep, f"{root}/hmi/{h}", f"{root}/aia/{h}", f"{root}/series")

    def aia_worker(h, g, r, prep):
        try:
            nb, dl = download(r, f"{root}/aia/{h}")
            ok = [p for p in glob.glob(f"{root}/aia/{h}/*.fits") if valid_fits(p)]
            rec(dict(harpnum=h, kind="aia", request_id=r.id, prep_s=round(prep, 1), download_s=round(dl, 1), files=len(ok),
                     expected=expected_frames(g), bytes=nb, error=""), elog)
            dispatch(h, g)
        except Exception as err:
            rec(dict(harpnum=h, kind="aia", request_id=getattr(r, "id", ""), error=repr(err)), flog)

    harps = list(eps.groupby("harpnum"))
    for i, (h, g) in enumerate(harps):
        try:
            hdir = f"{root}/hmi/{h}"
            if not all(hmi_files(hdir, x)[0] for x in g.t_rec_tai):
                for k in range(3):
                    try:
                        r = submit(hmi_ds(h, g)); prep = wait(r); nb, dl = download(r, hdir)
                        rec(dict(harpnum=h, kind="hmi", request_id=r.id, prep_s=round(prep, 1), download_s=round(dl, 1),
                                 files=len(glob.glob(f"{hdir}/*.fits")), expected=2 * len(g), bytes=nb, error=""), elog)
                        break
                    except Exception as err:
                        log(f"HARP {h} HMI attempt {k + 1}: {err!r}"); time.sleep(120 * (k + 1))
                assert all(hmi_files(hdir, x)[0] for x in g.t_rec_tai), "HMI files missing after export"
            adir = f"{root}/aia/{h}"
            have = [p for p in glob.glob(f"{adir}/*.fits") if valid_fits(p)] if os.path.isdir(adir) else []
            if len(have) >= 0.97 * expected_frames(g):
                dispatch(h, g)
            else:
                ds, proc = aia_spec(h, g, hdir)
                for k in range(3):
                    try:
                        r = submit(ds, proc); prep = wait(r); break          # export complete -> next HARP may be submitted
                    except Exception as err:
                        log(f"HARP {h} AIA attempt {k + 1}: {err!r}"); time.sleep(120 * (k + 1))
                else:
                    raise RuntimeError("AIA export failed 3 times")
                th = threading.Thread(target=aia_worker, args=(h, g, r, prep)); th.start(); threads.append(th)
        except Exception as err:
            rec(dict(harpnum=h, kind="harp", request_id="", error=repr(err)), flog); log(f"HARP {h} FAILED: {err!r}")
        if time.time() - last_prog > progress_every or i == len(harps) - 1:
            done_r = len(glob.glob(f"{root}/results/*.json"))
            gb = sum(os.path.getsize(p) for p in glob.glob(f"{root}/aia/*/*.fits")) / 1e9
            el = (time.time() - t_start) / 3600
            log(f"PROGRESS {pd.Timestamp.now():%H:%M}: HARPs submitted {i + 1}/{len(harps)}, episode results {done_r}/{len(eps)}, "
                f"AIA files {len(glob.glob(f'{root}/aia/*/*.fits'))}, {gb:.1f} GB, failures "
                f"{sum(1 for _ in open(flog)) - 1 if os.path.exists(flog) else 0}, elapsed {el:.1f} h, "
                f"ETA ~{el / (i + 1) * (len(harps) - i - 1):.1f} h", "logs/progress.log")
            last_prog = time.time()
        for eid, f in list(futs.items()):                       # harvest finished computations
            if f.done():
                try:
                    json.dump({k: str(v) for k, v in f.result().items()}, open(f"{root}/results/{eid}.json", "w"))
                except Exception as err:
                    rec(dict(harpnum=eid.split("_")[0], kind="compute", request_id=eid, error=repr(err)), flog)
                futs.pop(eid)
    for th in threads:
        th.join()
    for eid, f in list(futs.items()):
        try:
            json.dump({k: str(v) for k, v in f.result().items()}, open(f"{root}/results/{eid}.json", "w"))
        except Exception as err:
            rec(dict(harpnum=eid.split("_")[0], kind="compute", request_id=eid, error=repr(err)), flog)
    if not compute:
        return None
    pool.shutdown()
    res = [json.load(open(p)) for p in sorted(glob.glob(f"{root}/results/*.json"))]
    pd.DataFrame(res).to_csv(f"{root}/episode_results.csv", index=False)
    return pd.DataFrame(res)


def dryrun():
    eps = episodes(pilot=True); root = f"{R}/dryrun"
    t0 = time.time(); res = run_pipeline(eps, root, workers=8); log(f"dry run pipeline wall {time.time() - t0:.0f} s", "logs/dryrun.log")
    # single-process recomputation from the same downloaded files
    os.makedirs(f"{root}/series_single", exist_ok=True)
    single = [compute_episode(dict(eid=e.eid, harpnum=int(e.harpnum), t=str(e.t), t_rec_tai=e.t_rec_tai, noaa_ars=str(e.noaa_ars)),
                              f"{root}/hmi/{e.harpnum}", f"{root}/aia/{e.harpnum}", f"{root}/series_single")
              for e in eps.itertuples()]
    single = pd.DataFrame(single).set_index("eid"); multi = res.set_index("eid")
    pil = pd.read_csv("data/euv_pilot/dctrl_cutout.csv"); pil = pil[pil.tag == "cutout_94"].set_index("harpnum").dCV
    rows = []
    for e in eps.itertuples():
        mv = float(multi.loc[e.eid, "sens_dCV"]); sv = float(single.loc[e.eid, "sens_dCV"])
        mp_, sp_ = float(multi.loc[e.eid, "primary_dCV"]), float(single.loc[e.eid, "primary_dCV"])
        rows.append(dict(harpnum=e.harpnum, pilot_dCV_exposure_rule=float(pil[e.harpnum]), dryrun_sens_dCV=mv,
                         abs_diff_vs_pilot=abs(mv - float(pil[e.harpnum])), single_eq_multi_sens=mv == sv, single_eq_multi_primary=mp_ == sp_,
                         frames=int(multi.loc[e.eid, "frames"])))
    df = pd.DataFrame(rows); df["PASS"] = (df.abs_diff_vs_pilot < 1e-6) & df.single_eq_multi_sens & df.single_eq_multi_primary
    df.to_csv(f"{root}/dryrun_check.csv", index=False)
    pd.set_option("display.width", 250); log("\n" + df.to_string(index=False), "logs/dryrun.log")
    log(f"step 2b dry run: {'PASS' if df.PASS.all() else 'FAIL'}", "logs/dryrun.log")


def hmi_test():
    """per-HARP multi-T_REC HMI export vs per-alarm exports, 3 pilot HARPs (decisions.md, addition before full run)."""
    from euv_dctrl import samples
    eps = episodes(); eps = eps[eps.harpnum.isin([3248, 4231, 6975])]
    root = f"{R}/hmi_test"; rows = []; timing = []
    for h, g in eps.groupby("harpnum"):
        d = f"{root}/per_harp/{h}"
        if not all(hmi_files(d, x)[0] for x in g.t_rec_tai):
            r = submit(hmi_ds(h, g)); prep = wait(r); nb, dl = download(r, d)
            timing.append(dict(kind="per_harp", harpnum=h, n_trec=len(g), request_id=r.id, prep_s=round(prep, 1), download_s=round(dl, 1)))
        for e in g.itertuples():
            d1 = f"{root}/per_alarm/{h}/{e.t_rec_tai[:16].replace('.', '').replace(':', '')}"
            if not hmi_files(d1, e.t_rec_tai)[0]:
                r = submit(f"hmi.sharp_720s[{h}][{e.t_rec_tai}]{{magnetogram,bitmap}}"); prep = wait(r); nb, dl = download(r, d1)
                timing.append(dict(kind="per_alarm", harpnum=h, n_trec=1, request_id=r.id, prep_s=round(prep, 1), download_s=round(dl, 1)))
    pd.DataFrame(timing).to_csv(f"{root}/timing.csv", mode="a", header=not os.path.exists(f"{root}/timing.csv"), index=False)
    for e in eps.itertuples():
        h = int(e.harpnum)
        A = hmi_files(f"{root}/per_harp/{h}", e.t_rec_tai)
        B = hmi_files(f"{root}/per_alarm/{h}/{e.t_rec_tai[:16].replace('.', '').replace(':', '')}", e.t_rec_tai)
        row = dict(harpnum=h, t_rec=e.t_rec_tai)
        for seg, pa, pb in [("magnetogram", A[0], B[0]), ("bitmap", A[1], B[1])]:
            ha, hb = fits.open(pa), fits.open(pb)
            xa, xb = ha[-1], hb[-1]
            da, db = np.asarray(xa.data), np.asarray(xb.data)
            row[f"{seg}_data_identical"] = bool(da.dtype == db.dtype and da.shape == db.shape and da.tobytes() == db.tobytes())
            ca = {c.keyword: str(c.value) for c in xa.header.cards if c.keyword not in ("", "COMMENT", "HISTORY")}
            cb = {c.keyword: str(c.value) for c in xb.header.cards if c.keyword not in ("", "COMMENT", "HISTORY")}
            dk = sorted(k for k in set(ca) | set(cb) if ca.get(k) != cb.get(k))
            row[f"{seg}_header_diff_keys"] = ";".join(dk)
            row[f"{seg}_file_bytes_identical"] = open(pa, "rb").read() == open(pb, "rb").read()
        ma, mb = sunpy.map.Map(A[0]), sunpy.map.Map(B[0])
        Sa, *_ = samples(ma.data, fits.open(A[1])[-1].data); Sb, *_ = samples(mb.data, fits.open(B[1])[-1].data)
        row["pil_diff_px"] = int((pil_mask(ma.data) != pil_mask(mb.data)).sum()); row["ar_diff_px"] = int((ar_mask(ma.data) != ar_mask(mb.data)).sum())
        row["dctrl_samples_identical"] = all(np.array_equal(Sa[k], Sb[k]) for k in Sa)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["PASS_bytes"] = (df.magnetogram_data_identical & df.bitmap_data_identical & (df.magnetogram_header_diff_keys == "")
                        & (df.bitmap_header_diff_keys == ""))
    df.to_csv(f"{root}/hmi_per_harp_check.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    log("\n" + df.to_string(index=False), "logs/dryrun.log")
    log(f"HMI per-HARP test: byte-identical data+header {int(df.PASS_bytes.sum())}/{len(df)}; masks/samples identical "
        f"{int(((df.pil_diff_px == 0) & (df.ar_diff_px == 0) & df.dctrl_samples_identical).sum())}/{len(df)}", "logs/dryrun.log")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "hmi_test":
        hmi_test()
    if cmd == "dryrun":
        dryrun()
    elif cmd == "run":
        eps = episodes(); log(f"FULL RUN start: {len(eps)} episodes, {eps.harpnum.nunique()} HARPs")
        res = run_pipeline(eps, R, workers=8); log(f"FULL RUN done: {len(res)} episode results")
    if cmd == "hmi_check":
        ok = hmi_check(); log(f"step 2a HMI direct access: {'PASS' if ok else 'FAIL'}", "logs/dryrun.log")
