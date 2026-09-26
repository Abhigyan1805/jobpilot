# jobpilot

A config-driven, read-only-first pipeline that finds internships, writes a resume
tailored to each job description, and applies on your behalf - automatically for
strong matches, with a one-click review queue for everything uncertain.

Built for a BITS Pilani student looking for an internship that runs **January to
May/June** and is **open to candidates in India** (or remote-eligible from India),
not a full-time role.

The master profile is the only source of resume facts. Generated resumes may
select, reorder and re-emphasise real content, but they **never invent** a fact,
employer, date, metric or project.

---

## What it does

1. **Discovery** - pulls internship postings from the public, permission-respecting
   endpoints of Greenhouse, Lever, Ashby and Workable (a configurable list of board
   tokens), plus four catalogue/search sources: Himalayas, Unstop, Workable's
   global job search and The Muse, plus an optional read-only LinkedIn listing
   reader that never logs in, never authenticates and never applies. Every source
   is a pluggable adapter behind one interface, and one source failing never
   aborts the run. Before any adapter fetches, a **robots.txt gate** checks each
   source host once per run (cached) and evaluates the concrete request path and
   query; it fails closed: a host whose policy cannot be read, or a path the
   policy disallows, is not fetched. Sources whose terms
   forbid automation are never scraped: they are surfaced as **link-out** channels
   instead (see below).
2. **Filtering and matching** - hard filters first (must be an internship, must
   plausibly run in Jan-Jun, must be open to India or remote from India), then a
   deterministic, documented scoring rubric against the master profile.
3. **Tailored resume generation** - selects, reorders and re-emphasises profile
   content in the exact existing LaTeX style, then compiles it to PDF. Also produces
   a short cover letter per application.
4. **Applying** - auto-applies only to strong matches, behind mandatory guardrails
   (dedupe, never-missing-required-field, daily cap, durable record). The only
   automatic channel is email to an explicit, source-supplied application address
   (with SMTP configured). Greenhouse, Lever, Ashby and Workable expose no
   documented, verifiable public application endpoint, so they are prepared as
   link-out packets and routed to the review queue for one-click human submission.
5. **Tracker and review queue** - a durable SQLite store of every posting seen and a
   queue of uncertain / no-public-path applications with a direct link and the
   generated PDFs, plus a CLI to list, approve and export. Submitted or approved
   applications are archived to disk (the exact materials plus the posting text),
   and a deterministic lifecycle (`outcome`, `followups`, `stale`) keeps the
   tracker alive after applying. A `upskill` command turns the stored gaps into a
   ranked learning list.

### What submits automatically - and what does not

There is exactly **one automatic submission channel: email**. It is used only
when both of these are true:

