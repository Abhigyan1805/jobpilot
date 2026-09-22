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
   tokens), plus an optional read-only LinkedIn listing reader that never logs in,
   never authenticates and never applies. Every source is a pluggable adapter behind
   one interface, and one source failing never aborts the run.
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
- **LinkedIn is never auto-submitted.** LinkedIn postings are discovered, ranked,
  tailored and packaged, then placed in the review queue with their direct apply
  link - you submit them yourself. The pipeline never authenticates and never
  touches your LinkedIn account.
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

All sources are read-only and unauthenticated. Source failures are isolated and
reported; the rest of the run continues.

| Source | Endpoint | Limitations |
| --- | --- | --- |
| **Greenhouse** | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | Undocumented public endpoint; may change shape or rate-limit; only boards whose token you configure. |
| **Lever** | `api.lever.co/v0/postings/{token}?mode=json` | Team/commitment fields vary; only configured tokens. |
| **Ashby** | `api.ashbyhq.com/posting-api/job-board/{token}` | Undocumented; compensation fields optional; only configured tokens. |
| **Workable** | `apply.workable.com/api/v1/widget/accounts/{token}?details=true` | Public widget API; some boards return zero jobs; only configured tokens. |
| **LinkedIn** (optional, disabled by default) | public guest job-search HTML | **Against LinkedIn's Terms of Service; best-effort; may stop working at any time.** Never logs in, never authenticates, never applies, low rate, degrades gracefully to the ATS sources. Never auto-submitted. |

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
- Discovery only sees boards whose tokens you configure - there is no global job
  search, and there is no public directory mapping companies to board tokens.
