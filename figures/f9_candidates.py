"""F9 all candidates: one row per evaluation in candidate_inventory.csv that has a Δ log-loss; point = Δ, line = 95% CI.
Plotted by code written by Claude Code (AI). Every plotted number comes from numbers.json (InvDelta/InvCIlo/InvCIhi<ID>,
ID = inventory row id in letters); the CSV supplies only row text (name, comparison, data set) and status_class.
Usage: python paper_template/figures/f9_candidates.py"""
import csv, os, re
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
from matplotlib.lines import Line2D
from figstyle import STATUS, status_style, INK, INK2, GRID, FULL, ROOT, numbers, num, save


def letters(n):                      # same rule as build_numbers.letters (1 -> A, 27 -> AA)
    out = ""
    while n:
        n, r = divmod(n - 1, 26); out = chr(65 + r) + out
    return out


BASES = ["A", "A + R4a", "C", "C_CV"]
NAMES = {"#22": "#22 S_last", "#23": "#23 dots", "#24": "#24 F_new", "#26": "#26 MR", "#27": "#27 MRKT",
         "#28": "#28 CNN1D", "#29": "#29 FBL", "n_B + R4a (F3 combination)": "n_B + R4a (F3)"}


def short_name(s):
    s = re.sub(r"^(21-list|unnumbered): ", "", s)
    s = re.sub(r"^(Phase [XF]|Step B|mask) ", "", s)
    return NAMES.get(s, s)


def short_cmp(s):
    s = s.split(" (")[0]                                   # drop parenthetical model notes
    s = re.sub(r" = .*$", "", s)                           # "A vs E94 = A + ΔCV_94" -> "A vs E94"
    return s.replace("A_CV", "A + log10 CV_box").replace("vs C_CV", "vs C + log10 CV_box") if s.endswith("_CV") else s


N = numbers()
DEV, TEST, SENS, CONF = (N[k]["value"] for k in ("SetDevYears", "SetTestYears", "SetSensYear", "SetConfYears"))
GROUPS = [("dev", f"Development {DEV}"), ("held-out", f"Held-out {TEST}, single-region"),
          ("EUV-unseen", f"EUV-unseen {TEST} (two-region)"), ("2022", f"{SENS} sensitivity set (never pooled)"), ("2025-26", f"{CONF}, ≤2-region")]
rows = []
for r in csv.DictReader(open(os.path.join(ROOT, "candidate_inventory.csv"), encoding="utf-8")):
    i, ID = int(r["id"]), letters(int(r["id"]))
    if r["delta"].strip() in ("", "none"):
        continue
    need = [f"{m}{ID}" for m in ("InvDelta", "InvCIlo", "InvCIhi")]
    miss = [m for m in need if m not in N]
    assert not miss, f"numbers.json lacks {miss}: rebuild with build_numbers.py"
    g = next(k for k, (key, _) in enumerate(GROUPS) if r["dataset"].startswith(key))
    cmp_ = short_cmp(r["comparison"])
    b = BASES.index(cmp_.split(" vs ")[0])
    rows.append(dict(id=i, g=g, b=b, name=short_name(r["number"]), cmp=cmp_, cls=r["status_class"].strip(),
                     d=num(N, need[0]), lo=num(N, need[1]), hi=num(N, need[2])))
assert len(rows) == 49, f"expected 49 rows with a Δ, found {len(rows)}"
rows.sort(key=lambda q: (q["g"], q["b"], q["id"]))

# y layout: one line per group header and per row, top to bottom
lines, y = [], 0
for k, (_, head) in enumerate(GROUPS):
    lines.append((head, y)); y += 1
    for q in (q for q in rows if q["g"] == k):
        q["y"] = y; y += 1
n_lines = y

PITCH, TOP, BOT, GAP = 0.133, 0.42, 0.78, 0.10              # in
H = n_lines * PITCH + TOP + BOT
fig = plt.figure(figsize=(FULL, H))
R = fig.canvas.get_renderer()


def wmax(key):
    """widest 8 pt label among rows[key], in inches (measured, then removed)."""
    ts = [fig.text(0, 0, q[key]) for q in rows]
    w = max(t.get_window_extent(R).width for t in ts) / fig.dpi
    for t in ts:
        t.remove()
    return w


x_name, w_name = 0.08, wmax("name")
x_cmp = x_name + w_name + GAP
LAB = x_cmp + wmax("cmp") + GAP                             # in: label column width (measured)
ax = fig.add_axes([LAB / FULL, BOT / H, 1 - LAB / FULL - 0.03, n_lines * PITCH / H])
ax.set_ylim(n_lines - 0.5, -0.5)
ax.set_yticks([]); ax.spines["left"].set_visible(False)
ax.axvline(0, color=INK2, lw=0.8, zorder=1)
ax.xaxis.grid(True, color=GRID, lw=0.5); ax.set_axisbelow(True)

tr = mtrans.blended_transform_factory(fig.transFigure, ax.transData)
x_name, x_cmp = x_name / FULL, x_cmp / FULL
for head, yy in lines:
    ax.text(0.0, yy, head, transform=tr, ha="left", va="center", fontweight="bold", color=INK)
    if yy:
        ax.axhline(yy - 0.5, color=GRID, lw=0.6, zorder=0, clip_on=False, xmin=-LAB / (FULL * ax.get_position().width))
for p, q in zip(rows, rows[1:]):                            # dotted rule between comparison families within a data set
    if p["g"] == q["g"] and p["b"] != q["b"]:
        ax.axhline(q["y"] - 0.5, color=GRID, lw=0.6, ls=":", zorder=0, clip_on=False,
                   xmin=-(LAB - x_cmp * FULL) / (FULL * ax.get_position().width), xmax=0)
for q in rows:
    col, mk, filled, _ = status_style(q["cls"])
    ax.text(x_name, q["y"], q["name"], transform=tr, ha="left", va="center", color=INK)
    ax.text(x_cmp, q["y"], q["cmp"], transform=tr, ha="left", va="center", color=INK2)
    ax.plot([q["lo"], q["hi"]], [q["y"]] * 2, "-", color=col, lw=1.1, solid_capstyle="butt", zorder=2)
    ax.plot(q["d"], q["y"], mk, color=col, ms=4, mfc=col if filled else "white", mec=col,
            mew=0.4 if filled else 0.8, zorder=3)
lo, hi = ax.get_xlim()
assert all(lo < v < hi for q in rows for v in (q["lo"], q["d"], q["hi"])), "a Δ or CI end lies outside the x-limits"

ax.set_xlabel("Δ log-loss = log-loss(baseline) − log-loss(baseline + candidate); line: 95% CI", loc="right")
used = [c for c in STATUS if c != "PRE-REGISTERED" and any(q["cls"] == c for q in rows)]
assert {q["cls"] for q in rows} <= set(used), "status_class must be a full STATUS key (no short alias)"
handles = [Line2D([0], [0], color=col, marker=mk, lw=1.1, ms=4, mfc=col if f else "white", mec=col,
                  mew=0.4 if f else 0.8) for col, mk, f, _ in map(status_style, used)]
fig.legend(handles, [status_style(c)[3] for c in used], loc="upper left", bbox_to_anchor=(0.0, 1.0), ncol=2, handlelength=1.8,
           columnspacing=1.4, borderaxespad=0.0)
print(save(fig, "F9_candidates", "f9_candidates.py"))
for c in used:
    print(f"{c}: rows {[q['id'] for q in rows if q['cls'] == c]}")