- the posting carries a structured, source-supplied application address (never an
  address scraped from a job description's free text), optionally narrowed by
  `apply.submission.email_allowlist`; and
- you have configured SMTP under `[apply.submission.smtp]` in `config.toml`.

**Without SMTP configured, nothing is auto-submitted.** Every strong match is
still discovered, filtered, scored, tailored and compiled, but it is prepared as
a link-out packet and placed in the review queue for one-click human submission.

Greenhouse, Lever, Ashby and Workable are **link-out by design**: they expose no
documented, verifiable public application endpoint, so this pipeline never POSTs
to them. Their postings are prepared (tailored resume PDF, cover letter PDF,
direct apply link, and the matched and gap JD keywords) and queued. LinkedIn is
review-only by product decision. `apply.adapter = "none"` routes everything to
review. An application is recorded as *submitted* only when it was actually sent
through a genuine channel.

---

## Requirements

- Python 3.11+ (uses `tomllib` from the standard library). **No third-party
  packages** - HTTP, HTML parsing, SQLite, TOML and tests are all stdlib.
- A LaTeX engine and its `pdftotext` companion. The reference setup uses MiKTeX on
  Windows through WSL:
  - `pdflatex`: `/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdflatex.exe`
  - `pdftotext`: `/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdftotext.exe`

## Setup

```bash
cp config.example.toml config.toml          # set profile path, engine, tokens, thresholds
cp answers.example.toml answers.toml        # fill in form answers you can always give
```

`config.toml` and `answers.toml` are git-ignored. Nothing personal is hardcoded in
the source: the profile path, style template, engine paths, company tokens,
thresholds and caps all come from config.

Read-only inputs the pipeline uses (never modified):

- the master profile markdown (`profile.path`),
- the resume whose LaTeX preamble defines the style (`profile.style_template`),
- the LaTeX engine (`profile.pdflatex`).

---

## Quick start (no network, no risk)

The repo ships a demo posting file so the whole pipeline can be run offline:

```bash
python -m jobpilot --config examples/demo.config.toml run --dry-run
python -m jobpilot --config examples/demo.config.toml queue list
python -m jobpilot --config examples/demo.config.toml queue export --out review.json
```

You will see discovery, filtering, matching, tailoring (with real PDFs compiled)
and the review queue - **nothing is submitted**.

## Dry-run walkthrough

`--dry-run` runs discovery, filtering, matching and tailoring but submits nothing.
Use it to verify filters, scores and generated resumes before ever going live:

```bash
# 1. Discover + filter + score, no tailoring, no submissions
python -m jobpilot --config config.toml run --dry-run --stages discover,match
python -m jobpilot --config config.toml postings --eligible --limit 20

# 2. Add tailoring for the top shortlisted postings (compiles PDFs, checks parseability)
python -m jobpilot --config config.toml run --dry-run --limit 5

# 3. Inspect and export the queue
python -m jobpilot --config config.toml queue list
python -m jobpilot --config config.toml queue export --out review.json
```

Only when you are satisfied:

```bash
python -m jobpilot --config config.toml run            # live; strong matches only
```

### Review queue

```bash
python -m jobpilot --config config.toml queue list
python -m jobpilot --config config.toml queue approve 3   # prints apply link + artifacts
python -m jobpilot --config config.toml queue reject 4
python -m jobpilot --config config.toml queue export --out review.md
```

Each queued item has a packet directory with `resume.pdf`, `cover_letter.pdf`,
`apply_link.txt`, `packet.json` and a human-readable `requirements.md` listing the
JD keywords the profile matches and the gaps it does not, so approval is one
click.

### Present: a browsable review surface

```bash
python -m jobpilot --config config.toml present
# -> out/present/index.html  (open it in a browser; no server needed)
```

`present` turns the queued matches into one self-contained HTML page so you can
actually look at the roles and choose, rather than read a list. One card per
match, ordered by score, with company, title, location, window evidence, the
match score, the matched skills versus the gaps, the direct apply link, and the
tailored resume and cover letter embedded beside the card (the PDFs are copied
into `out/present/assets/` and linked relatively). The card's obvious click opens
the tailored resume: the **job title** and the **Open tailored resume PDF**
button both link to `assets/<slug>/resume.pdf` in a new tab, as plain relative
anchors that work straight from disk (no server, no JavaScript). The posting link
is a separate, clearly-labelled **Apply / view posting** button, so "read the
resume I generated" and "go to the posting" cannot be confused. Every card states the safety
state: nothing was submitted, and whether the role is auto-apply eligible or
review-only, with the reason. A role is auto-apply eligible only when it is in
the strong band *and* the pipeline queued it for a transient reason (daily cap,
missing channel or auto-apply config); a strong-band role the pipeline routed to
review for a blocking reason (for example an unconfirmed window), and every
link-out, LinkedIn or non-strong-band role, is labelled review-only. Each card
also shows the measured page count of its tailored resume (`Resume: 1-page ✓`,
or a warning badge when it is over the limit and needs attention) and the
resume's stored parseability verdict (`Resume: parseable ✓`, or a red
`Resume: parseability failed` badge; a row with no stored verdict shows no
badge and claims no pass). A failed card names the stored failure detail when
there is one (`missing sections: Projects`) and otherwise says only that the
resume did not pass the check, and a banner above the cards counts the presented
packets that still need fixing before they are sent.

