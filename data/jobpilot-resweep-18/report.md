# jobpilot internship-source resweep — report (jobpilot-resweep-18)

Date: 2026-09-27. Operator: crewmate (firstmate-managed). Mode: **dry run only,
zero submissions**. Branch: `fm/jobpilot-internship-sources-18` (worktree
`/home/abhigyan/.treehouse/jobpilot-cf75eb/1/jobpilot`). Config:
`config.toml` (the captain's copy, git-ignored, retargeted this run to
`out-resweep-18` / `jobpilot-resweep-18.db`).

**Verdict up front: the page improved materially — `present` selected 14
genuinely-new technical internships, up from 1 in sweep 17 (14x).** The gain is
entirely traceable to the intended change: the Unstop `searchTerm` slices were
retargeted at the captain's AI/ML/data/software field and doubled in depth, and
The Muse's typed internship facet was paged to its full depth. No broad ATS token
was added; greenhouse/lever/himalayas/workable_global contributions are
byte-for-byte unchanged from sweep 17.

Machine-readable record: `jobpilot-resweep-18.db` (`runs.stats`); full CLI log
`out-resweep-18-run.log`; present/upskill output under `out-resweep-18/`. The
store and run output are git-ignored and are **not** committed; only this report
and the source/config change are.

## 1. Before (sweep 17) — re-measured from the preserved store

Sweep 17's report was discarded, so its "before" numbers were re-derived
read-only from the preserved store `jobpilot-resweep-17.db`
(`runs.stats` plus a re-run of `present.select_matches` with this config). The
re-derived figures agree with the firstmate spec's diagnosis to within a few
counts:

| Metric | Sweep 17 (measured from store) |
| --- | --- |
| discovered | 11,127 (discarded report said 11,135; store says 11,127) |
| eligible | 126 |
| shortlisted / queued | 101 |
| strong | 9 (greenhouse 3, themuse 1, unstop 5) |
| `present` selected | **1** (themuse — Biogen, Co-op Data Science & AI Innovation, 0.658) |
| excluded | 97 |
| held borderline | 3 (dropped by the inherited present-arithmetic gap, §7 R1) |
| submitted | 0 |

Sweep-17 exclusion breakdown (re-derived): **24** already applied, **35** role
relevance below the technical floor, **38** non-technical title term, **3** held
borderline. The bottleneck was discovery volume of *relevant* roles, not the
filters: of the 9 strong-band postings, all 9 were already-applied (hidden),
which is why a queue of 101 yielded a page of 1.

## 2. What changed (source/config only)

1. **Unstop `searchTerm` slices retargeted and deepened** (`jobpilot/discovery/unstop.py`,
   `DEFAULT_KEYWORDS`; and `[sources.unstop]` in `config.toml` /
   `config.example.toml`): the 5 generic terms became **20** high-precision
   AI/ML/data/software slices, and `keyword_max_pages` went **1 → 2** because the
   first page is saturated at 10 rows for every keyword. New terms: deep
   learning, ai ml, generative ai, llm, computer vision, nlp, ml engineer,
   ai engineer, data analyst, data engineer, software development, python, and
   the role-shaped ai intern / ml intern / research intern. Each was verified
   live read-only before the run and again by the run's own per-query counters (§4).
2. **The Muse paged to its typed depth** (`[sources.themuse] max_pages 2 → 4`):
   the typed `level=Internship&location=India` facet has only ~4 pages, so two
   pages were leaving typed internships unfetched. The broad `location=India`
   pass stays at 1 page.
3. No change to greenhouse/lever/himalayas/workable_global, the filters, the
   stipend classifier, the exclusion matching, the rubric, or `present`.

Himalayas and workable_global were **confirmed and left alone**: Himalayas'
`q=` slices return mostly full-time senior roles (e.g. `q=machine learning` →
"Senior Machine Learning Engineer") and its paged path is robots-disallowed, so
only the typed Intern page is useful; workable_global's `query=intern` result set
is exhausted at 4 pages (already used) and its other queries (`machine learning`,
`software engineer intern`) return full-time roles, not internships.

## 3. Source coverage — every source

6 `ok`, 2 `failed`, 1 `skipped`, **0 unexpected failures** (both failures are the
robots gate working as designed):

| Source | Status | Returned | Notes |
| --- | --- | --- | --- |
| greenhouse | ok | 10049 | 73 board tokens, full content |
| lever | ok | 642 | 15 tokens |
| ashby | **failed** | 0 | `robots.txt` unreadable (HTTP 401) → gate fails closed |
| workable | skipped | 0 | disabled by config |
| himalayas | ok | 34 | typed `employment_type=Intern&country=India` + `q=intern`, first page only, no `page` param |
| unstop | ok | **571** | generic feed (30 pages) + 20 `searchTerm` slices (2 pages each) |
| workable_global | ok | 65 | `query=intern&location=India`, 4 pages (exhausted) |
| themuse | ok | **67** | typed `level=Internship` (4 pages) + broad `location=India` (1 page) |
| linkedin | **failed** | 0 | `Disallow: /` for `user-agent: *` blocks the guest reader |

