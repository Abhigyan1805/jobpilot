# jobpilot full resweep — report (jobpilot-resweep-12)

Date: 2026-09-24. Operator: crewmate (firstmate-managed). Mode: **dry run only,
zero submissions**. Config: `/mnt/d/jobpilot/config.toml` (captain's copy,
untracked). Code: commit `cc6a284` (the merged `main`); the run was executed from
the primary checkout `/mnt/d/jobpilot`. Machine-readable record:
`/mnt/d/jobpilot/data/jobpilot-resweep-12/run.json` and the fresh SQLite store
`/mnt/d/jobpilot/jobpilot.db` (run id 1).

This is the payoff run the captain asked for: every recent change is merged -
the widened sources (Unstop's keyword API, Workable global, The Muse, the
Himalayas widening, the real LinkedIn query set), one-page tailored resumes, the
stricter scoring band, deadline tracking and the enforced robots gate. The stale
run-07 results on disk were preserved first:

- old store -> `/mnt/d/jobpilot/jobpilot-run-07.db`
- old run tree -> `/mnt/d/jobpilot/out-run-07/`
  (`out-run-07-prelinkedin/` and `out-run-04/` are unchanged.)

so this run's store, packets and presentation page are unambiguous.

## 1. What was run

```
# from /mnt/d/jobpilot, using the merged main code
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml run --dry-run
```

Run window: `2026-09-24T05:40:57+00:00` -> `2026-09-24T06:08:17+00:00` (~27 min).

Config highlights (full file at `/mnt/d/jobpilot/config.toml`):

- Window `window_start_month = 1`, `window_end_month = 6` (Jan-May/June);
  `allow_unknown_window = false` (unknown-window internships are discovered,
  scored and queued for review, never auto-applied), `allow_onsite_abroad = false`,
  `allow_unknown_location = false`.
- **Auto-apply OFF**: `apply.auto_apply_strong = false`, `apply.adapter = "none"`,
  no `[apply.submission.smtp]`; `--dry-run` is on top of that.
- `resume_page_limit = 1`, `resume_fit_attempts = 6` (reduces content, never
  spacing; never invents).
- `[robots]` enabled (the default), agent `jobpilot`.
- **The two widened-query config additions made for this run** (allowed config
  updates): `[sources.unstop] keywords = ["machine learning", "artificial
  intelligence", "ai", "data science", "software engineer"]` with
  `keyword_max_pages = 1`, and `[linkedin] keywords = ["machine learning intern",
  "AI intern", "data science intern", "research intern", "software engineer
  intern"]`, `max_pages = 2`, `max_results = 100`. Only the query lists were
  added/changed; no safety setting was touched.

## 2. Source coverage — every source, with per-query counts

The run reported 5 sources `ok`, 3 `failed`, 1 `skipped`, and **0 unexpected
failures** (all three failures are the robots gate working as designed):

| Source | Status | Returned | Notes |
| --- | --- | --- | --- |
| greenhouse | ok | 5895 | 30 board tokens, full content |
| lever | ok | 278 | 5 tokens |
| ashby | **failed** | 0 | `robots.txt` unreadable (HTTP 401 for every UA) -> gate fails closed |
| workable | skipped | 0 | disabled by config |
| himalayas | **failed** | 0 | `robots.txt` `Disallow: /jobs*&page=` blocks the paged search API |
| unstop | ok | 290 | generic feed + 5 `searchTerm` keyword queries (below) |
| workable_global | ok | 71 returned / 70 unique | `query=intern&location=India`, 4 pages |
| themuse | ok | 60 | typed `level=Internship` + broad `location=India` |
| linkedin | **failed** | 0 | `robots.txt` `Disallow: /` for `user-agent: *` blocks the guest reader |

`discover` dedupes by `source:job_id`, so the run's `discovered` count is **6593**.

### Unstop `searchTerm` keyword slices (the G4 fix) — per-query new counts

| Query | New postings (after dedupe) | Query error |
| --- | --- | --- |
| generic feed | 242 | none |
| `searchTerm=machine learning` | 10 | none |
| `searchTerm=artificial intelligence` | 10 | none |
| `searchTerm=ai` | 10 | none |
| `searchTerm=data science` | 8 | none |
| `searchTerm=software engineer` | 10 | none |
| **total** | **290** | 0 failures |

Every keyword query returned rows and none failed. The keyword slice adds 48
postings the generic feed did not return, and - critically - it is where the
technical matches come from (see §4).

### LinkedIn multi-query reader — NOT exercisable under the enforced gate

All five configured target queries were refused by the robots gate before any
fetch:

```
failed  linkedin: FetchError: machine learning intern: RobotsBlocked: robots gate:
DISALLOWED for jobpilot - robots.txt forbids this path; AI intern: ... ;
data science intern: ... ; research intern: ... ; software engineer intern: ...
```

Live `https://www.linkedin.com/robots.txt` ends with a `User-agent: *` group whose
only rule is `Disallow: /`, so the guest endpoint
(`/jobs-guest/jobs/api/seeMoreJobPostings/search`) is disallowed for an unknown
agent like `jobpilot`. Per-query counts are therefore all **0 / blocked**. The
widened query set itself could not be evaluated; the gate correctly wins over the
optional reader. (See §8 for the README documentation drift this exposes.)

## 3. Funnel

```
discovered ................ 6593
hard-filter survivors ..... 356   (eligible)
scored .................... 356
strong .................... 16
tailored .................. 205   (all compiled a one-page resume PDF)
queued for review ......... 205
submitted ................. 0
parseability failures ..... 0
LaTeX compile failures .... 0
cover-letter failures ..... 0
```

