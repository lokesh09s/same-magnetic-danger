"""EUV pilot run (items 2-4): register, saturation cut, mask reprojection, P2 exclusion, P1/P5 metrics, overlays.
Usage: python euv_run.py <item> [HARP ...]      item 2 = 94 A 12 min, 3 = 1600 A 12 min, 4 = 94 A 12 s (6 h)
Rules: see euv_pilot.py docstring and decisions.md (P1-P6, U1-U10)."""
import glob, sys, time
import numpy as np, pandas as pd, sunpy.map, astropy.units as u
from astropy.io import fits
from astropy.time import Time
from reproject import reproject_interp
from sunpy.coordinates import propagate_with_solar_surface
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import swpc
from aiapy.calibrate import update_pointing
from aiapy.calibrate.utils import get_pointing_table
from euv_pilot import pil_mask, ctrl_mask, cv, flare_excluded, detrended_sd, SAT_DN, MIN_PRIOR, MIN_FRAC
from euv_download import EP, ROOT

SPAN = {2: "24h", 3: "24h", 4: "6h"}
CAD = {2: "12min", 3: "12min", 4: "12s"}


def register_cutout(m):
    """Same pixel operation as aiapy.calibrate.register (rotate to north, rescale to 0.6"/px, order 3), without its
    full-disk-only recentre/crop, which cannot apply to a cutout."""
    m2 = m.rotate(scale=(m.scale[0] / (0.6 * u.arcsec / u.pix)).value, order=3, missing=np.nan)
    m2.meta["lvl_num"] = 1.5
    return m2


def to_frame(mask_map, target):
    with propagate_with_solar_surface():        # differential rotation from HMI time to AIA frame time (U8)
        out, _ = reproject_interp(mask_map, target.wcs, shape_out=target.data.shape)
    return np.nan_to_num(out) > 0.5


class Trailing:
    """P5 streaming: per-pixel mean + 3 SD (sample) of EARLIER valid frames, via running sums; frame i uses its mask."""
    def __init__(self):
        self.n = self.s = self.ss = None

    def frac(self, img, mask):
        out = np.nan
        if self.n is not None:
            n = self.n[mask]; c = img[mask]
            with np.errstate(invalid="ignore", divide="ignore"):
                mu = self.s[mask] / n
                sd = np.sqrt(np.clip((self.ss[mask] - n * mu ** 2) / (n - 1), 0, None))
            ok = np.isfinite(c) & (n >= MIN_PRIOR) & np.isfinite(sd)
            out = np.mean(c[ok] > (mu + 3 * sd)[ok]) if ok.any() else np.nan
        return out

    def add(self, img):
        if self.n is None:
            self.n, self.s, self.ss = (np.zeros(img.shape) for _ in range(3))
        ok = np.isfinite(img); v = np.where(ok, img, 0.0)
        self.n += ok; self.s += v; self.ss += v * v


