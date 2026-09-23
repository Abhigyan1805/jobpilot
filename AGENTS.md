# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

## Project notes

- **Test command:** `python -m unittest discover -s tests -t .` (from repo root). Tests use `unittest`, not pytest.
- **CI:** `.github/workflows/ci.yml` runs `ruff check .` and the test suite on every PR and push to `main`; the same commands are pinned in `.no-mistakes.yaml` (`commands.lint` is `uvx ruff check .` because `ruff` is not on the pipeline-host PATH, though `uvx` is). Use `python3`, not `python`: only `python3` is installed on the pipeline host (GitHub runners ship both).
- **Ruff pinning:** `pyproject.toml` pins `[tool.ruff.lint] select` to the stable pre-0.16 default (rationale in the comment there); widen it only together with fixing the resulting findings.
- **No third-party dependencies.** Stdlib only: `urllib`, `html.parser`, `sqlite3`, `tomllib`, `unittest`. Do not add a dependency without a strong reason; `pip install` is blocked in the dev environment anyway.
- **Read-only inputs** (never modify, paths come from `config.toml`): master profile `PROFILE.md`, style template `Abhigyan_Resume_AI_ML.tex`, and the LaTeX engine. The preamble of the style template is reused verbatim by `jobpilot/resume/generator.py`.
- **LaTeX engine is a Windows `.exe` run from WSL.** `jobpilot/resume/compiler.py` runs it with `cwd` set to the `.tex` directory and a relative filename so path translation works. `pdftotext.exe` ships in the same MiKTeX bin dir and powers the parseability check.
- **Any Windows `.exe` invoked from WSL must get a `cwd` + relative filename, never an absolute Linux path argument** (WSL does not translate those, so the process cannot open the file). Both `compiler.py` and `resume/parseability.py:extract_pdf_text` follow this; `tests/test_tailoring.py` guards the extractor invocation without needing the toolchain. The integration test `test_tailored_resume_compiles_and_is_parseable` is the end-to-end check.
- **Core invariant:** generated resumes never contain a fact absent from the profile. Enforced by `jobpilot/facts.py` (`FactValidator`); `jobpilot/resume/generator.py` raises `ContentInvariantError` on violation. Any change to tailoring must keep the no-invention tests green.
- **Guardrails live in `jobpilot/applying/applier.py`** and `jobpilot/store.py`; read the module docstrings before changing apply logic. Dedupe relies on recording an attempt before submitting.
- **Scoring rubric (`jobpilot/matching.py`) is a safety boundary, not a ranking nicety.** `strong` is the auto-apply band and requires both `score >= match.strong_threshold` *and* `role_relevance >= match.strong_min_role_relevance` (a low-relevance posting is capped to `shortlist` with a reason). Role relevance counts title hits (`TITLE_HIT_WEIGHT`) far above body hits (capped below the floor) and is computed over the role section only - `_role_description` drops company boilerplate above the first role heading. Retarget a search through config (`[match.target_terms]` + the floor), never by hardcoding. Keep `tests/test_matching.py` green.
- **Parseability keyword survival uses profile-present surface forms**, not canonical labels: `pipeline._run_parseability` calls `lexicon.present_surface_forms`, because the never-invent generator can only emit aliases the profile actually contains (e.g. canonical `Communication` supported via `cross-functional`). Checking the canonical label false-fails a parseable resume; don't revert it.
- **Review detail vs category (`jobpilot/store.py`):** `applications.review_reason` holds the detailed human-readable reason; `applications.review_category` holds the guard category. `TRANSIENT_REVIEW_REASONS`, `submitted_or_attempted`, and `decide_review` must read the category, never the detail, or transient-route/dedupe behaviour breaks.
- **Safe verification:** use `--dry-run` (and `examples/demo.config.toml` for a fully offline run). Never perform a real application during development.
- **Source taxonomy lives in `jobpilot/config.py` and the loaded config.** Automated read-only adapters are registered in `jobpilot/discovery/registry.py` and listed in `DEFAULT_DISCOVERY_SOURCES`. Manual link-out sources come from `config.link_out.sources` (defaulting to `DEFAULT_LINK_OUT_SOURCES`), so a source a user adds under `[link_out.sources.<name>]` is usable end to end: `linkout.is_manual_source(config, name)` drives both `link-out add` validation and the applier's review-only guard. Configured link-out sources must never be added to the registry or scraped. LinkedIn is the single documented exception: an optional, off-by-default read-only listing reader gated by `config.linkedin.enabled`; link-out is the default LinkedIn path and it is not a licence to scrape any other manual-only site.
- **Adapters carry each board's typed employment value but never drop on it.** `JobPosting.employment_type` carries the board's own typed field; the shared hard filter (`filtering.fulltime_check`) decides, rescuing a genuine intern tagged `FullTime` into human review. Do not add adapter-level typed-value drops or title-regex intern filters upstream. On search endpoints a server-side typed facet (e.g. Himalayas `employment_type=Intern`, The Muse `level=Internship`) may be used as a high-precision slice, but it must never be the only path by which a posting can be discovered: pair it with a broader query, merge and dedupe by source job id (`discovery.base.dedupe_postings`), and never let a secondary-query failure fail the adapter.
- **LinkedIn and every manual-only source are review-only** by explicit product decision: discovered/tailored/packaged, never auto-submitted, never authenticated. The applier guard returns `linkedin_review` for LinkedIn and `manual_review` (`manual_source`, a non-transient reason) for the rest.