Selection is deliberately narrow: only genuine technical, software-engineering,
data and AI/ML roles are shown. Unrelated internships (design, UX,
communications, video/content, marketing, HR, recruiting, non-technical product
management, …) are left out entirely - not shown in a separate tier. Fit comes
from the data the pipeline already computes: a posting's role relevance across
the configured technical domains, confirmed by the matched skills against the
master profile. `[present]` controls the target role set:

```toml
[present]
out_dir = "present"                 # relative to [output].dir
min_role_relevance = 0.5            # technical floor (per configured domain)
borderline_role_relevance = 0.4     # shown only if nothing clears the floor
technical_domains = ["ai_ml", "software", "research"]
guarded_domains = ["research"]      # counts only with a matched core skill
# exclude_terms = [...]             # non-technical role keywords, excluded outright
```

The broad `research` domain is *guarded*: it only counts as technical when the
posting also matches a core technical skill, so design/policy/market research is
not presented as an AI/ML role. If nothing clears the floor, the page says so and
shows the closest technical matches with a note explaining why each is
borderline, instead of padding the list. `present` never re-scores, never invents
resume content and never submits.

Two more presentation-layer rules apply. A `[filter].stipend_floor` (default
₹30,000/month) drops postings whose stipend is confirmed below the floor or is
explicitly unpaid/performance-based; postings whose stipend is simply *not
stated* are kept but shown in a separate **"Stipend not stated — verify before
applying"** section, never silently failed. And `[filter].exclude_file` names a
tracked TOML list of postings already applied to; `present` drops them entirely
(matched case-insensitively on company+title and on url), without deleting
anything from the store. Each card shows its stipend outcome and, when the board
reports it, an applicant count as a warning (never a cutoff).

### Tracking: outcomes, follow-ups and the skill-gap heatmap

Once you apply, the tracker keeps working. On an auto-submission or a
`queue approve`, the exact submitted materials (resume/cover PDFs and their
`.tex` sources) plus the posting text are archived to
`out/applications/<company>-<title>-<hash>/`; an existing file is never
overwritten, so the archive always holds the version that was actually sent.
`outcome.md` records the current status.

```bash
# What happened?  (no id lists the open applications)
python -m jobpilot --config config.toml outcome 3 --status interview --note "phone screen booked"
# Open applications gone quiet for 10+ days, with a plain follow-up draft
python -m jobpilot --config config.toml followups
python -m jobpilot --config config.toml followups --record 3      # log a follow-up
# Batch-resolve applications quiet for 60+ days
python -m jobpilot --config config.toml stale            # preview
python -m jobpilot --config config.toml stale --write    # mark no_response
```

The lifecycle vocabulary is `applied | interview | offer | hired | rejected |
no_response | offer_declined | withdrawn`; everything except the final five stays
open. Follow-ups are plain templates (role, company and date only - no new
claims), capped at two per application, and nothing is ever sent by the pipeline.

Stored gaps are turned into a learning list:

```bash
python -m jobpilot --config config.toml upskill
```

`upskill` aggregates `postings.missing_keywords` and `applications.gaps`,
weighting each job by `(1 - score)` so the roles that exposed the most gaps count
for more, and prints a ranked table. No model is involved, and a job with no
recorded gaps contributes nothing rather than being guessed at.

### Deadlines and posting staleness

