"""HELD-OUT EUV TEST -- DOWNLOAD AND VERIFY ONLY (decisions.md 2026-09-25; design 3283478 item 1h). Nothing is computed on
test years. Cohort data/stage5/cohort_test_primary.csv, columns harpnum/t/noaa_ars only (no labels, no model outputs).
Same per-HARP HMI + AIA url-tar exports as the dev run (euv_full.run_pipeline, compute=False). Output: data/euv_test/ only.
Usage: python euv_test_download.py run | verify"""
import glob, os, sys, time
import numpy as np, pandas as pd
import euv_full
from euv_full import run_pipeline, expected_frames, valid_fits, hmi_files, trec_of, log

ROOT = euv_full.R = "data/euv_test"                       # euv_full.log() writes under R -> data/euv_test/logs
os.makedirs(f"{ROOT}/logs", exist_ok=True)


def episodes_test():
    lab = pd.read_csv("data/labelled_20100501_20250101.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"],
                      parse_dates=["t_rec_utc"], low_memory=False)
    c = pd.read_csv("data/stage5/cohort_test_primary.csv", usecols=["harpnum", "t", "noaa_ars"], parse_dates=["t"])
    assert len(c) == 313 and c.harpnum.nunique() == 98 and set(c.t.dt.year) <= {2021, 2023, 2024}
    e = c.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert e.t_rec_tai.notna().all()
    e["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(e.harpnum, e.t)]
    return e.sort_values(["harpnum", "t"]).reset_index(drop=True)


if __name__ == "__main__" and sys.argv[1:] == ["run"]:
    eps = episodes_test(); t0 = time.time()
    log(f"HELD-OUT DOWNLOAD start: {len(eps)} episodes, {eps.harpnum.nunique()} HARPs (download only)")
    run_pipeline(eps, ROOT, progress_every=1800, compute=False)
    log(f"HELD-OUT DOWNLOAD done: wall {(time.time() - t0) / 3600:.2f} h")

if __name__ == "__main__" and sys.argv[1:] == ["verify"]:
    from astropy.io import fits
    eps = episodes_test(); rows = []
    for h, g in eps.groupby("harpnum"):
        hd, ad = f"{ROOT}/hmi/{h}", f"{ROOT}/aia/{h}"
        hmi_ok = 0
        for x in g.t_rec_tai:                                  # magnetogram + bitmap present; header HARPNUM and T_REC match
            m, b = hmi_files(hd, x) if os.path.isdir(hd) else (None, None)
            if m and b and all(int(fits.getheader(f, 1)["HARPNUM"]) == h and str(fits.getheader(f, 1)["T_REC"])[:19] == x[:19]
                               for f in (m, b)):
                hmi_ok += 1
        files = sorted(glob.glob(f"{ad}/*.fits")) if os.path.isdir(ad) else []
        lo, hi = g.t.min() - pd.Timedelta("24h") + pd.Timedelta("12min") - pd.Timedelta("1min"), g.t.max() + pd.Timedelta("1min")
        good = [p for p in files if valid_fits(p)]
        wl = [p for p in good if int(fits.getheader(p, 1 if len(fits.open(p)) > 1 else 0).get("WAVELNTH", -1)) == 94]
        inr = [p for p in wl if lo <= trec_of(p) <= hi]
        rows.append(dict(harpnum=h, episodes=len(g), hmi_expected=2 * len(g), hmi_pairs_ok=hmi_ok, aia_expected=expected_frames(g),
                         aia_files=len(files), aia_header_ok=len(good), aia_94=len(wl), aia_in_range=len(inr),
                         aia_frac=round(len(inr) / expected_frames(g), 4), GB=sum(os.path.getsize(p) for p in files) / 1e9
                         + sum(os.path.getsize(p) for p in glob.glob(f"{hd}/*.fits")) / 1e9))
    v = pd.DataFrame(rows); v.to_csv(f"{ROOT}/verify_per_harp.csv", index=False)
    x = pd.read_csv(f"{ROOT}/exports.csv") if os.path.exists(f"{ROOT}/exports.csv") else pd.DataFrame()
    pd.set_option("display.width", 250)
    print(f"HARPs {len(v)}, episodes {v.episodes.sum()}")
    print(f"HMI: record pairs OK {v.hmi_pairs_ok.sum()}/{v.episodes.sum()} (files expected {v.hmi_expected.sum()})")
    print(f"AIA: files {v.aia_files.sum()}, header OK {v.aia_header_ok.sum()}, 94 A {v.aia_94.sum()}, in range {v.aia_in_range.sum()}, "
          f"expected {v.aia_expected.sum()}; GB {v.GB.sum():.2f}")
    print(f"HARPs with HMI missing: {v.loc[v.hmi_pairs_ok < v.episodes, 'harpnum'].tolist()}")
    print(f"HARPs with no AIA files: {v.loc[v.aia_files == 0, 'harpnum'].tolist()}")
    print("HARPs short (< expected AIA frames in range):")
    print(v.loc[(v.aia_in_range < v.aia_expected) & (v.aia_files > 0), ["harpnum", "episodes", "aia_expected", "aia_in_range", "aia_frac"]]
          .to_string(index=False))
    if len(x):
        print(f"exports: {len(x)} ({(x.kind == 'hmi').sum()} HMI, {(x.kind == 'aia').sum()} AIA); prep {x.prep_s.sum() / 3600:.2f} h, "
              f"download {x.download_s.sum() / 3600:.2f} h (downloads overlap)")
    if os.path.exists(f"{ROOT}/failed.csv"):
        print("failures:"); print(pd.read_csv(f"{ROOT}/failed.csv").to_string(index=False))

if __name__ == "__main__" and sys.argv[1:2] == ["reexport"]:
    # re-export check (user 2026-09-25): AIA once for the given HARPs into data/euv_test/reexport/<H>/; files not already in
    # aia/<H> are copied there (kept); nothing is deleted or overwritten
    import shutil
    from euv_full import aia_spec, submit, wait, download
    eps = episodes_test(); rows = []
    for h in [int(x) for x in sys.argv[2:]]:
        g = eps[eps.harpnum == h]; dest = f"{ROOT}/reexport/{h}"
        ds, proc = aia_spec(h, g, f"{ROOT}/hmi/{h}")
        r = submit(ds, proc); prep = wait(r); nb, dl = download(r, dest)       # one pending export at a time
        old = {os.path.basename(p) for p in glob.glob(f"{ROOT}/aia/{h}/*.fits") if valid_fits(p)}
        new = {os.path.basename(p) for p in glob.glob(f"{dest}/*.fits") if valid_fits(p)}
        for f in sorted(new - old):
            shutil.copy2(f"{dest}/{f}", f"{ROOT}/aia/{h}/{f}")
        rows.append(dict(harpnum=h, request_id=r.id, prep_s=round(prep, 1), expected=expected_frames(g), before=len(old),
                         reexport=len(new), new_frames_added=len(new - old), missing_in_reexport=len(old - new)))
        log(f"re-export HARP {h}: {rows[-1]}")
    pd.DataFrame(rows).to_csv(f"{ROOT}/reexport.csv", index=False); print(pd.DataFrame(rows).to_string(index=False))
