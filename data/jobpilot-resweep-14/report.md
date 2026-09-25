# jobpilot full resweep — report (jobpilot-resweep-14)

Date: 2026-09-25. Operator: crewmate (firstmate-managed). Mode: **dry run only,
zero submissions**. Config: `/mnt/d/jobpilot/config.toml` (captain's copy,
untracked). Code: commit `ba78d2c` (the merged `main` in `/mnt/d/jobpilot`,
including the Himalayas first-page-only fix from PR #11). Run executed from
`/mnt/d/jobpilot`. Machine-readable record:
`/mnt/d/jobpilot/data/jobpilot-resweep-14/run.json`, full CLI log
`run.log`, `present.log`, `upskill.log` in the same directory.

This run answers the captain's two changes since resweep-12: **Himalayas is
reachable again via a robots-compliant first-page-only fetch**, and **the master
profile changed** (CSIR-NAL added, Astro Deus removed, project description
lines, two repos public). Both effects were verified by measurement, not
assertion. The headline: Himalayas is contributing again, but the profile edit
has a **real, measurable regression** — the tailored resumes no longer emit a
`Projects` section, and that trips the parseability safety check on 38 of 234
resumes (15 of the 46 presented cards). Details in §7.

The previous run's artifacts were preserved before this run started, so this
run's store and page are unambiguous:

- old store -> `/mnt/d/jobpilot/jobpilot-resweep-12.db` (it held resweep-12 run 1
  plus a later profile-updated re-tailor, run 2)
- old run tree -> `/mnt/d/jobpilot/out-resweep-12/`
  (`out-run-04/`, `out-run-07/`, `out-run-07-prelinkedin/` are unchanged.)

## 1. What was run

```
# from /mnt/d/jobpilot, using the merged main code (ba78d2c)
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml run --dry-run
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml present
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml upskill
```

Run window: `2026-09-25T01:53:33+00:00` -> `2026-09-25T02:34:29+00:00` (~41 min;
slower than resweep-12's 27 min, with 234 vs 205 resumes to compile).

Config unchanged from resweep-12 and still safe:

- Window `window_start_month = 1`, `window_end_month = 6` (Jan-May/June);
  `allow_unknown_window = false`, `allow_onsite_abroad = false`,
  `allow_unknown_location = false`.
- **Auto-apply OFF**: `apply.auto_apply_strong = false`, `apply.adapter = "none"`,
  no `[apply.submission.smtp]`, plus `--dry-run`.
- `resume_page_limit = 1`, `resume_fit_attempts = 6`.
- `[robots]` enabled (default), agent `jobpilot`.

## 2. Source coverage — every source, with per-query counts

6 sources `ok`, 2 `failed`, 1 `skipped`, **0 unexpected failures** (both
failures are the robots gate working as designed):

| Source | Status | Returned | Notes |
| --- | --- | --- | --- |
| greenhouse | ok | 5903 | 30 board tokens, full content |
| lever | ok | 276 | 5 tokens |
| ashby | **failed** | 0 | `robots.txt` unreadable (HTTP 401 for every UA) -> gate fails closed |
| workable | skipped | 0 | disabled by config |
| **himalayas** | **ok** | **34** | **first page only, no `page` param; typed `employment_type=Intern&country=India` + `q=intern` merged/deduped** |
| unstop | ok | 285 | generic feed + 5 `searchTerm` keyword queries (below) |
| workable_global | ok | 68 returned / 67 stored | `query=intern&location=India`, 4 pages |
| themuse | ok | 60 | typed `level=Internship` + broad `location=India` |
| linkedin | **failed** | 0 | `robots.txt` `Disallow: /` for `user-agent: *` blocks the guest reader |

`discover` dedupes by `source:job_id`, so the run's `discovered` count is
**6625** (the 68→67 drop is one repeated stable_id inside workable_global's
result set).

### Himalayas is contributing again — verified live, not asserted

The adapter was exercised directly while recording the concrete request URLs
(with the real robots gate installed):

```
requests:
  https://himalayas.app/jobs/api/search?country=India&employment_type=Intern
  https://himalayas.app/jobs/api/search?country=India&q=intern
any page= param: False
any &page: False
```

Exactly **two** requests (the typed slice plus the `q=intern` broader query),
**neither carries a `page` parameter**, and the adapter returned **34 postings**
this run. The first page of each query is the only page requested; the paged
path (`Disallow: /jobs*&page=`) is never requested. Live
`https://himalayas.app/robots.txt` still carries `Allow: /` plus the
`Disallow: /jobs*&page=` family, so the first-page search path is permitted and
the gate admits it. **Himalayas is back.**

### Unstop `searchTerm` keyword slices — per-query new counts

| Query | New postings (after dedupe) | Query error |
| --- | --- | --- |
| generic feed | 239 | none |
| `searchTerm=machine learning` | 10 | none |
| `searchTerm=artificial intelligence` | 10 | none |
| `searchTerm=ai` | 10 | none |
| `searchTerm=data science` | 6 | none |
| `searchTerm=software engineer` | 10 | none |
| **total** | **285** | 0 failures |

### LinkedIn — still not exercisable under the enforced gate

All five configured target queries were refused before any fetch:

```
failed  linkedin: FetchError: machine learning intern: RobotsBlocked: robots gate:
DISALLOWED for jobpilot - robots.txt forbids this path; AI intern: ... ;
data science intern: ... ; research intern: ... ; software engineer intern: ...
```

Live `https://www.linkedin.com/robots.txt` ends with `User-agent: *` /
`Disallow: /`. Per-query counts are all **0 / blocked**. The gate correctly wins
over the optional reader. (The README's LinkedIn robots row still says
"readable, permits the path" — see §7, D4.)

## 3. Funnel

```
discovered ................ 6625
hard-filter survivors ..... 379   (eligible)
scored .................... 379
strong .................... 16
tailored .................. 234
queued for review ......... 234
submitted ................. 0
parseability failures ..... 38    <-- new; see §7 D1
LaTeX compile failures .... 0
```

Per source (returned / eligible / scored / strong / queued / submitted):

| Source | returned | eligible | scored | strong | queued | submitted |
| --- | --- | --- | --- | --- | --- | --- |
| greenhouse | 5903 | 10 | 10 | 3 | 9 | 0 |
| lever | 276 | 5 | 5 | 0 | 5 | 0 |
| himalayas | 34 | 32 | 32 | 0 | 29 | 0 |
| unstop | 285 | 264 | 264 | 12 | 141 | 0 |
| workable_global | 67 | 27 | 27 | 0 | 24 | 0 |
| themuse | 60 | 41 | 41 | 1 | 26 | 0 |
| **total** | **6625** | **379** | **379** | **16** | **234** | **0** |

## 4. Technical / AI-ML / data / research matches

```
python3 -m jobpilot --config /mnt/d/jobpilot/config.toml present
# presented 46 technical match(es)
# excluded 184 non-technical / low-relevance queued posting(s)
# review page: /mnt/d/jobpilot/out/present/index.html
# nothing was submitted.
```

`present` selected **46 technical matches** (0 borderline shown, 184
non-technical/low-relevance queued postings excluded). By source: unstop 37,
themuse 4, greenhouse 3, himalayas 1, workable_global 1.

### 4a. All 16 `strong`-band matches

| # | Score | Source | Company | Title | Location | Window evidence | Link |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.835 | greenhouse | Rubrik Job Board | Software Engineer - Winter Intern | Bangalore | Jan-May 2027 (explicit, conf 1.0) | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 2 | 0.810 | greenhouse | Rubrik Job Board | Software Engineer (CPD) - Winter Intern | Bangalore | Jan-May 2027 (explicit, conf 1.0) | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
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

Selected reason lines (full per-match reasons and component breakdowns are in
`run.json`):

- **Rubrik SWE - Winter Intern** (0.835): skill coverage 80% (4/5), role
  relevance 0.70 (software), location fit 1.00 (India), window fit 1.00
  (explicit Jan-May 2027), seniority 1.00; gap `Fine-tuning` never inserted.
- **Rubrik SWE (CPD) - Winter Intern** (0.810): same shape, role relevance 0.60.
- **PrepLinc AI - AI/ML Application Developer** (0.780): coverage 100% (5/5),
  role relevance 0.70 (ai_ml), location fit 0.50 (`Online` not confirmably
  India), window fit 0.30 (unknown).
- **Pariskq - Software Engineer Internship** (0.761): coverage 68% (17/25),
  role relevance 0.90 (software), location fit 1.00, window unknown; gaps
  include TypeScript, AWS, CI/CD, NLP, Computer Vision.
- **PrepLinc AI - Data Science & AI** (0.761): coverage 85% (11/13), relevance
  0.90 (ai_ml), location 0.50, window unknown; gaps Data Science, Deep Learning.
- **Vortizo AI - Data Science Internship** (0.723): coverage 82%, relevance
  0.80 (ai_ml), location 0.50, window unknown.
- **Stripe - Software Engineer, Intern** (0.718): coverage 75%, relevance 0.60
  (software), location 1.00 (Bengaluru), window unknown.
- **Labcorp - Data Science Intern** (0.715): coverage 80%, relevance 0.80
  (ai_ml), location 0.50 (Flexible/Remote), window unknown.
- The remaining Unstop strong roles (Zenotalent, godstockss, TalentCV,
  Learntricks, Learn Depth, Maytrixtech, Skillorbit ×2) are 0.680-0.711, all
  unknown-window and mostly `Online`.

No posting reached a `strong`-band routing issue: all 16 queue as
`manual_required` because auto-apply is off (`adapter = "none"`).

### 4b. The 46 presented technical matches (ordered by score)

| # | Score | Source | Company | Title | Location | Window | Domain (tech rel) | Link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.835 | greenhouse | Rubrik Job Board | Software Engineer - Winter Intern | Bangalore | Jan-May 2027 | software (0.70) | https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523 |
| 2 | 0.810 | greenhouse | Rubrik Job Board | Software Engineer (CPD) - Winter Intern | Bangalore | Jan-May 2027 | software (0.60) | https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537 |
| 3 | 0.780 | unstop | PrepLinc AI | AI/ML Application Developer Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/aiml-application-developer-internship-preplinc-ai-1760453 |
| 4 | 0.761 | unstop | Pariskq | Software Engineer Internship | Bangalore, Online | unknown | software (0.90) | https://unstop.com/internships/software-engineer-internship-pariskq-1729187 |
| 5 | 0.761 | unstop | PrepLinc AI | Data Science & Artificial Intelligence Internship | Online | unknown | ai_ml (0.90) | https://unstop.com/internships/data-science-artificial-intelligence-internship-preplinc-ai-1760823 |
| 6 | 0.723 | unstop | Vortizo AI | Data Science Internship | Online | unknown | ai_ml (0.80) | https://unstop.com/internships/data-science-internship-vortizo-ai-1752060 |
| 7 | 0.718 | greenhouse | Stripe | Software Engineer, Intern | Bengaluru | unknown | software (0.60) | https://stripe.com/jobs/search?gh_jid=8031833 |
| 8 | 0.715 | themuse | Labcorp | Data Science Intern - Real World Data Strategy Team | Flexible / Remote | unknown | ai_ml (0.80) | https://www.themuse.com/jobs/labcorp/data-science-intern-real-world-data-strategy-team-fa4bac |
| 9 | 0.711 | unstop | Zenotalent | Data Science Internship | Chennai, Mangaluru, Bangalore, Pune, Noida, Delhi, Kolkata, Hyderabad, Online | unknown | ai_ml (0.80) | https://unstop.com/internships/data-science-internship-zenotalent-1755823 |
| 10 | 0.705 | unstop | godstockss | Software Engineer Internship | Online | unknown | software (0.80) | https://unstop.com/internships/software-engineer-internship-godstockss-1731267 |
| 11 | 0.692 | unstop | Learntricks Edutech | Machine Learning Internship | Online | unknown | ai_ml (0.90) | https://unstop.com/internships/machine-learning-internship-unstop-tech-fair-2025-learntricks-edutech-1724312 |
| 12 | 0.692 | unstop | TalentCV | Software Engineer Internship | Online | unknown | software (0.90) | https://unstop.com/internships/software-engineer-intern-talentcv-1694821 |
| 13 | 0.690 | unstop | Learn Depth | Machine Learning Trainer Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/machine-learning-trainer-internship-learn-depth-1735074 |
| 14 | 0.689 | unstop | Maytrixtech | Software Engineer Internship | Online | unknown | software (0.90) | https://unstop.com/internships/software-engineer-internship-maytrixtech-1733361 |
| 15 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Internship | Bangalore, Online | unknown | ai_ml (0.90) | https://unstop.com/internships/machine-learning-intern-skillorbit-private-limited-1759582 |
| 16 | 0.680 | unstop | Skillorbit Private Limited | Machine Learning Engineer Internship | Bangalore, Chennai, Online | unknown | ai_ml (0.80) | https://unstop.com/internships/machine-learning-engineer-internship-skillorbit-private-limited-1752362 |
| 17 | 0.680 | unstop | Operonn | AI Engineer Internship | Online | unknown | ai_ml (0.90) | https://unstop.com/internships/ai-engineer-internship-operonn-1755613 |
| 18 | 0.672 | unstop | BluMotiv | Software Engineer Internship | Online | unknown | software (0.90) | https://unstop.com/internships/software-engineer-internship-blumotiv-1668628 |
| 19 | 0.672 | himalayas | Ritual | Research Intern | Worldwide | unknown | research (0.60) | https://himalayas.app/companies/ritual-net/jobs/research-intern-1464631102 |
| 20 | 0.667 | unstop | Vision AI Learning | Curriculum Developer – Artificial Intelligence Internship | Bharatpur, Online | unknown | ai_ml (0.70) | https://unstop.com/internships/curriculum-developer-artificial-intelligence-internship-vision-ai-learning-1759335 |
| 21 | 0.661 | themuse | The Muse | AI Engineer – Remote Internship | Flexible / Remote | unknown | ai_ml (0.90) | https://www.themuse.com/jobs/themuse/ai-engineer-remote-internship |
| 22 | 0.655 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship | Bangalore Urban, Online | unknown | ai_ml (0.90) | https://unstop.com/internships/artificial-intelligence-internship-skillorbit-private-limited-1758984 |
| 23 | 0.650 | unstop | Embolo Technologies Private Limited | Software Engineer Internship | Chandigarh, Online | unknown | software (0.90) | https://unstop.com/internships/software-engineer-internship-embolo-technologies-private-limited-1727893 |
| 24 | 0.642 | unstop | JobLuxe | Software Engineer Internship | Online | unknown | software (0.60) | https://unstop.com/internships/software-engineer-intern-jobluxe-1750680 |
| 25 | 0.625 | unstop | Skill Orbit | Artificial Intelligence Internship | Online | unknown | ai_ml (0.80) | https://unstop.com/internships/artificial-intelligence-internship-skill-orbit-1756034 |
| 26 | 0.625 | unstop | Codeatrix | AI/ML Internship | Online | unknown | ai_ml (0.80) | https://unstop.com/internships/aiml-internship-codeatrix-1761049 |
| 27 | 0.625 | themuse | The Muse | Data Engineer – Remote Internship | Flexible / Remote | unknown | software (0.80) | https://www.themuse.com/jobs/themuse/data-engineer-remote-internship |
| 28 | 0.623 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | Hyderabad, Online | unknown | ai_ml (0.80) | https://unstop.com/internships/artificial-intelligence-internship-xtragrad-technologie-private-limited-1754902 |
| 29 | 0.605 | unstop | Xtragrad Technologie Private Limited | Artificial Intelligence Internship | Hyderabad, Online | unknown | ai_ml (0.90) | https://unstop.com/internships/artificial-intelligence-internship-xtragrad-technologie-private-limited-1747534 |
| 30 | 0.600 | unstop | Zenotalent | Data Science Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/data-science-internship-zenotalent-1748389 |
| 31 | 0.600 | themuse | Atlassian | Research Intern, 2026 Summer U.S. | Flexible / Remote, Seattle, WA | Jun-Aug 2026 | research (0.60) | https://www.themuse.com/jobs/atlassian/research-intern-2026-summer-us |
| 32 | 0.586 | unstop | Kukbit SL | Machine Learning Internship | Online | unknown | ai_ml (0.60) | https://unstop.com/internships/machine-learning-internship-kukbit-sl-1751307 |
| 33 | 0.585 | unstop | Skillorbit Academy | Artificial Intelligence Internship | Bangalore, Online | unknown | ai_ml (0.70) | https://unstop.com/internships/artificial-intelligence-intern-skillorbit-academy-1750189 |
| 34 | 0.580 | unstop | Kukbit SL | Data Science Internship | Online | unknown | ai_ml (0.80) | https://unstop.com/internships/data-science-internship-kukbit-sl-1761158 |
| 35 | 0.573 | unstop | Zenotalent | Machine Learning Internship | Online | unknown | ai_ml (0.90) | https://unstop.com/internships/machine-learning-internship-zenotalent-1749292 |
| 36 | 0.560 | unstop | Vortizo AI | Machine Learning Internship | Online | unknown | ai_ml (0.90) | https://unstop.com/internships/machine-learning-internship-vortizo-ai-1744336 |
| 37 | 0.555 | unstop | Aalteon | Artificial Intelligence Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/artificial-intelligence-internship-aalteon-1758771 |
| 38 | 0.555 | unstop | IntelleQAcademy | Data Science and ML Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/data-science-and-ml-internship-intelleqacademy-1751493 |
| 39 | 0.535 | unstop | Aalteon | Artificial Intelligence Internship | Online | unknown | ai_ml (0.80) | https://unstop.com/internships/artificial-intelligence-internship-aalteon-1742163 |
| 40 | 0.530 | unstop | Zenotalent | Data Science Internship | Online | unknown | ai_ml (0.60) | https://unstop.com/internships/data-science-internship-zenotalent-1760539 |
| 41 | 0.505 | unstop | Cornixe Edutech Pvt. Ltd. | Data Science & Machine Learning Internship | Perungudi, Online | unknown | ai_ml (0.80) | https://unstop.com/internships/data-science-machine-learning-internship-cornixe-edutech-pvt-ltd-1761310 |
| 42 | 0.505 | workable_global | Blue Machines AI | Evaluation & Insights Intern, AI Delivery | Bengaluru, Karnataka, India | unknown | ai_ml (0.50) | https://jobs.workable.com/view/hYkVydG3ua3RuasU6CTiMw/evaluation-%26-insights-intern%2C-ai-delivery-in-bengaluru-at-blue-machines-ai |
| 43 | 0.480 | unstop | Skillorbit Private Limited | Artificial Intelligence Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/artificial-intelligence-internship-skillorbit-private-limited-1748852 |
| 44 | 0.455 | unstop | Skillorbit Private Limited | Machine Learning Internship | Online | unknown | ai_ml (0.60) | https://unstop.com/internships/machine-learning-internship-skillorbit-private-limited-1758836 |
| 45 | 0.455 | unstop | Digital Back Office | Software Engineer Internship | Abrama, Online | unknown | software (0.60) | https://unstop.com/internships/software-engineer-intern-digital-back-office-1756610 |
| 46 | 0.443 | unstop | Qveto | Data Science and Machine Learning Internship | Online | unknown | ai_ml (0.70) | https://unstop.com/internships/data-science-and-machine-learning-internship-qveto-1747163 |

### 4c. Held borderline (shown only if nothing clears the floor; nothing did not)

`select_matches` holds candidates with technical relevance 0.40 as borderline
and, because 46 matches cleared the 0.50 floor, does not render them. The four
are in `run.json`; the two worth naming are the best Himalayas technical roles:

| Score | Source | Company | Title | Location | Window | Tech rel |
| --- | --- | --- | --- | --- | --- | --- |
| 0.667 | himalayas | Drivetrain | Engineering Intern - Gen AI for FP&A Platform | India | unknown | ai_ml 0.40 |
| 0.657 | unstop | EdJAMON | AI Professional Internship | Chennai, Online | unknown | ai_ml 0.40 |
| 0.621 | unstop | GradGuide | Software Engineering Internship | Mumbai, Online | unknown | software 0.40 |
| 0.592 | himalayas | Abstrabit Technologies Pvt Ltd | Software Engineering Intern | India | unknown | ai_ml 0.40 |

## 5. Explicit Jan-May/June window vs unknown

### Among the 46 presented match(es)

- **Explicit** (3): Rubrik SWE - Winter Intern and Rubrik SWE (CPD) - Winter
  Intern (both **Jan-May 2027**, confidence 1.0 — the only true Jan-May
  presented matches), and Atlassian Research Intern, 2026 Summer U.S.
  (**Jun-Aug 2026**, confidence 1.0, a US research role).
- **Unknown** (43). The remaining 43 have no timing signal and are review-only
  for an unconfirmed window.

### Among all 234 queued postings

| Window label | Count |
| --- | --- |
| unknown | 208 |
| Summer (season, conf 0.6) | 11 |
| Jan-May 2027 (`Jan-5 2027`; store label quirk, rendered "Jan-May 2027" on the card) | 3 |
| Dec-Jun 2027 | 3 |
| Dec-Jun 2026 | 2 |
| Jan-Aug / Jun-Aug 2026 / Dec-Feb / Summer 2025 / Mar-Mar 2024 / Mar-Mar 2023 / 5-5 2023 | 1 each |

The only **explicit Jan-May** India roles found are Rubrik's three winter
interns (SWE, SWE CPD, and ENG Project/Program - Intern; the third is queued but
excluded from the presented page). There are **no unknown-window-but-in-window
auto-apply risks**: `allow_unknown_window = false` keeps every unknown-window
posting in review.

## 6. Deadlines surfaced (display only, never a filter)

6 postings carry a deadline; **none is a technical match**, and only one is not
already expired:

| Source | Company | Title | Deadline | Label | Tailored? |
| --- | --- | --- | --- | --- | --- |
| greenhouse | Stripe | Account Executive, Platforms (Existing Business) | 2026-09-30 | 2026-09-30 (closing soon) | no (ineligible) |
| himalayas | Center for International Sustainable Development Law | International Legal Research Group | 2016-10-01 | expired | no |
| unstop | Net Impact, Delhi University | Content Marketing and Strategy Internship | 2023-05-03 | expired | yes |
| unstop | Net Impact, Delhi University | Content Creation / Writer Internship | 2024-03-05 | expired | yes |
| unstop | Net Impact, Delhi University | Social Media Marketing Internship | 2024-03-05 | expired | no |
| themuse | PCORI | Spring Intern 2025 - EDI, Public and Patient Engagement | 2025-02-01 | expired | no |

**No shortlisted technical match carries a deadline**, so deadline tracking
changed nothing about readiness — it only adds badges where a date exists.

## 7. Defects and unexpected behaviour (exact command + error)

### D1. (REAL REGRESSION, not run-blocking) The profile edit removed the `Projects` section; 38/234 resumes fail parseability

- **Command:** `python3 -m jobpilot --config /mnt/d/jobpilot/config.toml run --dry-run`
- **Observed:** `"parseability_failed": 38` (resweep-12 run 1: `0`; resweep-12
  run 2, after the profile edit: `32`).
- **Stored reason (36 rows):**
  `parseability check failed: missing sections: Projects; resume layout is unreadable: a required section could not be extracted from the fitted PDF`
- **Stored reason (2 rows, e.g. One Oath Foundation, ForeTeach):**
  `parseability check failed: keyword survival 33% below 50%; unextractable: Statistics, statistics`

**Root cause — measured, not inferred.** The master profile no longer has a
`## Projects` heading. Its projects (`costsmart-rag`, `tsfm-benchmark`,
`guardrailed-sql-analyst`, `EV Transition & Grid Feasibility Analysis`) now sit
under `## Experience`:

```
$ grep -n '^## ' /mnt/d/LaTeX/resume/PROFILE.md
13:## Education
20:## Experience
64:## Positions of Responsibility
73:## Technical Skills
```

`jobpilot/profile.py:_canonical_section` only maps an H2 whose name starts with
"project" to the `projects` bucket, so the profile parser now yields:

```
experiences: 7   (CSIR-NAL, Outlier, CRIS + the four projects)
projects:    0
```

The generator only emits `\section{Projects}` when `profile.projects` is
non-empty, so every tailored resume lost its `Projects` section and renders the
projects as **Experience subheadings** instead. `check_parseability` requires
the configured `required_sections` (`["Education", "Experience", "Projects",
"Technical Skills"]`); the 196 resumes that still happened to contain the word
"projects"/"Projects" incidentally passed the substring check, and the 38 that
did not failed.

Hard evidence that this is a profile-structure regression and not a code change:

- `out-run-07/.../software-engineer-winter-intern-8166523/resume.tex` contains
  `132:\section{Projects}` (old profile, same generator logic).
- resweep-12 DB: run 1 (pre-edit) = 205 apps, **0** parseability failures; run 2
  (post-edit re-tailor) = 205 apps, **32** failures.

Two further consequences of the same misclassification, both visible in the new
`resume.tex`:

- **The now-public repo URLs are dropped.** The four project entries carry
  `links = ["Repo: github.com/Abhigyan1805/..."]`, but `_render_experiences`
  ignores `entry.links` (only `_render_projects` emits them). No tailored resume
  carries the newly public repo links.
- **Project stack lines are lost.** The `*Python, RAG, ...*` stack/description
  line is stored in `entry.note`/`stack`, which the experience renderer also
  ignores; that is why the 2 "Statistics" keyword-survival failures occur (the
  only profile source of "Statistics" is the costsmart-rag stack line, which no
  longer reaches the PDF).

Per the task ("fix nothing except a genuine run-blocking defect"), **no code or
profile change was made**. The run itself completed and nothing unsafe
happened. The fix belongs in the captain's profile: restore a `## Projects`
heading around those entries (or otherwise keep the projects out of the
`Experience` H2). This is a content/input decision, not a pipeline change.

### D2. (PRESENTATION GAP) `present` cards do not surface the parseability failure

15 of the 46 presented cards are D1-failed resumes
(`parse_ok=0`), yet each still shows a green `Resume: 1-page ✓` badge and a
generic "Review-only (auto-apply off)" route, because `present._page_badge`
only compares page count and `_classify_route` only consults
`review_reason` when auto-apply is armed. The parseability reason is stored in
the DB but never shown on the card. The captain should not read a green badge on
a D1-failed card as "ready".

Affected presented cards (15): Rubrik SWE - Winter Intern; Rubrik SWE (CPD) -
Winter Intern; PrepLinc AI - Data Science & AI; Stripe - Software Engineer,
Intern; Labcorp - Data Science Intern; Zenotalent - Data Science Internship;
Operonn - AI Engineer Internship; Skillorbit - Artificial Intelligence
Internship; The Muse - Data Engineer; Xtragrad - Artificial Intelligence
Internship; Zenotalent - Data Science Internship (#30); Kukbit SL - ML and
Kukbit SL - Data Science; Aalteon - Artificial Intelligence Internship;
Cornixe Edutech - Data Science & ML. Full list in `run.json`
(`included[*].parse_ok`).

### D3. (minor) Window label renders May as `5` in the store

`window._label` picks a month name longer than 3 chars, so `"may"` (length 3)
renders the stored label as `Jan-5 2027`. `present._pretty_window` corrects this
on the card (the card shows `Jan-May 2027 (confidence 1.00)`), but `queue list`
/ `postings` still print the raw store label. Classification and confidence are
correct (Jan-May 2027, conf 1.0). Not fixed.

### D4. (documentation drift, inherited) The README's LinkedIn robots row is still wrong

The README source table says LinkedIn is "readable, permits the path"; live
`https://www.linkedin.com/robots.txt` has `User-agent: *` / `Disallow: /`, so
the optional reader cannot run under the enforced gate (as this run and
resweep-12 both show). Flagged again for a normal documentation change; not
fixed here.

### D5. (minor) `workable_global` returned 68 but stored 67

One repeated `stable_id` inside the adapter's own result set; `discover` dedupes
by `source:job_id`. Harmless.

Ashby remains unfetchable (robots 401) and LinkedIn blocked; both are the
intended fail-closed behaviour, not defects.

## 8. Tailored artifacts — one page, verified by measurement

- **Presentation assets:** 46 `resume.pdf` + 46 `cover_letter.pdf` copied under
  `out/present/assets/<slug>/`.
- **Every copied asset resume PDF is exactly 1 page**, measured independently
  with `pdftotext -layout` form feeds (never `/Count`): `{1: 46}`,
  zero extraction failures, zero missing PDFs.
- **Assets reflect the current profile:** 46/46 contain `CSIR`; 0/46 contain
  `Astro Deus`.
- Store agrees: every one of the 234 queued rows has `resume_pages = 1`,
  `resume_page_limit = 1`; `compile_failed = 0`.
- All 234 cover-letter PDFs exist; no cover-letter failures.
- The 38 D1 parseability failures are stored on the durable application record
  and the resume is still reduced/enforced to one page; they are queued for
  review (never silently shipped as ready).
- No-invention invariant held: unsupported JD terms appear only as gaps and were
  never inserted (e.g. Rubrik's `Fine-tuning`, PrepLinc's `Deep Learning`).

## 9. Zero-submission verification (from the run's own record)

- run `mode = dry_run`; `stats.submitted = 0`.
- `applications`: **234 rows, all `status = manual_required`; 0 `submitted`**.
- `attempts`: **empty (0 rows)** — no submission was ever attempted.
- `review_queue`: 234 rows, all `pending`.
- CLI printed `dry run: nothing was submitted.`
- Present/upskill printed `nothing was submitted.`

## 10. Comparison with the previous sweep (resweep-12)

| Metric | resweep-12 | resweep-14 | Why |
| --- | --- | --- | --- |
| discovered | 6593 | 6625 | +32; Himalayas back (+34) vs small Unstop/greenhouse drift |
| eligible | 356 | 379 | +23; Himalayas adds 32 eligible, Unstop -9, others ~flat |
| strong | 16 | **16** | **unchanged — Himalayas added no strong match** |
| tailored / queued | 205 | 234 | +29, almost all from Himalayas (29 queued) |
| submitted | 0 | 0 | dry run, auto-apply off |
| parseability failures | 0 (run 1) | **38** | profile edit removed the `Projects` section (D1) |

**Did restoring Himalayas add matches? Yes, but modestly and not at the top.**
It went from blocked (0) to **34 discovered / 32 eligible / 29 queued**, and it
contributed **1 presented technical match** (Ritual - Research Intern,
worldwide) plus **2 held-borderline** AI/ML roles (Drivetrain - Gen AI FP&A,
Abstrabit - Software Engineering Intern). It added **zero strong-band matches**,
and its best AI/ML role (Drivetrain Gen AI) sits only at tech relevance 0.40, so
it is held rather than presented. First-page-only volume is 34 versus run-07's
paged 99, so the restored path is real but much narrower. The strong band stayed
flat at 16, entirely greenhouse+unstop+themuse.

**Did the profile changes alter how the tailored resumes read? Yes — materially,
and for the worse.** CSIR-NAL now appears (verified in all 46 assets) and Astro
Deus is gone. But the same edit moved the projects under `## Experience`, so:
(1) no tailored resume has a `Projects` section; (2) the four projects render as
Experience subheadings; (3) the newly public repo URLs and the project stack
lines are dropped by the experience renderer; and (4) 38/234 resumes (15/46
presented) fail the parseability safety check and are queued for review. This is
the single most important finding in this sweep, and it is an input/profile
structural issue rather than a pipeline code bug.

## 11. `jobpilot upskill` — top skill gaps across the postings found

```
 #  skill                            jobs  weight  source
--  -------------------------------- ----  ------  ------------
 1  Research                          115   69.74  application,posting
 2  Problem Solving                    88   46.84  application,posting
 3  Data Analysis                      58   31.74  application,posting
 4  Data Science                       20    8.00  application
 5  Computer Vision                    13    7.84  application,posting
 6  Model Deployment                   15    7.26  application,posting
 7  Algorithms                         17    6.60  application,posting
 8  Agile                              12    5.62  application,posting
 9  REST APIs                          13    5.09  application
10  AWS                                 9    3.89  application,posting
11  Azure                               5    2.44  application
12  TensorFlow                          5    1.83  application
13  TypeScript                          5    1.67  application
14  Linux                               4    1.66  application
15  Deep Learning                       4    1.35  application
16  Fine-tuning                         4    1.17  application
17  CI/CD                               3    1.02  application
18  Data Engineering                    2    0.80  application
19  NLP                                 1    0.24  application
```

Compared with resweep-12 the ordering is essentially unchanged (Research,
Problem Solving, Data Analysis lead), with slightly higher counts from the
larger posting set.

## 12. What the captain can actually apply to

- **Most actionable, in-window, India:** **Rubrik - Software Engineer (Winter
  Intern)** and **Rubrik - Software Engineer (CPD) (Winter Intern)**,
  Bangalore, explicit **Jan-May 2027**, strong band (0.835 / 0.810). Both are
  review-only because `auto_apply_strong = false`. **Caveat (D1):** these two
  are among the 15 presented cards whose tailored resume currently fails the
  parseability check (no `Projects` section) — fix the profile's `## Projects`
  heading before using them.
  - https://www.rubrik.com/company/careers/departments/job.8166523?gh_jid=8166523
  - https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537
- **Strong AI/ML/data, window unconfirmed (verify dates first):** Stripe SWE
  Intern (Bengaluru), Labcorp Data Science (remote/US-loose), and the Unstop
  strong roles (PrepLinc AI, Vortizo AI, Zenotalent, Skillorbit, Learntricks,
  Learn Depth, Operonn). Window is unknown, so review-only by design.
- **Himalayas comeback role:** Ritual - Research Intern (worldwide, research
  domain 0.60) is presented; Drivetrain Gen AI and Abstrabit are held
  borderline.

## 13. Verdict

The full merged pipeline ran end to end in dry-run mode: **6625 discovered, 379
eligible, 16 strong, 234 tailored (234/234 measured one page, 234/234 compile,
no cover-letter failures), 234 queued, 0 submitted**. **Himalayas is back** via
a verified first-page-only, no-`page`-parameter fetch (34 postings, 1 presented
match, 2 held borderline), but it adds no strong-band matches. The dominant
finding is that the **profile edit flattened the `Projects` section into
`## Experience`**, which removes `\section{Projects}` from every tailored resume
and causes **38/234 parseability failures (15/46 presented)** plus the loss of
the newly public repo links and project stack lines. The run is safe (zero
submissions, robots gate intact, no invention), and the fix is a profile-content
change, which the captain owns.
