"""Shared helpers for the colour image figures (F3 colour, F4 colour, F10 gallery).
Code written by Claude (AI, chat), 2026-10-06, at the user's request; rule recorded in decisions.md (commit f2cb21d).
Illustration only: reads stored files in data/euv_confirm/, computes no analysis quantity.

Display conventions
- AIA 94 A: stored Level 1 cutout as downloaded, divided by exposure time (DN/s), rotated to solar north for display,
  log10 scale, standard AIA 94 colour table (sunpy 'sdoaia94'). One display range per figure.
- HMI: stored SHARP line-of-sight magnetogram (CCD frame, CROTA2 ~ 180 deg) rotated to solar north, +-1000 G,
  diverging colour table (red = positive / toward the observer, blue = negative). HARP region = bitmap >= 33 (outline).
- The CV_box 'box' is every pixel of the HMI patch (euv_dctrl.samples: box = all pixels). Its outline on an AIA frame is
  the patch boundary mapped with solar differential rotation, as euv_dctrl.hmi_to_frame does (no pointing update:
  display only)."""
import glob, os, warnings
import numpy as np, pandas as pd
import astropy.units as u
warnings.filterwarnings("ignore")
import sunpy.map
import sunpy.visualization.colormaps  # noqa: F401  (registers sdoaia94, hmimag)
from sunpy.coordinates import propagate_with_solar_surface

from examples import C, series

AIA_CMAP, HMI_CMAP, B_LIM = "sdoaia94", "RdBu_r", 1000.0


def _ts_aia(f):
    return pd.Timestamp(os.path.basename(f).split(".")[2].rstrip("Z").replace("T", " "))


def aia_file_near(eid, when, not_after=None):
    """stored AIA 94 cutout nearest `when` (optionally not after `not_after`)."""
    fs = sorted(glob.glob(f"{C}/aia/{eid.split('_')[0]}/aia.lev1_euv_12s.*Z.94.image.fits"))
    if not_after is not None:
        fs = [f for f in fs if _ts_aia(f) <= not_after]
    return min(fs, key=lambda f: abs(_ts_aia(f) - when)) if fs else None


def valid_aia_file(eid, t):
    """stored AIA 94 cutout of the VALID frame (valid_primary, the frames CV_box used) nearest to and not after t
    (decisions.md amendment, commit bc6c4e8)."""
    s = series(eid)
    v = s[s.t_obs <= t + pd.Timedelta(seconds=30)]
    assert len(v), f"{eid}: no valid frame before t"
    to = v.t_obs.iloc[-1]
    f = aia_file_near(eid, to)
    assert abs((_ts_aia(f) - to).total_seconds()) < 60, f"{eid}: file does not match the valid frame"
    return f


def hmi_files_near(eid, t):
    """stored SHARP magnetogram and bitmap whose T_REC (TAI, file name) is nearest t (UTC; TAI = UTC + 37 s)."""
    fs = sorted(glob.glob(f"{C}/hmi/{eid.split('_')[0]}/*.magnetogram.fits"))
    def ts(f):
        return pd.Timestamp(os.path.basename(f).split(".")[3].replace("_TAI", "").replace("_", " "))
    m = min(fs, key=lambda f: abs(ts(f) - (t + pd.Timedelta(seconds=37))))
    return m, m.replace("magnetogram", "bitmap")


def extent(mp):
    """imshow extent (arcsec) of a north-up map."""
    bl, tr = mp.bottom_left_coord, mp.top_right_coord
    sx, sy = mp.scale.axis1.to_value("arcsec/pix") / 2, mp.scale.axis2.to_value("arcsec/pix") / 2
    return [bl.Tx.to_value("arcsec") - sx, tr.Tx.to_value("arcsec") + sx, bl.Ty.to_value("arcsec") - sy, tr.Ty.to_value("arcsec") + sy]


def load_aia(f):
    """-> (north-up map of log10 DN/s, observation time)."""
    m = sunpy.map.Map(f)
    exp = m.exposure_time.to_value("s")
    d = m.data.astype(float) / (exp if exp > 0 else np.nan)
    m = sunpy.map.Map(np.log10(np.clip(d, 1e-1, None)), m.meta)
    r = m.rotate(order=1, missing=np.nan)
    return r, pd.Timestamp(m.meta["t_obs"].rstrip("Z"))


def load_hmi(mag_f, bit_f):
    """-> (north-up magnetogram map in G, north-up bitmap map, original magnetogram map)."""
    m0 = sunpy.map.Map(mag_f)
    b0 = sunpy.map.Map(bit_f)
    m = m0.rotate(order=1, missing=np.nan)
    b = b0.rotate(order=0, missing=0)
    return m, b, m0


def box_outline(mag0, frame):
    """HMI patch boundary mapped onto `frame` (north-up AIA map) with differential rotation -> (Tx, Ty) in arcsec."""
    ny, nx = mag0.data.shape
    xs = np.r_[np.arange(nx), np.full(ny, nx - 1), np.arange(nx)[::-1], np.zeros(ny)]
    ys = np.r_[np.zeros(nx), np.arange(ny), np.full(nx, ny - 1), np.arange(ny)[::-1]]
    c = mag0.pixel_to_world(xs * u.pix, ys * u.pix)
    with propagate_with_solar_surface():
        cc = c.transform_to(frame.coordinate_frame)
    return cc.Tx.to_value("arcsec"), cc.Ty.to_value("arcsec")


def show_aia(ax, mp, vmin, vmax):
    import matplotlib
    cmap = matplotlib.colormaps[AIA_CMAP].copy(); cmap.set_bad(cmap(0.0))
    return ax.imshow(mp.data, cmap=cmap, origin="lower", extent=extent(mp), vmin=vmin, vmax=vmax, interpolation="nearest")


def show_hmi(ax, m, b):
    im = ax.imshow(m.data, cmap=HMI_CMAP, origin="lower", extent=extent(m), vmin=-B_LIM, vmax=B_LIM, interpolation="nearest")
    ax.contour((b.data >= 33).astype(float), levels=[0.5], colors="#3a2f8f", linewidths=0.8, origin="lower", extent=extent(b))
    return im


def aia_range(maps, lo=35.0, hi=99.9):
    v = np.concatenate([mp.data[np.isfinite(mp.data)].ravel() for mp in maps])
    return np.percentile(v, [lo, hi])


def clean_axes(ax, label_axes=False):
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_linewidth(0.5); sp.set_color("#52514e")
