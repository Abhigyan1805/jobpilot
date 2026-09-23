# jobpilot full-source-set run — report (jobpilot-run-07)

Date: 2026-09-23. Operator: crewmate (firstmate-managed). Mode: **dry run only,
zero submissions**. Config: `/mnt/d/jobpilot/config.toml` (captain's copy,
untracked). Code: branch `fm/jobpilot-run-07` (the LinkedIn fix below is on it).
Machine-readable record: `/mnt/d/jobpilot/data/jobpilot-run-07/run.json` and the
SQLite store `/mnt/d/jobpilot/jobpilot.db` (run id 1). Pre-LinkedIn baseline kept
at `/mnt/d/jobpilot/jobpilot-run-07-prelinkedin.db` + `out-run-07-prelinkedin/`;
run-04 kept at `/mnt/d/jobpilot/jobpilot-run-04.db` + `out-run-04/`.

This is the honest re-test the captain asked for: the full source set is enabled
and the scoring/parseability fixes are in, so this report says what the tool
really finds now.

## 1. What was run

```
# from /mnt/d/jobpilot, using the fm/jobpilot-run-07 code
python3 -m jobpilot --config config.toml run --dry-run
```

Config highlights (full file at `/mnt/d/jobpilot/config.toml`):

- profile `/mnt/d/LaTeX/resume/PROFILE.md`; style template
  `/mnt/d/LaTeX/resume/Abhigyan_Resume_AI_ML.tex`; engine
  `.../pdflatex.exe`; extractor `.../pdftotext.exe`.
- Window `window_start_month = 1`, `window_end_month = 6` (Jan–May/June).
- India / remote-from-India: `allow_onsite_abroad = false`,
  `allow_unknown_location = false`, `allow_unknown_window = false` (unknown-window
  internships are still discovered and scored, but review-only).
- **Auto-apply OFF**: `apply.auto_apply_strong = false`, `apply.adapter = "none"`,
  no `[apply.submission.smtp]`. There is no submission channel at all, and
  `--dry-run` is on top of that.
- ATS boards kept as verified: greenhouse 30 tokens, lever 5, ashby 8; workable
  (per-account) left disabled.
- Search adapters enabled: `himalayas` (typed `employment_type=Intern&country=India`
  paged to exhaustion + `q=intern`), `unstop` (generic India internships feed),
  `workable_global` (`query=intern&location=India`), `themuse`
  (`level=Internship&location=India` + broader `location=India`).
- `linkedin` read-only reader enabled at the captain's request (low rate, never
  authenticates, never applies).
- `[link_out.sources.internshala]` set up as the manual channel (search link
  `https://internshala.com/internships/machine-learning-internship`); never scraped.

## 2. Sources enabled and what each actually returned

Every source was probed read-only before the run. The run itself reported all 8
built sources `ok` and **0 source failures**:

| Source | Returned by adapter | Notes |
| --- | --- | --- |
| greenhouse | 5898 | 30 board tokens, full content |
| lever | 278 | 5 tokens |
| ashby | 410 | 8 tokens |
| himalayas | 99 | typed India interns paged to exhaustion (100 total) + keyword pass |
| unstop | 300 fetched → **252 unique** | generic `opportunity=internships` feed; the API repeats rows across pages |
| workable_global | 73 fetched → **72 unique** | `query=intern&location=India`, 4 pages |
| themuse | 60 | typed + broad India passes |
| linkedin | 10 | read-only guest reader, 1 page |
| workable | skipped | disabled by config (documented) |

`discover` dedupes by `source:job_id`, so the run's `discovered` count is **7079**.

## 3. Funnel

```
discovered ................ 7079
hard-filter survivors ..... 416   (eligible)
scored .................... 416
strong .................... 4
tailored .................. 252   (all compiled a resume PDF)
queued for review ......... 252
submitted ................. 0
parseability failures ..... 0
LaTeX compile failures .... 0
```

Per source (returned / eligible / scored / strong / tailored / queued / submitted):

