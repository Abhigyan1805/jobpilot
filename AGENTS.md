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
- **No third-party dependencies.** Stdlib only: `urllib`, `html.parser`, `sqlite3`, `tomllib`, `unittest`. Do not add a dependency without a strong reason; `pip install` is blocked in the dev environment anyway.
- **Read-only inputs** (never modify, paths come from `config.toml`): master profile `PROFILE.md`, style template `Abhigyan_Resume_AI_ML.tex`, and the LaTeX engine. The preamble of the style template is reused verbatim by `jobpilot/resume/generator.py`.
- **LaTeX engine is a Windows `.exe` run from WSL.** `jobpilot/resume/compiler.py` runs it with `cwd` set to the `.tex` directory and a relative filename so path translation works. `pdftotext.exe` ships in the same MiKTeX bin dir and powers the parseability check.
- **Any Windows `.exe` invoked from WSL must get a `cwd` + relative filename, never an absolute Linux path argument** (WSL does not translate those, so the process cannot open the file). Both `compiler.py` and `resume/parseability.py:extract_pdf_text` follow this; `tests/test_tailoring.py` guards the extractor invocation without needing the toolchain. The integration test `test_tailored_resume_compiles_and_is_parseable` is the end-to-end check.
- **Core invariant:** generated resumes never contain a fact absent from the profile. Enforced by `jobpilot/facts.py` (`FactValidator`); `jobpilot/resume/generator.py` raises `ContentInvariantError` on violation. Any change to tailoring must keep the no-invention tests green.
- **Guardrails live in `jobpilot/applying/applier.py`** and `jobpilot/store.py`; read the module docstrings before changing apply logic. Dedupe relies on recording an attempt before submitting.
- **Safe verification:** use `--dry-run` (and `examples/demo.config.toml` for a fully offline run). Never perform a real application during development.
- **Source taxonomy is split in `jobpilot/config.py`.** Automated read-only adapters are registered in `jobpilot/discovery/registry.py` and listed in `DEFAULT_DISCOVERY_SOURCES`. Manual-only sources live in `DEFAULT_LINK_OUT_SOURCES` / `MANUAL_ONLY_SOURCES`: they must never be added to the registry or scraped. `jobpilot/linkout.py` owns the link-out channel; `run_manual_pipeline` in `pipeline.py` + `jobpilot link-out add` prepare a review packet from a hand-added posting.
- **Internship status comes from a source's typed field, never a title.** `SourceAdapter.keep_intern` (`discovery/base.py`) enforces this for per-source adapters; a typed value absent is kept for the shared hard filter, a present non-intern value is dropped. Do not add title-regex intern filters upstream.
- **LinkedIn and every manual-only source are review-only** by explicit product decision: discovered/tailored/packaged, never auto-submitted, never authenticated. The applier guard returns `linkedin_review` for LinkedIn and `manual_review` (`manual_source`, a non-transient reason) for the rest.

