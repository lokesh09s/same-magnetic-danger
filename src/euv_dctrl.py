"""D-CTRL metric (decisions.md 2026-09-22, user definition recorded verbatim; implementation details same date).
Per episode: PIL / control samples drawn once on the LoS magnetogram at t (20 seeds), mapped forward to every AIA
frame; per-frame means -> CV = detrended SD / mean over valid frames; dCV = CV_PIL - CV_ctrl (mean over draws).
Sources: 'cutout' (items 2/3/4 JSOC cutouts, pointing-updated + registered as approved) or 'synoptic' (JSOC synoptic
level 1.5 1024^2). Usage: python euv_dctrl.py cutout|synoptic|cadence [HARP ...]; python euv_dctrl.py selftest"""
import glob, os, sys, time, urllib.request
import numpy as np, pandas as pd, sunpy.map, astropy.units as u
from astropy.io import fits
from scipy import ndimage
from sunpy.coordinates import propagate_with_solar_surface
from euv_pilot import pil_mask, ctrl_mask, flare_excluded, detrended_sd, SAT_DN

NDRAW, B_AR = 20, 30.0
SYN = "https://jsoc1.stanford.edu/data/aia/synoptic"


def samples(b, bitmap):
    """-> dict name -> flat HMI pixel indices; plus ctrl_short, n. Draw k = seed k."""
    pil = pil_mask(b)
    cand = (bitmap >= 33) & (np.abs(np.nan_to_num(b)) >= B_AR) & ~pil
    pi, ci = np.flatnonzero(pil), np.flatnonzero(cand)
    n = min(len(pi), len(ci)); short = len(ci) < len(pi)
    out = {"box": np.arange(b.size), "pil_full": pi, "ctrl_far": np.flatnonzero(ctrl_mask(b, pil)[0])}
    for s in range(NDRAW):
        out[f"ctrl_{s}"] = np.random.RandomState(s).choice(ci, n, replace=False) if n else ci[:0]
        out[f"pil_{s}"] = np.random.RandomState(s).choice(pi, n, replace=False) if short else pi
    return out, short, n


def hmi_to_frame(mag, frame):
    """flat AIA index for every HMI pixel (-1 if it maps outside the frame), with differential rotation."""
    ny, nx = mag.data.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    c = mag.pixel_to_world(xx.ravel() * u.pix, yy.ravel() * u.pix)
    with propagate_with_solar_surface():
        px, py = frame.world_to_pixel(c.transform_to(frame.coordinate_frame))
    ix, iy = np.round(np.asarray(px.value)), np.round(np.asarray(py.value))
    fy, fx = frame.data.shape
    ok = np.isfinite(ix) & np.isfinite(iy) & (ix >= 0) & (iy >= 0) & (ix < fx) & (iy < fy)
    idx = np.full(ix.size, -1, int); idx[ok] = (iy[ok] * fx + ix[ok]).astype(int)
    return idx


def frame_means(img, idx, S):
    v = np.full(idx.size, np.nan); ok = idx >= 0
    v[ok] = img.ravel()[idx[ok]]
    return {k: (np.nanmean(v[p]) if len(p) and np.isfinite(v[p]).any() else np.nan) for k, p in S.items()}


def cv(t, y):
    ok = np.isfinite(y)
    return detrended_sd(np.asarray(t)[ok], np.asarray(y)[ok]) / np.mean(y[ok]) if ok.sum() >= 3 else np.nan


def summarise(s, S, short, n, tag):
    """s: per-frame DataFrame (t_obs, valid, means per sample). -> one dict of CV results."""
    v = s[s.valid]; t = v.t_obs.to_numpy()
    cp = np.array([cv(t, v[f"pil_{k}"].to_numpy()) for k in range(NDRAW)])
    cc = np.array([cv(t, v[f"ctrl_{k}"].to_numpy()) for k in range(NDRAW)])
    d = cp - cc
    return dict(tag=tag, frames=len(s), valid=len(v), n_pix=n, ctrl_short=short,
                CV_PIL=np.mean(cp), CV_PIL_sd=np.std(cp, ddof=1), CV_ctrl=np.mean(cc), CV_ctrl_sd=np.std(cc, ddof=1),
                dCV=np.mean(d), dCV_sd=np.std(d, ddof=1), CV_box=cv(t, v["box"].to_numpy()),
                CV_PIL_full=cv(t, v["pil_full"].to_numpy()), CV_ctrl_far=cv(t, v["ctrl_far"].to_numpy()),
                dCV_far=cv(t, v["pil_full"].to_numpy()) - cv(t, v["ctrl_far"].to_numpy()))