| Source | returned | eligible | scored | strong | tailored | queued | submitted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| greenhouse | 5898 | 10 | 10 | 3 | 9 | 9 | 0 |
| lever | 278 | 6 | 6 | 0 | 5 | 5 | 0 |
| ashby | 410 | 1 | 1 | 0 | 0 | 0 | 0 |
| himalayas | 99 | 91 | 91 | 0 | 81 | 81 | 0 |
| unstop | 252 | 230 | 230 | 0 | 97 | 97 | 0 |
| workable_global | 72 | 28 | 28 | 0 | 25 | 25 | 0 |
| themuse | 60 | 40 | 40 | 1 | 25 | 25 | 0 |
| linkedin | 10 | 10 | 10 | 0 | 10 | 10 | 0 |
| **total** | **7079** | **416** | **416** | **4** | **252** | **252** | **0** |

"eligible" means it passed every hard filter (internship, India/remote, window
not known-out-of-range); a few eligible rows still score below the shortlist
threshold (`reject` band) and are not tailored.

## 4. Top matches — technical / AI-ML separated from non-technical

### 4a. The `strong` band (4 postings; all queued, none submitted)

| # | Company | Title | Location | Window evidence | Score | Link |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Rubrik | Software Engineer — Winter Intern | Bangalore, India | **explicit Jan–May 2027** | 0.835 | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 2 | Rubrik | Software Engineer (CPD) — Winter Intern | Bangalore, India | **explicit Jan–May 2027** | 0.810 | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
| 3 | Stripe | Software Engineer, Intern | Bengaluru, India | none found | 0.718 | https://stripe.com/jobs/search?gh_jid=8031833 |
| 4 | Labcorp | Data Science Intern — Real World Data Strategy | Flexible / Remote | none found | 0.715 | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |

Score reasons for #1 (identical shape for #2):
`skill coverage 80% (4/5 JD terms supported); role relevance 0.70 (software=0.70);
location fit 1.00 (in India); window fit 1.00 (explicit Jan–May 2027); seniority
fit 1.00 (internship)`. Matched Java, C++, Python, Security; gap Fine-tuning
(never inserted).

