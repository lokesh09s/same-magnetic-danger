"""No-download reproduction check for the public release (code by Claude Code (AI), 2026-10-11; new file, no new method).
Run from public_release/ after restoring the data layout (README, "Reproduce without downloads"):
    PYTHONPATH=src python scripts/00_reproduce_from_results.py
1. TEST 1 with the registered code (euv_f2_replication.twins, euv_confirm_tests.ratio_block; loader = euv_confirm_tests.conf_cohort
   lines 19-23 as prospective_look1_analysis.load_cv) on data/euv_confirm. Expected: logs/euv_confirm_tests.log lines 2 and 5.
2. Post-hoc region checks: runs scripts/10_posthoc_region_checks.py unchanged; its output must equal logs/posthoc_region_checks.log."""
import contextlib, io, runpy
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
from euv_f2_replication import twins
from euv_confirm_tests import ratio_block
from phase_f import W
from prospective_look1_analysis import load_cv

if __name__ == "__main__":
    ok = []
    c = load_cv("data/euv_confirm", "data/euv_confirm/cohort_le2.csv")
    c1 = c[(c.primary_fill >= 0.80) & c.primary_CV_box.notna()].reset_index(drop=True)      # euv_confirm_tests.py:61
    tw, nt = twins(c1)
    with ProcessPoolExecutor(W) as pool:
        P = ratio_block("PRIMARY CV_box twins (<= 2)", c1, tw, pool)
    cv = c1.set_index("eid").primary_CV_box
    higher = int((cv[tw.true_eid].to_numpy() > cv[tw.false_eid].to_numpy()).sum())
    got = (f"set {len(c1)} (true {int(c1.true_alarm.sum())}, HARPs {c1.harpnum.nunique()}); {len(tw)} pairs of {nt} true; "
           f"twins ratio {P['ratio_twins']:.4f} [{P['tw_CI_lo']:.4f}, {P['tw_CI_hi']:.4f}]; true higher in {higher} of {P['pairs']} pairs")
    want = "set 378 (true 56, HARPs 101); 50 pairs of 56 true; twins ratio 3.2624 [1.2956, 9.4887]; true higher in 39 of 50 pairs"
    same_pairs = tw[["true_eid", "false_eid"]].equals(pd.read_csv("data/euv_confirm/twins_le2.csv")[["true_eid", "false_eid"]])
    ok.append(got == want and same_pairs)
    print(f"TEST 1: {got}\n  expected {want} (euv_confirm_tests.log:2,5; 39/50: sensitivity_combined.log:16); "
          f"pairs identical to twins_le2.csv: {same_pairs} -> {'PASS' if ok[-1] else 'FAIL'}")
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path("scripts/10_posthoc_region_checks.py", run_name="__main__")      # writes ./posthoc_region_checks.log
    ok.append(open("posthoc_region_checks.log").read() == open("logs/posthoc_region_checks.log").read())
    print(f"post-hoc region checks: output identical to logs/posthoc_region_checks.log -> {'PASS' if ok[-1] else 'FAIL'}")
    print(f"RESULT: {'PASS' if all(ok) else 'FAIL'} ({sum(ok)}/{len(ok)})")