Where a posting states an application deadline ("apply by", "applications
close", "deadline"), it is extracted into an ISO date and stored. `jobpilot
postings` and `jobpilot queue list` label a deadline as *closing soon* (within
`[deadline].closing_soon_days`, default 7) or *expired*, and flag a posting
published more than `[deadline].stale_days` ago. A stated deadline that has
passed **closes the posting**: the shared open-state check (`jobpilot/openstate`)
rejects it, alongside a falsy Unstop `regn_open`, a past `end_date`, or explicit
closed text ("application closed", "no longer accepting"). A missing deadline
never changes a posting's status; a bare date or an ambiguous numeric date is
never guessed as a deadline, and the internship's own start/end window is
untouched.

---

## Safety model

- **Auto-apply only to strong matches.** Everything else is queued for review.
- **LinkedIn and every other manual-only source are never auto-submitted.**
  LinkedIn postings are discovered, ranked, tailored and packaged, then placed in
  the review queue with their direct apply link - you submit them yourself. The
  pipeline never authenticates and never touches your LinkedIn account. Postings
  from the link-out channel (Internshala, Naukri, Wellfound, HiringCafe, a16z,
  Peak XV, Remote.co) are never scraped and never auto-submitted either: they are
  prepared as packets for one-click human submission.
- **Dedupe on a stable job id.** An attempt is recorded *before* submitting, so a
  crash mid-submit cannot produce a second application.
- **No required field is ever guessed.** If a required form field cannot be answered
  from the profile or `answers.toml`, the application is not submitted.
- **Configurable daily cap.** Once reached, further strong matches are queued instead.
- **Durable record** of every attempt and its outcome in SQLite.
- **No improvised endpoints, ever.** A submission is recorded as *submitted* only
  when it was actually sent through a genuine channel. The only automatic channel
  is email to an explicit, source-supplied application address (with SMTP
  configured). Greenhouse, Lever, Ashby and Workable have no documented,
  verifiable public application endpoint, so they are never POSTed to: each is
  prepared as a link-out packet and queued for a one-click human submission. An
  unknown `apply.adapter` value is rejected rather than silently enabling a
  submission path.
- **Never invent content.** The no-invention validator fails generation if any number
  or word carrying a fact is not present in the master profile.
- **robots.txt is checked, not just claimed.** A gate checks each source host's
  policy once per run before any fetch, evaluated against the concrete request
  path and query, and fails closed when it cannot be read (see `[robots]`). It
  is on by default.
- **A tailored resume is verified after compilation.** The compiled PDF's page
  count is measured against `profile.resume_page_limit`; an over-long or
  unreadable resume is reduced by dropping the least relevant content (never by
  tightening spacing) or routed to review with the measured count. The text layer
  must still carry the required sections, keywords and the profile's contact
  details, compared with LaTeX-aware Unicode folding so a curly apostrophe or an
  en-dash cannot false-fail a genuinely parseable resume.

---

## Matching: a documented rubric, not an oracle

The score is a transparent weighted rubric. It exists to **rank postings for human
review**; it does **not** predict hiring outcomes, and should not be read as one.

Components (weights configurable under `[match.weights]`):

| Component | What it measures |
| --- | --- |
| `skill_coverage` | share of the role section's extractable skills the profile genuinely supports |
| `role_relevance` | overlap with the configured target domains (`[match.target_terms]`), where a **title** hit counts far more than a body mention |
| `location_fit` | India / remote-eligible-from-India |
| `window_fit` | Jan-Jun plausibility, weighted by how explicit the dates are |
| `seniority_fit` | clearly an internship vs. not |

Every score is stored with its reasons, its component breakdown and its formula.
Keyword coverage is exact: supported JD terms are listed as **matched**; terms the
profile does not support are listed as **gaps** and are **never inserted** into the
resume.

**Bands.** `strong` (auto-apply), `shortlist` (tailor + review), `reject`. A
posting reaches `strong` only when it clears `match.strong_threshold` *and* its
`role_relevance` reaches `match.strong_min_role_relevance` (default `0.5`). That
second gate is deliberate: location, seniority and window can saturate for any
India internship and a single soft-skill keyword can lift skill coverage, so an
unrelated internship can clear the score threshold while being irrelevant to the
search. When that happens the posting is **capped to `shortlist`** - tailored and
queued for review, never auto-applied - and the reason string says so:
`strong band withheld: role relevance 0.00 is below the 0.50 minimum for the
configured target domains (...)`.

**Retargeting.** The search target is configuration, not code: edit
`[match.target_terms]` (default `ai_ml`, `software`, `research`) and
`match.strong_min_role_relevance` to serve a different search. Skill coverage and
role relevance are computed from the **role section** of the description
(everything from the first `what you'll do` / `responsibilities` /
`requirements`-style heading onward); the company blurb above it is ignored, so a
blurb mention of "machine learning" or "generative AI" cannot establish
relevance. Role relevance is also title-weighted and its body contribution is
capped below the floor: only a title that names a target domain, or a title match
plus supporting role-description terms, can reach it.

