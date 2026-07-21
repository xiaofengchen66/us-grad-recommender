# Automated PR Review Loop

**Phase 1 (this document, implemented): automated review, posted directly
to the PR. Phase 2 (proposed below, not implemented): automated repair of
accepted findings.** Approved 2026-07-21 with the GitHub App authentication
option (Option A) — see the rationale in §3.

---

## 1. What this replaces

Previously: primary agent opens a PR → human manually runs `/code-review`
and/or briefs a second Claude Code session with `docs/REVIEW_AGENT_PROMPT.md`
→ human copies findings back. This workflow removes the "copy findings
between sessions" step: review now runs automatically on every push and
lands as a comment on the PR itself.

It does **not** remove the human from the loop entirely — Phase 1 only
automates the *review*, not the *fix*. Applying accepted findings is still
a human (or primary-agent) action until Phase 2 exists.

---

## 2. Architecture

```
pull_request: opened / reopened / synchronize / ready_for_review
  (or workflow_dispatch with a pr_number input — manual forced re-review)
       │
       ▼
concurrency group "pr-review-<PR#>" — a new push cancels any in-flight
review for the same PR, so you never pay for reviewing a commit that's
already stale
       │
       ▼
"Resolve PR number and head SHA" — normalizes both trigger types to the
same (pr_number, head_sha) pair
       │
       ▼
"Check if this commit was already reviewed" — greps existing PR comments
for the marker `automated-review-bot sha=<head_sha>`; skipped entirely
for workflow_dispatch (manual re-run always forces a fresh review)
       │  (not yet reviewed, or forced)
       ▼
checkout (default pull_request ref, fetch-depth: 1)
       │
       ▼
anthropics/claude-code-action@v1 — reads docs/FULL_HANDOFF.md,
docs/REVIEW_AGENT_PROMPT.md, docs/PHASE_2_CATALOG_DESIGN.md, and the PR
diff (via `gh pr diff`/`gh pr view`, not by checking out untrusted code as
executable — see §5)
       │
       ▼
posts exactly one new PR comment:
  <!-- automated-review-bot sha=<head_sha> -->
  REVIEW_RESULT: BLOCK | READY_AFTER_FIXES | READY_TO_MERGE
  BLOCKING: / HIGH: / MEDIUM: / TEST_GAPS: / OPTIONAL:
       │
       ▼
workflow ends — no merge step exists anywhere in this workflow
```

Each review posts a **new** comment rather than editing one in place, so
the PR keeps a full audit trail of every review across every push — this
was a deliberate choice over the action's built-in `use_sticky_comment`
option, which would overwrite history instead of preserving it.

---

## 3. Authentication: GitHub App (Option A)

