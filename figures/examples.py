"""Rule-based example selection for F3/F4 (rule recorded in decisions.md BEFORE looking, commit 983bcae).
Code written by Claude Code (AI). Reads stored results only; computes nothing new except the pair-selection ranking."""
import glob, json, os
import numpy as np, pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(REPO, "data", "euv_confirm")


def cv_box(eid):
    return float(json.load(open(f"{C}/results/{eid}.json"))["primary_CV_box"])


def select_pair():
    """F4 rule: of the 50 TEST 1 pairs, the pair with the LOWER-MEDIAN ratio r = CV_box(true)/CV_box(false)
    (25th smallest; identical r -> first in file order)."""
    tw = pd.read_csv(f"{C}/twins_le2.csv")
    assert len(tw) == 50, "TEST 1 twins file must hold 50 pairs"
    tw["r"] = [cv_box(a) / cv_box(b) for a, b in zip(tw.true_eid, tw.false_eid)]
    order = tw.reset_index().sort_values(["r", "index"], kind="stable")
    return order.iloc[24]                      # 25th smallest (0-based 24)


def series(eid):
    """stored primary-version series: valid frames only, in file order (the frames CV_box used)."""
    s = pd.read_csv(f"{C}/series/{eid}.csv", usecols=["t_obs", "box", "valid_primary"], parse_dates=["t_obs"])
    return s[s.valid_primary.astype(bool) & np.isfinite(s.box)].reset_index(drop=True)


def episode_t(eid):
    h, ts = eid.split("_")
    co = pd.read_csv(f"{C}/cohort_le2.csv", usecols=["harpnum", "t", "score"], parse_dates=["t"])
    co["eid"] = [f"{a}_{b:%Y%m%dT%H%M}" for a, b in zip(co.harpnum, co.t)]
    r = co.set_index("eid").loc[eid]
    return r.t, float(r.score)


def nearest_aia(eid, t):
    """the stored AIA 94 A cutout FITS nearest to (and not after) t, or None if none is stored."""
    files = sorted(glob.glob(f"{C}/aia/{eid.split('_')[0]}/aia.lev1_euv_12s.*Z.94.image.fits"))
    best, bt = None, None
    for f in files:
        ts = pd.Timestamp(os.path.basename(f).split(".")[2].rstrip("Z").replace("T", " "))
        if ts <= t and (bt is None or ts > bt):
            best, bt = f, ts
    return best, bt