def run(e, item):
    h, t = int(e.harpnum), e.t
    t0 = time.time()
    mag = sunpy.map.Map(glob.glob(f"{ROOT}/{h}/1/*magnetogram*.fits")[0])
    pil = pil_mask(mag.data)
    pil_map = sunpy.map.Map(pil.astype(float), mag.meta)
    box_map = sunpy.map.Map(np.ones_like(pil, float), mag.meta)     # HARP box = the SHARP patch (U9)
    ctrl, ctrl_short = ctrl_mask(mag.data, pil)
    ctrl_map = sunpy.map.Map(ctrl.astype(float), mag.meta)
    ptab = get_pointing_table("JSOC", time_range=(Time(t - pd.Timedelta("26h")), Time(t + pd.Timedelta("2h"))))   # keyword query
    regions = {int(x) for x in str(e.noaa_ars).split(",") if x.strip()}
    ev, _ = swpc.load(t - pd.Timedelta("2D"), t)                        # starts up to 2 days before: catches long events

    fs = sorted(glob.glob(f"{ROOT}/{h}/{item}/*.fits"))
    hd = [fits.getheader(f, 1) for f in fs]                              # pass 1: headers -> exclusions
    s = pd.DataFrame(dict(t_obs=[pd.Timestamp(x["T_OBS"].rstrip("Z")) for x in hd],
                          quality=[hex(int(x.get("QUALITY", 0))) for x in hd]))
    ex, na, nb, nab = flare_excluded(s.t_obs, ev, regions)
    qbad = (s.quality != "0x0").to_numpy()                             # QUALITY != 0 excluded (me; pending approval)
    nq = int(qbad.sum()); ex = ex | qbad
    s["excluded"] = ex
    tp, tb, cols, keep, shp, n_pt = Trailing(), Trailing(), [], {}, set(), 0
    for i, f in enumerate(fs):                                         # pass 2: stream frames
        m = sunpy.map.Map(f)
        try:
            m = update_pointing(m, pointing_table=ptab); n_pt += 1       # approved-optional: before registration
        except IndexError:
            pass                                                        # no table entry: header pointing kept (counted)
        raw = m.data.astype(float)
        exp = m.exposure_time.to_value("s")
        if exp <= 0:                                                    # calibration/dark frame: cannot be normalised
            raw[:] = np.nan; exp = 1.0
        bm_raw = to_frame(box_map, m)                                   # box on raw grid: saturation flag (U4)
        sat = bool((raw[bm_raw] > SAT_DN).any())
        raw[raw > SAT_DN] = np.nan                                      # cut on RAW DN (P4) ...
        r = register_cutout(sunpy.map.Map(raw / exp, m.meta))           # ... then DN/s, level 1.5
        pm, bm, cm = to_frame(pil_map, r), to_frame(box_map, r), to_frame(ctrl_map, r)
        shp.add(r.data.shape)
        row = dict(sat_flag=sat, n_pil=int(pm.sum()), mean_pil=np.nan, mean_box=np.nan, mean_ctrl=np.nan, frac_pil=np.nan, frac_box=np.nan)
        if not ex[i]:                                                   # excluded frames: no metric, no baseline
            row.update(mean_pil=np.nanmean(r.data[pm]) if pm.any() else np.nan, mean_box=np.nanmean(r.data[bm]),
                       mean_ctrl=np.nanmean(r.data[cm]) if cm.any() else np.nan,
                       frac_pil=tp.frac(r.data, pm), frac_box=tb.frac(r.data, bm))
            tp.add(r.data); tb.add(r.data)
        cols.append(row)
        if i in (0, len(fs) - 1):
            keep[f] = (r, pm, bm, cm)
    assert len(shp) == 1, f"registered frames differ in shape: {shp}"
    s = pd.concat([s, pd.DataFrame(cols)], axis=1)
    n_exp = len(pd.date_range(t - pd.Timedelta(SPAN[item]) + pd.Timedelta(CAD[item]), t, freq=CAD[item]))
    valid = s[~s.excluded & s.mean_box.notna()]
    sd_p, sd_b = detrended_sd(valid.t_obs.to_numpy(), valid.mean_pil.to_numpy()), \
        detrended_sd(valid.t_obs.to_numpy(), valid.mean_box.to_numpy())
    tv = valid.t_obs.to_numpy()
    cvp, cvc, cvb = cv(tv, valid.mean_pil.to_numpy()), cv(tv, valid.mean_ctrl.to_numpy()), cv(tv, valid.mean_box.to_numpy())
    s.to_csv(f"{ROOT}/{h}/series_item{item}.csv", index=False)
    summ = dict(harpnum=h, role=e.role, item=item, frames=len(s), expected=n_exp, excl_rule_a=na, excl_rule_b=nb,
                excl_both=nab, excl_quality=nq, excl_total=int(ex.sum()), sat_frames=int(s.sat_flag.sum()),
                valid=len(valid), valid_frac=round(len(valid) / n_exp, 3), meets_80pct=len(valid) / n_exp >= MIN_FRAC,
                pil_px_hmi=int(pil.sum()), ctrl_px_hmi=int(ctrl.sum()), ctrl_short=ctrl_short, pointing_updated=n_pt,
                cv_pil=cvp, cv_ctrl=cvc, cv_box=cvb, cv_pil_minus_ctrl=cvp - cvc,        # primary (design fix)
                sd_pil=sd_p, sd_box=sd_b, ratio_old=sd_p / sd_b if sd_b else np.nan,
                proc_s=round(time.time() - t0, 1))
    plots(h, e.role, item, mag, pil, ctrl, keep, s)
    return summ


