---
description: Report the cross-session backlog reconciled against git, the tracker and pact-memory, then steer or record what the user decides
argument-hint: "[optional: e.g., add <title>, that one is done, do those two together]"
---

## What this command is for

The backlog holds **what the user intends to do next**, in order. It is not a
view of the tracker, not a filter over it, and nothing here syncs the two. The
tracker holds everything that is wrong or wanted; an item enters the backlog by
a deliberate act.

You are the **sole writer**. The user never hand-edits the file, so their only
view of it is what you report. Reconcile before you steer.

## Mode

- **Without arguments** (`/PACT:next`): report the reconciled backlog and
  recommend what to do next.
- **With arguments**: apply what the user asked for, then report.

## Step 1 — Reconcile and report

Run:

```bash
python3 "{plugin_root}/hooks/shared/backlog.py" show
```

This resolves every drift class in one pass: refs against the tracker in a
single batched query, `plan` paths against the project root, `memory` ids
against the store, staleness, and dangling relational ids.

Read the output and report to the user in plain language:

1. What is `active` right now.
2. The next two or three `planned` items by rank.
3. Every flag, with what you think it means.

Exit code 2 means the file could not be read. Report that and go to Step 4.

**Never cite an item's `id` to the user.** Ids exist so the relational fields
survive a retitling; they mean nothing to a person. Refer to items by title.

## Step 2 — Propose, never repair

Drift is **reported and never silently repaired**. A flag is a proposal:

| Flag | Propose |
|---|---|
| ref is closed but the item is not `done` | mark it done |
| ref is unverifiable | check the ref by hand, or clear it |
| `blocked_by` names an item already done | unblock it |
| a relational field names an unknown id | drop the dangling reference |
| two exclusive items are both `active` | pause one |
| active with no branch or worktree | confirm the work is still live |
| active and untouched for a fortnight | confirm it is still live |
| `plan` does not resolve | find where the document moved |
| a `memory` id no longer resolves | drop it or replace it |
| a `memory` record changed after linking | re-read it before relying on it |

An automatic fix is you overwriting the user's recorded intent on the strength
of an inference. Put the proposal to the user with `AskUserQuestion` and let
them decide.

## Step 3 — Write what the user decides

Add an item:

```bash
python3 "{plugin_root}/hooks/shared/backlog.py" add "<title>" \
  --rank <n> --ref "<opaque tracker reference>" \
  --note "<one line, your voice>"
```

Change one:

```bash
python3 "{plugin_root}/hooks/shared/backlog.py" set <item-id> \
  --status done
```

Both accept `--status`, `--rank`, `--ref`, `--plan`, `--note`, and the
repeatable `--memory`, `--blocked-by`, `--batch-with`, `--exclusive-with`.
`--ref none` clears a ref.

Field rules the writer enforces, and a violation is REFUSED with nothing
written rather than quietly adjusted:

- `note` is capped at 200 characters. Anything longer is a mission brief, and
  mission briefs are what rot. Put it in the tracker issue or in pact-memory
  and point at it.
- `note` is written in YOUR voice, never in the user's first person. A relay in
  the user's first person gains an authority it never had and no later reader
  can strip it off. Where the distinction carries weight, mark it: `user
  ruled:` or `inferred:`.
- `plan` is repo-relative. An absolute path captured inside a worktree points
  into a directory that `git worktree remove` deletes.
- `memory` holds at most 5 record ids. The cap is a curation forcing-function,
  not a storage limit.
- An item with no `ref` is fully supported and is never second-class.

Write when work lands — a PR merges, `/PACT:peer-review` completes,
`/PACT:wrap-up` or `/PACT:pause` runs — and when the user steers. Not on every
small action: the file's value is its stability.

## Step 4 — When the file is corrupt

The read path reports a corrupt backlog and changes nothing. Repair is a write,
and it is yours:

```bash
python3 "{plugin_root}/hooks/shared/backlog.py" repair
```

This RENAMES the corrupt file aside and reports where it went. It never
overwrites and never deletes, so a wrong rebuild loses nothing. Tell the user
the moved-aside path, then rebuild the items from what you can recover.

## Store location

The file lives under the directory `get_backlog_dir()` resolves in
`hooks/shared/paths.py`, one JSON file per project. Ask that function rather
than writing the path out — it is home-pinned rather than config-dir-pinned, so
one project keeps one backlog across every backend the user switches between.

The session-start block that surfaces this backlog automatically is a pure file
read. It reports a corrupt or unresolvable store loudly and never writes.
