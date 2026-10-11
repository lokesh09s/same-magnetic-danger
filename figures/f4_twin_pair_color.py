"""F4 (colour): example twin pair with magnetogram, AIA 94 A image and 24-h box series for each member.
Same pair as f4_twin_pair.py (rule 983bcae). Code written by Claude (AI, chat), 2026-10-06; display rules in decisions.md
(commit f2cb21d) and solar_images.py. The series panels reproduce the stored CV_box to 1e-12 (checked below).
Usage: python paper_template/figures/f4_twin_pair_color.py"""
import os, sys
import numpy as np, matplotlib.pyplot as plt
from figstyle import TRUE_ALARM, FALSE_ALARM, INK2, GRID, FULL, save
from examples import select_pair, series, episode_t, cv_box
from solar_images import (valid_aia_file, hmi_files_near, load_aia, load_hmi, box_outline, show_aia, show_hmi,
                          aia_range, clean_axes)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from euv_pilot import detrended_sd

p = select_pair()
ROWS = [(p.true_eid, "True alarm (M1.0+ flare in next 24 h)", TRUE_ALARM), (p.false_eid, "False alarm (no M1.0+ flare)", FALSE_ALARM)]
D = {}
for eid, _, _ in ROWS:
    s = series(eid); t, _ = episode_t(eid)
    c = detrended_sd(s.t_obs.to_numpy(), s.box.to_numpy(float)) / s.box.mean()
    assert abs(c - cv_box(eid)) <= 1e-12 * cv_box(eid), f"{eid}: series does not reproduce stored CV_box"
    af = valid_aia_file(eid, t)
    aia, at = load_aia(af)
    mf, bf = hmi_files_near(eid, t)
    m, b, m0 = load_hmi(mf, bf)
    D[eid] = dict(t=t, s=s, aia=aia, at=at, m=m, b=b, m0=m0, mt=os.path.basename(mf).split(".")[3])
vmin, vmax = aia_range([d["aia"] for d in D.values()])
rel = {e: ((d["s"].t_obs - d["t"]).dt.total_seconds() / 3600, d["s"].box / d["s"].box.mean() - 1) for e, d in D.items()}
lo = min(v.min() for _, v in rel.values()); hi = max(v.max() for _, v in rel.values()); pad = 0.06 * (hi - lo)

fig = plt.figure(figsize=(FULL, 4.9))
outer = fig.add_gridspec(1, 2, width_ratios=[2.0, 1.3], wspace=0.30, left=0.01, right=0.99, top=0.94, bottom=0.16)
gi = outer[0].subgridspec(2, 2, hspace=0.30, wspace=0.06)
gp = outer[1].subgridspec(2, 1, hspace=0.42)
for row, (eid, label, (col, mk)) in enumerate(ROWS):
    d = D[eid]
    a0 = fig.add_subplot(gi[row, 0]); ih = show_hmi(a0, d["m"], d["b"]); clean_axes(a0)
    a0.set_title(f"({'ad'[row]}) HMI magnetogram", fontsize=8, loc="left")
    a1 = fig.add_subplot(gi[row, 1]); ia = show_aia(a1, d["aia"], vmin, vmax); clean_axes(a1)
    x, y = box_outline(d["m0"], d["aia"]); a1.plot(x, y, color="white", lw=0.7, ls="--")
    a1.set_xlim(a1.get_xlim()); a1.set_title(f"({'be'[row]}) AIA 94 Å, {d['at']:%H:%M} UTC", fontsize=8, loc="left")
    a2 = fig.add_subplot(gp[row, 0])
    h, yy = rel[eid]
    a2.axhline(0, color=GRID, lw=0.8, zorder=0)
    a2.plot(h, yy, "-", color=col, lw=0.9); a2.plot(h, yy, mk, color=col, ms=2.2, mew=0)
    a2.set_xlim(-24.5, 0.5); a2.set_ylim(lo - pad, hi + pad)
    a2.set_ylabel("box brightness\n/ mean − 1")
    a2.set_title(f"({'cf'[row]}) {label}\nHARP {eid.split('_')[0]}, 24 h before t", fontsize=8, loc="left")
    if row == 1:
        a2.set_xlabel("hours relative to alarm time t")
cb1 = fig.add_axes([0.03, 0.075, 0.25, 0.018]); fig.colorbar(ih, cax=cb1, orientation="horizontal").set_label("line-of-sight field (G); red = positive", fontsize=7)
cb2 = fig.add_axes([0.33, 0.075, 0.25, 0.018]); fig.colorbar(ia, cax=cb2, orientation="horizontal").set_label("log$_{10}$ AIA 94 Å (DN s$^{-1}$)", fontsize=7)
for cb in (cb1, cb2):
    cb.tick_params(labelsize=7)
print(save(fig, "F4_twin_pair_color", "f4_twin_pair_color.py"))
for e, d in D.items():
    print(e, "AIA", d["at"], "HMI", d["mt"])
