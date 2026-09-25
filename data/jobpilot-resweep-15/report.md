# jobpilot full resweep — report (jobpilot-resweep-15)

Date: 2026-09-25. Operator: crewmate (firstmate-managed). Mode: **dry run only,
zero submissions**. Config: `/mnt/d/jobpilot/config.toml` (captain's copy,
untracked, unchanged this run). Code: commit `2d370ff` (the merged `main` in
`/mnt/d/jobpilot`). Run executed from `/mnt/d/jobpilot`.

This run re-runs the sweep after firstmate restored the master profile's
`## Projects` H2 heading, which resweep-14 had found missing (its §7 D1). The
question was whether the restored heading removes the **38/234 parseability
failures** and puts the projects back into the tailored resumes. It does: the
fresh run reports **`parseability_failed: 0`** and every presented asset now
carries a `Projects` section. Measurement details in §7 and §8.

Machine-readable record: `/mnt/d/jobpilot/data/jobpilot-resweep-15/run.json`;
full CLI log `run.log`, present/upskill logs, and the verification dumps
(`verify.log`, `verify2.log`) in the same directory.

Previous run's artifacts were preserved before this run started, so the fresh
store and page are unambiguous:

- old store -> `/mnt/d/jobpilot/jobpilot-resweep-14.db` (resweep-14: 234
  applications, 38 parseability failures — re-read read-only to confirm the
  "before" count, §1)
- old run tree -> `/mnt/d/jobpilot/out-resweep-14/`

## 1. Profile pre-check — verified before the run

`/mnt/d/LaTeX/resume/PROFILE.md` (83 lines) now carries:

- `## Education` (line 13)
- `## Experience` (line 20) holding **exactly the three** experience entries:
  CSIR-National Aerospace Laboratories (ML Intern), Outlier.ai (AI Content
  Evaluator & Trainer), CRIS (ML Intern)
- `## Projects` (line 37) holding the four project entries: `costsmart-rag`,
  `tsfm-benchmark`, `guardrailed-sql-analyst`, `EV Transition & Grid
  Feasibility Analysis`
- `## Technical Skills` (line 77)
- (`## Positions of Responsibility` also present, excluded from the AI/ML
  resume by config.)

The project parser confirms the split: **`experiences: 3`, `projects: 4`**
(resweep-14 measured `experiences: 7`, `projects: 0`). A cheap generator
pre-check emitted `\section{Education}`, `\section{Experience}`,
`\section{Projects}`, `\section{Technical Skills}` and the repo link, so the
expensive run went ahead on measured evidence, not assumption.

"Before" count re-read read-only from the archived store
`jobpilot-resweep-14.db`: `parseability_ok=0 -> 38`, `parseability_ok=1 -> 196`,
234 application rows. This run's store: `parseability_ok=1 -> 230`, zero rows
with `parseability_ok=0`.

## 2. What was run

```
# from /mnt/d/jobpilot, using merged main (2d370ff)
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml run --dry-run
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml present
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml upskill
```

Run window: `2026-09-25T13:27:40+00:00` -> `2026-09-25T13:56:04+00:00`
(~28 min).

Config unchanged from resweep-14 and still safe: window Jan–May/June
(`window_start_month = 1`, `window_end_month = 6`), `allow_unknown_window =
false`, `allow_onsite_abroad = false`, `allow_unknown_location = false`;
**auto-apply OFF** (`apply.auto_apply_strong = false`, `apply.adapter = "none"`,
no SMTP block) plus `--dry-run`; `resume_page_limit = 1`,
`resume_fit_attempts = 6`; robots gate enabled, agent `jobpilot`.

## 3. Source coverage — every source, with per-query counts

6 `ok`, 2 `failed`, 1 `skipped`, **0 unexpected failures** (both failures are
the robots gate working as designed):

