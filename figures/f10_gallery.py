"""F10: image gallery of four TEST 1 twin pairs chosen by rule (decisions.md, commit f2cb21d, recorded before selection; image rule amended in bc6c4e8):
rank the 50 pairs by r = CV_box(true)/CV_box(false) (ascending, ties by file order) and take nearest-rank 10th, 35th,
65th and 90th percentiles = positions 5, 18, 33, 45 (1-based). Illustration only. Code written by Claude (AI, chat),
2026-10-06. Writes F10_gallery.pdf and prints the pairs and r (logged to f10_gallery.log by the caller).
Usage: python paper_template/figures/f10_gallery.py | tee paper_template/figures/f10_gallery.log"""
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from figstyle import FULL, save
from examples import C, cv_box, episode_t
from solar_images import valid_aia_file, hmi_files_near, load_aia, load_hmi, show_aia, show_hmi, aia_range, clean_axes

tw = pd.read_csv(f"{C}/twins_le2.csv")
assert len(tw) == 50, "TEST 1 twins file must hold 50 pairs"
tw["r"] = [cv_box(a) / cv_box(b) for a, b in zip(tw.true_eid, tw.false_eid)]
order = tw.reset_index().sort_values(["r", "index"], kind="stable").reset_index(drop=True)
PCT = [10, 35, 65, 90]
POS = [int(np.ceil(p / 100 * len(order))) for p in PCT]          # nearest rank, 1-based
assert POS == [5, 18, 33, 45]
gal = order.iloc[[p - 1 for p in POS]]

panels = []
for (_, row), pct in zip(gal.iterrows(), PCT):
    pr = {}
    for role in ("true", "false"):
        eid = row[f"{role}_eid"]; t, _ = episode_t(eid)
        a, at = load_aia(valid_aia_file(eid, t))
        mf, bf = hmi_files_near(eid, t); m, b, _ = load_hmi(mf, bf)
        pr[role] = dict(eid=eid, aia=a, at=at, m=m, b=b)
    panels.append((pct, row.r, row.group, pr))
vmin, vmax = aia_range([p[3][r]["aia"] for p in panels for r in ("true", "false")])

fig = plt.figure(figsize=(FULL, 6.6))
gs = fig.add_gridspec(len(panels), 4, hspace=0.42, wspace=0.07, left=0.085, right=0.995, top=0.935, bottom=0.075)
fig.text(0.085 + 0.455 * 0.5, 0.975, "TRUE alarm (M1.0+ flare in next 24 h)", ha="center", fontsize=8, fontweight="bold", color="#eb6834")
fig.text(0.085 + 0.455 * 1.5, 0.975, "FALSE alarm (no M1.0+ flare)", ha="center", fontsize=8, fontweight="bold", color="#52514e")
for i, (pct, r, grp, pr) in enumerate(panels):
    for j, role in enumerate(("true", "false")):
        d = pr[role]
        a0 = fig.add_subplot(gs[i, 2 * j]); ih = show_hmi(a0, d["m"], d["b"]); clean_axes(a0)
        a1 = fig.add_subplot(gs[i, 2 * j + 1]); ia = show_aia(a1, d["aia"], vmin, vmax); clean_axes(a1)
        a0.set_title(f"HARP {d['eid'].split('_')[0]}, {d['at']:%Y-%m-%d}", fontsize=7, loc="left")
        a1.set_title(f"AIA 94 Å, {d['at']:%H:%M} UTC", fontsize=7, loc="left")
    fig.text(0.012, 1 - (0.065 + (i + 0.5) * (0.86 / len(panels))), f"{pct}th percentile\nr = {r:.2f}",
             rotation=90, ha="left", va="center", fontsize=7.5)
cb1 = fig.add_axes([0.12, 0.03, 0.32, 0.012]); fig.colorbar(ih, cax=cb1, orientation="horizontal").set_label("line-of-sight field (G); red = positive", fontsize=7)
cb2 = fig.add_axes([0.60, 0.03, 0.32, 0.012]); fig.colorbar(ia, cax=cb2, orientation="horizontal").set_label("log$_{10}$ AIA 94 Å (DN s$^{-1}$)", fontsize=7)
for cb in (cb1, cb2):
    cb.tick_params(labelsize=6.5)
print(save(fig, "F10_gallery", "f10_gallery.py"))
print("rule: decisions.md commit f2cb21d; positions", POS, "of 50 pairs ranked by r = CV_box(true)/CV_box(false)")
for pct, r, grp, pr in panels:
    print(f"p{pct}: true {pr['true']['eid']} (AIA {pr['true']['at']:%Y-%m-%d %H:%M}), false {pr['false']['eid']} "
          f"(AIA {pr['false']['at']:%Y-%m-%d %H:%M}), group {grp}, r = {r:.4f}")