Per source (returned / eligible / scored / strong / tailored / queued /
submitted):

| Source | returned | eligible | scored | strong | tailored | queued | submitted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| greenhouse | 5895 | 10 | 10 | 3 | 9 | 9 | 0 |
| lever | 278 | 6 | 6 | 0 | 5 | 5 | 0 |
| themuse | 60 | 40 | 40 | 1 | 25 | 25 | 0 |
| unstop | 290 | 273 | 273 | 12 | 142 | 142 | 0 |
| workable_global | 70 | 27 | 27 | 0 | 24 | 24 | 0 |
| **total** | **6593** | **356** | **356** | **16** | **205** | **205** | **0** |


### Comparison with run-07

| Metric | run-07 | resweep-12 | Why |
| --- | --- | --- | --- |
| discovered | 7079 | 6593 | robots gate now removes Himalayas (99), Ashby (410) and LinkedIn (10); Unstop adds ~38 |
| eligible | 416 | 356 | Himalayas' 91 eligible are gone |
| strong | 4 | **16** | **Unstop keyword search adds 12 strong AI/ML/software roles** |
| tailored | 252 | 205 | fewer eligible |
| submitted | 0 | 0 | dry run, auto-apply off |

The strong band is where the payoff lands: **4 -> 16**, entirely from Unstop's
keyword slices.

## 4. Technical / AI-ML / data / research matches

```
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml present
# presented 47 technical match(es)
# excluded 155 non-technical / low-relevance queued posting(s)
# review page: /mnt/d/jobpilot/out/present/index.html
# nothing was submitted.
```

`jobpilot present` selected **47 technical matches** (0 borderline, 155
non-technical/low-relevance queued postings excluded). By source:
unstop: 39, themuse: 4, greenhouse: 3, workable_global: 1. The presented page is
`/mnt/d/jobpilot/out/present/index.html` with all 47 resumes + cover letters
copied under `out/present/assets/`.

### 4a. All 16 `strong`-band matches (full reasoning)

Observed bands and routing: band `strong` requires `score >= 0.68` **and**
`role_relevance >= 0.50`; a low-relevance high scorer is capped to `shortlist`
with an explicit reason (no non-technical internship reached `strong` this run).

| # | Score | Source | Company | Title | Location | Window evidence | Link |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.835 | greenhouse | Rubrik Job Board | Software Engineer - Winter Intern | Bangalore | Jan-5 2027 | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 2 | 0.810 | greenhouse | Rubrik Job Board | Software Engineer (CPD) - Winter Intern | Bangalore | Jan-5 2027 | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
| 3 | 0.780 | unstop | PrepLinc AI | AI/ML Application Developer Internship | Online | unknown | https://unstop.com/internships/aiml-application-developer-internship-preplinc-ai-1760453 |
| 4 | 0.761 | unstop | Pariskq | Software Engineer Internship | Bangalore, Online | unknown | https://unstop.com/internships/software-engineer-internship-pariskq-1729187 |
| 5 | 0.761 | unstop | PrepLinc AI | Data Science & Artificial Intelligence Internship | Online | unknown | https://unstop.com/internships/data-science-artificial-intelligence-internship-preplinc-ai-1760823 |
| 6 | 0.723 | unstop | Vortizo AI | Data Science Internship | Online | unknown | https://unstop.com/internships/data-science-internship-vortizo-ai-1752060 |
| 7 | 0.718 | greenhouse | Stripe | Software Engineer, Intern | Bengaluru | unknown | https://stripe.com/jobs/search?gh_jid=8031833 |
| 8 | 0.715 | themuse | Labcorp | Data Science Intern - Real World Data Strategy Team | Flexible / Remote | unknown | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |
| 9 | 0.711 | unstop | Zenotalent | Data Science Internship | Chennai, Mangaluru, Bangalore, Pune, Noida, Delhi, Kolkata, Hyderabad, Online | unknown | https://unstop.com/internships/data-science-internship-zenotalent-1755823 |
| 10 | 0.705 | unstop | godstockss | Software Engineer Internship | Online | unknown | https://unstop.com/internships/software-engineer-internship-godstockss-1731267 |
| 11 | 0.692 | unstop | TalentCV | Software Engineer Internship | Online | unknown | https://unstop.com/internships/software-engineer-intern-talentcv-1694821 |
| 12 | 0.692 | unstop | Learntricks Edutech | Machine Learning Internship | Online | unknown | https://unstop.com/internships/machine-learning-internship-unstop-tech-fair-2025-learntricks-edutech-1724312 |
| 13 | 0.690 | unstop | Learn Depth | Machine Learning Trainer Internship | Online | unknown | https://unstop.com/internships/machine-learning-trainer-internship-learn-depth-1735074 |
| 14 | 0.689 | unstop | Maytrixtech | Software Engineer Internship | Online | unknown | https://unstop.com/internships/software-engineer-internship-maytrixtech-1733361 |
| 15 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Engineer Internship | Bangalore, Chennai, Online | unknown | https://unstop.com/internships/machine-learning-engineer-internship-skillorbit-private-limited-1752362 |
| 16 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Internship | Bangalore, Online | unknown | https://unstop.com/internships/machine-learning-intern-skillorbit-private-limited-1759582 |


**1. Rubrik Job Board — Software Engineer - Winter Intern** (score 0.835, greenhouse)

- skill coverage 80% (4/5 JD terms supported by profile)
- role relevance 0.70 (ai_ml=0.00, software=0.70, research=0.00)
- location fit 1.00: location is in India
- window fit 1.00: explicit range Jan-5 2027
- seniority fit 1.00: internship
- gaps (never inserted): Fine-tuning
- supported JD terms: Java, C++, Python, Security