| Source | Status | Returned | Notes |
| --- | --- | --- | --- |
| greenhouse | ok | 5915 | 30 board tokens, full content |
| lever | ok | 280 | 5 tokens |
| ashby | **failed** | 0 | `robots.txt` unreadable (HTTP 401 for every UA) -> gate fails closed (`UNCONFIRMED`) |
| workable | skipped | 0 | disabled by config |
| **himalayas** | **ok** | **34** | first page only, no `page` param; typed `employment_type=Intern&country=India` + `q=intern` merged/deduped |
| unstop | ok | 288 | generic feed + 5 `searchTerm` keyword queries (below) |
| workable_global | ok | 66 adapter / 65 stored | `query=intern&location=India`, 4 pages; one repeated `stable_id` deduped by `discover` |
| themuse | ok | 60 | typed `level=Internship` + broad `location=India` |
| linkedin | **failed** | 0 | `Disallow: /` for `user-agent: *` blocks the guest reader |

`discover` dedupes by `source:job_id`, so the run's `discovered` count is
**6642**.

### Himalayas — still contributing via the first-page-only path

Himalayas returned **34 postings** (typed slice + `q=intern`, merged/deduped),
the same shape as resweep-14 and again with no `page` parameter (the paged API
path is robots-disallowed). It contributed **1 presented technical match** and
**2 of the 4 held-borderline** candidates. No strong-band matches.

### Unstop `searchTerm` keyword slices — per-query new counts

| Query | New postings (after dedupe) |
| --- | --- |
| generic feed | 242 |
| `searchTerm=machine learning` | 10 |
| `searchTerm=artificial intelligence` | 10 |
| `searchTerm=ai` | 10 |
| `searchTerm=data science` | 6 |
| `searchTerm=software engineer` | 10 |
| **total** | **288** |

### LinkedIn — still refused by the enforced gate

All five configured target queries were refused before any fetch
(`RobotsBlocked: robots gate: DISALLOWED for jobpilot`). Live
`https://www.linkedin.com/robots.txt` ends with `User-agent: *` / `Disallow: /`.
Per-query counts are all **0 / blocked**. Intended safe behaviour.

## 4. Funnel

```
discovered ................ 6642
hard-filter survivors ..... 383   (eligible)
scored .................... 383
strong .................... 16
tailored .................. 230
queued for review ......... 230
submitted ................. 0
parseability failures ..... 0     <-- was 38 in resweep-14
LaTeX compile failures .... 0
```

Per source (returned / eligible / scored / strong / queued / submitted):

| Source | returned | eligible | scored | strong | queued | submitted |
| --- | --- | --- | --- | --- | --- | --- |
| greenhouse | 5915 | 10 | 10 | 3 | 9 | 0 |
| lever | 280 | 5 | 5 | 0 | 5 | 0 |
| himalayas | 34 | 32 | 32 | 0 | 29 | 0 |
| unstop | 288 | 270 | 270 | 12 | 139 | 0 |
| workable_global | 65 | 25 | 25 | 0 | 22 | 0 |
| themuse | 60 | 41 | 41 | 1 | 26 | 0 |
| **total** | **6642** | **383** | **383** | **16** | **230** | **0** |

## 5. Technical / AI-ML / data / research matches

```
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml present
# nothing was submitted.
# presented 45 technical match(es)
# excluded 181 non-technical / low-relevance queued posting(s)
# review page: /mnt/d/jobpilot/out/present/index.html
```

`present` selected **45 technical matches** (0 borderline shown, 181 excluded,
4 held borderline — §7 R1). By source: unstop 36, themuse 4, greenhouse 3,
himalayas 1, workable_global 1.

### 5a. All 16 `strong`-band matches