## Tailoring and the no-invention guarantee

Tailoring means **selecting, reordering and re-emphasising** real content:

- entries, bullet order and skills order are chosen by relevance to the JD;
- existing measured values are bolded for emphasis (formatting only, no word changes);
- an outcome-first ("XYZ": *accomplished X, as measured by Y, by doing Z*) rewrite may
  reorder an existing bullet's clauses, but only when the result still passes the
  strict fact validator - otherwise the original bullet is kept verbatim.

The no-invention validator is deterministic: every numeric token must appear in the
profile, and every content word must appear in the profile vocabulary (or be an
allowed connective). Any violation fails generation.

Additional checks from the recruiter-prompt workflow:

- **Deterministic keyword coverage** instead of an opaque "match score out of 100":
  the JD's terms are extracted and coverage is reported with the specific missing
  terms; unsupported terms are gaps, never inserted.
- **Parseability check on the compiled PDF**: text is extracted with `pdftotext` and
  the standard sections and target keywords must be present as machine-readable
  text. Keyword survival is tested against the **profile-present surface forms**,
  not canonical labels, so a term the profile supports only through an alias
  (e.g. `Communication` via `cross-functional`) is checked as that alias and a
  perfectly parseable resume is not reported unparseable. If a required section
  or keyword is unextractable, generation fails and the application is forced to
  review, with the detailed reason persisted on the durable application record.
- **Red-flag critique**: a deterministic advisor proposes operator-facing
  suggestions. They are suggestions, never facts, and never alter content. They are
  stored with the application record. (An optional LLM-advisor hook is a documented
  follow-up, not part of v1.)
- **One-page enforcement.** A student resume should be one page, so the pipeline
  measures the compiled PDF's page count deterministically (form feeds in the
  existing `pdftotext` output, no new dependency) and compares it with
  `profile.resume_page_limit` (default `1`). When over, it drops content and
  recompiles within `profile.resume_fit_attempts` bounded attempts, in a fixed
  order: the least relevant bullets first, then whole projects - relevance being
  the posting fit the tool already computes. Spacing is never tightened: the
  style template's vertical layout is already calibrated, so compressing it
  overlaps headings and makes the page unreadable. Reduction only removes; every
  surviving line still comes verbatim from the profile, and a variant that no
  longer extracts a required section is rejected as unreadable rather than
  shipped. If it still cannot fit, the posting is queued
  for review with the measured count and the reason, and the `present` card shows
  the page count with a warning badge instead of silently presenting two pages.
  Nothing is ever invented, inflated or rewritten to make it fit.

### A note on "ATS rejects most resumes"

The widely repeated claim that an ATS automatically rejects most resumes is
**overstated**. ATS software is mostly a database; rejection is a human decision.
What is real and testable is **parseability** - columns, tables, images, text boxes,
and headers/footers can break text extraction - and **keyword relevance**. That is
exactly what this pipeline checks: it compiles, re-extracts the PDF text, and asserts
the sections and keywords survive, then reports keyword gaps honestly.

---

## Discovery sources and their honest limitations

