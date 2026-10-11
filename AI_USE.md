# AI use

This summary follows the project's decision log, `preregistration/decisions.md`. Every entry there says who decided
it ("decided by: user") and who drafted or ran what. The running list is the "AI-use disclosure" section (line 712);
the per-entry tags appear throughout. The paper's own AI-use statement is the authoritative version.

## Claude Code (Anthropic)

- Wrote the data pipeline and the analysis code in `src/` and `scripts/`, and the figure scripts not listed under
  Claude (chat) below, and ran the analyses at the user's request.
  - The prospective Look 1 downloads are the exception. The students run every Look 1 step and log who ran each one
    (`preregistration/LOOK1_RUN_SHEET.md`).
- Wrote this release at the user's request on 2026-10-11:
  - the file selection;
  - the minimal path edits listed in `CHANGES.md`;
  - `scripts/00_reproduce_from_results.py`;
  - `README.md`, `MANIFEST.md`, `CHANGES.md`, this file and `preregistration/PREREG_INDEX.md`.

## Claude (Anthropic, chat)

- **Pre-registration wording:** drafted the wording of pre-registrations, which Lokesh reviewed and adopted. These
  entries are marked "wording drafted by Claude AI, reviewed and adopted by Lokesh".
- **Exploratory designs:** drafted several exploratory designs, which the students adopted ("design drafted by AI,
  adopted by the student").
- **The C+ protection rule** was designed after post-hoc inspection by Claude AI (in chat) of all 2010–2026 alarms.
  - The disclosure is recorded verbatim in the 2026-09-28 C+ entry of `decisions.md`.
  - On 2026-10-09 the user clarified that the pattern was first seen in 2010–2019 development data. That
    clarification is recorded in `decisions.md` (an entry recorded by Codex at the user's request).
  - The log keeps both accounts visible and states that the chronology is unresolved.
  - All C+ results are therefore reported as POST-HOC, not as independent confirmation.
- **Figure scripts:** wrote `figures/f1_method_updated.py`, `f3_cvbox_color.py`, `f4_twin_pair_color.py`, `f10_gallery.py`,
  `results_figs.py` and `solar_images.py`. Each says so in its header.
- **Post-hoc analyses:** computed several in chat. They are reproduced by code in `logs/posthoc_2026-09-28.md`
  (`src/posthoc_2026_09_28.py`).

## Codex (OpenAI)

- Generated and ran one exploratory verification run (`verification/` in the project repository). It was not part
  of the final analysis and is not included here.
- Did editing work, including recording the 2026-10-09 clarification entry in `decisions.md` at the user's request.
- Produced a private reference manuscript draft. It is not for submission and is not included here; it was fact-checked
  against the repository (`decisions.md`, 2026-10-05).

## Decisions

Every scientific decision (hypotheses, tests, thresholds, data periods, run dates) is recorded in `decisions.md` as
the user's. The log is append-only.