| # | Score | Source | Company | Title | Location | Link |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.835 | greenhouse | Rubrik Job Board | Software Engineer - Winter Intern | Bangalore | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 2 | 0.810 | greenhouse | Rubrik Job Board | Software Engineer (CPD) - Winter Intern | Bangalore | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
| 3 | 0.780 | unstop | PrepLinc AI | AI/ML Application Developer Internship | Online | https://unstop.com/internships/aiml-application-developer-internship-preplinc-ai-1760453 |
| 4 | 0.761 | unstop | Pariskq | Software Engineer Internship | Bangalore, Online | https://unstop.com/internships/software-engineer-internship-pariskq-1729187 |
| 5 | 0.761 | unstop | PrepLinc AI | Data Science & Artificial Intelligence Internship | Online | https://unstop.com/internships/data-science-artificial-intelligence-internship-preplinc-ai-1760823 |
| 6 | 0.723 | unstop | Vortizo AI | Data Science Internship | Online | https://unstop.com/internships/data-science-internship-vortizo-ai-1752060 |
| 7 | 0.718 | greenhouse | Stripe | Software Engineer, Intern | Bengaluru | https://stripe.com/jobs/search?gh_jid=8031833 |
| 8 | 0.715 | themuse | Labcorp | Data Science Intern - Real World Data Strategy Team | Flexible / Remote | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |
| 9 | 0.711 | unstop | Zenotalent | Data Science Internship | Chennai, Mangaluru, Bangalore, Pune, Noida, Delhi, Kolkata, Hyderabad, Online | https://unstop.com/internships/data-science-internship-zenotalent-1755823 |
| 10 | 0.705 | unstop | godstockss | Software Engineer Internship | Online | https://unstop.com/internships/software-engineer-internship-godstockss-1731267 |
| 11 | 0.692 | unstop | TalentCV | Software Engineer Internship | Online | https://unstop.com/internships/software-engineer-intern-talentcv-1694821 |
| 12 | 0.692 | unstop | Learntricks Edutech | Machine Learning Internship | Online | https://unstop.com/internships/machine-learning-internship-unstop-tech-fair-2025-learntricks-edutech-1724312 |
| 13 | 0.690 | unstop | Learn Depth | Machine Learning Trainer Internship | Online | https://unstop.com/internships/machine-learning-trainer-internship-learn-depth-1735074 |
| 14 | 0.689 | unstop | Maytrixtech | Software Engineer Internship | Online | https://unstop.com/internships/software-engineer-internship-maytrixtech-1733361 |
| 15 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Engineer Internship | Bangalore, Chennai, Online | https://unstop.com/internships/machine-learning-engineer-internship-skillorbit-private-limited-1752362 |
| 16 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Internship | Bangalore, Online | https://unstop.com/internships/machine-learning-intern-skillorbit-private-limited-1759582 |

Auto-apply is off (`adapter = "none"`), so all 16 queue as `manual_required`.

### 5b. The 45 presented technical matches (ordered by score)