All automated sources are read-only and unauthenticated. Source failures are
isolated and reported; the rest of the run continues. Internship status is
carried from each board's own **typed field** where it exists (`commitment` on
Lever, `employmentType` on Ashby, `employment_type` on Workable, Greenhouse's
employment-type metadata, `level` on The Muse, `employment_type` on Himalayas),
and a title alone is never used to invent it. Adapters never drop a posting on
its typed value: every posting reaches the shared hard filter, which keeps a
genuine intern that a board tagged with a generic value like `FullTime` and
routes it to human review instead of discarding it. The search adapters
(Himalayas, The Muse) may use a typed query as a high-precision slice, but it is
never the only path: a broader query runs alongside it and the two result sets
are merged and deduplicated by source job id, so a mis-tagged posting the typed
facet would have excluded is still discovered and filtered.

| Source | Endpoint | Limitations |
| --- | --- | --- |
| **Greenhouse** | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | Undocumented public endpoint; may change shape or rate-limit; only boards whose token you configure. Carries each job's typed employment-type metadata for the shared filter; never drops on it. |
| **Lever** | `api.lever.co/v0/postings/{token}?mode=json` | Documented postings endpoint; carries each job's typed `commitment` for the shared filter and never drops on it, so a genuine intern a board tags `Fulltime` still reaches review. Only boards whose token you configure. |
| **Ashby** | `api.ashbyhq.com/posting-api/job-board/{token}` | Undocumented; carries each job's typed `employmentType` for the shared filter; never drops on it. Only configured tokens. |
| **Workable** (per-account) | `apply.workable.com/api/v1/widget/accounts/{token}?details=true` | Public widget API; some boards return zero jobs; only configured tokens. Carries each row's typed `employment_type` for the shared filter; never drops on it. |
| **Himalayas** | `himalayas.app/jobs/api/search?employment_type=Intern&country=India` plus a `q=intern` keyword pass | Free, no key. **Only the first page of each query is requested, and no `page` parameter is ever sent**, because the board's published policy disallows the paged path (`Disallow: /jobs*&page=`) and the enforced robots gate honours it per concrete URL. The typed `employment_type=Intern` slice is a high-precision path, not the only one: a `q=intern` keyword query is merged in and deduplicated by guid so a mis-tagged intern is still discovered. Terms require a visible link back to himalayas.app and the attribution "data sourced from Himalayas". India intern volume is modest and includes stale/volunteer entries. |
| **Unstop** | `unstop.com/api/public/opportunity/search-result?opportunity=internships&page=N` plus one `searchTerm=<keyword>` pass per configured keyword | India-native live internship feed (~10,000 rows); its `robots.txt` explicitly allows `/api/public/*`. 10/page. The generic feed is recency-sorted and non-technical-dominated, so the API's server-side `searchTerm` keyword filter is run as a high-precision slice too; the generic feed and each keyword pass are merged and deduped by Unstop's own id. Typed `start_date`/`end_date` are mapped into the window check; a lone date is left as "unknown window" (review-only). Rows also carry `regn_open`, `registerCount` and `end_date`, which the shared open-state check uses to drop a posting whose application is actually closed even when its `status` still says `LIVE`; `registerCount` is shown as an applicant warning, never a cutoff. |
| **Workable** (global search) | `jobs.workable.com/api/v1/jobs?query=intern&location=India` | **Undocumented** cross-company search; paginates with an opaque `pageToken`. `robots.txt` sets `ai-train=no` (data must not be used for model training). Its `employmentType` is unreliable, so it relies on Workable's own server-side `query=intern` search. |
| **The Muse** | `themuse.com/api/public/jobs?page=N&level=Internship&location=India` plus a `location=India` pass without `level` | Free public API (500 req/hr unauthenticated); typed `level=Internship`. That typed slice is not the only path: the API ignores keyword parameters, so a broader `location=India` query without the level facet is merged in and deduplicated by id. The `location=India` parameter is loose, so the hard location filter rechecks every hit. |
| **LinkedIn** (optional reader, disabled by default) | public guest job-search HTML, one pass per configured target query | **Against LinkedIn's Terms of Service; best-effort; may stop working at any time.** An off-by-default, captain-authorized exception: link-out is the default LinkedIn path. Runs a configurable list of target queries (`[linkedin].keywords`), pages each a few times, and merges/dedupes by job id, so it is not limited to one generic `intern` word. Never logs in, never authenticates, never applies, low rate, degrades gracefully. Never auto-submitted. |