`discover` dedupes by `source:job_id`, so the run's `discovered` count is
**11,428**.

## 4. Unstop `searchTerm` slices — live per-query new counts (this run)

Unstop returned **571** postings (was 276). The CLI's per-query counters, from
the run itself:

| Query | New postings | Query | New postings |
| --- | ---: | --- | ---: |
| generic feed | 237 | ml engineer | 17 |
| machine learning | 20 | ai engineer | 16 |
| artificial intelligence | 19 | data science | 15 |
| ai | 20 | data analyst | 17 |
| deep learning | 9 | data engineer | 20 |
| ai ml | 15 | software engineer | 20 |
| generative ai | 18 | software development | 19 |
| llm | 18 | python | 20 |
| computer vision | 19 | ai intern | 12 |
| nlp | 12 | ml intern | 10 |
| | | research intern | 18 |
| | | **total** | **571** |

Every new slice returned non-zero new rows. The generic feed contributed 237
(unchanged shape — recency-sorted, non-technical-dominated), so the ~334
keyword-slice postings are the high-precision addition. The first pages remain
saturated (all 10 rows for essentially every term) and second pages stay
on-topic (checked: page 2 of `ai intern` is still AI-titled; page 2 of
`computer vision` is still CV-titled).

## 5. Funnel

```
discovered ................ 11428
hard-filter survivors ..... 165     (eligible)
scored .................... 165
strong .................... 14
tailored .................. 128
queued for review ......... 132
submitted ................. 0
parseability failures ..... 4       (inherited, identical to sweep 17; §7)
LaTeX compile failures .... 0
```

Per source (returned / eligible / scored / strong / queued):

| Source | returned | eligible | scored | strong | queued |
| --- | ---: | ---: | ---: | ---: | ---: |
| greenhouse | 10049 | 10 | 10 | 3 | 9 |
| lever | 642 | 5 | 5 | 0 | 5 |
| himalayas | 34 | 27 | 27 | 0 | 24 |
| **unstop** | **571** | **58** | **58** | **10** | **45** |
| workable_global | 65 | 19 | 19 | 0 | 17 |
| themuse | 67 | 46 | 46 | 1 | 32 |
| **total** | **11428** | **165** | **165** | **14** | **132** |

The entire eligible/queued gain comes from **unstop (25 → 58 eligible)** and
**themuse (40 → 46)**; every other source is unchanged from sweep 17.

## 6. What `present` selected — the headline

```
$ python3 -m jobpilot --config config.toml present
presented 14 technical match(es)
stipend not stated (verify separately) for 13 match(es)
excluded 115 non-technical / low-relevance queued posting(s)
review page: out-resweep-18/present/index.html
```

**`present` selected 14**, versus **1** in sweep 17. All 14 are not on the
already-applied exclusion list, are open by the pipeline's shared open-state
check, clear the technical role floor, and are not below the stipend floor.
One has a **confirmed ₹50,000/month** stipend; 13 are unstated-but-verified
(the page shows them in the "verify before applying" section).

| # | Score | Band | Source | Company | Title | Tech rel | Stipend | Window |
| ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.741 | strong | unstop | Frugality Fintech | AI/ML & Data Analyst Internship | 0.90 ai_ml | not stated | unknown |
| 2 | 0.730 | strong | unstop | Prism Labs | AI/ML Research Internship | 0.80 ai_ml | not stated | unknown |
| 3 | 0.710 | strong | unstop | FlatUIUX | AI/ML Engineer Internship | 0.90 ai_ml | not stated | unknown |
| 4 | 0.705 | strong | unstop | Kisan Udyog | Python Developer Internship | 0.70 software | not stated | unknown |
| 5 | 0.658 | shortlist | themuse | Biogen | Co-op, Data Science & AI Innovation | 0.90 ai_ml | not stated | **Jan-Jun 2027** |
| 6 | 0.643 | shortlist | unstop | AI Invito | Python Developer Internship | 0.60 software | not stated | unknown |
| 7 | 0.630 | shortlist | unstop | Deep Variance Inc | Research Internship - AI Infrastructure | 0.70 research | **₹50,000/mo** | unknown |
| 8 | 0.630 | shortlist | unstop | PSYC Aerospace & Defence | AI/ML & Test Engineering Internship | 0.90 ai_ml | not stated | unknown |
| 9 | 0.630 | shortlist | unstop | SmaranAI.in | Junior AI Developer Internship (Deep Learning) | 0.70 ai_ml | not stated | unknown |
| 10 | 0.605 | shortlist | unstop | Qveto | Python Developer Internship | 0.60 software | not stated | unknown |
| 11 | 0.605 | shortlist | unstop | IntelleQAcademy | Python Development Internship | 0.60 software | not stated | unknown |
| 12 | 0.600 | shortlist | unstop | Zenotalent | Python Internship | 0.70 software | not stated | unknown |
| 13 | 0.560 | shortlist | unstop | IntelleQAcademy | Generative AI Internship | 0.90 ai_ml | not stated | unknown |
| 14 | 0.555 | shortlist | unstop | Vortizo AI | Python Internship | 0.70 software | not stated | unknown |