| # | Score | Source | Company | Title | Tech rel | Link |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.835 | greenhouse | Rubrik Job Board | Software Engineer - Winter Intern | software 0.70 | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 2 | 0.810 | greenhouse | Rubrik Job Board | Software Engineer (CPD) - Winter Intern | software 0.60 | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
| 3 | 0.780 | unstop | PrepLinc AI | AI/ML Application Developer Internship | ai_ml 0.70 | https://unstop.com/internships/aiml-application-developer-internship-preplinc-ai-1760453 |
| 4 | 0.761 | unstop | Pariskq | Software Engineer Internship | software 0.90 | https://unstop.com/internships/software-engineer-internship-pariskq-1729187 |
| 5 | 0.761 | unstop | PrepLinc AI | Data Science & Artificial Intelligence Internship | ai_ml 0.90 | https://unstop.com/internships/data-science-artificial-intelligence-internship-preplinc-ai-1760823 |
| 6 | 0.723 | unstop | Vortizo AI | Data Science Internship | ai_ml 0.80 | https://unstop.com/internships/data-science-internship-vortizo-ai-1752060 |
| 7 | 0.718 | greenhouse | Stripe | Software Engineer, Intern | software 0.60 | https://stripe.com/jobs/search?gh_jid=8031833 |
| 8 | 0.715 | themuse | Labcorp | Data Science Intern - Real World Data Strategy Team | ai_ml 0.80 | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |
| 9 | 0.711 | unstop | Zenotalent | Data Science Internship | ai_ml 0.80 | https://unstop.com/internships/data-science-internship-zenotalent-1755823 |
| 10 | 0.705 | unstop | godstockss | Software Engineer Internship | software 0.80 | https://unstop.com/internships/software-engineer-internship-godstockss-1731267 |
| 11 | 0.692 | unstop | Learntricks Edutech | Machine Learning Internship | ai_ml 0.90 | https://unstop.com/internships/machine-learning-internship-unstop-tech-fair-2025-learntricks-edutech-1724312 |
| 12 | 0.692 | unstop | TalentCV | Software Engineer Internship | software 0.90 | https://unstop.com/internships/software-engineer-intern-talentcv-1694821 |
| 13 | 0.690 | unstop | Learn Depth | Machine Learning Trainer Internship | ai_ml 0.70 | https://unstop.com/internships/machine-learning-trainer-internship-learn-depth-1735074 |
| 14 | 0.689 | unstop | Maytrixtech | Software Engineer Internship | software 0.90 | https://unstop.com/internships/software-engineer-internship-maytrixtech-1733361 |
| 15 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Internship | ai_ml 0.90 | https://unstop.com/internships/machine-learning-intern-skillorbit-private-limited-1759582 |
| 16 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Engineer Internship | ai_ml 0.80 | https://unstop.com/internships/machine-learning-engineer-internship-skillorbit-private-limited-1752362 |
| 17 | 0.680 | unstop | Operonn | AI Engineer Internship | ai_ml 0.90 | https://unstop.com/internships/ai-engineer-internship-operonn-1755613 |
| 18 | 0.673 | unstop | BluMotiv | Software Engineer Internship | software 0.90 | https://unstop.com/internships/software-engineer-internship-blumotiv-1668628 |
| 19 | 0.672 | himalayas | Ritual | Research Intern | research 0.60 | https://himalayas.app/companies/ritual-net/jobs/research-intern-1464631102 |
| 20 | 0.667 | unstop | Vision AI Learning | Curriculum Developer – Artificial Intelligence Internship | ai_ml 0.70 | https://unstop.com/internships/curriculum-developer-artificial-intelligence-internship-vision-ai-learning-1759335 |
| 21 | 0.661 | themuse | The Muse | AI Engineer – Remote Internship | ai_ml 0.90 | https://www.themuse.com/jobs/themuse/ai-engineer-remote-internship |
| 22 | 0.655 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship | ai_ml 0.90 | https://unstop.com/internships/artificial-intelligence-internship-skillorbit-private-limited-1758984 |
| 23 | 0.650 | unstop | Embolo Technologies Private Limited | Software Engineer Internship | software 0.90 | https://unstop.com/internships/software-engineer-internship-embolo-technologies-private-limited-1727893 |
| 24 | 0.643 | unstop | JobLuxe | Software Engineer Internship | software 0.60 | https://unstop.com/internships/software-engineer-intern-jobluxe-1750680 |
| 25 | 0.625 | unstop | Skill Orbit | Artificial Intelligence Internship | ai_ml 0.80 | https://unstop.com/internships/artificial-intelligence-internship-skill-orbit-1756034 |
| 26 | 0.625 | themuse | The Muse | Data Engineer – Remote Internship | software 0.80 | https://www.themuse.com/jobs/themuse/data-engineer-remote-internship |
| 27 | 0.623 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | ai_ml 0.80 | https://unstop.com/internships/artificial-intelligence-internship-xtragrad-technologie-private-limited-1754902 |
| 28 | 0.605 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | ai_ml 0.90 | https://unstop.com/internships/artificial-intelligence-internship-xtragrad-technologie-private-limited-1747534 |
| 29 | 0.600 | unstop | Zenotalent | Data Science Internship | ai_ml 0.70 | https://unstop.com/internships/data-science-internship-zenotalent-1748389 |
| 30 | 0.600 | themuse | Atlassian | Research Intern, 2026 Summer U.S. | research 0.60 | https://www.themuse.com/jobs/atlassian/research-intern-2026-summer-us |
| 31 | 0.586 | unstop | Kukbit SL | Machine Learning Internship | ai_ml 0.60 | https://unstop.com/internships/machine-learning-internship-kukbit-sl-1751307 |
| 32 | 0.585 | unstop | Skillorbit Academy | Artificial Intelligence Internship | ai_ml 0.70 | https://unstop.com/internships/artificial-intelligence-intern-skillorbit-academy-1750189 |
| 33 | 0.580 | unstop | Kukbit SL | Data Science Internship | ai_ml 0.80 | https://unstop.com/internships/data-science-internship-kukbit-sl-1761158 |
| 34 | 0.573 | unstop | Zenotalent | Machine Learning Internship | ai_ml 0.90 | https://unstop.com/internships/machine-learning-internship-zenotalent-1749292 |
| 35 | 0.560 | unstop | Vortizo AI | Machine Learning Internship | ai_ml 0.90 | https://unstop.com/internships/machine-learning-internship-vortizo-ai-1744336 |
| 36 | 0.555 | unstop | Aalteon | Artificial Intelligence Internship | ai_ml 0.70 | https://unstop.com/internships/artificial-intelligence-internship-aalteon-1758771 |
| 37 | 0.555 | unstop | IntelleQAcademy | Data Science and ML Internship | ai_ml 0.70 | https://unstop.com/internships/data-science-and-ml-internship-intelleqacademy-1751493 |
| 38 | 0.535 | unstop | Aalteon | Artificial Intelligence Internship | ai_ml 0.80 | https://unstop.com/internships/artificial-intelligence-internship-aalteon-1742163 |
| 39 | 0.530 | unstop | Zenotalent | Data Science Internship | ai_ml 0.60 | https://unstop.com/internships/data-science-internship-zenotalent-1760539 |
| 40 | 0.505 | unstop | Cornixe Edutech Pvt. Ltd. | Data Science & Machine Learning Internship | ai_ml 0.80 | https://unstop.com/internships/data-science-machine-learning-internship-cornixe-edutech-pvt-ltd-1761310 |
| 41 | 0.505 | workable_global | Blue Machines AI | Evaluation & Insights Intern, AI Delivery | ai_ml 0.50 | https://jobs.workable.com/view/hYkVydG3ua3RuasU6CTiMw/evaluation-%26-insights-intern%2C-ai-delivery-in-bengaluru-at-blue-machines-ai |
| 42 | 0.480 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship | ai_ml 0.70 | https://unstop.com/internships/artificial-intelligence-internship-skillorbit-private-limited-1748852 |
| 43 | 0.455 | unstop | Skillorbit Private Limited | Machine Learning Internship | ai_ml 0.60 | https://unstop.com/internships/machine-learning-internship-skillorbit-private-limited-1758836 |
| 44 | 0.455 | unstop | Digital Back Office | Software Engineer Internship | software 0.60 | https://unstop.com/internships/software-engineer-intern-digital-back-office-1756610 |
| 45 | 0.443 | unstop | Qveto | Data Science and Machine Learning Internship | ai_ml 0.70 | https://unstop.com/internships/data-science-and-machine-learning-internship-qveto-1747163 |