**2. Rubrik Job Board — Software Engineer (CPD) - Winter Intern** (score 0.810, greenhouse)

- skill coverage 80% (4/5 JD terms supported by profile)
- role relevance 0.60 (ai_ml=0.00, software=0.60, research=0.00)
- location fit 1.00: location is in India
- window fit 1.00: explicit range Jan-5 2027
- seniority fit 1.00: internship
- gaps (never inserted): Fine-tuning
- supported JD terms: Java, C++, Python, Security

**3. PrepLinc AI — AI/ML Application Developer Internship** (score 0.780, unstop)

- skill coverage 100% (5/5 JD terms supported by profile)
- role relevance 0.70 (ai_ml=0.70, software=0.10, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- supported JD terms: Machine Learning, React, Node.js, JavaScript, LLMs

**4. Pariskq — Software Engineer Internship** (score 0.761, unstop)

- skill coverage 68% (17/25 JD terms supported by profile)
- role relevance 0.90 (ai_ml=0.40, software=0.90, research=0.00)
- location fit 1.00: location is in India
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): TypeScript, AWS, CI/CD, Model Deployment, REST APIs, Linux, NLP, Computer Vision
- supported JD terms: React, Node.js, JavaScript, Python, PostgreSQL, Evaluation, Machine Learning, Automation, Generative AI, Security, Java, C++

**5. PrepLinc AI — Data Science & Artificial Intelligence Internship** (score 0.761, unstop)

- skill coverage 85% (11/13 JD terms supported by profile)
- role relevance 0.90 (ai_ml=0.90, software=0.20, research=0.10)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Data Science, Deep Learning
- supported JD terms: Python, SQL, Machine Learning, LLMs, Prompt Engineering, RAG, Data Visualization, Statistics, pandas, NumPy, Scikit-learn

**6. Vortizo AI — Data Science Internship** (score 0.723, unstop)