if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    b = np.zeros((100, 200)); b[30:70, 10:98] = 400; b[30:70, 102:190] = -400; bm = np.full(b.shape, 34)
    S, short, n = samples(b, bm)
    pil = pil_mask(b)
    assert not short and n == pil.sum() and all(len(S[f"ctrl_{k}"]) == n for k in range(NDRAW))
    assert not any(pil.ravel()[S[f"ctrl_{k}"]].any() for k in range(NDRAW)), "ctrl outside PIL"
    assert len({tuple(S[f"ctrl_{k}"][:5]) for k in range(NDRAW)}) == NDRAW, "draws differ by seed"
    assert (samples(b, bm)[0]["ctrl_3"] == S["ctrl_3"]).all(), "deterministic per seed"
    b2 = b.copy(); b2[:, :] = 0; b2[45:55, 90:98] = 400; b2[45:55, 102:110] = -400          # tiny AR: few candidates
    S2, short2, n2 = samples(b2, bm)
    assert short2 and all(len(S2[f"pil_{k}"]) == len(S2[f"ctrl_{k}"]) == n2 for k in range(NDRAW)), "equal counts when short"
    bm0 = bm.copy(); bm0[:, :100] = 1
    S3, _, _ = samples(b, bm0)
    assert all((np.unravel_index(S3[f"ctrl_{k}"], b.shape)[1] >= 100).all() for k in range(NDRAW)), "ctrl inside bitmap"
    print("selftest passed: D-CTRL draws (equal counts, outside PIL, inside bitmap/AR, seeded, short case)")
    sys.exit()


# ---------------------------------------------------------------- frame sources
def syn_files(h, t, wl, span="24h"):
    """synoptic files at the 12-min slots of (t-span, t]; cached in data/euv_pilot/<h>/syn_<wl>/. -> (paths, bytes, s)"""
    d = f"data/euv_pilot/{h}/syn_{wl}"; os.makedirs(d, exist_ok=True)
    slots = pd.date_range(t - pd.Timedelta(span) + pd.Timedelta("12min"), t, freq="12min").round("2min")
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()

    def get(s):                                          # parallel (6 connections); .tmp then rename = no partial files
        fn = f"AIA{s:%Y%m%d_%H%M}_{wl:04d}.fits"; p = f"{d}/{fn}"
        if not os.path.exists(p):
            for k in range(5):
                try:
                    urllib.request.urlretrieve(f"{SYN}/{s:%Y/%m/%d}/H{s:%H}00/{fn}", p + ".tmp"); os.replace(p + ".tmp", p); break
                except Exception as err:
                    if "404" in str(err):
                        break
                    time.sleep(10)
        return p if os.path.exists(p) else None
    with ThreadPoolExecutor(6) as ex:
        paths = [p for p in ex.map(get, slots) if p]
    nb = sum(os.path.getsize(p) for p in paths)
    return paths, nb, time.time() - t0


def frames(paths, source, ptab=None):
    """yield (t_obs, quality, frame map in DN/s at level 1.5) with the approved rules."""
    from euv_run import register_cutout
    from aiapy.calibrate import update_pointing
    for f in paths:
        m = sunpy.map.Map(f)
        q, exp = int(m.meta.get("quality", 0)), m.exposure_time.to_value("s")
        raw = m.data.astype(float)
        if exp <= 0:
            raw[:] = np.nan; exp = 1.0
        raw[raw > SAT_DN] = np.nan                                  # P4 (synoptic: on averaged values, stated deviation)
        if source == "cutout":
            try:
                m = update_pointing(m, pointing_table=ptab)
            except IndexError:
                pass
            r = register_cutout(sunpy.map.Map(raw / exp, m.meta))
        else:
            r = sunpy.map.Map(raw / exp, m.meta)
        yield pd.Timestamp(m.meta["t_obs"].rstrip("Z")), q, exp, r


