---
description: Interactively prune pins from CLAUDE.md via paginated AskUserQuestion
---

## What this command does

Presents the curator with the current evictable-pin list, asks which
one (or none) to remove, **archives the selected pin to long-term memory
and verifies the archive before removing anything**, then removes it.
Useful after `/PACT:pin-memory` is denied by the count cap: use
`/PACT:prune-memory` to demote an existing pin to long-term memory, then
retry the add.

Demotion is not deletion. A pin leaves `## Pinned Context` only once its
content is provably somewhere else — see [Step 3](#step-3--archive-the-selected-pin).

The `pin_caps_gate` PreToolUse hook ALLOWS the resulting Edit because
the pin count strictly decreases (net-worse predicate: pre has ≥N
pins, post has N-1 — not worse, so allow). **The hook cannot enforce the
archive**: it sees a count decrease and allows it, whether or not Step 3
ran. Step 3 is enforced by this file and by nothing else, which is why
every exit below emits a journal event — an invocation that evicts a pin
while emitting nothing is the one state that should never occur.

## Process

### Step 1 — Read the evictable-pin list

Invoke the advisory CLI to get the current state:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_pin_caps.py" --status
```

The CLI emits a JSON payload with `evictable_pins`:

```json
{
  "allowed": true,
  "violation": null,
  "slot_status": "Pin slots: N/12 used, ...",
  "evictable_pins": [
    {"index": 0, "heading": "First Pin", "chars": 40, "stale": false, "override": false,
     "age_days": 60, "overdue": true},
    {"index": 1, "heading": "Second Pin", "chars": 30, "stale": true, "override": false,
     "age_days": null, "overdue": null},
    ...
  ]
}
```

`age_days` is computed from the pin's `<!-- pinned: ... -->` date comment;
`overdue` is true once that age reaches the staleness threshold. Both are
distinct from `stale`, which reports only that a `<!-- STALE: ... -->` marker
has been written into the body. A pin can be `overdue` without being `stale`.

**`age_days: null` is a third state and is NOT `overdue: false`.** It means the
pin carries no parseable date and its age is unknown. Surface it to the curator
as unknown rather than silently treating it as fresh — an undated pin is the one
most likely to have been sitting there longest.

If `slot_status` starts with `Pin slots: unknown (...)`, the CLI could
not parse CLAUDE.md. Report the reason, emit the skip event with outcome
`unknown_state`, and stop — do NOT attempt to evict from an unknown state.

If `evictable_pins` is empty, report "No pins to prune.", emit the skip
event with outcome `no_candidates`, and stop.

### Step 2 — Ask the curator which pin to prune

Present up to 3 candidate pins per `AskUserQuestion` call (plus a 4th
"Show more" or "Cancel" option). `AskUserQuestion` accepts at most 4
options per question and at most 4 questions per call, so 3 candidates
plus one navigation slot sits exactly at the option cap — this pagination
cannot be widened, only paged.

**Order `overdue` pins first** — they have outlived the horizon they were
pinned for and are the default prune candidates. Within the same overdue
bucket, Prefer STALE pins over fresh ones. Label shape:

```
AskUserQuestion(questions=[{
  header: "Pin prune",
  question: "Which pin to demote to long-term memory? (page N of M)",
  options: [
    {label: "Pin {index} — {heading}", description: "{chars} chars{, OVERDUE {age_days}d if overdue}{, age unknown if age_days is null}{, STALE if stale}{, OVERRIDE if override}"},
    ...
    {label: "Show more",                description: "Next page of candidates"}
       | {label: "Cancel",              description: "Do not prune any pin"}
  ]
}])
```

Pagination rules:
- **≤ 3 evictable pins**: present all + "Cancel".
- **> 3 evictable pins**: present 3 pins + "Show more" per page. The last page shows remaining pins + "Cancel".
- Label format: `Pin {index} — {heading}` (the index is the position in `evictable_pins`, not the line in CLAUDE.md).

If the curator picks "Cancel", report "Prune cancelled; CLAUDE.md unchanged.",
emit the skip event with outcome `cancelled`, and stop.

#### Justify the eviction

Once a pin is selected, ask the curator — as a plain question, not an
`AskUserQuestion` call, because a rationale cannot be enumerated as options
in advance — **what concrete next-session question this pin resolves**.

A justification MUST name a concrete question ("how do parsers scope their
reads in CLAUDE.md?") and cite the pin's answer ("use `_extract_managed_region()`").
It MUST NOT fall back to "load-bearing", "accurate", "important", or similar
non-discriminating generalities. If the answer is one of those, say so and ask
again — a pin nobody can frame a question for is a pin that has stopped earning
its slot, and that is the finding, not an obstacle.

This is a discipline rule you apply by reading the answer. It is deliberately
NOT a banned-word check: a word list is satisfied by any synonym, and a
mechanical-looking gate suppresses the scrutiny a prose rule invites.

#### Re-confirm the other overdue pins

For pins that are `overdue` but were NOT selected, batch re-confirmation into
`AskUserQuestion` calls of up to 4 questions each (with 6 overdue pins that is
2 calls, not 6). Ask whether each is still worth its slot. For each pin the
curator keeps, collect a one-line reason and extend its date comment in place:

```markdown
<!-- pinned: 2026-05-26, reconfirmed: 2026-07-25 because {concrete reason} -->
```

The reason MUST be single-line and MUST NOT contain `>` — the parser reads the
comment as `<!--\s*pinned:\s*[^>]+?-->`, so a `>` truncates it. Re-confirming
resets the clock: age computes from the `reconfirmed:` date once present. The
reason is free text and is subject to the same concreteness rule above.

Scope note: justification is asked for the pin being evicted and for
age-flagged borderline pins only — **not for every retained pin**. At 12 pins
the exhaustive form serialises into roughly 20 prompts to evict one pin, and a
curator facing 20 prompts answers with exactly the generalities this step
exists to forbid.

### Step 3 — Archive the selected pin

Demote the pin into long-term memory and **verify it arrived** before anything
is removed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/archive_pin.py" --index N
```

The script always exits 0 and reports its verdict inside the JSON payload — a
non-zero exit is a crash, not a verdict, and is treated as `UNEVALUABLE`. It
writes the pin block to pact-memory, re-fetches it by the returned `memory_id`,
and confirms the block is present byte-for-byte:

```json
{"outcome": "ARCHIVED", "memory_id": "<32-hex>", "heading": "...", "chars": 412, "contained": true}
{"outcome": "NOT_ARCHIVED", "memory_id": "<32-hex>|null", "reason": "<why>", "heading": "..."}
{"outcome": "UNEVALUABLE", "reason": "<why>", "heading": "...|null"}
```

**Check the returned `heading` against the pin the curator chose in Step 2.**
`--index N` is a position in `evictable_pins`, and the script re-resolves that
index against CLAUDE.md as it reads the file. If anything changed the pinned
section in between, the index now denotes a different pin — and the archive
would succeed, and its containment check would pass, for the wrong pin. On any
mismatch, stop and re-run from Step 1. A verification that measures the right
property on the wrong object reports success and proves nothing.

`heading` is always present as a key. It is the pin's real parsed heading, never
an echo of the index you passed — an echo would make this check compare the
index against itself and pass unconditionally. It is `null` only on
`UNEVALUABLE` where no pin could be resolved at all (unreadable CLAUDE.md, no
pinned section, index out of range). **Read `null` as unresolvable and take the
escape hatch below — never as a mismatch**; there is no heading to disagree with.

Then act on the verdict — only one of the three permits removal:

| Verdict | Meaning | Action |
|---|---|---|
| `ARCHIVED` | the pin's bytes are provably in long-term memory | proceed to Step 4 |
| `NOT_ARCHIVED` | the archive definitively failed | **refuse**; report `reason`; emit `archive_refused`; stop |
| `UNEVALUABLE` | could not tell — CLI absent, crash, timeout, unreadable file | **refuse**; report `reason`; offer the escape hatch below |

**Do NOT warn-and-proceed on a failed archive.** Elsewhere in PACT a failed
journal write degrades to a warning because the journal survives independently
of the thing being written about. Here nothing survives: proceeding past a
failed archive destroys the only copy of the pin, and CLAUDE.md is frequently
git-ignored, so there may be no commit to recover it from. The degradation is
to keep the pin, not to keep going.

#### Escape hatch — `UNEVALUABLE` only

A curator at the cap with a broken memory CLI must not be trapped between a
command that will not add and a command that will not remove. So on
`UNEVALUABLE` — and never on `NOT_ARCHIVED`, where the failure is definite:

1. Read the pin block from CLAUDE.md and **print it verbatim into the
   conversation**, under a heading stating it is the only remaining copy.
   (If CLAUDE.md cannot be read, there is nothing to print and nothing to
   evict — refuse outright and stop.)
2. Ask the curator to confirm they have captured it elsewhere. This is an
   explicit acknowledgement — never a default, never inferred from silence.
3. Only on that acknowledgement, proceed to Step 4.
4. Emit the skip event with outcome `unverified_eviction`, so the unverified
   eviction is auditable.

The hatch exists to make **the pin survive**, not to make the eviction proceed.

### Step 4 — Remove the selected pin

**Proceed only if Step 3 returned `ARCHIVED` with a matching `heading`, or if
the `UNEVALUABLE` escape hatch was explicitly acknowledged.** If neither holds,
this step does not run — go back and report the refusal. Do not remove a pin
you cannot show is somewhere else.

Read the current CLAUDE.md. Locate the pin block for the selected
`{heading}`:

- The date comment immediately preceding `### {heading}` (if any).
- The `### {heading}` line itself.
- The body up to (but not including) the next `### ` heading OR the
  end of the `## Pinned Context` section.

Use the `Edit` tool to remove the full block, preserving surrounding
blank lines (one blank line between remaining pins). The `pin_caps_gate`
hook ALLOWS the edit because `len(post_pins) < len(pre_pins)` — strictly
better, not worse.

### Step 5 — Report

- Report: "Pruned pin {index}: {heading} — archived as {memory_id}." Name the
  `memory_id` so the curator can retrieve the demoted content later.
- Emit `pin_pruned` carrying that `memory_id`, the pin's `heading`, and
  `pin_count`. It has no `outcome` field — the event's existence IS the
  outcome. An escape-hatch eviction never reaches this event; it already
  emitted `pin_prune_skipped` with `unverified_eviction` back at Step 3.
- Commit the change — then **confirm `CLAUDE.md` is actually in the resulting
  commit.** Where a project git-ignores `CLAUDE.md` (a bare `CLAUDE.md` line in
  `.gitignore` matches at any depth), an explicit `git add CLAUDE.md` errors and
  a commit whose only change is `CLAUDE.md` reports "nothing to commit" — both
  loud. The silent case is a blanket `git commit -a` / `-am` that also picks up
  other changed files: it succeeds, exits 0, and omits `CLAUDE.md`. Verify the
  file is in the commit rather than trusting the commit's exit status, and if it
  is not, report the prune as applied to the working file but not
  version-controlled. NEVER use `git add -f`.

## Telemetry

Every exit emits exactly one journal event, so that an invocation which removed
a pin while emitting nothing is detectable after the fact. That is the only
check on Step 3 there is — the hook cannot enforce the archive, so the audit
trail is what makes a skipped archive visible at all.

| Exit | Event | `outcome` |
|---|---|---|
| Curator picks Cancel | `pin_prune_skipped` | `cancelled` |
| `evictable_pins` empty | `pin_prune_skipped` | `no_candidates` |
| `slot_status` unknown | `pin_prune_skipped` | `unknown_state` |
| Archive refused (Step 3) | `pin_prune_skipped` | `archive_refused` |
| Escape-hatch eviction | `pin_prune_skipped` | `unverified_eviction` |
| Pin archived and removed | `pin_pruned` | — (no `outcome` field) |

`pin_prune_skipped` carries `outcome`, `pin_count` at the time of the skip, and
`age_distribution` (oldest / newest / median `age_days`, over pins whose age is
known). `reason` is optional — a bare Cancel does not elicit one, and emitting a
field with nothing behind it is a report with no measurement in it.

`pin_pruned` carries `heading`, the `memory_id` of the archive, and `pin_count`
— the count BEFORE the removal, matching `pin_prune_skipped`'s "count at the
time of the decision" so the two events share one referent and stay directly
comparable. The post-eviction count is derivable, since this command never
evicts more than one pin per invocation. It carries no `outcome` field: only
required fields are validated, so an extra one would be written into the audit
trail looking authoritative while guaranteed by nothing. The `memory_id` is the
point of the event — it makes the claim checkable by fetching it, rather than
merely asserted.

**Reading the trail: an eviction is a UNION, not a single event.** An
escape-hatch eviction removed a pin but is filed under the skip event, because
it has no `memory_id` to carry and `pin_pruned` requires one:

    evictions = pin_pruned  UNION  (pin_prune_skipped WHERE outcome = "unverified_eviction")

The second arm is exactly the set of evictions with no archive record. An audit
that queries only `pin_pruned` under-counts evictions and, worse, misses the
ones that went unverified — the population it most needs to see.

Substitute `{session_dir}` from the `- Session dir:` line in CLAUDE.md's
`## Current Session` block, falling back to `pact-session-context.json` for that
one field. **If neither resolves, skip the emit, note it in the report, and
carry on** — telemetry never blocks a prune. A failed audit write that refused a
legitimate eviction would be a data-loss bug arriving from the observability
layer, which is the one place nobody is watching for it.

```bash
set -e
trap 'rc=$?; echo "[JOURNAL WRITE FAILED] prune-memory.md (bash line $LINENO): \"${BASH_COMMAND%%$'\''\n'\''*}\" exit=$rc" >&2; exit $rc' ERR
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shared/session_journal.py" write \
  --type pin_prune_skipped --session-dir '{session_dir}' --stdin <<'JSON'
{"outcome": "cancelled", "pin_count": 12, "age_distribution": {"oldest": 60, "newest": 3, "median": 33}}
JSON
```

The heredoc delimiter is quoted (`<<'JSON'`) so bash performs no expansion
inside it — a curator's reason containing an apostrophe or a backtick passes
through verbatim instead of closing the quote and aborting the write under
`set -e`. Construct JSON-valid string content (escape `\"`, `\\`, and control
characters).

## Notes

- This command NEVER evicts more than one pin per invocation. Run it
  multiple times to prune multiple pins — this keeps each evict/retry
  cycle auditable.
- Stale pins (marked with `<!-- STALE: Last relevant YYYY-MM-DD -->`)
  are surfaced with a `STALE` tag in the option description. Prefer
  pruning stale pins before non-stale.
- Overdue pins (`age_days` past the threshold) are surfaced with an
  `OVERDUE` tag and sorted first. `stale` and `overdue` are independent
  signals — a pin can be either, both, or neither.
- Override-carrying pins (with `pin-size-override` rationale) are
  surfaced with an `OVERRIDE` tag. These are load-bearing verbatim
  content; prune only with deliberate intent.

## See also

- `/PACT:pin-memory` — add a new pin (hook enforces caps).
- `hooks/pin_caps_gate.py` — the authoritative cap enforcer.
