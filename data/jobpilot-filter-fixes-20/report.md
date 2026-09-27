# jobpilot filter fixes — report (jobpilot-filter-fixes-20)

Date: 2026-09-27. Operator: crewmate (firstmate-managed). Mode: **dry run only,
zero submissions**. Branch: `fm/jobpilot-filter-fixes-20`.

Captain's review page 19 was 14 listings and all 14 were misses: 5 already
closed, 3 already applied, 6 with stipends below ₹30,000/month that the page did
not show (they sat in the "stipend not stated" bucket, so the floor excluded
nothing). Verbatim per-card feedback: `/home/abhigyan/firstmate/data/jobpilot-feedback-page19.md`.

Three distinct defects were fixed.

## Defect 1 — closed applications passed the open-state filter (5 misses)

Named misses: #1 Deep Variance Inc, #3 Prism Labs, #5 Kisan Udyog Python
Developer, #12 Zenotalent Python Internship, #14 Vortizo AI Python Internship.

**Root cause.** Unstop keeps returning a row as `status="LIVE"` with
`regn_open=1` long after the application has closed, and the top-level
`end_date` is the *internship's* end, not the registration close. The old check
trusted `status` implicitly and only read the top-level `end_date`, so all five
passed.

**Fix.** `jobpilot/openstate.py:assess_open_state` now reads the registration
window Unstop returns separately under `regnRequirements`
(`start_regn_dt`/`end_regn_dt`, flat or nested) and rejects a row whose
registration close has passed, comparing the *time of day* when the board states
one (Kisan Udyog #5 closed 2026-09-27 13:21 and was still shown that afternoon).
A future `start_regn_dt` is likewise treated as not yet open. `status="LIVE"` is
no longer trusted. `OpenState.key` (`open`/`closed`/`unverified`) is persisted on
the posting so the page can show the verdict.

**Non-Unstop / no-signal sources.** A source that publishes no closure signal is
still **unverified** — the pipeline never drops a posting for missing
information — but `jobpilot present` now marks it on the card
(`Open state: unverified - the source published no closure signal`). We chose
this over dropping every unverified posting, which would discard legitimate open
roles from boards that simply do not publish a deadline. A posting with a
confirmed signal is labelled `Open state: confirmed open`.

**Live probe (2026-09-27, read-only).** Every one of the five named closed rows
carried a future-looking `end_date` and `status=LIVE` with a passed
`end_regn_dt`:

| Posting | end_date | end_regn_dt | Result |
| --- | --- | --- | --- |
| #1 Deep Variance Inc | 2026-09-29 | 2026-09-15 | closed |
| #3 Prism Labs | 2026-09-27 | 2026-09-13 | closed |
| #5 Kisan Udyog | 2026-09-27 13:21 | 2026-09-27 13:21 | closed (time-of-day) |
| #12 Zenotalent | 2026-09-30 | 2026-09-22 | closed |
| #14 Vortizo AI | 2026-10-07 | 2026-10-07 | **open** (see note below) |

**Note on #14.** The feedback tags #14 CLOSED, but the live typed data shows it
open (`status=LIVE`, `regn_open=1`, registration open until 2026-10-07) and
paying ₹35,000/month. No honest signal closes it. The captain's verbatim note
for #14 is "done", which reads as *already applied* rather than *closed*; if
that is correct, its entry just needs to be appended to
`data/applied-postings.toml` (it is not there today). We did not fabricate a
closure or hide a genuinely-open qualifying posting. It is the one card the
fixed page shows.

## Defect 2 — stipend parser missed stated amounts (6 misses)

Named misses: #2 Frugality 12k, #4 FlatUIUX 12k, #7 AI Invito 5k, #10 Qveto 10k,
#11 IntelleQAcademy Python Dev 20k, #13 IntelleQAcademy GenAI 20k.

**Root cause.** The amounts are not in the description at all: Unstop publishes
them in a structured `jobDetail` block (`min_salary`/`max_salary`/`currency`/
`pay_in`). The adapter only mapped `details`/skills into `description`, so the
parser saw no rupee figure and returned `unstated`.

**Fix.** `jobpilot/discovery/unstop.py` now appends the board's own typed salary
to the description as a line the existing parser already understands, e.g.
`Stipend: ₹8,000 - ₹12,000 per month`. Nothing is invented: the figure, its
range and its period come from `jobDetail`, and the line is emitted only when
`show_salary` is truthy, the salary is disclosed, and the currency is rupees. An
explicit `paid_unpaid = unpaid` is carried as `Stipend: Unpaid`.

**Live values now recovered** (all below the ₹30,000 floor; the captain's
numbers are the range maxima):

| Posting | jobDetail (min–max) | Parser output |
| --- | --- | --- |
| #2 Frugality Fintech | 8,000–12,000 | ₹8,000-12,000/mo below floor |
| #4 FlatUIUX | 7,000–12,000 | ₹7,000-12,000/mo below floor |
| #7 AI Invito | 1,000–5,000 | ₹1,000-5,000/mo below floor |
| #10 Qveto | 1,000–10,000 | ₹1,000-10,000/mo below floor |
| #11 IntelleQAcademy | 10,000–20,000 | ₹10,000-20,000/mo below floor |
| #13 IntelleQAcademy | 10,000–20,000 | ₹10,000-20,000/mo below floor |

## Defect 3 — applied-list path resolution (3 misses + recurrence risk)

**Root cause.** `[filter].exclude_file` resolved relative to the config file's
directory. A run-config placed outside the repo therefore resolved to a
non-existent file and silently loaded zero exclusions, so already-applied
postings reappeared.

**Fix.** `Config.resolve_exclude_file()` searches the output dir's project, then
the config's directory, then the package/repo root, and returns the first
existing file. A configured path that resolves nowhere now raises `ConfigError`
instead of silently loading an empty list. `present` uses the new resolver.

The three page-19 applied postings (Biogen, PSYC, SmaranAI) were already
appended to the shared list by the captain; the tracked repo copy is updated to
the same 48 entries, so the fix and the data travel together.

## Verification — fresh dry-run sweep + present

```
python3 -m jobpilot --config /tmp/opencode/config-verify20.toml run --dry-run --stages discover,match
python3 -m jobpilot --config /tmp/opencode/config-verify20.toml run --dry-run --stages tailor,apply --limit 40
python3 -m jobpilot --config /tmp/opencode/config-verify20.toml present
```

Fresh DB/out dir (`out-verify20/jobpilot-verify20.db`). The config lives in
`/tmp` (outside the repo) with a **relative** `exclude_file =
"data/applied-postings.toml"`, so the run exercises Defect 3 end to end; it
resolved to the repo's 48-entry list. To bound the LaTeX/tailoring cost the sweep
enabled only `unstop` and `themuse` (the two sources that produced page 19);
the other configured sources were left disabled. This is a bounded sweep, not
the full source set.

**Before → after**

| | Page 19 | Fixed fresh page |
| --- | --- | --- |
| cards | 14 | 1 |
| closed | 5 | 0 |
| already applied | 3 | 0 |
| stipend below floor | 6 | 0 |

Filter-level counts on the fresh sweep (650 postings upserted):

- **512** rejected as closed (`registration closed ...`) — all Unstop.
- **497** stipend-check rejections (**277** confirmed below floor, **220**
  explicitly unpaid).
- **7** eligible postings on the applied list dropped by `present`
  (`already applied`), including the captain-added Biogen entry.
- Final page: **1** card — Vortizo AI, Python Internship, `Open state: confirmed
  open`, `₹35,000/mo confirmed`.

The page contains no `application closed`, `registration closed`,
`already applied`, or `below floor` string. The five named closed postings are
all rejected with `application_open: registration closed ...`; the six named
below-floor postings are all rejected with their recovered amounts.

## Residual, stated plainly

#14 Vortizo AI Python Internship is shown because it is genuinely open and pays
₹35,000/month; it is not one of the three categories the captain wants gone. If
his "done" note means he applied to it, it belongs in the applied list (a data
update) — the filters are behaving correctly. No other residual: every named
closed, applied, and below-floor posting is now dropped.

## Tests

- `tests/test_openstate.py`: the five named closed postings' real typed values,
  nested and flat `regnRequirements`, same-day time-of-day closure, future
  registration start, and the unverified key.
- `tests/test_source_adapters.py`: typed stipend carried per real form,
  disclosed/undisclosed/unshown/non-rupee/unpaid handling.
- `tests/test_stipend.py`: the six recovered `Stipend: ...` forms confirmed
  below floor using the real description tail.
- `tests/test_exclusions.py`: a config outside the repo resolves and applies the
  shipped list, and a missing configured file raises instead of loading zero.
- `tests/test_present.py`: unverified vs confirmed open-state card marking.

Full suite: 453 tests, green. `uvx ruff check .`: clean.