- skill coverage 82% (9/11 JD terms supported by profile)
- role relevance 0.80 (ai_ml=0.80, software=0.20, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Data Science, Problem Solving
- supported JD terms: Evaluation, Machine Learning, Communication, Statistics, Python, pandas, NumPy, Scikit-learn, SQL

**7. Stripe — Software Engineer, Intern** (score 0.718, greenhouse)

- skill coverage 75% (3/4 JD terms supported by profile)
- role relevance 0.60 (ai_ml=0.00, software=0.60, research=0.10)
- location fit 1.00: location is in India
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Research
- supported JD terms: Communication, Java, JavaScript

**8. Labcorp — Data Science Intern - Real World Data Strategy Team** (score 0.715, themuse)

- skill coverage 80% (4/5 JD terms supported by profile)
- role relevance 0.80 (ai_ml=0.80, software=0.20, research=0.00)
- location fit 0.50: location 'Flexible / Remote' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Data Science
- supported JD terms: Machine Learning, Statistics, Python, SQL

**9. Zenotalent — Data Science Internship** (score 0.711, unstop)

- skill coverage 62% (5/8 JD terms supported by profile)
- role relevance 0.80 (ai_ml=0.80, software=0.10, research=0.00)
- location fit 1.00: location is in India
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Data Science, Data Analysis, Problem Solving
- supported JD terms: Machine Learning, Evaluation, Communication, Statistics, Python

**10. godstockss — Software Engineer Internship** (score 0.705, unstop)

- skill coverage 78% (7/9 JD terms supported by profile)
- role relevance 0.80 (ai_ml=0.00, software=0.80, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): REST APIs, Problem Solving
- supported JD terms: Data Scraping, Python, Node.js, JavaScript, Automation, HTML/CSS, Communication

**11. TalentCV — Software Engineer Internship** (score 0.692, unstop)

- skill coverage 69% (9/13 JD terms supported by profile)
- role relevance 0.90 (ai_ml=0.00, software=0.90, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Agile, Model Deployment, REST APIs, Problem Solving
- supported JD terms: Python, JavaScript, React, Java, C++, HTML/CSS, Git, SQL, Communication

**12. Learntricks Edutech — Machine Learning Internship** (score 0.692, unstop)

- skill coverage 69% (9/13 JD terms supported by profile)
- role relevance 0.90 (ai_ml=0.90, software=0.10, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Algorithms, TensorFlow, Data Analysis, Problem Solving
- supported JD terms: Machine Learning, Evaluation, Communication, Python, Scikit-learn, PyTorch, Data Visualization, pandas, Matplotlib

**13. Learn Depth — Machine Learning Trainer Internship** (score 0.690, unstop)

- skill coverage 80% (8/10 JD terms supported by profile)
- role relevance 0.70 (ai_ml=0.70, software=0.10, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Algorithms, Data Analysis
- supported JD terms: Machine Learning, Python, NumPy, pandas, Data Visualization, Evaluation, Scikit-learn, Communication

**14. Maytrixtech — Software Engineer Internship** (score 0.689, unstop)

- skill coverage 69% (11/16 JD terms supported by profile)
- role relevance 0.90 (ai_ml=0.30, software=0.90, research=0.00)
- location fit 0.50: location 'Online' is not confirmably open to India; review before applying
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Model Deployment, Problem Solving, REST APIs, Agile, Data Science
- supported JD terms: Machine Learning, Communication, Python, Java, JavaScript, React, Node.js, Git, SQL, Data Visualization, Statistics

**15. Skillorbit Private Limited — Machine Learning Engineer Internship** (score 0.680, unstop)

- skill coverage 56% (5/9 JD terms supported by profile)
- role relevance 0.80 (ai_ml=0.80, software=0.30, research=0.00)
- location fit 1.00: location is in India
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Data Science, Algorithms, Data Analysis, TensorFlow
- supported JD terms: Machine Learning, Statistics, Python, Flask, Docker

**16. Skillorbit Private Limited — Machine Learning Internship** (score 0.680, unstop)

- skill coverage 50% (5/10 JD terms supported by profile)
- role relevance 0.90 (ai_ml=0.90, software=0.00, research=0.10)
- location fit 1.00: location is in India
- window fit 0.30: no timing signal found
- seniority fit 1.00: internship
- gaps (never inserted): Research, Algorithms, Problem Solving, Data Science, Data Analysis
- supported JD terms: Machine Learning, Evaluation, Statistics, Communication, Predictive Modeling

### 4b. The 47 presented technical matches

| # | Score | Source | Company | Title | Location | Window | Tech domain | Route |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.835 | greenhouse | Rubrik Job Board | Software Engineer - Winter Intern | Bangalore | Jan-5 2027 | software (0.70) | Review-only (auto-apply off) |
| 2 | 0.810 | greenhouse | Rubrik Job Board | Software Engineer (CPD) - Winter Intern | Bangalore | Jan-5 2027 | software (0.60) | Review-only (auto-apply off) |
| 3 | 0.780 | unstop | PrepLinc AI | AI/ML Application Developer Internship | Online | unknown | ai_ml (0.70) | Review-only (auto-apply off) |
| 4 | 0.761 | unstop | Pariskq | Software Engineer Internship | Bangalore, Online | unknown | software (0.90) | Review-only (auto-apply off) |
| 5 | 0.761 | unstop | PrepLinc AI | Data Science & Artificial Intelligence Internship | Online | unknown | ai_ml (0.90) | Review-only (auto-apply off) |
| 6 | 0.723 | unstop | Vortizo AI | Data Science Internship | Online | unknown | ai_ml (0.80) | Review-only (auto-apply off) |
| 7 | 0.718 | greenhouse | Stripe | Software Engineer, Intern | Bengaluru | unknown | software (0.60) | Review-only (auto-apply off) |
| 8 | 0.715 | themuse | Labcorp | Data Science Intern - Real World Data Strategy Team | Flexible / Remote | unknown | ai_ml (0.80) | Review-only (auto-apply off) |
| 9 | 0.711 | unstop | Zenotalent | Data Science Internship | Chennai, Mangaluru, Bangalore, Pune, Noida, Delhi, Kolkata, Hyderabad, Online | unknown | ai_ml (0.80) | Review-only (auto-apply off) |
| 10 | 0.705 | unstop | godstockss | Software Engineer Internship | Online | unknown | software (0.80) | Review-only (auto-apply off) |
| 11 | 0.692 | unstop | Learntricks Edutech | Machine Learning Internship | Online | unknown | ai_ml (0.90) | Review-only (auto-apply off) |
| 12 | 0.692 | unstop | TalentCV | Software Engineer Internship | Online | unknown | software (0.90) | Review-only (auto-apply off) |
| 13 | 0.690 | unstop | Learn Depth | Machine Learning Trainer Internship | Online | unknown | ai_ml (0.70) | Review-only (auto-apply off) |
| 14 | 0.689 | unstop | Maytrixtech | Software Engineer Internship | Online | unknown | software (0.90) | Review-only (auto-apply off) |
| 15 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Internship | Bangalore, Online | unknown | ai_ml (0.90) | Review-only (auto-apply off) |
| 16 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Engineer Internship | Bangalore, Chennai, Online | unknown | ai_ml (0.80) | Review-only (auto-apply off) |
| 17 | 0.680 | unstop | Operonn | AI Engineer Internship | Online | unknown | ai_ml (0.90) | Review-only |
| 18 | 0.673 | unstop | BluMotiv | Software Engineer Internship | Online | unknown | software (0.90) | Review-only |
| 19 | 0.667 | unstop | Vision AI Learning | Curriculum Developer – Artificial Intelligence Internship | Bharatpur, Online | unknown | ai_ml (0.70) | Review-only |
| 20 | 0.661 | themuse | The Muse | AI Engineer – Remote Internship | Flexible / Remote | unknown | ai_ml (0.90) | Review-only |
| 21 | 0.655 | unstop | Sai Silks Kalamandir | RAG & Machine Learning Internship | Hyderabad, Online | unknown | ai_ml (0.80) | Review-only |
| 22 | 0.655 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship  | Bangalore Urban, Online | unknown | ai_ml (0.90) | Review-only |
| 23 | 0.650 | unstop | Embolo Technologies Private Limited | Software Engineer Internship | Chandigarh, Online | unknown | software (0.90) | Review-only |
| 24 | 0.643 | unstop | JobLuxe | Software Engineer Internship | Online | unknown | software (0.60) | Review-only |
| 25 | 0.637 | unstop | Newton School | Academic Internship (Data Science) | Bangalore, Online | unknown | ai_ml (0.60) | Review-only |
| 26 | 0.625 | unstop | Skill Orbit | Artificial Intelligence Internship | Online | unknown | ai_ml (0.80) | Review-only |
| 27 | 0.625 | themuse | The Muse | Data Engineer – Remote Internship | Flexible / Remote | unknown | software (0.80) | Review-only |
| 28 | 0.623 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | Hyderabad, Online | unknown | ai_ml (0.80) | Review-only |
| 29 | 0.605 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | Hyderabad, Online | unknown | ai_ml (0.90) | Review-only |
| 30 | 0.600 | unstop | Zenotalent | Data Science Internship | Online | unknown | ai_ml (0.70) | Review-only |
| 31 | 0.600 | themuse | Atlassian | Research Intern, 2026 Summer U.S. | Flexible / Remote, Seattle, WA | Jun-Aug 2026 | research (0.60) | Review-only |
| 32 | 0.586 | unstop | Kukbit SL | Machine Learning Internship | Online | unknown | ai_ml (0.60) | Review-only |
| 33 | 0.585 | unstop | Skillorbit Academy | Artificial Intelligence Internship | Bangalore, Online | unknown | ai_ml (0.70) | Review-only |
| 34 | 0.573 | unstop | Zenotalent | Machine Learning Internship | Online | unknown | ai_ml (0.90) | Review-only |
| 35 | 0.560 | unstop | Vortizo AI | Machine Learning Internship | Online | unknown | ai_ml (0.90) | Review-only |
| 36 | 0.560 | unstop | IntelleQAcademy | Generative AI Internship | Online | unknown | ai_ml (0.90) | Review-only |
| 37 | 0.555 | unstop | Aalteon | Artificial Intelligence Internship | Online | unknown | ai_ml (0.70) | Review-only |
| 38 | 0.555 | unstop | IntelleQAcademy | Data Science and ML Internship | Online | unknown | ai_ml (0.70) | Review-only |
| 39 | 0.535 | unstop | Aalteon | Artificial Intelligence Internship | Online | unknown | ai_ml (0.80) | Review-only |
| 40 | 0.530 | unstop | Yelow Payments Private Limited | Market Research Internship | Online | unknown | research (0.60) | Review-only |
| 41 | 0.530 | unstop | Zenotalent | Data Science Internship | Online | unknown | ai_ml (0.60) | Review-only |
| 42 | 0.530 | unstop | Airkrit India Pvt. Ltd. | Data Science Internship | Online | unknown | ai_ml (0.60) | Review-only |
| 43 | 0.505 | workable_global | Blue Machines AI | Evaluation & Insights Intern, AI Delivery | Bengaluru, Karnataka, India | unknown | ai_ml (0.50) | Review-only |
| 44 | 0.480 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship | Online | unknown | ai_ml (0.70) | Review-only |
| 45 | 0.455 | unstop | Skillorbit Private Limited | Machine Learning Internship | Online | unknown | ai_ml (0.60) | Review-only |
| 46 | 0.455 | unstop | Digital Back Office | Software Engineer Internship | Abrama, Online | unknown | software (0.60) | Review-only |
| 47 | 0.443 | unstop | Qveto | Data Science and Machine Learning Internship | Online | unknown | ai_ml (0.70) | Review-only |


### 4c. AI/ML-domain matches (best domain `ai_ml`), with links

| # | Score | Source | Company | Title | Location | Window | Link |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.780 | unstop | PrepLinc AI | AI/ML Application Developer Internship | Online | unknown | https://unstop.com/internships/aiml-application-developer-internship-preplinc-ai-1760453 |
| 2 | 0.761 | unstop | PrepLinc AI | Data Science & Artificial Intelligence Internship | Online | unknown | https://unstop.com/internships/data-science-artificial-intelligence-internship-preplinc-ai-1760823 |
| 3 | 0.723 | unstop | Vortizo AI | Data Science Internship | Online | unknown | https://unstop.com/internships/data-science-internship-vortizo-ai-1752060 |
| 4 | 0.715 | themuse | Labcorp | Data Science Intern - Real World Data Strategy Team | Flexible / Remote | unknown | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |
| 5 | 0.711 | unstop | Zenotalent | Data Science Internship | Chennai, Mangaluru, Bangalore, Pune, Noida, Delhi, Kolkata, Hyderabad, Online | unknown | https://unstop.com/internships/data-science-internship-zenotalent-1755823 |
| 6 | 0.692 | unstop | Learntricks Edutech | Machine Learning Internship | Online | unknown | https://unstop.com/internships/machine-learning-internship-unstop-tech-fair-2025-learntricks-edutech-1724312 |
| 7 | 0.690 | unstop | Learn Depth | Machine Learning Trainer Internship | Online | unknown | https://unstop.com/internships/machine-learning-trainer-internship-learn-depth-1735074 |
| 8 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Internship | Bangalore, Online | unknown | https://unstop.com/internships/machine-learning-intern-skillorbit-private-limited-1759582 |
| 9 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Engineer Internship | Bangalore, Chennai, Online | unknown | https://unstop.com/internships/machine-learning-engineer-internship-skillorbit-private-limited-1752362 |
| 10 | 0.680 | unstop | Operonn | AI Engineer Internship | Online | unknown | https://unstop.com/internships/ai-engineer-internship-operonn-1755613 |
| 11 | 0.667 | unstop | Vision AI Learning | Curriculum Developer – Artificial Intelligence Internship | Bharatpur, Online | unknown | https://unstop.com/internships/curriculum-developer-artificial-intelligence-internship-vision-ai-learning-1759335 |
| 12 | 0.661 | themuse | The Muse | AI Engineer – Remote Internship | Flexible / Remote | unknown | https://www.themuse.com/jobs/themuse/ai-engineer-remote-internship |
| 13 | 0.655 | unstop | Sai Silks Kalamandir | RAG & Machine Learning Internship | Hyderabad, Online | unknown | https://unstop.com/internships/rag-machine-learning-internship-sai-silks-kalamandir-1733553 |
| 14 | 0.655 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship  | Bangalore Urban, Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-skillorbit-private-limited-1758984 |
| 15 | 0.637 | unstop | Newton School | Academic Internship (Data Science) | Bangalore, Online | unknown | https://unstop.com/internships/academic-internship-data-science-newton-school-1752360 |
| 16 | 0.625 | unstop | Skill Orbit | Artificial Intelligence Internship | Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-skill-orbit-1756034 |
| 17 | 0.623 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | Hyderabad, Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-xtragrad-technologie-private-limited-1754902 |
| 18 | 0.605 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | Hyderabad, Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-xtragrad-technologie-private-limited-1747534 |
| 19 | 0.600 | unstop | Zenotalent | Data Science Internship | Online | unknown | https://unstop.com/internships/data-science-internship-zenotalent-1748389 |
| 20 | 0.586 | unstop | Kukbit SL | Machine Learning Internship | Online | unknown | https://unstop.com/internships/machine-learning-internship-kukbit-sl-1751307 |
| 21 | 0.585 | unstop | Skillorbit Academy | Artificial Intelligence Internship | Bangalore, Online | unknown | https://unstop.com/internships/artificial-intelligence-intern-skillorbit-academy-1750189 |
| 22 | 0.573 | unstop | Zenotalent | Machine Learning Internship | Online | unknown | https://unstop.com/internships/machine-learning-internship-zenotalent-1749292 |
| 23 | 0.560 | unstop | Vortizo AI | Machine Learning Internship | Online | unknown | https://unstop.com/internships/machine-learning-internship-vortizo-ai-1744336 |
| 24 | 0.560 | unstop | IntelleQAcademy | Generative AI Internship | Online | unknown | https://unstop.com/internships/generative-ai-internship-intelleqacademy-1751495 |
| 25 | 0.555 | unstop | Aalteon | Artificial Intelligence Internship | Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-aalteon-1758771 |
| 26 | 0.555 | unstop | IntelleQAcademy | Data Science and ML Internship | Online | unknown | https://unstop.com/internships/data-science-and-ml-internship-intelleqacademy-1751493 |
| 27 | 0.535 | unstop | Aalteon | Artificial Intelligence Internship | Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-aalteon-1742163 |
| 28 | 0.530 | unstop | Zenotalent | Data Science Internship | Online | unknown | https://unstop.com/internships/data-science-internship-zenotalent-1760539 |
| 29 | 0.530 | unstop | Airkrit India Pvt. Ltd. | Data Science Internship | Online | unknown | https://unstop.com/internships/data-science-internship-airkrit-india-pvt-ltd-1749446 |
| 30 | 0.505 | workable_global | Blue Machines AI | Evaluation & Insights Intern, AI Delivery | Bengaluru, Karnataka, India | unknown | https://jobs.workable.com/view/hYkVydG3ua3RuasU6CTiMw/evaluation-%26-insights-intern%2C-ai-delivery-in-bengaluru-at-blue-machines-ai |
| 31 | 0.480 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship | Online | unknown | https://unstop.com/internships/artificial-intelligence-internship-skillorbit-private-limited-1748852 |
| 32 | 0.455 | unstop | Skillorbit Private Limited | Machine Learning Internship | Online | unknown | https://unstop.com/internships/machine-learning-internship-skillorbit-private-limited-1758836 |
| 33 | 0.443 | unstop | Qveto | Data Science and Machine Learning Internship | Online | unknown | https://unstop.com/internships/data-science-and-machine-learning-internship-qveto-1747163 |


### 4d. What is new from Unstop or LinkedIn vs run-07

- **Unstop: heavily yes.** The previous run's generic feed produced **no** AI/ML
  internship in 300 rows (gap G4). With the keyword slices now on, Unstop
  contributes **39 of the 47 presented technical matches**
  (including 30 whose best domain is `ai_ml`) and **12 of the 16
  strong roles** - e.g. PrepLinc AI (AI/ML Developer, Data Science & AI),
  Vortizo AI (Data Science, ML), Learntricks (ML), Learn Depth (ML Trainer),
  Skillorbit (ML, ML Engineer, AI), Operonn (AI Engineer), IntelleQAcademy
  (Generative AI), Aalteon/Xtragrad (AI). None of these appeared in run-07.
- **LinkedIn: cannot say - blocked.** In run-07 the single-query reader returned
  10 non-technical listings (0 AI/ML). In this run the enforced robots gate
  refuses the guest path, so the widened query set returned **0 postings**. No
  LinkedIn match exists to report, by design of the gate, not by a source change.
- **Himalayas: cannot say - blocked.** Run-07's single best automated AI/ML
  source (Drivetrain Gen-AI, Mactores, Tether, Ritual) is now refused by its own
  `Disallow: /jobs*&page=`. This is the intended robots behaviour, documented in
  the README.
- The new technical matches not from Unstop are the ones run-07 already had:
  Rubrik (x2), Stripe, Labcorp, The Muse AI/Data Engineer, and Workable global's
  Blue Machines AI (Bengaluru).

## 5. Explicit Jan-Jun window vs unknown

Of the **205 tailored/queued** postings:

| Window label | Count |
| --- | --- |
| unknown | 180 |
| Summer (season, conf 0.6) | 11 |
| Jan-May 2027 (`Jan-5 2027`; label render quirk, see §8) | 3 |
| Dec-Jun 2027 | 2 |
| Dec-Jun 2026 | 2 |
| Summer 2025 / Mar-Mar 2024 / Mar-Mar 2023 / Jun-Aug 2026 / Jan-Aug / Dec-Feb / 5-5 2023 | 1 each |

- **14 of the 16 `strong` matches have no timing signal** and
  are correctly review-only for an unconfirmed window. The only explicit
  Jan-May strong matches are Rubrik's two winter interns, whose window is
  **Jan-May 2027** (`Jan-5 2027`, confidence 1.0).
- Among the **47 presented technical matches**, only **3** carry a window at all
  (Rubrik x2 `Jan-May 2027`; Atlassian `Jun-Aug 2026`, and Atlassian is a US
  research role - research-guarded and location-loose). The other 44 are
  unknown-window and are surfaced for human review rather than applied.
- The window rule is doing exactly its job: nearly every AI/ML posting states no
  dates, so nothing in-window-but-unverified is auto-applied.

## 6. Deadlines surfaced (display only, never a filter)

The new deadline extraction stored a deadline on **8 postings**; none of them is
one of the technical matches, and only one is not already expired:

| Source | Company | Title | Deadline | Label | Published | Shortlisted? |
| --- | --- | --- | --- | --- | --- | --- |
| unstop | Emertxe | Campus Ambassador Program - Internship Opportunity for Engineering Students | 2023-02-23 | 2023-02-23 (expired) | 2023-01-30 15:34:54 GMT+0530 | no |
| unstop | Net Impact, Delhi University | Impact Consultancy and Capability Internship | 2023-05-03 | 2023-05-03 (expired) | 2023-04-28 11:29:11 GMT+0530 | no |
| unstop | Net Impact, Delhi University | Content Marketing and Strategy Internship | 2023-05-03 | 2023-05-03 (expired) | 2023-04-28 11:55:39 GMT+0530 | yes |
| unstop | Net Impact, Delhi University | Content Creation / Writer Internship | 2024-03-05 | 2024-03-05 (expired) | 2024-02-29 11:50:30 GMT+0530 | yes |
| unstop | Net Impact, Delhi University | Impact Consultancy and Capabilities Membership | 2024-03-05 | 2024-03-05 (expired) | 2024-02-29 12:03:15 GMT+0530 | no |
| unstop | Net Impact, Delhi University | Social Media Marketing Internship | 2024-03-05 | 2024-03-05 (expired) | 2024-02-28 17:43:08 GMT+0530 | no |
| themuse | PCORI | Spring Intern 2025 - EDI, Public and Patient Engagement | 2025-02-01 | 2025-02-01 (expired) | 2025-01-29T12:59:01Z | no |
| greenhouse | Stripe | Account Executive, Platforms (Existing Business) | 2026-09-30 | 2026-09-30 (closing soon) | 2026-01-29T23:56:00-05:00 | no |


- **7 are expired** (2023-2025 `Unstop`/`The Muse` rows, all stale by 600-1300
  days).
- **1 is closing soon**: Stripe - Account Executive, Platforms
  (`2026-09-30`, 6 days out) - but it is **ineligible** (Sydney, Australia; not
  an internship) and was never tailored.
- **No shortlisted or tailored technical match carries a deadline**, so deadline
  tracking changed nothing about what is ready to apply to - it only adds a
  "closing soon"/"expired" badge where a date exists.

## 7. Tailored artifacts - one page, verified

- **205/205 resumes compiled and measured at exactly 1 page**, verified
  independently of the store by form feeds in the `pdftotext` output:
  `{"1": 205}`, zero extraction failures, zero store mismatches. (`/Type /Page`
  or `/Count` was never used.)
- Store agrees: `resume_pages = 1`, `resume_page_limit = 1` for all 205.
- **205/205 parseable** (`parseability_ok = 1`), 0 parseability failures, 0 LaTeX
  compile failures.
- **205/205 cover-letter PDFs exist** - the run-07 non-ASCII cover-letter defect
  (G3) did not recur: the merged `latex_safe_text` rendering means non-Latin
  titles no longer crash the compile.
- **0 resumes were flagged for review** for a page/parseability/no-invention
  reason (0 such rows). Every one of the 205 queued reasons is a window
  (180), band (23) or config (2) reason.
- The presentation page shows a `Resume: 1-page ✓` badge on all **47/47** cards;
  0 warning badges; 47 resume PDFs and 47 cover-letter PDFs copied into
  `out/present/assets/`.
- Packet example (Rubrik SWE - Winter Intern):
  `/mnt/d/jobpilot/out/review/greenhouse-Rubrik-Job-Board-Software-Engineer----87fad9533f/`
  (`resume.tex`, `resume.pdf`, `cover_letter.tex`, `cover_letter.pdf`).
- No-invention invariant held: unsupported JD terms appear only as gaps and were
  never inserted (e.g. Rubrik's `Fine-tuning`, PrepLinc's `Deep Learning`).

## 8. Defects and unexpected behaviour (exact command + error)

### D1. (REPORTED, not run-blocking) LinkedIn's robots.txt makes the optional reader dead under the enforced gate

- **Command:** `python3 -m jobpilot --config /mnt/d/jobpilot/config.toml run --dry-run`
- **Error:** `failed  linkedin: FetchError: machine learning intern: RobotsBlocked:
  robots gate: DISALLOWED for jobpilot - robots.txt forbids this path; ...`
- **Evidence:** live `https://www.linkedin.com/robots.txt` has a `User-agent: *`
  group with `Disallow: /`. The README's robots table (dated 2026-09-24) lists
  LinkedIn as "readable, permits the path", which is **incorrect** - the reader
  can never run with the gate on for the default `jobpilot` agent. This is
  documentation drift in `README.md`, not a code bug; no fix applied (the task
  authorises fixes only for a run-blocking defect, and this run did not block).
  The safe behaviour (gate wins over the ToS-questionable reader) is correct.

### D2. (REPORTED, not run-blocking) Himalayas widening is unreachable by design

- **Error:** `failed  himalayas: FetchError: typed: page 1: robots gate:
  DISALLOWED for jobpilot - robots.txt forbids this path; intern: page 1: ...`
- The widened typed + keyword query logic cannot run because every
  `himalayas.app/jobs/api/search?...&page=N` request matches its published
  `Disallow: /jobs*&page=`. The README already documents this as intended; it is
  surfaced here because it is why the best run-07 AI/ML source contributes
  nothing now.

### D3. (minor, cosmetic) Window label renders May as `5`

- `window._label` picks a month name key with `len > 3`; `"may"` is length 3, so
  an explicit Jan-May range renders `Jan-5 2027` instead of `Jan-May 2027`. The
  classification and confidence are correct (`Jan-May 2027` = Jan-May, conf 1.0);
  only the display string is ugly. No fix applied.

### D4. (minor) `workable_global` returned 71 rows but stores 70 unique

- The adapter returned 71; `discover` dedupes by `source:job_id`, so 70 unique
  rows are stored. Harmless.

### D5. (minor, present-selection quirk) A market-research role passed the guarded `research` domain

- `Yelow Payments - Market Research Internship` (Unstop, score 0.53) is presented
  as a technical `research` match because it matches a `core_skills` term
  (Statistics). It is review-only and low-score; the guard is working as coded,
  but "market research + Statistics" is a false positive of the intended
  "research only when a core technical skill is present" rule.

No errors occurred that blocked the run; there were no compile, parseability or
submission errors.

## 9. Honest diagnosis - did the widened sources help?

**Yes, but through Unstop only; Himalayas and LinkedIn are correctly off the
table.** Precisely:

- The single biggest win is the **Unstop `searchTerm` path** (run-07's gap G4):
  12 of 16 strong and 39 of 47 presented technical matches come from it, all
  from the India-native Unstop platform (many listed simply as "Online"). That
  is the change that answers "what does the tool find now".
- **Himalayas**, run-07's best automated AI/ML source, is now refused by its own
  robots policy; its widening is unreachable. That is intended and safe, but it
  is why eligible/tailored counts fell (416 -> 356; 252 -> 205).
- **LinkedIn** cannot be evaluated: the enforced robots gate refuses the guest
  path. The widened query set is not the reason it returns nothing.
- **Ashby** remains unfetchable (robots 401), as documented.
- The residual scarcity is genuine coverage: outside Unstop, India-eligible
  AI/ML internships with a stated Jan-Jun window remain rare. The window rule
  correctly keeps the unknown-window AI/ML flood in review rather than applying.

## 10. `jobpilot upskill` — top skill gaps across the postings found

```
 #  skill                            jobs  weight  source
--  -------------------------------- ----  ------  ------------
 1  Research                          108   66.39  application,posting
 2  Problem Solving                    86   46.09  application,posting
 3  Data Analysis                      57   30.82  application,posting
 4  Data Science                       20    7.84  application
 5  Model Deployment                   15    7.19  application,posting
 6  Computer Vision                    11    7.06  application,posting
 7  Algorithms                         16    6.29  application,posting
 8  Agile                              11    5.25  application,posting
 9  REST APIs                          13    5.19  application,posting
10  TensorFlow                          6    2.27  application
11  AWS                                 6    2.21  application
12  Azure                               4    1.90  application
13  Deep Learning                       4    1.37  application
14  TypeScript                          4    1.27  application
15  Fine-tuning                         4    1.17  application
16  CI/CD                               3    1.17  application,posting
17  Linux                               2    0.56  application
18  Data Engineering                    1    0.38  application
19  NLP                                 1    0.24  application
```

## 11. Zero-submission verification (from the run's own record)

- run `mode = dry_run`; `stats.submitted = 0`.
- `applications`: **205 rows, all `status = manual_required`; 0 `submitted`**.
- `attempts`: **empty (0 rows)** - no submission was ever attempted.
- `review_queue`: 205 rows, all `pending`.
- CLI printed `dry run: nothing was submitted.`

## 12. What the captain can actually apply to

- **Most actionable, in-window, India:** **Rubrik - Software Engineer (Winter
  Intern)** and **Rubrik - Software Engineer (CPD) (Winter Intern)**, Bangalore,
  explicit **Jan-May 2027**, strong band (0.835 / 0.810). They are review-only
  solely because `auto_apply_strong = false`; with a public apply link they are
  one click each.
  - https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523
  - https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537
- **Strong AI/ML/data, window unconfirmed (verify dates first):** Stripe SWE
  Intern (Bengaluru), Labcorp Data Science (remote/US-loose), and the 12 Unstop
  strong roles (PrepLinc AI, Vortizo AI, Skillorbit, Learntricks, Learn Depth,
  Operonn, ...). All are queued review-only for an unconfirmed window; the
  packets are ready.
- **Everything else** (the other 155 excluded / 44 unknown-window presented
  technical matches) is browseable on `out/present/index.html` with tailored
  resumes and cover letters attached, badge-verified one-page.

## 13. Verdict

The full merged pipeline ran end to end in dry-run mode: **6593 discovered, 356
eligible, 16 strong, 205 tailored (205/205 measured one page, 205/205 parseable,
205/205 cover letters), 205 queued, 0 submitted**. The restored Unstop
`searchTerm` keyword path is the payoff: it took the strong band from 4 to 16 and
produced 39 of the 47 presented technical matches from the India-native Unstop
platform (many listed simply as "Online"). The two
explicitly Jan-May, India-based strong matches (Rubrik x2) are the clearest
apply-now targets. The enforced robots gate correctly removed Himalayas, LinkedIn
and Ashby; that cost coverage but is the intended safety behaviour, and the
LinkedIn README table should be corrected in a normal change.
