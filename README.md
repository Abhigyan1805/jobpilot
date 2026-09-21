# jobpilot

Automated internship-search workflow: discovery across public job-board endpoints
(Greenhouse, Lever, Ashby, Workable) plus an optional read-only LinkedIn listing
feed, JD-to-profile matching, tailored resume generation from a master profile,
automatic application to strong matches with a review queue for the rest, and a
durable application tracker.

Targeting: internships running January to May/June, open to candidates in India
or remote-eligible from India.

## Status

Initial scaffold. The pipeline is under construction; see the repository history
and the task brief for what has landed.

## Safety model

- Applies only to strong matches, with dedupe, a daily cap, and a durable record
  of every attempt.
- Never submits a form with a required field it cannot answer.
- Generated resumes select and re-emphasise real profile content only; they never
  invent facts, employers, dates or metrics.
- `--dry-run` exercises discovery, matching and tailoring without submitting.