## 6. Explicit Jan-May/June window vs unknown

Among the 45 presented matches only **3 are explicit**:

- **Rubrik SWE - Winter Intern** and **Rubrik SWE (CPD) - Winter Intern**,
  Bangalore, **Jan-May 2027**, confidence 1.0 (the only true in-window
  presented matches).
- **Atlassian Research Intern, 2026 Summer U.S.**, **Jun-Aug 2026**,
  confidence 1.0 (a US research role).

The other 42 are unknown-window and therefore review-only.

Among all 230 queued postings: 205 `unknown`, 11 `Summer` (conf 0.6), 3
`Dec-Jun 2027`, 3 `Jan-5 2027` (store label for Jan-May 2027), 2 `Dec-Jun
2026`, and 1 each of `Jan-Aug`, `Jun-Aug 2026`, `Summer 2025`, `5-5 2023`,
`Mar-Mar 2024`, `Mar-Mar 2023`. With `allow_unknown_window = false` no
unknown-window posting can auto-apply.

## 7. Defects and unexpected behaviour

### D1. RESOLVED — the restored `## Projects` heading removed all 38 parseability failures

- **Command:** `python3 -m jobpilot --config /mnt/d/jobpilot/config.toml run --dry-run`
- **Before (archived `jobpilot-resweep-14.db`, latest per stable_id):**
  `parseability_ok=0 -> 38`, `parseability_ok=1 -> 196`; run record
  `"parseability_failed": 38`; every failure reason was
  `parseability check failed: missing sections: Projects; ...` or the
  `Statistics` keyword-survival fallout.
