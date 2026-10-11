"""Shared style for every paper_template figure (code written by Claude Code (AI)).
Palette: dataviz reference categorical slots, validated with validate_palette.js (light surface): lightness, chroma, CVD
separation (worst adjacent dE 9.2) and normal-vision floor PASS; contrast < 3:1 for AQUA/YELLOW -> always paired with
labels/legends. Every series also gets its own marker or line style, so figures stay readable in greyscale.
Text: sans-serif, 8 pt at final size (figures are made at their final printed width)."""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, ORANGE, AQUA, VIOLET, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#eda100"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#d9d9d6"
TEXTWIDTH = 6.30          # in: LaTeX text width (A4, 2.5 cm margins; main.tex uses the same geometry)
FULL = 6.20               # in: full-width figure size; figures are included at natural size (no scaling), so 8 pt stays 8 pt
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

# fixed role -> (colour, marker); colour follows the entity in every figure
TRUE_ALARM, FALSE_ALARM = (ORANGE, "^"), (INK2, "o")   # BLUE is reserved for pre-registered status
# status -> (colour, marker, filled, legend text). One map for every figure and table (status_class in candidate_inventory.csv).
# A development-years result is always EXPLORATORY (dev), even if its design was pre-registered.
STATUS = {
    "PRE-REGISTERED CONFIRMATORY": (BLUE, "o", True, "pre-registered, confirmatory"),
    "PRE-REGISTERED SECONDARY": (BLUE, "o", False, "pre-registered, secondary or sensitivity"),
    "PRE-REGISTERED RE-TEST ON ALREADY-ANALYSED DATA": (BLUE, "s", False, "pre-registered re-test (already-analysed data)"),
    "EXPLORATORY (dev)": (AQUA, "D", True, "exploratory (development years)"),
    "SENSITIVITY (post-hoc)": (VIOLET, "^", True, "sensitivity (post-hoc)"),
    "POST-HOC": (YELLOW, "v", False, "post-hoc"),
}
STATUS["PRE-REGISTERED"] = STATUS["PRE-REGISTERED CONFIRMATORY"]          # short key


def status_style(status):
    """-> (colour, marker, filled, legend text) for a status string (exact key, or prefix of a known key)."""
    s = status.strip().upper()
    for k, v in STATUS.items():
        if s == k.upper():
            return v
    raise KeyError(f"unknown status {status!r}; use one of {list(STATUS)}")

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 8,
    "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "lines.linewidth": 1.2,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


_USED = set()


class _Tracked(dict):
    """records every macro a figure script reads (check_outputs.py lists them per figure)."""
    def __getitem__(self, k):
        _USED.add(k)
        return super().__getitem__(k)

    def get(self, k, default=None):
        if k in self:
            _USED.add(k)
        return super().get(k, default)


def _dump_used():
    path = os.environ.get("FIGSTYLE_MACROS")
    if path:
        open(path, "w").write("\n".join(sorted(_USED)))


import atexit
atexit.register(_dump_used)


def numbers():
    """{macro: {"value": str, "num": float|None, ...}} written by build_numbers.py (the only number source for figures)."""
    return _Tracked(json.load(open(os.path.join(ROOT, "numbers.json"), encoding="utf-8")))


def num(N, macro):
    v = N[macro]["num"]
    assert v is not None, f"{macro} is not numeric"
    return v


def save(fig, name, script):
    path = os.path.join(os.environ.get("FIGSTYLE_OUTDIR", HERE), f"{name}.pdf")   # check_outputs.py writes re-runs elsewhere
    fig.savefig(path, metadata={"Creator": f"Claude Code (AI): paper_template/figures/{script}", "Title": name})
    plt.close(fig)
    return path