### robots.txt gating

Every automated adapter is gated at the shared fetch layer
(`jobpilot/http.py`), so no adapter can bypass it by construction. Each host's
robots.txt is read at most once per run and cached, and the verdict is computed
for the **concrete request path and query** - not the host root - so a
path-specific Disallow (for example Himalayas' `Disallow: /jobs*&page=`) is
honoured. An unreadable policy fails closed (the fetch does not happen), with no
override of any kind. The rules are the cautious RFC-9309 subset: longest match
wins with ties to Disallow, a Disallow for the agent (`jobpilot`) or `*` blocks,
an empty body is allow-all, and a 404 means no published policy (permitted).
`[robots]` controls this.

| Source | Host checked | Gate result (2026-09-25) |
| --- | --- | --- |
| Greenhouse | `boards-api.greenhouse.io` | readable, permits the path |
| Lever | `api.lever.co` | readable, permits the path |
| Workable (per-account) | `apply.workable.com` | readable, permits the path |
| **Himalayas** | `himalayas.app` | readable, permits the first-page search path (the adapter sends no `page` parameter); the paged path (`...&page=N`) is disallowed and never requested |
| Unstop | `unstop.com` | readable, permits the path |
| Workable (global) | `jobs.workable.com` | readable, permits the path |
| The Muse | `www.themuse.com` | readable, permits the path |
| LinkedIn (optional) | `www.linkedin.com` | readable but **disallows the path** (`User-agent: *` / `Disallow: /`), so the guest reader cannot run under the gate even with `[linkedin].enabled = true`; fetch skipped |
| **Ashby** | `api.ashbyhq.com` | **unreadable: HTTP 401 for every user agent; fetch skipped** |

Ashby is therefore not fetched by default: its API host returns 401 for
`/robots.txt`, so the gate cannot confirm permission and the fetch is skipped.
This is the intended safe behaviour, not an oversight - the public posting API it
would use is the documented way to read a board, but jobpilot never overrides an
unreadable policy. Set `[robots].enabled = false` to disable gating globally
(not recommended).

Himalayas' published policy contains `Disallow: /jobs*&page=`, which matches the
`...&page=N` paged search API. Because the gate is evaluated against the concrete
request path, a paged request would be refused even though the host root is
allowed. Rather than override the rule, the adapter requests only the **first
page** of each query and omits the `page` parameter entirely, which both avoids
the disallowed pattern and is permitted by the policy (`/jobs/api/search?...`
without `&page=`). Paging is deliberately not attempted, and no per-host
exception is carved out. The path-specific rule is working as intended; it is
not an oversight.

### Link-out sources (manual only, never scraped)

Some of the best inventory for a January-May India internship lives on sites whose
terms **forbid automation**, so jobpilot deliberately does not scrape or
authenticate to them. This is a product choice, not a missing feature: the
pipeline still does everything it lawfully can, and you do the final click.

```bash
python -m jobpilot --config config.toml link-out list
```

This prints a configured saved-search link per source - Internshala, Naukri,
LinkedIn, Wellfound, HiringCafe, a16z Portfolio Jobs, Peak XV and Remote.co - with
a one-line note on why each is manual. Link-out is the **default** path for every
one of these sources, LinkedIn included. Internshala, Naukri, Wellfound,
HiringCafe, a16z, Peak XV and Remote.co have **no automated reader at all**: their
terms forbid automation, so they are link-out only.

LinkedIn is the single, deliberate, off-by-default exception: alongside its
link-out channel, the optional read-only listing reader can be enabled under
`[linkedin]`. It is never authenticated, never logged in, never applies, runs at
a low rate, is against LinkedIn's terms, is best-effort, and may stop working at
any time. It is not the default LinkedIn path and it is not a licence to scrape
any other manual-only source. Its postings, like every link-out posting, remain
review-only: prepared and queued, never auto-submitted.

**Internshala matters most**: its listings
carry explicit start windows ("can start the internship between 13th Jan'26 and
17th Feb'26") and it has the largest AI/ML internship inventory in India, but its
terms expressly prohibit automated extraction. When you find a posting there, add
it by hand and jobpilot runs its normal requirement extraction, matching, tailored
resume, cover letter and packet generation:

```bash
python -m jobpilot --config config.toml link-out add \
  --source internshala \
  --url "https://internshala.com/internship/..." \
  --title "Machine Learning Intern" \
  --company "Acme" \
  --location "Bengaluru, India" \
  --description-file jd.txt
```

The result is a ready-to-apply packet (resume PDF, cover letter PDF, direct link,
matched and gap JD keywords) in the review queue. Manual-source postings are
**always review-only**: the pipeline never auto-submits them, and re-adding the
same URL dedupes on a stable id derived from it. The search links are configurable
under `[link_out]` in `config.toml`.

The local-file adapter (`[sources.local]`) reads a JSON posting list and exists for
offline verification, fixtures and the demo; it is a demonstration that sources are
genuinely pluggable. Because it can carry a structured `apply_email`, it is also the
demonstrable automatic-application path: seed a posting with `apply_email` set,
configure SMTP, and a strong match is submitted by the email channel. None of the
default ATS discovery sources supply an application address, so without that (or
another source that does) strong matches are queued for review rather than applied.

---

## Tests

```bash
python -m unittest discover -s tests -t .
```

Coverage includes filtering, matching (matched vs. gap terms), dedupe, the daily cap,
guardrails (missing required field, LinkedIn review-only, dry-run), the
"never invent content" rule, the `present` selection rules (a non-technical
India-eligible internship is excluded and a technical one is included), the
one-page fit (an over-long resume is reduced to one page, cutting preserves
every fact, and the bounded-attempts fallback flags review with the measured
count), the robots.txt gate (rule precedence and the fail-closed case), deadline
extraction/urgency/staleness, the typographic-folding parseability comparison,
contact-detail verification, the skill-gap heatmap, and the lifecycle (archive
idempotence, outcome recording, follow-up cadence and the stale sweep). An
integration test compiles a tailored resume with the real LaTeX engine and
asserts the PDF is parseable (skipped when the toolchain is unavailable).

## Limitations

- The public ATS endpoints are undocumented and may change; adapters are per-source
  and isolated for that reason.
- Applying automatically is inherently channel-specific. The default
  `adapter = "auto"` submits strong matches by email to an explicit, structured
  application address supplied by the source (optionally narrowed by
  `apply.submission.email_allowlist`); free-text addresses in a job description are
  never used, and SMTP must be configured. Greenhouse, Lever, Ashby and Workable do
  not expose a documented, verifiable public application endpoint, so they are never
  submitted programmatically: they are prepared as link-out packets (resume, cover
  letter, direct apply link) and routed to the review queue. `adapter = "none"`
  routes everything to review. There is deliberately no generic web-form filler, and
  an unknown adapter value is rejected.
- The window check is a best-effort inference from posting text; postings rarely
  state exact dates. A posting with no timing signal is discovered, scored and shown,
  but is only ever eligible for review, never auto-apply. Set
  `filter.allow_unknown_window = true` to allow auto-apply of unknown-window
  internships.
- Discovery covers four ATS board APIs (only the tokens you configure), four
  catalogue/search sources (Himalayas, Unstop, Workable global, The Muse) and an
  optional read-only LinkedIn reader, plus the manual link-out channel. The
  search sources are best-effort: endpoints can change, some are undocumented,
  and their intern/India filters vary in precision, so the hard filters still run
  over every hit.
