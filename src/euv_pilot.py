"""EUV PILOT (exploratory; dev data 2010-2019 only).  Primary measure: PIL-localised EUV variability at 12-min cadence,
"motivated by BADPIT and Leka et al." -- NOT BADPIT.  Decisions: EUV pilot parts 1-2, U1-U10, P1-P6 (P2 amended,
P4 clarified) in decisions.md.

Per episode (HARPNUM, t):
  magnetogram : hmi.sharp_720s LoS `magnetogram` segment at t (CCD-frame patch with WCS)
  masks       : PIL area = overlap of |B|>150 G masks of each polarity, each dilated by a disk of radius 16 px (U6);
                AR mask |B| > 30 G (reported, not used: U9 uses the HARP box)
  AIA         : 94 A (and 1600 A) tracked cutouts (JSOC im_patch, U10) over (t-24h, t] at 12 min; 94 A at 12 s over
                (t-6h, t] (cost test, process-and-delete); registered to level 1.5 (aiapy); saturation: raw DN > 12,000
                excluded BEFORE exposure normalisation, frame flagged (P4, U4); then DN/s
  mapping     : masks reprojected onto each AIA frame with differential rotation (U8)
  flares      : frame excluded if inside [begin, end] of (a) a C1+ event of the HARP's own region(s) or (b) any M1+ (P2)
  metrics     : per frame, mean intensity in the PIL mask and in the HARP box; fraction of mask pixels above a trailing
                per-pixel mean + 3 SD from earlier frames only (P5, >= 12 earlier frames); per episode, SD of the
                linearly detrended mean series (P1); primary feature = SD(PIL) / SD(HARP box); >= 80% of frames required
"""
import json, os, sys, time, hashlib, shutil
import numpy as np, pandas as pd
from scipy import ndimage

OUT = "data/euv_pilot"
SAT_DN, B_PIL, B_AR, DIL, MIN_PRIOR, MIN_FRAC = 12000, 150.0, 30.0, 16, 12, 0.80


# ---------------------------------------------------------------- pure functions (tested without JSOC)
def disk(r):
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def pil_mask(b):
    """BADPIT-style PIL area on a LoS magnetogram: overlap of the dilated |B|>150 G masks of each polarity."""
    b = np.nan_to_num(b)
    pos = ndimage.binary_dilation(b > B_PIL, structure=disk(DIL))
    neg = ndimage.binary_dilation(b < -B_PIL, structure=disk(DIL))
    return pos & neg


def ar_mask(b):
    return np.abs(np.nan_to_num(b)) > B_AR


def ctrl_mask(b, pil):
    """Control mask (decisions.md, 2026-09-22): n_PIL pixels of the 30 G AR mask outside the dilated PIL, farthest
    from the PIL (Euclidean px); ties by a fixed permutation (seed 0) + stable sort. Returns (mask, short_flag)."""
    n = int(pil.sum())
    cand = ar_mask(b) & ~pil
    out = np.zeros_like(pil, bool)
    if n == 0 or not cand.any():
        return out, True
    dist = ndimage.distance_transform_edt(~pil)
    idx = np.flatnonzero(cand)
    idx = idx[np.random.RandomState(0).permutation(len(idx))]
    idx = idx[np.argsort(-dist.ravel()[idx], kind="stable")][:n]
    out.ravel()[idx] = True
    return out, len(np.flatnonzero(cand)) < n


def cv(times, series):
    """Design fix: CV = SD of the linearly detrended mean series / mean of the series (same valid frames)."""
    ok = np.isfinite(series)
    return detrended_sd(np.asarray(times)[ok], np.asarray(series)[ok]) / np.mean(np.asarray(series)[ok]) if ok.sum() >= 3 else np.nan


def flare_excluded(times, events, harp_regions):
    """P2: boolean per frame time; also returns how many frames each rule removes."""
    t = pd.to_datetime(pd.Series(times))
    ev = events.dropna(subset=["start", "end"])
    a_ev = ev[(ev["flux"] >= 1e-6) & ev["noaa_ar"].isin(harp_regions)]
    b_ev = ev[ev["flux"] >= 1e-5]
    inside = lambda E: t.apply(lambda x: bool(((E["start"] <= x) & (x <= E["end"])).any())).to_numpy()
    a, b = inside(a_ev), inside(b_ev)
    return a | b, int(a.sum()), int(b.sum()), int((a & b).sum())