#4 is the only AI/ML-domain posting in `strong`: `role relevance 0.80
(ai_ml=0.80); location fit 0.50 (location 'Flexible / Remote' is not confirmably
open to India; review before applying); window unknown`. It is a genuine Data
Science internship but **not confirmably India-eligible** — The Muse's
`location=India` parameter is loose and this is a US employer.

### 4b. Non-technical internships that score high but are correctly capped

35 eligible postings reached `score >= 0.68` but were **withheld from `strong`**
because their role relevance was below the 0.50 floor. Every one carries the
reason `strong band withheld: role relevance X is below the 0.50 minimum ...`.
Examples:

| Score | Source | Company | Title |
| --- | --- | --- | --- |
| 0.705 | greenhouse | InMobi | Intern — Creative & Communications, People Team |
| 0.705 | himalayas | Resilinc | Risk & Compliance Intern |
| 0.705 | himalayas | Parqet Fintech | Working Student — Data Support Engineer |
| 0.705 | workable_global | A2MAC1 | HR Internship |
| 0.700 | themuse | Labcorp | Intern — IT Database Server Administration |
| 0.680 | greenhouse | Groww | Video Editor Intern |
| 0.680 | greenhouse | Sigmoid | HR Intern + Trainee |
| 0.680 | lever | Paytm | Talent Acquisition Intern (Bangalore / Gurgaon / Tech) |

## 5. Did any true AI/ML internship surface? — Yes, mostly from Himalayas and The Muse

Genuine AI/ML / data / research internships that survived the hard filters this
run (band, score, role-relevance, location, window):

| Source | Company | Title | Location | Band/Score | Window | Link |
| --- | --- | --- | --- | --- | --- | --- |
| themuse | Labcorp | Data Science Intern — Real World Data Strategy | Flexible / Remote (not India-confirmable) | strong 0.715 | unknown | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |
| himalayas | Ritual | Research Intern | Worldwide (remote) | shortlist 0.672 | unknown | https://himalayas.app/companies/ritual-net/jobs/research-intern-1464631102 |
| himalayas | Drivetrain | Engineering Intern – Gen AI for FP&A Platform | **India** | shortlist 0.667 | unknown | https://himalayas.app/companies/drivetrain/jobs/engineering-intern-gen-ai-for-fp-a-platform |
| themuse | The Muse | AI Engineer – Remote Internship | Flexible / Remote | shortlist 0.661 | unknown | https://www.themuse.com/jobs/themuse/ai-engineer-remote-internship |
| themuse | The Muse | Data Engineer – Remote Internship | Flexible / Remote | shortlist 0.625 | unknown | https://www.themuse.com/jobs/themuse/data-engineer-remote-internship |
| himalayas | Tether | Research Engineer Intern (Video/Multimodal LLM) | Worldwide (remote) | shortlist 0.622 | unknown | https://himalayas.app/companies/tether-operations-limited/jobs/research-engineer-intern-video-multimodal-llm |
| himalayas | Mactores | Data Engineer (Intern) | **India** | shortlist 0.585 | unknown | https://himalayas.app/companies/mactores/jobs/data-engineer-intern |
| himalayas | Portcast | Data Analyst Intern | **India** (+SEA) | shortlist 0.580 | unknown | https://himalayas.app/companies/portcast/jobs/data-analyst-intern |
| workable_global | Blue Machines AI | Evaluation & Insights Intern, AI Delivery | **Bengaluru, India** | shortlist 0.505 | unknown | https://jobs.workable.com/view/hYkVydG3ua3RuasU6CTiMw/evaluation-%26-insights-intern%2C-ai-delivery-in-bengaluru-at-blue-machines-ai |

So: **yes, real AI/ML/DS/research internships surfaced** — the strongest signals
come from **Himalayas** (the single best automated source for this search:
Drivetrain Gen-AI, Mactores Data Engineer, Tether multimodal-LLM research, Ritual
research) and **The Muse** (Labcorp Data Science, The Muse's own AI/Data Engineer
remote internships), plus one from **Workable global** (Blue Machines AI,
Bengaluru). None of the genuinely India-based ones reached `strong` (their scores
sit at 0.50–0.67, below the 0.68 threshold, and Drivetrain's Gen-AI title does not
trip a configured target term), and almost all have **no timing signal**, so they
are review-only by design.

- **Unstop** (the largest India source) yielded **no** AI/ML internship from its
  generic feed in the 300 rows fetched — see gap G3 below.
- **LinkedIn** yielded **no** AI/ML internship (see §8).
- **Internshala**, the captain's chosen best source for the Jan–May window, is
  manual-only by design and is set up as a link-out channel (§1).

## 6. Tailored artifacts — resumes and cover letters compiled

- 252 tailored resumes compiled to PDF: **252/252 resume PDFs exist**, all
  `parseability_ok = 1` (0 parseability failures, 0 LaTeX compile failures).
- 251/252 cover-letter PDFs compiled. The one failure is the non-ASCII defect G3
  in §10 (MGID, a Ukrainian-language title); its resume still compiled.
- Confirmed example packet paths (also under `/mnt/d/jobpilot/out/review/<slug>/`):
  - Rubrik SWE Winter Intern —
    `/mnt/d/jobpilot/out/greenhouse-rubrik-job-board-software-engineer-winter-intern-8166523/resume.pdf`
    (134 KB) and `.../cover_letter.pdf` (25 KB).
  - Stripe SWE Intern —
    `/mnt/d/jobpilot/out/greenhouse-stripe-software-engineer-intern-8031833/resume.pdf`.
  - Drivetrain Gen-AI Intern (India) —
    `/mnt/d/jobpilot/out/himalayas-drivetrain-engineering-intern-gen-ai-for-fp-a-platform-https:/himalayas.app/companies/drivetrain/jobs/engineering-intern-gen-ai-for-fp-a-platform/resume.pdf`.
  - Mactores Data Engineer (Intern) (India) —
    `/mnt/d/jobpilot/out/himalayas-mactores-data-engineer-intern-https:/himalayas.app/companies/mactores/jobs/data-engineer-intern/resume.pdf`.
  - Blue Machines AI (Bengaluru) —
    `/mnt/d/jobpilot/out/workable_global-blue-machines-ai-evaluation-insights-intern-ai-delivery-897025dc-5483-468d-a0b3-e81f283d7d0c/resume.pdf`.

No-invention invariant held: unsupported JD terms appear only as gaps and were
never inserted (e.g. Rubrik's `Fine-tuning`, Labcorp's `Data Science`).

## 7. The scoring fixes hold on real data

- **No non-technical internship reached `strong`.** The `strong` band is exactly
  3 software-engineering internships (Rubrik ×2, Stripe) plus 1 data-science
  internship (Labcorp). 35 high-scoring non-technical internships (HR, talent
  acquisition, video editing, communications, graphic design, business
  development, …) were capped to `shortlist` with the explicit
  `strong band withheld: role relevance ... below the 0.50 minimum` reason.
- **No alias-only parseability false failures.** `parseability_failed = 0` and all
  252 applications have `parseability_ok = 1`, versus 7/16 false failures
  (`Communication` alias) in the last run. Keyword survival is now checked against
  profile-present surface forms.
- Role relevance is computed over the role section only: the prior run's boilerplate
  inflation (Glance UX / InMobi Communications ranking above Stripe) is gone —
  those postings now score role relevance 0.10 and are capped.

## 8. LinkedIn (captain's addition) — enabled, exercised, reported separately

Authorized addition: enable the optional read-only LinkedIn reader, low rate,
never authenticate/apply, report it separately.

- **Returned: 10 postings** (1 guest page, `keywords=intern&location=India`). No
  captcha, no auth wall, HTTP 200. The endpoint is usable, but the adapter needed
  two fixes to be usable at all (D1, D2 in §10).
- **Hard-filter survivors: 10 of 10** (all India-located internships with an
  internship title; window unknown).
- **Queued: 10, all review-only** with guard category `linkedin`
  (`linkedin_review`); **0 auto-applied** (LinkedIn is review-only by product
  decision, and auto-apply is off regardless).
- **AI/ML: none.** All 10 are accounting, finance, graphic design, digital
  marketing, sales or business-operations internships. The only "AI" mention is
  `Hex Wireless — Internship - Sales and Marketing : AI Enabled Omnichannel
  Product and Services`, which is a sales role (role relevance 0.00).
- Verdict: **usable as a source, not a useful AI/ML source for this search** at
  1 page. Reading it remains against LinkedIn's ToS and best-effort.

## 9. Zero-submission verification (from the run's own record)

- run `mode = dry_run`; `stats.submitted = 0`.
- `applications`: **252 rows, all `status = manual_required`; 0 `submitted`**.
- `attempts`: **empty (0 rows)** — no submission was ever attempted.
- `review_queue`: 252 rows, all `pending`.
- CLI printed `dry run: nothing was submitted.`

## 10. Defects and gaps hit (with the exact command and error)

### D1. (FIXED) `[linkedin] enabled = true` did not run the LinkedIn reader

- **Command:** `python3 -m jobpilot --config config.toml run --dry-run` with
  `[linkedin] enabled = true`.
- **Symptom:** LinkedIn was absent from `sources:`; only 7 sources ran. The reader
  was never built.
- **Root cause:** `build_adapters` iterates `config.sources`, but `linkedin` is not
  in `DEFAULT_DISCOVERY_SOURCES` and the config has no `[sources.linkedin]`, so
  `config.sources.get("linkedin")` was `None` and the adapter was skipped even
  though `[linkedin].enabled` was true. The documented toggle was a no-op.
- **Fix:** `jobpilot/discovery/registry.py` now registers the LinkedIn adapter on
  demand when `config.linkedin.enabled` is true (and still respects a
  `[sources.linkedin]` entry if present). Test:
  `test_linkedin_adapter_built_only_when_reader_enabled`.

### D2. (FIXED) LinkedIn parser read only 1 of 10 result cards

- **Symptom:** the guest page contained 10 `data-entity-urn` cards; the adapter
  returned 1.
- **Root cause:** `_LinkedInParser` tracks nesting depth to close a card, but
  counted HTML void elements (`<br>`, `<img>`, …) inside a card, which never carry
  an end tag. Depth drifted upward, so only the first card was recognised and the
  rest were swallowed.
- **Fix:** `jobpilot/discovery/linkedin.py` excludes void elements from the depth
  count. Test: `test_linkedin_parser_reads_every_card_despite_void_elements`
  (3-card markup with `<img>`/`<br>`). The fixture-based test still passes.

### G3. (REPORTED, not fixed) Cover-letter compile crashes on non-ASCII posting text

- **Command:** the same `run --dry-run`.
- **Error (from the run record):**
  `cover letter error: 'utf-8' codec can't decode byte 0xd0 in position 2496: invalid continuation byte`
  on `MGID Academy — почни професійний шлях в AdTech`
  (`/mnt/d/jobpilot/out/himalayas-mgid-mgid-academy-adtech-https:/himalayas.app/companies/mgid/jobs/mgid-academy-adtech/`).