**Decision**: use the official [Claude GitHub App](https://github.com/apps/claude)
rather than a narrowly-scoped `github_token`, because the long-term goal
(Phase 2 and beyond) is a fully automated review-and-repair loop, which
will need to push commits to feature branches — something the App is
built for and a bare `permissions:`-scoped `GITHUB_TOKEN` is not meant to
do safely across workflows. Using the App now means Phase 2 doesn't
require re-doing this authentication setup.

**Important nuance worth understanding, not just accepting**: the
`permissions:` block in `claude-pr-review.yml` (`contents: read,
pull-requests: write, id-token: write`) scopes the *ambient*
`GITHUB_TOKEN` used for this workflow's own steps (checkout, the
idempotency check). It does **not** limit what the Claude GitHub App's own
installation token can do — that token is obtained through a separate
mechanism (the App's installation credentials) and carries whatever
permissions the App was granted at install time, which per Anthropic's own
docs is broader: **Contents (Read & Write), Pull Requests (Read & Write),
Issues (Read & Write)**.

This means the real enforcement of "review-only, no writes, no merge" in
this design is **not** the workflow's `permissions:` block — it's the
`--allowedTools` restriction on the Claude Code run itself (§5). That's a
real, CLI-enforced technical boundary (a disallowed tool call simply
fails), not a soft prompt instruction, but it is one level less absolute
than "the token is physically incapable of writing." If a harder guarantee
is ever needed for a specific workflow, that would mean going back to a
narrowly-scoped `github_token` for that one workflow — worth knowing this
tradeoff exists rather than assuming the permissions block alone is doing
the job.

### 3.1 Installation steps

1. You must be a repository admin.
2. Easiest path: in a terminal, run `claude` then `/install-github-app`,
   and follow the prompts — this installs the GitHub App on this
   repository and walks through adding the required secret.
3. Manual alternative: visit https://github.com/apps/claude, click
   "Install", select `xiaofengchen66/us-grad-recommender`, grant the
   requested permissions (Contents, Pull requests, Issues — all
   Read & Write, as listed above).
4. Add the `ANTHROPIC_API_KEY` secret: repo Settings → Secrets and
   variables → Actions → New repository secret → name it
   `ANTHROPIC_API_KEY`, value from your Anthropic Console API key. Never
   commit this key to the repo.

### 3.2 Permissions summary

| Grantee | Scope | Why |
|---|---|---|
| Workflow's `GITHUB_TOKEN` (`permissions:` block) | `contents: read`, `pull-requests: write`, `id-token: write` | Covers this workflow's own steps (checkout, idempotency check) |
| Claude GitHub App (installed separately) | Contents R&W, Pull Requests R&W, Issues R&W | What `claude-code-action` actually operates with; broader than the block above, per §3 |
| Claude Code CLI tool access (`--allowedTools`) | `Read, Grep, Glob, Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh pr comment:*)` | The actual operative restriction — no edit/write/push/merge tool exists to call |
| `ANTHROPIC_API_KEY` secret | N/A (not a GitHub permission) | Anthropic API billing/auth only |

---

## 4. Cost implications

Two components:

- **Anthropic API usage** — one Claude Code run per un-reviewed commit
  (reading 3 docs + the PR diff + producing a structured review). Actual
  per-run cost depends on PR size and hasn't been measured yet on this
  repo; report real numbers after the first several runs rather than
  estimating blind.
- **GitHub Actions minutes** — a few minutes of `ubuntu-latest` runner
  time per run; negligible at this repo's current PR volume.

Cost controls already built in: concurrency cancellation (a rapid second
push cancels the stale in-flight review before it finishes) and the
idempotency check (zero Claude calls for a commit that's already been
reviewed). Cost scales with number of distinct commits pushed to open
PRs, which is expected and accepted, not a bug.

---

## 5. Security boundaries

Restated from the design discussion, now as implemented:

- **Trigger**: plain `pull_request` (not `pull_request_target`) — GitHub
  does not pass repository secrets to `pull_request`-triggered workflows
  on fork PRs. Currently moot (this is a private, single-owner repo) but
  the correct default regardless.
- **No code modification, ever**: `--allowedTools` has no `Edit`/`Write`.
  The tool call fails outright if attempted — this isn't a matter of the
  model "choosing" not to.
- **No commit, no push**: no `Bash(git commit:*)` or `Bash(git push:*)` in
  the allowlist.
- **No approval, no merge**: no `gh pr merge`/`gh pr review --approve` in
  the allowlist, and no such step exists anywhere in this workflow file.
- **No secret leakage**: `ANTHROPIC_API_KEY` only via `secrets.*`;
  `show_full_output` is left at its default (`false`), so tool output
  (which could echo file contents) isn't dumped into public Actions logs.
- **Prompt injection from PR content**: bounded impact by design — even if
  a crafted diff tried to manipulate the model into asserting
  `REVIEW_RESULT: READY_TO_MERGE`, that string has zero mechanical effect
  in Phase 1. Nothing reads the verdict and acts on it; a human (or, later,
  the Phase 2 repair workflow under its own separate constraints) does.
  This is exactly why Phase 2 needs its own security review before it
  exists, not an extension assumed safe by default.

---

## 6. How to disable

- **Temporarily**: repo → Actions tab → "Automated PR Review" workflow →
  "..." menu → Disable workflow. Re-enable the same way.
- **Permanently**: delete `.github/workflows/claude-pr-review.yml` (and,
  if no longer wanted at all, uninstall the GitHub App from repo Settings
  → Integrations → GitHub Apps).
- **Per-PR**: no per-PR opt-out exists in Phase 1; every non-draft PR gets
  reviewed on every push. If that's ever undesirable for a specific PR,
  disabling the workflow repo-wide is the only lever right now — a
  path-filter or label-based opt-out would be a small follow-up if needed.

---

## 7. How to rerun a review

GitHub's native "Re-run jobs" button will **not** produce a fresh review
of an unchanged commit — it re-runs the same job, which re-checks the
same marker for the same SHA, and skips again by design.

To force one: **Actions tab → "Automated PR Review" → "Run workflow" →
enter the PR number**. This uses the `workflow_dispatch` trigger, which
always bypasses the already-reviewed check.

(Pushing a new commit, even a trivial one, also triggers a fresh review
naturally via `synchronize` — no special action needed for that case.)

---

## 8. Phase 2 (proposed — not implemented)

A separate repair workflow, triggered once a human marks specific
Phase-1 findings as accepted (exact trigger mechanism — e.g. a specific PR
comment format or label — to be designed separately, not decided here).
Constraints, as approved:

- **Write access limited to the current feature branch only** — never
  `main`, never any other branch.
- **Automatic re-review after fixes**: pushing the repair commit to the
  feature branch naturally re-triggers the Phase 1 review workflow via its
  existing `synchronize` trigger — no new re-review mechanism needed,
  Phase 1 already does this.
- **Maximum of 2 repair cycles.** If the review still isn't
  `READY_TO_MERGE`/`READY_AFTER_FIXES` after 2 automated repair attempts,
  the workflow stops.
- **No merge capability, under any circumstance** — same permission
  philosophy as Phase 1, extended rather than loosened.
- **`NEEDS_HUMAN` after the cycle limit**: once the 2-cycle limit is hit
  without success, the workflow posts a clear `NEEDS_HUMAN` state (exact
  mechanism — label, comment, or both — to be decided during Phase 2
  design) and stops permanently for that PR until a human intervenes.
  It must not silently keep retrying, and must not merge whatever state
  the branch is in.

This section is a placeholder for a future, separately-approved design
pass — matching how Phase 1 itself went through an architecture-and-
security review before implementation. Building Phase 2 without that same
scrutiny would undercut the whole reason Phase 1 was designed this
carefully.
