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
- **Core invariant:** generated resumes never contain a fact absent from the profile. Enforced by `jobpilot/facts.py` (`FactValidator`); `jobpilot/resume/generator.py` raises `ContentInvariantError` on violation. Any change to tailoring must keep the no-invention tests green.
- **Guardrails live in `jobpilot/applying/applier.py`** and `jobpilot/store.py`; read the module docstrings before changing apply logic. Dedupe relies on recording an attempt before submitting.
- **Safe verification:** use `--dry-run` (and `examples/demo.config.toml` for a fully offline run). Never perform a real application during development.
- **LinkedIn is review-only** by explicit product decision: discovered/tailored/packaged, never auto-submitted, never authenticated.

