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

## Multiple agent sessions sharing this repo

As of 2026-07-31 this is a real, not hypothetical, situation: more than one
independently-launched Claude Code session can be pointed at this same
checkout at the same time (e.g. one session building a feature while
another reviews or builds something else). A few things follow from that:

- **There is no live agent-to-agent messaging channel.** `SendMessage`
  only reaches agents spawned within the *same* session's orchestration
  tree (via the `Agent` tool) — it cannot reach a separate,
  independently-launched Claude Code process, confirmed by trying it
  2026-07-31 (`"No agent named 'reviewer' is reachable..."`). Coordination
  between independently-launched sessions is **manual relay by the human**,
  or **async via PR comments** — nothing else is wired up. Don't assume
  otherwise.
- **Check before you touch a branch.** Before switching branches, committing,
  or pushing, run `git status` and `git log -3` on the branch you're about
  to touch. If there's a commit newer than a few minutes that you don't
  recognize, another session is very likely actively working there —
  don't check it out, don't push to it, don't edit its files. Wait, or ask
  the human.
- **Use a separate `git worktree` for unrelated work**, rather than
  switching branches in the shared working directory, when another
  session might be mid-edit. Branch-switching changes every file in the
  working tree out from under whatever the other session currently has
  open; a worktree (`git worktree add <path> -b <branch> origin/main`)
  gives you an isolated directory on its own branch without touching the
  shared one at all.
- **Check `gh pr list` before starting substantial work** to avoid two
  sessions independently building the same thing, or one session's fix
  landing on top of another's in-flight, uncommitted changes.