The one true in-window, India-relevant, confirmed-new posting is **Biogen —
Co-op, Data Science & AI Innovation** (themuse, Jan-Jun 2027, ai_ml 0.90), which
was also sweep 17's single selected match and is still new (not applied). The
rest are Unstop India roles with an unstated window — review-only, exactly as the
window filter intends.

### 6a. Exclusion breakdown (all 132 candidates reconciled)

| Reason | Count |
| --- | ---: |
| already applied (exclusion list) | 24 |
| role relevance below the technical floor | 46 |
| non-technical role term | 45 |
| **subtotal excluded** | **115** |
| held borderline (present-arithmetic gap, §7 R1) | 3 |
| **presented** | **14** |
| **total** | **132** |

Reconciliation: 115 + 3 + 14 = 132 = pending queue. Of sweep 17's 9 strong-band
postings, all were already-applied; in sweep 18 the strong band grew to 14, and
**10 of the 14 strong are hidden (9 already-applied, 1 non-technical "video"
title), leaving 4 genuinely-new strong matches presented** (Frugality Fintech,
Prism Labs, FlatUIUX, Kisan Udyog). The strong-band already-applied set is
dominated by the same roles sweep 17 already hid (Rubrik ×2, PrepLinc ×2, Stripe,
Labcorp, Zenotalent, Skillorbit, …) — the new page is not just those again.

## 7. Defects and unexpected behaviour

### R1. (inherited, unchanged) `present` silently holds borderline candidates

`select_matches` collects candidates with role relevance in
`[borderline_role_relevance, min_role_relevance)` in a local list, then only
assigns it to the result when *nothing* cleared the floor; otherwise those
candidates are neither included nor excluded. Three candidates are held this run
(role relevance 0.40):

| Score | Source | Company | Title | Domain |
| --- | --- | --- | --- | --- |
| EdJAMon | unstop | EdJAMon | AI Professional Internship | ai_ml 0.40 |
| GradGuide | unstop | GradGuide | Software Engineering Internship | software 0.40 |
| Abstrabit | himalayas | Abstrabit Technologies | Software Engineering Intern | ai_ml 0.40 |

Identical to sweep 15's R1 and sweep 17's "3 held borderline". Inherited,
non-regressive, loses no safety guarantee (held candidates are simply not
shown). Not fixed — out of scope.

### R2. (inherited, intended) Ashby unreadable and LinkedIn disallowed

`ashby`: `robots.txt` HTTP 401 for every UA → gate fails closed, 0 fetched.
`linkedin`: `Disallow: /` for `user-agent: *` → all 5 queries refused before any
fetch. `workable`: skipped (disabled). All three are the robots gate working as
designed.

### R3. (inherited) four postings fail parseability with an extraction I/O error

Four queued postings carry
`parseability check failed: text extraction failed: I/O Error: Couldn't open
file 'resume.pdf'` (Abstrabit SWE, Momentum QA, A Healthier Democracy
Practicum, CLEAR Global Project Management). This is **identical to sweep 17**
(same four rows), is not caused by this change, and all four are non-technical
roles that `present` excludes anyway. Not fixed — out of scope.

### R4. (transient, observed once, not a code defect) first attempt lost The Muse

The first sweep-18 attempt failed `themuse` and reported `linkedin` as
`UNCONFIRMED (URLError)` rather than `DISALLOWED`, i.e. the robots.txt read for
those two hosts failed transiently at run time (fail-closed by design). A manual
re-read immediately after succeeded (HTTP 200 for both), so the run was restarted
cleanly; the committed run has `sources_failed: 2` (ashby, linkedin) and The Muse
present with 67 postings. The transient attempt logged 13 presented matches
without The Muse, corroborating the improvement; its log is kept outside the
repo. This is a network blip, not an adapter or config defect.

## 8. Safety — zero submissions (from the run's own record)

