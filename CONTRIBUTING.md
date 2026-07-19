# Contributing / agent workflow

This project is built issue-by-issue by AI coding agents (Claude Code,
Codex) with a human approving product assumptions and schema changes. Full
rationale is in [docs/FULL_HANDOFF.md](docs/FULL_HANDOFF.md) §22–25 — this
file just operationalizes it for this specific repo.

## Rules that apply to every change

See `docs/FULL_HANDOFF.md` §23 ("Mandatory Agent Rules") in full. The ones
most likely to bite you in this codebase specifically:

- Never invent institution, admission, ranking, or funding facts. If a
  value isn't in the source data, leave the field null and say so — don't
  infer or approximate it silently.
- Every imported fact carries provenance: source dataset, release year,
  and a verification/retrieval date (see `ipeds_year`, `source_dataset`,
  `last_verified_at` on `University`).
- Work one issue at a time. Don't fold unrelated features into a PR
  because "you're already in there."

## Branching

- `main` — always green (CI passing).
- `feature/<issue>` — implementation work.
- `review/<issue>` — a second agent's review pass, if used.

## Before opening a PR

Run the same checks CI runs:

```bash
ruff check .
mypy src
alembic upgrade head
pytest -q
```

For schema changes, also verify the migration is reversible:

```bash
alembic downgrade base
alembic upgrade head
```

## Review

A reviewer (human or a second agent using
`docs/REVIEW_AGENT_PROMPT.md`) reads the spec, the issue, the diff, and the
test output, then returns findings ordered: blocking, high, medium, test
gaps, optional. See `docs/FULL_HANDOFF.md` §25 for the full checklist
(provenance, master's/international eligibility, recency logic,
survivorship bias, migration safety, etc.).

## Picking the next issue

`docs/FULL_HANDOFF.md` §20–21 has the roadmap and the first-issue list.
Work is scoped issue-by-issue on purpose — don't ask an agent to "build the
whole platform" in one pass.