def trailing_frac(stack, mask, min_prior=MIN_PRIOR):
    """P5: per frame, fraction of mask pixels above the per-pixel mean + 3 SD of EARLIER frames only."""
    out = np.full(len(stack), np.nan)
    for i in range(min_prior, len(stack)):
        past = stack[:i][:, mask]
        mu, sd = np.nanmean(past, axis=0), np.nanstd(past, axis=0, ddof=1)
        cur = stack[i][mask]
        ok = np.isfinite(cur) & np.isfinite(mu) & np.isfinite(sd)
        out[i] = np.mean(cur[ok] > (mu + 3 * sd)[ok]) if ok.any() else np.nan
    return out


def detrended_sd(times, series):
    """P1: SD of the residuals after removing a least-squares linear fit."""
    t = (pd.to_datetime(pd.Series(times)) - pd.Timestamp(times[0])).dt.total_seconds().to_numpy() / 3600
    ok = np.isfinite(series)
    if ok.sum() < 3:
        return np.nan
    fit = np.polyval(np.polyfit(t[ok], series[ok], 1), t[ok])
    return float(np.std(series[ok] - fit, ddof=1))


def saturate_then_normalise(raw_dn, exptime):
    """P4 (clarified): the 12,000 DN cut on RAW DN, then exposure normalisation to DN/s."""
    bad = raw_dn > SAT_DN
    out = raw_dn.astype(float).copy()
    out[bad] = np.nan
    return out / exptime, bool(bad.any())


if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    b = np.zeros((80, 80)); b[20:60, 20:38] = 400; b[20:60, 42:60] = -400      # two polarities, 4 px gap
    m = pil_mask(b)
    assert m[40, 40] and not m[5, 5] and m.sum() > 0, "PIL mask"
    b2 = np.zeros((80, 80)); b2[20:60, 5:15] = 400; b2[20:60, 65:75] = -400     # 50 px apart: no overlap
    assert pil_mask(b2).sum() == 0, "far-apart polarities must not form a PIL area"
    ev = pd.DataFrame({"start": pd.to_datetime(["2014-06-12 01:00", "2014-06-12 05:00", "2014-06-12 09:00"]),
                       "end": pd.to_datetime(["2014-06-12 01:30", "2014-06-12 05:20", "2014-06-12 09:10"]),
                       "flux": [2e-6, 3e-5, 5e-6], "noaa_ar": [12089, 99999, 99999]})
    times = pd.date_range("2014-06-12 00:00", "2014-06-12 10:00", freq="12min")
    ex, na, nb, nab = flare_excluded(times, ev, {12089})
    assert na == 3 and nb == 2 and nab == 0, (na, nb, nab)     # C2 own region: 01:00,01:12,01:24; M3 any: 05:00,05:12; C5 other region: not excluded
    rng = np.random.RandomState(0); st = rng.normal(100, 1, (30, 10, 10)); st[25, 5, 5] = 200
    f = trailing_frac(st, np.ones((10, 10), bool))
    assert np.isnan(f[:12]).all() and f[25] >= 0.01, "trailing 3-sigma"
    s = np.linspace(0, 10, 50) + np.r_[np.zeros(49), 5.0]
    assert detrended_sd(pd.date_range("2014-01-01", periods=50, freq="12min"), s) > 0
    n, flag = saturate_then_normalise(np.array([[100, 13000]]), 2.0)
    assert flag and np.isnan(n[0, 1]) and n[0, 0] == 50.0, "saturation before normalisation"
    assert ctrl_mask(b, m)[1], "small AR: ctrl_short flagged"
    b3 = np.zeros((100, 200)); b3[30:70, 10:98] = 400; b3[30:70, 102:190] = -400; m3 = pil_mask(b3)
    c, short = ctrl_mask(b3, m3)
    assert c.sum() == m3.sum() and not (c & m3).any() and (np.abs(b3[c]) > B_AR).all() and not short, "ctrl mask"
    assert (c == ctrl_mask(b3, m3)[0]).all(), "ctrl mask deterministic"
    d = ndimage.distance_transform_edt(~m3); cand = ar_mask(b3) & ~m3
    assert d[c].min() >= d[cand & ~c].max(), "ctrl = farthest candidates"
    tt = pd.date_range("2014-01-01", periods=50, freq="12min")
    assert abs(cv(tt, 2 * (s + 100)) - cv(tt, s + 100)) < 1e-12, "CV scale-free"
    print("selftest passed: ctrl mask (area-matched, outside PIL, inside AR, farthest, deterministic), CV scale-free; PIL mask, flare exclusion (P2 counts), trailing 3-sigma (P5), detrended SD (P1), saturation (P4)")