- run `mode = dry_run`; `stats.submitted = 0`, `duplicates = 0`, `capped = 0`.
- `applications`: **132 rows, all `status = manual_required`; 0 submitted**.
- `attempts`: **empty (0 rows)** — no submission was ever attempted.
- `review_queue`: 132 rows, all `pending`.
- Auto-apply is off (`apply.auto_apply_strong = false`, `apply.adapter = "none"`)
  on top of `--dry-run`; the robots gate was active (`sources_failed` names the
  two intended refusals); no fact was invented for any resume.

## 9. Presented artifacts — one page, verified by measurement

- 14 `resume.pdf` + 14 `cover_letter.pdf` under
  `out-resweep-18/present/assets/<slug>/`; 14 cards in `index.html`.
- **Every copied asset resume PDF is exactly 1 page** (`pdftotext` form-feed
  count): `{1: 14}`.
- Independent re-check of each asset PDF against the configured
  `required_sections` (Education, Experience, Projects, Technical Skills) and the
  profile's name/email/phone/linkedin/github: **14/14 parseable, 0 failures**.
- Store agrees: `resume_pages = 1` for every presented row;
  `resume_page_limit = 1`; `compile_failed = 0`.
- No-invention invariant held; unsupported JD terms appear only as gaps.

## 10. Before / after comparison

| Metric | Sweep 17 | Sweep 18 | Delta |
| --- | ---: | ---: | --- |
| discovered | 11127 | 11428 | +301 (unstop +295, themuse +7) |
| eligible | 126 | **165** | **+39** (unstop +33, themuse +6) |
| shortlisted / queued | 101 | **132** | **+31** |
| strong | 9 | **14** | **+5** (unstop 5 → 10) |
| tailored | 97 | 128 | +31 |
| **`present` selected** | **1** | **14** | **+13 (14×)** |
| — new (not already-applied) | 1 | 14 | +13 |
| — confirmed stipend ≥ floor | 0 | 1 | +1 |
| — unstated (verify separately) | 1 | 13 | +12 |
| excluded | 97 | 115 | +18 |
| submitted | 0 | 0 | dry run |

The success criterion — genuinely-new, technical, open, not-already-applied,
stipend-qualifying (or unstated-but-verified) postings presented materially
greater than sweep 17's 1 — **is met: 14 versus 1.**

Honest caveats: (a) the gain is almost entirely Unstop, so it is one source's
inventory standing up better to a targeted query, not a broad-market windfall;
(b) 13 of the 14 state no stipend and must be verified before applying; (c) most
are window-unstated, so they are review-only rather than auto-apply-eligible;
(d) a repeated run would surface a different Unstop page of 20-per-keyword and
therefore a somewhat different set — the count should be read as "tens, not
one", not exactly 14.

## 11. `jobpilot upskill` — top skill gaps

```
 #  skill                            jobs  weight  source
 1  Problem Solving                    61   30.41  application,posting
 2  Research                           48   23.98  application,posting
 3  Data Analysis                      41   21.50  application,posting
 4  Data Science                       20    8.29  application
 5  Model Deployment                   12    5.86  application,posting
 6  Agile                              11    5.56  application,posting
 7  Algorithms                         10    3.93  application
 8  AWS                                 8    3.58  application,posting
 9  REST APIs                           7    3.12  application
10  Deep Learning                       8    2.87  application
```

## 12. What the captain can actually apply to

- **Biogen — Co-op, Data Science & AI Innovation** (themuse): the one
  explicit **Jan-Jun 2027** window, ai_ml 0.90, remote/flexible.
  https://www.themuse.com/jobs/biogen/coop-data-science-ai-innovation
- **Deep Variance Inc — Research Internship - AI Infrastructure** (unstop):
  the one **confirmed ₹50,000/month**, research/ai_ml 0.70.
  https://unstop.com/internships/research-internship-ai-infrastructure-deep-variance-inc-1755818
- **New strong AI/ML, window unstated (verify dates/stipend first):**
  Frugality Fintech (AI/ML & Data Analyst), Prism Labs (AI/ML Research),
  FlatUIUX (AI/ML Engineer), Kisan Udyog (Python Developer) — plus the
  shortlist Python/GenAI roles from AI Invito, PSYC, SmaranAI, Qveto,
  IntelleQAcademy, Zenotalent, Vortizo AI.

The review page the captain should open is
`out-resweep-18/present/index.html` (self-contained, relative links, no server).

## 13. Verdict

Retargeting discovery at internship-dense sources worked: the same broad ATS
boards still contribute nothing new, but the widened Unstop keyword slices plus
The Muse's full typed depth moved `present` from **1 to 14** genuine technical
internships (eligible 126 → 165, queued 101 → 132, strong 9 → 14), with zero
submissions, zero compile failures, every presented resume one page and
parseable, and no fact invented. The result is honestly one source (Unstop)
doing the heavy lifting and most matches are stipend/window-unstated
review-only roles, but the page is materially fuller and the captain has a real
set to choose from this week.