def run(e, source, item_or_wl, span="24h"):
    import swpc
    from astropy.time import Time
    from aiapy.calibrate.utils import get_pointing_table
    h, t = int(e.harpnum), e.t
    mag = sunpy.map.Map(glob.glob(f"data/euv_pilot/{h}/1/*magnetogram*.fits")[0])
    bitmap = fits.open(glob.glob(f"data/euv_pilot/{h}/1/*bitmap*.fits")[0])[-1].data
    S, short, n = samples(mag.data, bitmap)
    info = {}
    if source == "cutout":
        paths = sorted(glob.glob(f"data/euv_pilot/{h}/{item_or_wl}/*.fits"))
        ptab = get_pointing_table("JSOC", time_range=(Time(t - pd.Timedelta("26h")), Time(t + pd.Timedelta("2h"))))
    else:
        paths, nb, dl = syn_files(h, t, item_or_wl, span); ptab = None
        info = dict(syn_files=len(paths), syn_MB=round(nb / 1e6, 1), syn_download_s=round(dl, 1))
    ev, _ = swpc.load(t - pd.Timedelta("2D"), t)
    regions = {int(x) for x in str(e.noaa_ars).split(",") if x.strip()}
    t0, rows, keep = time.time(), [], None
    for i, (to, q, exp, r) in enumerate(frames(paths, source, ptab)):
        idx = hmi_to_frame(mag, r)
        rows.append(dict(t_obs=to, quality=q, exptime=exp, **frame_means(r.data, idx, S)))
        if i == len(paths) - 1:
            keep = (r, idx)
    s = pd.DataFrame(rows)
    ex, na, nb_, _ = flare_excluded(s.t_obs, ev, regions)
    med = s.loc[(s.quality == 0) & (s.exptime > 0), "exptime"].median()          # exposure rule: >= 50% of the
    s["exp_ok"] = s.exptime >= 0.5 * med                                          # channel median in this window
    s["valid"] = ~ex & (s.quality == 0) & s.box.notna() & s.exp_ok
    info.update(excl_P2a=na, excl_P2b=nb_, excl_quality=int((s.quality != 0).sum()),
                exptime_median=round(float(med), 4), excl_exposure=int((~s.exp_ok).sum()), proc_s=round(time.time() - t0, 1))
    return s, S, short, n, info, keep, mag


def overlay(h, role, tag, mag, S, keep):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    r, idx = keep; fy, fx = r.data.shape
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.imshow(np.log10(np.clip(r.data, 1e-1, None)), origin="lower", cmap="inferno")
    for k, c, lab in [("box", "w", "HARP box"), ("pil_0", "c", "PIL (draw 0)"), ("ctrl_0", "lime", "ctrl (draw 0)")]:
        j = idx[S[k]]; j = j[j >= 0]
        ax.plot(j % fx, j // fx, ",", color=c, alpha=0.4 if k == "box" else 1, label=lab)
    js = idx[S["box"]]; js = js[js >= 0]; pad = 15
    ax.set_xlim((js % fx).min() - pad, (js % fx).max() + pad); ax.set_ylim((js // fx).min() - pad, (js // fx).max() + pad)
    ax.legend(loc="upper right", markerscale=20, fontsize=7); ax.set_title(f"HARP {h} ({role}) {tag} {r.meta['t_obs'][:19]}")
    fig.savefig(f"data/euv_pilot/{h}/overlay_dctrl_{tag}.png", dpi=90, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    from euv_download import EP
    mode = sys.argv[1]; harps = [int(x) for x in sys.argv[2:]] or list(EP.harpnum)
    out = []
    for e in EP[EP.harpnum.isin(harps)].itertuples():
        jobs = {"cutout": [("cutout", 2, "cutout_94"), ("cutout", 3, "cutout_1600")],
                "synoptic": [("synoptic", 94, "synoptic_94"), ("synoptic", 1600, "synoptic_1600")],
                "cadence": [("cutout", 4, "12s_94")]}[mode]
        for src, it, tag in jobs:
            s, S, short, n, info, keep, mag = run(e, src, it, "6h" if mode == "cadence" else "24h")
            s.to_csv(f"data/euv_pilot/{e.harpnum}/series_dctrl_{tag}.csv", index=False)
            overlay(e.harpnum, e.role, tag, mag, S, keep)
            if mode == "cadence":                                    # (a) all 12-s frames, (b) 12-min-slot frames only
                slots = pd.date_range(e.t - pd.Timedelta("6h") + pd.Timedelta("12min"), e.t, freq="12min")
                near = np.abs(s.t_obs.to_numpy()[:, None] - slots.to_numpy()[None, :]).min(axis=1) <= np.timedelta64(6, "s")
                for sub, lab in [(s, "(a) all 12 s"), (s[near], "(b) 12-min slots")]:
                    out.append(dict(harpnum=e.harpnum, role=e.role, **summarise(sub.reset_index(drop=True), S, short, n, f"{tag} {lab}"), **info))
            else:
                out.append(dict(harpnum=e.harpnum, role=e.role, **summarise(s, S, short, n, tag), **info))
            print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in out[-1].items()}, flush=True)
    pd.DataFrame(out).to_csv(f"data/euv_pilot/dctrl_{mode}.csv", index=False)
