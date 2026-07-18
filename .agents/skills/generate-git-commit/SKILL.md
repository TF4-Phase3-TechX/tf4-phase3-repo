---
name: generate-git-commit
description: Generates git commit messages from current diff or PR messages from last N commits using the embedded TF4 GitHub branch/commit/PR convention. Use when the user asks to auto-generate a commit message, git commit message, PR message, pull request body, release PR summary, or asks for "auto git commit".
---

# Skill: generate-git-commit

Generate a commit message or PR message from real git changes, using the embedded convention below. Do not invent another convention.

Never commit, push, stage, open a PR, rewrite history, or otherwise mutate repo state unless the user explicitly asks after seeing the generated message.

## Convention

### Commit message format

```
<type>[optional scope]: <description>

[optional body]
```

Allowed types:

| Type | Meaning |
|---|---|
| `fix` | bug fix |
| `feat` | new/updated feature |
| `build` | build system, Docker, dependency, package manager |
| `chore` | supporting work, no app behavior change |
| `docs` | documentation |
| `style` | formatting/whitespace/lint, no logic change |
| `refactor` | refactor, no new feature, no direct bug fix |
| `perf` | performance improvement |
| `test` | add/update tests |

Description: short, imperative mood if English, no trailing period. Body only when it explains "why".

Suggested scopes: `frontend`, `checkout`, `cart`, `payment`, `product-catalog`, `product-reviews`, `llm`, `kafka`, `db`, `helm`, `deploy`, `observability`, `ci`, `docs`

Example: `fix(payment): add readiness probe before receiving traffic`

If the diff is mixed (multiple unrelated concerns), recommend splitting into 2-4 separate commits instead of one.

### PR convention

Title uses the same format: `<type>(<scope>): <description>` — repo squashes/rebases, so this title often becomes the final commit message. Make it precise.

Required PR body template:

```md
## Summary
- 

## Why
- 

## Changes
- 

## Verification
- [ ] test/lint/build pass
- [ ] helm template pass if touching chart/deploy
- [ ] deploy/smoke test if touching runtime

## Risk & rollback
- Risk:
- Rollback:

## Scope
- Team: AIO01 / CDO04 / CDO07 / CDO08
- Area:
```

PR size: one clear goal per PR, ideally <300-500 line diff; keep docs-only separate from code/config changes; keep refactors separate from behavior changes.

## Pipeline

```
[0. Ask Mode] → [1. Fan-out Git Exploration] → [2. Synthesize] → [3. Convention Check]
```

### Stage 0 — Ask Mode

Ask the user to pick a mode before inspecting anything. Do not guess:

```
Choose mode:
1. Generate commit message from current git diff
2. Generate PR message from the last N commits

If 2, tell me N.
```

### Stage 1 — Fan-out Git Exploration

Spawn one read-only subagent (`Explore` type, or `general-purpose` with strict read-only instructions). It must not edit, stage, commit, push, create a PR, delete a branch, or rewrite history.

**Mode 1 — current diff.** Report: whether a staged diff exists (use staged diff only if so, else unstaged working tree diff; if no diff at all, say so — don't fabricate a message); files grouped by scope; user-facing/config/docs/test changes; likely type + scope; whether the diff is mixed and should be split; breaking change (yes/no + evidence); verification hints.

Useful commands: `git status --short`, `git diff --cached --stat`, `git diff --cached`, `git diff --stat`, `git diff`

**Mode 2 — last N commits / PR message.** Ask for N if missing. Report: commit list (hashes + subjects); aggregate diff summary; files grouped by scope; feature/fix/docs/config/test/runtime impact; likely PR title; PR body content for each required section; breaking change (yes/no + evidence); verification hints. If `HEAD~N` doesn't exist, use what's available and state the limitation.

Useful commands: `git log --oneline -n <N>`, `git diff --stat HEAD~<N>..HEAD`, `git diff HEAD~<N>..HEAD`

### Stage 2 — Synthesize

Use only the embedded convention and the subagent's evidence — no unsupported claims.

**Commit message output:**

```
Recommended commit message:

<type>(<scope>): <description>

[optional body]

Why:
- type: ...
- scope: ...
- evidence: ...

Optional alternatives:
- ...
```

**PR message output:**

```
Recommended PR title:

<type>(<scope>): <description>

Recommended PR body:
[filled template from above]

Why:
- title type/scope: ...
- main areas: ...
- risk: ...
```

### Stage 3 — Convention Check

Before answering, verify: type is one of the 9 allowed; scope is from the list or intentionally omitted; no trailing period; PR body uses the exact template sections; text reflects real diff/commit evidence; no mutating command was run.

## Hard safety boundaries

Never run these unless the user explicitly asks after seeing the generated message, and only after they confirm the exact message:

```
git add · git commit · git push · gh pr create
git branch -d/-D · git reset · git rebase · git tag · git merge
```

## Response style

Message first, explanation short. For a mixed diff:

```
Diff mixed. Better split:
1. docs(...): ...
2. fix(...): ...
```

No essays, no git lecture.
