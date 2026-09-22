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
   aborts the run. Sources whose terms forbid automation are never scraped:
   they are surfaced as **link-out** channels instead (see below).
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
   generated PDFs, plus a CLI to list, approve and export.

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

---

## Matching: a documented rubric, not an oracle

The score is a transparent weighted rubric. It exists to **rank postings for human
review**; it does **not** predict hiring outcomes, and should not be read as one.

Components (weights configurable under `[match.weights]`):

| Component | What it measures |
| --- | --- |
| `skill_coverage` | share of the JD's extractable skills the profile genuinely supports |
| `role_relevance` | overlap with target domains (AI/ML, software, research), with a title boost |
| `location_fit` | India / remote-eligible-from-India |
| `window_fit` | Jan-Jun plausibility, weighted by how explicit the dates are |
| `seniority_fit` | clearly an internship vs. not |

Every score is stored with its reasons, its component breakdown and its formula.
Keyword coverage is exact: supported JD terms are listed as **matched**; terms the
profile does not support are listed as **gaps** and are **never inserted** into the
resume. Bands: `strong` (auto-apply), `shortlist` (tailor + review), `reject`.

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
  text. If a required section or keyword is unextractable, generation fails and the
  application is forced to review.
- **Red-flag critique**: a deterministic advisor proposes operator-facing
  suggestions. They are suggestions, never facts, and never alter content. They are
  stored with the application record. (An optional LLM-advisor hook is a documented
  follow-up, not part of v1.)

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
routes it to human review instead of discarding it.

| Source | Endpoint | Limitations |
| --- | --- | --- |
| **Greenhouse** | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | Undocumented public endpoint; may change shape or rate-limit; only boards whose token you configure. Carries each job's typed employment-type metadata for the shared filter; never drops on it. |
| **Lever** | `api.lever.co/v0/postings/{token}?mode=json&commitment=Intern` | Documented `commitment` field (case-sensitive); the adapter requests `commitment=Intern` as a search scope and carries each job's typed `commitment` for the shared filter. Only boards whose token you configure. |
| **Ashby** | `api.ashbyhq.com/posting-api/job-board/{token}` | Undocumented; carries each job's typed `employmentType` for the shared filter; never drops on it. Only configured tokens. |
| **Workable** (per-account) | `apply.workable.com/api/v1/widget/accounts/{token}?details=true` | Public widget API; some boards return zero jobs; only configured tokens. Carries each row's typed `employment_type` for the shared filter; never drops on it. |
| **Himalayas** | `himalayas.app/jobs/api/search?employment_type=Intern&country=India` | Free, no key; integer `page` pagination (20/page). Terms require a visible link back to himalayas.app and the attribution "data sourced from Himalayas". India intern volume is modest and includes stale/volunteer entries. |
| **Unstop** | `unstop.com/api/public/opportunity/search-result?opportunity=internships&page=N` | India-native live internship feed (~10,000 rows); its `robots.txt` explicitly allows `/api/public/*`. 10/page. Typed `start_date`/`end_date` are mapped into the window check; a lone date is left as "unknown window" (review-only). |
| **Workable** (global search) | `jobs.workable.com/api/v1/jobs?query=intern&location=India` | **Undocumented** cross-company search; paginates with an opaque `pageToken`. `robots.txt` sets `ai-train=no` (data must not be used for model training). Its `employmentType` is unreliable, so it relies on Workable's own server-side `query=intern` search. |
| **The Muse** | `themuse.com/api/public/jobs?page=N&level=Internship&location=India` | Free public API (500 req/hr unauthenticated); typed `level=Internship`. The `location=India` parameter is loose, so the hard location filter rechecks every hit. |
| **LinkedIn** (optional reader, disabled by default) | public guest job-search HTML | **Against LinkedIn's Terms of Service; best-effort; may stop working at any time.** An off-by-default, captain-authorized exception: link-out is the default LinkedIn path. Never logs in, never authenticates, never applies, low rate, degrades gracefully. Never auto-submitted. |

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
"never invent content" rule, and an integration test that compiles a tailored resume
with the real LaTeX engine and asserts the PDF is parseable (skipped when the
toolchain is unavailable).

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