- **After (this run):** `parseability_ok=1 -> 230`, `parseability_ok=0 -> 0`;
  run record `"parseability_failed": 0`; no stored reason contains
  `parseability check failed`.
- **Root cause fixed:** the profile now has `## Projects`, `profile.projects`
  is non-empty, the generator emits `\section{Projects}`, and the stack lines
  that carry `Statistics` reach the PDF again.

### R1. (inherited presentation arithmetic) `present` silently holds the 4 borderline candidates

`select_matches` puts candidates in `[borderline_role_relevance,
min_role_relevance)` aside as borderline and, when at least one role clears the
floor, drops the borderline list entirely — it is neither included nor
excluded. So `present` prints `presented 45` + `excluded 181` while the queue is
`230`. The 4 held candidates are:

| Score | Source | Company | Title | Domains |
| --- | --- | --- | --- | --- |
| 0.667 | himalayas | Drivetrain | Engineering Intern – Gen AI for FP&A Platform | ai_ml 0.40 |
| 0.657 | unstop | EdJAMon | AI Professional Internship | ai_ml 0.40 |
| 0.621 | unstop | GradGuide | Software Engineering Internship | software 0.40 |
| 0.593 | himalayas | Abstrabit Technologies Pvt Ltd | Software Engineering Intern | ai_ml 0.40 |

**Reconciliation:** 45 presented + 181 excluded + 4 held-borderline = **230** =
pending queue. The same 4 candidates were held in resweep-14 (46+184+4=234);
this is inherited behaviour, not a regression, and nothing unsafe ships — held
candidates are simply not shown.

### R2. (inherited, intended) Ashby unreadable and LinkedIn disallowed

- `ashby`: `robots gate: UNCONFIRMED (HTTPError)` for all 8 tokens -> fails
  closed (0 fetched).
- `linkedin`: `RobotsBlocked: robots gate: DISALLOWED for jobpilot`, all 5
  queries refused before any fetch.
- `workable` skipped (disabled by config).

All three are the robots gate working as designed.

### R3. (minor, inherited) `workable_global` returned 66 but stored 65

One repeated `stable_id` inside the adapter's own result set; `discover`
dedupes by `source:job_id`. Harmless.

### R4. (minor, inherited) Window label renders May as `5`

The store label for Jan-May 2027 is `Jan-5 2027`; `present._pretty_window`
corrects it to `Jan-May 2027` on the card. Classification and confidence are
correct. Not fixed.

No run-blocking defect appeared; no code or config was changed.

## 8. Tailored artifacts — one page, verified by measurement

- **Presentation assets:** 45 `resume.pdf` + 45 `cover_letter.pdf` under
  `out/present/assets/<slug>/` (45 cards in `out/present/index.html`).
- **Every copied asset resume PDF is exactly 1 page**, measured from the
  `pdftotext -layout` output's form feeds (the project's `extract_pdf_text` +
  `count_pages`, never `/Count`): `{1: 45}`, zero extraction failures, zero
  missing PDFs.
- **Independent parseability re-check on every asset PDF** against the
  configured `required_sections = ["Education", "Experience", "Projects",
  "Technical Skills"]` and the profile's name/email/phone/linkedin/github:
  **45 checked, 0 failures**.
- **Assets reflect the current profile:** 45/45 contain `CSIR`; 0/45 contain
  `Astro Deus`; 45/45 carry a `Projects` section.
- Store agrees: all 230 queued rows have `resume_pages = 1`,
  `resume_page_limit = 1`; `compile_failed = 0`; all 230 have
  `parseability_ok = 1`.
- No-invention invariant held: unsupported JD terms appear only as gaps and were
  never inserted.

### R5. The restored heading changed the resumes — confirmed on extracted text

