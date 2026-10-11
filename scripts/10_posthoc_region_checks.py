"""POST-HOC region-level robustness checks of TEST 1 (2025-26 CV_box twins), on already-analysed data.
Code written by Claude (AI) at the user's request, 2026-10-11. Reads only data/euv_confirm/twins_le2.csv and
data/euv_confirm/results/*.json (no data with t >= 2026-08-17). Output: posthoc_region_checks.log"""
import json, csv, math, random, statistics as st
from math import comb
D = "data/euv_confirm/"
tw = list(csv.DictReader(open(D + "twins_le2.csv")))
cv = lambda e: float(json.load(open(f"{D}results/{e}.json"))["primary_CV_box"])
P = [(r["true_harp"], cv(r["true_eid"]), cv(r["false_eid"])) for r in tw]
ratio = lambda P: st.median(p[1] for p in P) / st.median(p[2] for p in P)
out = []
out.append(f"pairs {len(P)}; twins ratio (median true / median false) {ratio(P):.4f}; true more restless in {sum(p[1] > p[2] for p in P)} of {len(P)} pairs")
H = {}
for h, t, f in P: H.setdefault(h, []).append(t > f)
maj = sum(sum(v) > len(v) / 2 for v in H.values()); tie = sum(sum(v) == len(v) / 2 for v in H.values()); opp = len(H) - maj - tie
p_all = 2 * sum(comb(len(H), k) for k in range(maj, len(H) + 1)) / 2 ** len(H)
n2 = maj + opp; p_ex = 2 * sum(comb(n2, k) for k in range(maj, n2 + 1)) / 2 ** n2
out.append(f"region-level sign: {len(H)} true-alarm HARPs; true more restless in most pairs {maj}, evenly split {tie}, opposite {opp}")
out.append(f"  two-sided sign test, ties counted against: {maj}/{len(H)} p = {p_all:.4f}; ties excluded: {maj}/{n2} p = {p_ex:.4f}")
out.append("  per HARP (true-higher / pairs): " + ", ".join(f"{h} {sum(v)}/{len(v)}" for h, v in sorted(H.items(), key=lambda x: -len(x[1]))))
loo = {h: ratio([p for p in P if p[0] != h]) for h in H}
lo = min(loo, key=loo.get); hi = max(loo, key=loo.get)
out.append(f"leave-one-true-HARP-out twins ratio: {loo[lo]:.2f} (without {lo}) to {loo[hi]:.2f} (without {hi})")
L = {}
for h, t, f in P: L.setdefault(h, []).append(math.log(t / f))
est = math.exp(st.median([x for v in L.values() for x in v]))
rng = random.Random(20261011); keys = list(L); B = []
for _ in range(2000):
    s = [x for h in (rng.choice(keys) for _ in keys) for x in L[h]]
    B.append(math.exp(st.median(s)))
B.sort()
out.append(f"paired estimate (median of within-pair CV_box ratios): {est:.2f} [{B[49]:.2f}, {B[1949]:.2f}] (2,000 resamples of true-alarm HARPs, seed 20261011; one-way, like the registered interval)")
txt = "POST-HOC region-level checks of TEST 1 (not pre-registered)\n" + "\n".join(out) + "\n"
open("posthoc_region_checks.log", "w").write(txt); print(txt)