- **Root cause:** `jobpilot/resume/compiler.py:35` calls `subprocess.run(..., text=True)`,
  which decodes the Windows `pdflatex.exe` stdout/stderr as UTF-8 with no error
  handler. A `.tex` containing Cyrillic makes the engine emit non-UTF-8 bytes and
  the decode raises `UnicodeDecodeError` (a `ValueError`, so the pipeline reports it
  as a cover-letter error). Reproduced directly: `compile_tex(...)` on that
  `cover_letter.tex` raises `UnicodeDecodeError` at the same byte.
- **Impact:** 1/252 this run; any JD/company/title with non-ASCII text can hit it.
  **One-line fix available** (`errors="replace"` on the `subprocess.run`), left
  unapplied because it does not block the run; flagged for the next change.

### G4. (REPORTED) Unstop's adapter ignores the API's `searchTerm` filter

- Unstop's public API supports a server-side keyword filter the adapter does not
  use. Evidence (read-only):
  `curl 'https://unstop.com/api/public/opportunity/search-result?opportunity=internships&page=1&searchTerm=ai'`
  returns `total 2121` (vs `total 10000` unfiltered); `searchTerm=machine learning`
  similarly returns AI/ML rows. The adapter only pages the generic feed, which is
  recency-sorted and dominated by marketing/sales/BD: in 300 rows it surfaced **no**
  AI/ML internship. This is the main reason the largest India source contributed
  nothing technical.
