"""F3 (colour): how CV_box is computed, with five AIA 94 A snapshots of the same episode across the 24-h window.
Same episode as f3_cvbox.py (true member of the 983bcae pair). Code written by Claude (AI, chat), 2026-10-06; display
rules in decisions.md (commit f2cb21d) and solar_images.py. The fit/residual SD reproduce the stored CV_box to 1e-12.
Usage: python paper_template/figures/f3_cvbox_color.py"""
import os, sys
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from figstyle import TRUE_ALARM, INK2, GRID, FULL, save
from examples import select_pair, series, episode_t, cv_box
from solar_images import aia_file_near, hmi_files_near, load_aia, load_hmi, box_outline, show_aia, aia_range, clean_axes

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from euv_pilot import detrended_sd

eid = select_pair().true_eid
s = series(eid); t, _ = episode_t(eid)
times, y = s.t_obs.to_numpy(), s.box.to_numpy(float)
hrs0 = (pd.to_datetime(pd.Series(times)) - pd.Timestamp(times[0])).dt.total_seconds().to_numpy() / 3600
coef = np.polyfit(hrs0, y, 1); fit = np.polyval(coef, hrs0); res = y - fit
sd, mean = np.std(res, ddof=1), y.mean()
assert sd == detrended_sd(times, y), "residual SD differs from euv_pilot.detrended_sd"
assert abs(sd / mean - cv_box(eid)) <= 1e-12 * cv_box(eid), "SD/mean does not reproduce the stored CV_box"
h = ((s.t_obs - t).dt.total_seconds() / 3600).to_numpy()
assert ((h >= -24.5) & (h <= 0.5)).all(), "series outside the plotted window"

TARGETS = [-24, -18, -12, -6, 0]
idx = [int(np.argmin(np.abs(h - k))) for k in TARGETS]                # nearest VALID frame (series holds valid frames only)
mf, bf = hmi_files_near(eid, t); _, _, m0 = load_hmi(mf, bf)
snaps = []
for i in idx:
    f = aia_file_near(eid, s.t_obs.iloc[i])
    mp, ft = load_aia(f)
    assert abs((ft - s.t_obs.iloc[i]).total_seconds()) < 60, "thumbnail file does not match the valid frame"
    snaps.append((mp, ft, h[i]))
vmin, vmax = aia_range([m for m, _, _ in snaps])
col, mk = TRUE_ALARM

fig = plt.figure(figsize=(FULL, 4.6))
gs = fig.add_gridspec(3, 5, height_ratios=[1.0, 1.25, 1.0], hspace=0.42, wspace=0.05, left=0.10, right=0.99, top=0.905, bottom=0.09)
for k, (mp, ft, hh) in enumerate(snaps):
    ax = fig.add_subplot(gs[0, k]); show_aia(ax, mp, vmin, vmax); clean_axes(ax)
    x, yy = box_outline(m0, mp); ax.plot(x, yy, color="white", lw=0.6, ls="--")
    ax.set_title(f"{k + 1}:  t {hh:+.0f} h".replace("-", "−"), fontsize=8)
fig.text(0.10, 0.975, "(a) AIA 94 Å snapshots of HARP " + eid.split("_")[0] + " (dashed: the box whose mean brightness is tracked)",
         fontsize=8, ha="left")
a1 = fig.add_subplot(gs[1, :]); a2 = fig.add_subplot(gs[2, :], sharex=a1)
a1.plot(h, y, mk, color=col, ms=2.4, mew=0, label="box mean (valid frames)")
a1.plot(h, y, "-", color=col, lw=0.6, alpha=0.6)
a1.plot(h, fit, "--", color=INK2, lw=1.1, label="least-squares straight line")
a1.axhline(mean, color=INK2, lw=0.9, ls=":", zorder=0)
a1.text(h[0], mean, " mean", va="bottom", ha="left", fontsize=8, color=INK2)
for k, i in enumerate(idx):
    a1.annotate(str(k + 1), (h[i], y[i]), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=7,
                color="#1f3a5f", arrowprops=dict(arrowstyle="-", color="#1f3a5f", lw=0.6))
a1.set_ylabel("94 Å box mean\n(DN/s per pixel)")
a1.legend(loc="upper right", handlelength=1.6)
a1.set_title("(b) Box-mean series and linear trend (numbers mark the snapshots above)", loc="left", fontsize=8)
plt.setp(a1.get_xticklabels(), visible=False)
a2.axhline(0, color=GRID, lw=1.0, zorder=0)
a2.fill_between([-24.5, 0.5], -sd, sd, color=GRID, alpha=0.6, lw=0, label="± 1 SD of residuals")
a2.plot(h, res, mk, color=col, ms=2.4, mew=0); a2.plot(h, res, "-", color=col, lw=0.6, alpha=0.6)
a2.set_xlim(-24.5, 0.5); a2.set_xlabel("hours relative to alarm time t"); a2.set_ylabel("residual\n(DN/s per pixel)")
a2.legend(loc="upper right")
a2.set_title("(c) Residuals from the trend · CV$_{\\rm box}$ = SD of residuals / mean of the series", loc="left", fontsize=8)
print(save(fig, "F3_cvbox_color", "f3_cvbox_color.py"))
print(f"episode {eid}: stored CV_box reproduced to 1e-12; snapshots at", [f"{ft:%Y-%m-%d %H:%M}" for _, ft, _ in snaps])