def plots(h, role, item, mag, pil, ctrl, keep, s):
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.5))
    ax[0].imshow(mag.data, origin="lower", cmap="gray", vmin=-500, vmax=500); ax[0].contour(pil, [0.5], colors="r")
    ax[0].contour(ctrl, [0.5], colors="lime"); ax[0].set_title("HMI LoS at t, PIL (red), ctrl (green)")
    for a, (f, (r, pm, bm, cm)) in zip(ax[1:], keep.items()):
        a.imshow(np.log10(np.clip(r.data, 1e-2, None)), origin="lower", cmap="inferno")
        a.contour(pm, [0.5], colors="c"); a.contour(bm, [0.5], colors="w", linewidths=0.6)
        a.contour(cm, [0.5], colors="lime")
        a.set_title(f"AIA item {item} {r.meta['t_obs'][:19]}")
    fig.suptitle(f"HARP {h} ({role}) item {item}: PIL (cyan), ctrl (green), HARP box (white); first and last frame")
    fig.savefig(f"{ROOT}/{h}/overlay_item{item}.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    ax[0].plot(s.t_obs, s.mean_pil, label="PIL mean"); ax[0].plot(s.t_obs, s.mean_box, label="HARP box mean")
    ax[0].plot(s.t_obs, s.mean_ctrl, label="ctrl mean")
    ax[0].set_ylabel("DN/s"); ax[0].legend()
    ax[1].plot(s.t_obs, s.frac_pil, label="PIL"); ax[1].plot(s.t_obs, s.frac_box, label="box")
    ax[1].set_ylabel("frac > trailing 3σ"); ax[1].legend()
    for a in ax:
        for x in s.t_obs[s.excluded]:
            a.axvline(x, color="0.85", lw=2, zorder=0)
    fig.suptitle(f"HARP {h} ({role}) item {item}; grey = excluded frames (P2 or QUALITY != 0)")
    fig.savefig(f"{ROOT}/{h}/series_item{item}.png", dpi=90, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    from euv_pilot import trailing_frac as ref                         # batch reference (P5)
    rng = np.random.RandomState(1); st = rng.normal(100, 2, (40, 8, 8)); st[30, 2, 2] = 150; mk = np.ones((8, 8), bool)
    tr = Trailing(); got = []
    for im in st:
        got.append(tr.frac(im, mk)); tr.add(im)
    assert np.allclose(np.array(got), ref(st, mk), equal_nan=True), "streaming P5 != batch P5"
    print("selftest passed: streaming trailing 3-sigma equals batch version"); sys.exit()

if __name__ == "__main__" and sys.argv[1] == "item4":               # 12-s cost test: download, process, delete
    import os
    from euv_download import fetch
    harps = [int(x) for x in sys.argv[2:]] or list(EP.harpnum)
    for e in EP[EP.harpnum.isin(harps)].itertuples():
        h = int(e.harpnum)
        if os.path.exists(f"{ROOT}/{h}/series_item4.csv"):
            print(f"HARP {h} item 4: already processed, skipped"); continue
        fetch(4, EP[EP.harpnum == h].iloc[0])                            # manifest keeps SHA-256 of every raw file
        row = run(e, 4)
        p = f"{ROOT}/pilot_summary.csv"; old = pd.read_csv(p)
        pd.concat([old[~((old.item == 4) & (old.harpnum == h))], pd.DataFrame([row])]).to_csv(p, index=False)
        n = 0
        for f in glob.glob(f"{ROOT}/{h}/4/*.fits"):
            os.remove(f); n += 1
        print(f"HARP {h} item 4: processed in {row['proc_s']} s; {n} raw files deleted", flush=True)
    sys.exit()

if __name__ == "__main__":
    item = int(sys.argv[1])
    harps = [int(x) for x in sys.argv[2:]] or list(EP.harpnum)
    out = pd.DataFrame([run(e, item) for e in EP[EP.harpnum.isin(harps)].itertuples()])
    p = f"{ROOT}/pilot_summary.csv"
    try:
        old = pd.read_csv(p); old = old[~((old.item == item) & old.harpnum.isin(harps))]; out = pd.concat([old, out])
    except FileNotFoundError:
        pass
    out.to_csv(p, index=False)
    print(out[out.item == item].to_string(index=False))