- Not fixed here (not run-blocking); it is the highest-value next improvement and
  fits the documented typed-slice-plus-broader-query pattern.

### G5. (REPORTED, minor) Unstop repeats rows across pages

- Unstop returned 300 rows for 252 unique ids (48 duplicate rows across pages); the
  adapter does not dedupe. Harmless (the registry dedupes by `stable_id`) but
  wasted fetches.

### G6. (KNOWN, minor) Greenhouse full-content fetch dominates run time

- The full run took ~19 minutes; greenhouse hard-codes `?content=true` for 30
  boards. A filtering-only `content=false` pass would cut this substantially.

## 11. Diagnosis — why the result is what it is

The result is **not** a filter or window bug; it is **board coverage**:

- The public ATS boards of India-office companies carry few AI/ML internships:
  greenhouse produced 10 eligible postings from 5898, ashby 1 from 410. The AI/ML
  labs that do hire interns run US-only programs the India filter correctly rejects.
- **Himalayas is the best automated source** for this search (91 eligible, ~10
  AI/ML/DS/research-titled), and **The Muse** contributes genuine AI/ML remote
  internships — but The Muse's `location=India` parameter is loose and its hits are
  not India-confirmable.
- **Unstop** is the biggest India source but its generic feed is non-technical
  (G4); **Internshala**, the best source for the Jan–May window, is manual-only by
  the captain's decision.
- The window rule is doing its job: nearly every AI/ML posting states no dates, so
  it is surfaced and queued for review rather than auto-applied — correct and
  conservative.

So the honest answer to the captain's question: **the tool does find real AI/ML
internships (Himalayas, The Muse, Workable global), and the scoring/parseability
fixes hold, but India-eligible AI/ML internships with a stated Jan–May/June window
remain scarce on the automated public sources.** The highest-leverage next step is
to use Unstop's `searchTerm` path (G4) and to work the Internshala manual channel.

## 12. Verdict

The full-source-set pipeline ran end to end in dry-run mode: **7079 discovered,
416 hard-filter survivors, 4 strong, 252 tailored (252/252 resumes compiled and
parseable), 252 queued, 0 submitted**. The scoring fix holds (no non-technical
internship in `strong`; 35 high scorers correctly withheld), and the alias-only
parseability false failures are gone (0/252). Genuine AI/ML/DS internships did
surface, led by Himalayas and The Muse; none reached the auto-apply band for an
India-confirmable role. Two LinkedIn defects that blocked the captain-requested
exercise were fixed and tested; one non-ASCII cover-letter defect (G3) and the
Unstop `searchTerm` gap (G4) are reported for the next change.
