# jobpilot first real run — report (jobpilot-run-04)

Date: 2026-09-22. Operator: crewmate (firstmate-managed). Mode: **dry run only**,
**zero submissions**. Config: `/mnt/d/jobpilot/config.toml` (captain's copy, untracked).
Run artifacts: `/mnt/d/jobpilot/out/` and `/mnt/d/jobpilot/jobpilot.db`.

## 1. What was run

```
cd /mnt/d/jobpilot
python3 -m jobpilot --config config.toml run --dry-run
```

Config highlights (full file at `/mnt/d/jobpilot/config.toml`):

- profile `/mnt/d/LaTeX/resume/PROFILE.md`; style template
  `/mnt/d/LaTeX/resume/Abhigyan_Resume_AI_ML.tex`; engine
  `/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdflatex.exe`; extractor
  `.../pdftotext.exe`.
- Window `window_start_month = 1`, `window_end_month = 6` (Jan–May/June).
- India / remote-from-India rules: `allow_onsite_abroad = false`,
  `allow_unknown_location = false`, default `india_keywords` / `remote_keywords`
  written out explicitly; `allow_unknown_window = false` (unknown-window
  internships are still discovered and scored, but only ever review-eligible).
- **Auto-apply OFF**: `apply.auto_apply_strong = false`, `apply.adapter = "none"`,
  no `[apply.submission.smtp]`. There is no submission channel configured at all.
- `--dry-run` on top of that.

## 2. Board tokens used, and how each was verified

Each token was checked with a read-only probe of its public board endpoint on
2026-09-22; **every token below returned at least one posting**. Preference was
given to companies with India offices or India-eligible remote roles, plus AI/ML
companies whose boards carry internships.

| Source | Tokens (verified live) |
| --- | --- |
| Greenhouse (30) | rubrik, stripe, groww, sigmoid, databricks, mongodb, gitlab, five9, coinbase, robinhood, glance, inmobi, druva, pubmatic, highradius, okta, twilio, samsara, figma, turing, observeai, neo4j, deliveroo, scaleai, datadog, elastic, canonical, vercel, reddit, dropbox |
| Lever (5) | paytm, zeta, mindtickle, meesho, cred |
| Ashby (8) | sarvam, atlan, cohere, langchain, llamaindex, pinecone, weaviate, fireworks |
| Workable | **disabled** — no India/AI candidate board returned postings and the widget API rate-limits (HTTP 429) |

Probe evidence (jobs returned at probe time, with the India/internship signal that
justified inclusion):

- Greenhouse: rubrik 132 (Bangalore SWE winter interns), stripe 669 (Bengaluru SWE
  Intern), groww 7 (Bengaluru interns), sigmoid 35 (Bengaluru data/AI), databricks
  883 (Bengaluru office, AI/ML), mongodb 400 (Gurugram), gitlab 203 (remote incl.
  Bangalore), five9 112 (Bengaluru AI), coinbase 217 (India), robinhood 161
  (Bengaluru), glance 43 (Bangalore applied scientist + intern), inmobi 66
  (Bangalore), druva 36 (Pune), pubmatic 79 (Pune), highradius 82 (Hyderabad), okta
  329 (Bangalore), twilio 143 (Bangalore), samsara 267 (Bangalore), figma 154
  (Bengaluru), turing 26 (remote India AI/ML), observeai 14 (India), neo4j 52
  (India), deliveroo 129 (India), scaleai 221, datadog 450, elastic 368, canonical
  305, vercel 86, reddit 155, dropbox 44.
- Lever: paytm 183 (India interns), zeta 22 (Bangalore PM intern), mindtickle 17
  (India), meesho 51 (India), cred 10 (India).
- Ashby: sarvam 61 (Bengaluru; India's sovereign-LLM lab), atlan 8 (India), cohere
  143, langchain 103, llamaindex 9, pinecone 7, weaviate 3, fireworks 80.

Tokens that returned 404 / zero and were therefore **not** added: postman,
browserstack, razorpay, flipkart, swiggy, zomato, phonepe, cred (greenhouse), ola,
paytm (greenhouse), freshworks (greenhouse), zoho, hasura, chargebee, clevertap,
moengage, whatfix, darwinbox, icertis, and all Workable candidates.

## 3. Discovery funnel (this run)

```
sources:
  ok      greenhouse: 5870 postings
  ok      lever: 283 postings
  ok      ashby: 414 postings
  skipped workable: source disabled
```

| Stage | Count |
| --- | --- |
| discovered | 6567 |
| eligible after hard filters | 17 |
| shortlisted (score ≥ 0.42) | 16 |
| strong (score ≥ 0.68) | 8 |
| tailored | 16 |
| LaTeX compile failures | 0 |
| parseability check failures | 7 (all false — see defect B) |
| queued for review | 16 |
| **submitted** | **0** |

Per source: greenhouse 10 eligible, lever 6, ashby 1. Rejection reasons across the
6567 (postings can hit several): not-an-internship 6446, not India-eligible 5067,
seniority 4107, full-time signal 2181, known out-of-window 17.

## 4. Top matches

`strong` band (all queued, none submitted):

| # | Company | Title | Location | Window | Score | Link |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Rubrik | Software Engineer (CPD) — Winter Intern | Bangalore, India | explicit Jan–May 2027 | 0.877 | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
| 2 | Rubrik | Software Engineer — Winter Intern | Bangalore, India | explicit Jan–May 2027 | 0.877 | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 3 | Glance | UX Design — Intern | Bengaluru, India | unknown | 0.847 | https://job-boards.greenhouse.io/glance/jobs/7916115 |
| 4 | InMobi | Intern — Creative & Communications, People Team | Bangalore, India | unknown | 0.847 | https://job-boards.greenhouse.io/inmobi/jobs/8207429 |
| 5 | Stripe | Software Engineer, Intern | Bengaluru, India | unknown | 0.784 | https://stripe.com/jobs/search?gh_jid=8031833 |
| 6 | Groww | Video Editor Intern | Bengaluru, India | unknown | 0.680 | https://job-boards.eu.greenhouse.io/groww/jobs/4956817101 |
| 7 | Paytm | Talent Acquisition Intern — Bangalore | Bangalore, India | unknown | 0.680 | https://jobs.lever.co/paytm/88e8b698-8f03-4e09-9581-168f831fb3af |
| 8 | Paytm | Talent Acquisition Intern — Gurgaon | Gurugram, India | unknown | 0.680 | https://jobs.lever.co/paytm/91ef4dc2-8cd8-427a-84cd-c9308753a203 |

Score reasons for #1 (identical for #2):
`skill coverage 80% (4/5 JD terms supported); role relevance 0.87 (software=0.67);
location fit 1.00 (in India); window fit 1.00 (explicit Jan–May 2027); seniority
fit 1.00 (internship)`. Matched terms Java, C++, Python, Security; gap Fine-tuning
(never inserted).

Shortlist band (score 0.42–0.68): Groww YouTube & Content Internship (0.538), Zeta
Product Management Intern (0.538), Rubrik ENG Project/Program Intern (0.480),
Sarvam Marketing Intern (0.463), Sigmoid HR Intern + Trainee (0.455), Paytm
Intern–TA Tech (0.455), Paytm Intern-Talent Acquisition (0.455), Paytm Internship -
Talent Acquisition (0.455).

**Honest read:** no pure AI/ML research or modelling internship surfaced. The only
genuinely technical, in-window, India-based internships are the two **Rubrik
Software Engineer winter interns** and the **Stripe Software Engineer intern**.
Everything else is non-AI (UX design, communications, video/content, talent
acquisition, HR, finance, marketing, product management). Glance and InMobi rank
high only because their JD boilerplate contains "Machine Learning" / "Generative
AI" (see defect C). This is a board-coverage reality, not a filter bug: the public
Greenhouse/Lever/Ashby boards of India-office companies carry few AI/ML
internships, and the AI/ML labs that do hire interns (OpenAI, Anthropic, Cohere,
Scale, etc.) run US-only or US-work-authorization programs that the India filter
correctly rejects.

## 5. Generated artifacts (best two/three confirmed)

All 16 shortlisted postings produced a tailored resume PDF and a cover-letter PDF;
**0 LaTeX compiles failed**. Packet directories:
`/mnt/d/jobpilot/out/review/<slug>/` containing `resume.pdf`, `cover_letter.pdf`,
`resume.tex`, `cover_letter.tex`, `apply_link.txt`, `packet.json`,
`requirements.md`. The compiled `.tex`/`.pdf` also live under
`/mnt/d/jobpilot/out/<slug>/`.

Confirmed for the top three:

- Rubrik Software Engineer (CPD) Winter Intern —
  `/mnt/d/jobpilot/out/review/greenhouse-Rubrik-Job-Board-Software-Engineer-CP-eae7a84e07/resume.pdf`
  (134 KB) and `.../cover_letter.pdf` (25 KB). `pdftotext` extracts all four
  required sections; keyword survival 100%.
- Rubrik Software Engineer Winter Intern —
  `/mnt/d/jobpilot/out/review/greenhouse-Rubrik-Job-Board-Software-Engineer----87fad9533f/resume.pdf`.
- Stripe Software Engineer Intern —
  `/mnt/d/jobpilot/out/review/greenhouse-Stripe-Software-Engineer-Intern-be6f25198e/resume.pdf`.

No-invention invariant held: the Rubrik packets list `Fine-tuning` as a gap and it
was never inserted; the generated text uses only profile facts.

## 6. Zero-submission verification

From the run's own record (`/mnt/d/jobpilot/jobpilot.db`):

- run `mode = dry_run`; `stats.submitted = 0`.
- `applications`: 16 rows, **all** `status = manual_required`; 0 `submitted`.
- `attempts`: **empty** (no submission attempt was ever recorded).
- `review_queue`: 16 rows, all `pending`.
- CLI printed `dry run: nothing was submitted.`

## 7. Tool defects found

### A. (FIXED) Parseability check always failed for the reference Windows-engine setup

- **Symptom:** every tailored resume was flagged unparseable:
  `stats.parseability_failed = 16/16`, and `python -m unittest tests.test_tailoring`
  errored with
  `jobpilot.resume.parseability.TextExtractionError: text extraction failed: I/O Error: Couldn't open file '/tmp/tmpXXXX/.../resume.pdf': No such file or directory.`
- **Root cause:** `extract_pdf_text` passed **absolute WSL paths** to the Windows
  `pdftotext.exe` (both input PDF and the temp output file). A Windows process
  launched from WSL does not translate an absolute Linux path argument, so it
  cannot open the file. `compile_tex` already avoids this by running the engine
  with `cwd` set to the file's directory and a **relative** filename; parseability
  did not.
- **Fix:** invoke the extractor as `[extractor, "-layout", pdf.name, "-"]` with
  `cwd = pdf.parent`, reading stdout pinned to UTF-8 decoding with
  `errors="replace"`. This mirrors the compiler's documented WSL pattern and needs
  no second (unreachable) output path. Added three toolchain-free unit tests: the
  relative-filename + `cwd` invocation, the no-output error, and non-UTF-8 stdout
  replaced rather than raised.
- **Effect:** `parseability_failed` fell from 16/16 to 7/16, and the previously red
  integration test `test_tailored_resume_compiles_and_is_parseable` now passes.

### B. (REPORTED, not fixed) False parseability failures from alias-only keyword matches

- **Symptom:** the remaining 7 failures are all the same shape — the only matched
  keyword is `Communication`, and the check reports
  `keyword survival 0% below 50%; unextractable: Communication`.
- **Root cause:** the lexicon maps `Communication` to the aliases
  `["communication", "stakeholder", "cross-functional", "collaboration"]`
  (`jobpilot/lexicon.py:73`). The profile contains "cross-functional" /
  "collaboration", so `Matcher` marks `Communication` as a **matched** profile
  term — but the no-invention generator can never emit the canonical word
  "Communication" because it is not in the profile text. `check_parseability` then
  requires that canonical word literally in the PDF and fails a perfectly
  parseable resume.
- **Impact:** misclassifies 7/16 postings (all the non-technical India
  internships) as unparseable, forcing them to review for a reason that is not
  real. Proposed fix: test keyword survival against the profile-present surface
  forms/aliases rather than the canonical label, or exclude soft-skill canonicals
  whose only support is an alias from the parseability requirement.

### C. (REPORTED, not fixed) Rubric promotes non-AI India internships to the "strong" band

- **Symptom:** 5 of the 8 `strong` postings are non-technical (UX Design,
  Communications, Video Editor, 2× Talent Acquisition). `Groww Video Editor Intern`
  and both `Paytm Talent Acquisition Intern` postings score exactly 0.680 with
  `role relevance 0.00` and a single soft-skill keyword (`Communication`).
- **Root cause:** `location_fit` (0.15) + `seniority_fit` (0.05) are saturated for
  any India internship, `window_fit` gives 0.30 for unknown windows, and
  `skill_coverage` can hit 1.00 from one soft-skill term, so an unrelated India
  internship clears the 0.68 `strong` threshold even with `role_relevance = 0`.
- **Impact:** "strong" is the auto-apply band; with auto-apply on, unrelated
  internships would be treated as strong matches. For a rubric whose stated job is
  to rank AI/ML internships, `role_relevance = 0` should be disqualifying from
  "strong" (or the strong threshold should require a minimum role relevance).
  Not fixed here because it is a scoring-policy change, not a run blocker.

### D. (REPORTED, minor) JD boilerplate inflates `role_relevance` for non-AI roles

- Glance UX Design Intern and InMobi Communications Intern score `ai_ml = 0.67`
  purely from "Machine Learning" / "Generative AI" in company boilerplate, ranking
  them above the genuinely technical Stripe SWE Intern. A title/description
  relevance signal should discount boilerplate mentions.

### E. (REPORTED, minor) Lost parseability detail in the durable record

- `applications.review_reason` stores the guard **category** (`"generation"`), not
  the detailed `plan.review_reason` (`"parseability check failed: <detail>"`), so
  the SQLite record alone does not say why a resume was flagged. The detail is
  only visible by re-running the check. Persisting `plan.review_reason` would make
  the store self-explanatory.

### F. (REPORTED, minor) Workable widget API rate-limits; Greenhouse always fetches full content

- Every Workable candidate either returned zero jobs or `HTTP 429` under light
  load, so Workable could not be given a worthwhile token and was disabled.
- The Greenhouse adapter hard-codes `?content=true`, downloading full HTML for
  every job on every board (up to ~10 MB / ~10 s for a large board such as
  Databricks). A `content=false` mode for filtering-only passes would cut run time
  and bandwidth.

## 8. Verdict

The pipeline ran end to end in dry-run mode, discovered 6567 postings across three
ATS sources, hard-filtered to 17 India-eligible Jan–Jun internships, scored 17,
tailored and compiled PDFs for all 16 shortlisted, and queued 16 — **with zero
submissions**. The best real matches are the two Rubrik Bangalore Software
Engineer winter interns (Jan–May 2027, score 0.877) and the Stripe Bengaluru
Software Engineer intern (0.784). No pure AI/ML internship surfaced from these
public boards; the run is honest about that. One run-blocking defect (the
parseability path bug) was fixed and covered by tests; the rest are reported above.