Extracted text from the presented Rubrik asset
(`greenhouse-Rubrik-Job-Board-Software-Engineer----87fad9533f/resume.pdf`)
contains the literal section headings `Education`, `Experience`, `Projects`,
`Technical Skills`, plus `costsmart-rag`, `tsfm-benchmark`,
`guardrailed-sql-analyst` and the costsmart-rag stack line
`Python, RAG, LLM Routing, Evaluation, Statistics`. The resweep-14
`out-resweep-14/greenhouse-rubrik-.../resume.tex` had **no**
`\section{Projects}` (only Education/Experience/Technical Skills) and rendered
the projects as Experience entries; the fresh `resume.tex` has
`\section{Projects}` and emits each project's `\href` repo link. This was
verified on the extracted PDF text, not assumed.

## 9. Zero-submission verification (from the run's own record)

- run `mode = dry_run`; `stats.submitted = 0`, `duplicates = 0`, `capped = 0`.
- `applications`: **230 rows, all `status = manual_required`; 0 submitted**.
- `attempts`: **empty (0 rows)** — no submission was ever attempted.
- `review_queue`: 230 rows, all `pending`.
- CLI printed `dry run: nothing was submitted.`; present printed
  `nothing was submitted.`

## 10. Comparison with resweep-14

| Metric | resweep-14 | resweep-15 | Why |
| --- | --- | --- | --- |
| discovered | 6625 | 6642 | small board drift (greenhouse +12, lever +4, unstop +3, workable_global -2) |
| eligible | 379 | 383 | same drift |
| strong | 16 | **16** | unchanged; same strong set |
| tailored / queued | 234 | 230 | 4 fewer shortlisted (drift), same shape |
| submitted | 0 | 0 | dry run, auto-apply off |
| **parseability failures** | **38** | **0** | `## Projects` heading restored (D1) |
| presented | 46 | 45 | drift; still ≥36 unstop |
| asset resumes 1-page | 46/46 | 45/45 | unchanged |

## 11. `jobpilot upskill` — top skill gaps

```
 1  Research           119  72.60
 2  Problem Solving     95  51.44
 3  Data Analysis       61  33.40
 4  Data Science        20   8.00
 5  Algorithms          19   7.76
 6  Model Deployment    15   7.33
 7  Computer Vision     12   7.32
 8  Agile               14   6.76
 9  REST APIs           14   5.69
10  AWS                  9   3.89
```

Ordering is essentially unchanged from resweep-14 (Research, Problem Solving,
Data Analysis lead).

## 12. What the captain can actually apply to

- **Most actionable, in-window, India:** **Rubrik - Software Engineer (Winter
  Intern)** and **Rubrik - Software Engineer (CPD) (Winter Intern)**, Bangalore,
  explicit **Jan-May 2027**, strong band (0.835 / 0.810). Both are review-only
  because `auto_apply_strong = false`, and both now have parseable one-page
  tailored resumes with a `Projects` section.
  - https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523
  - https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537
- **Strong AI/ML/data, window unconfirmed (verify dates first):** Stripe SWE
  Intern (Bengaluru), Labcorp Data Science (remote), and the Unstop strong roles
  (PrepLinc AI, Vortizo AI, Zenotalent, Skillorbit, Learntricks, Learn Depth).
- **Himalayas:** Ritual - Research Intern (worldwide, research 0.60) is
  presented; Drivetrain Gen AI and Abstrabit are held borderline.

## 13. Verdict

The profile re-run is clean: **6642 discovered, 383 eligible, 16 strong, 230
tailored, 230 queued, 0 submitted**, with **every tailored resume one page and
parseable (`parseability_failed: 0`, down from 38)** and all 45 presented assets
carrying `CSIR` and a `Projects` section with no `Astro Deus`. The restored
`## Projects` heading fixed the resweep-14 regression by measurement: the parser
now yields 3 experiences + 4 projects, the generator emits
`\section{Projects}` and repo hyperlinks, and the project stack lines (`...,
Statistics`) reach the PDF again. The run is safe — zero submissions, zero
attempts, robots gate intact, no invention. The only remaining oddity is the
inherited present-arithmetic gap (R1: 4 borderline candidates held, not shown),
which loses no safety guarantee.
