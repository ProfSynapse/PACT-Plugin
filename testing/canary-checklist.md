# Canary Verification Checklist

This checklist defines a 3-tier verification process for PRs that touch `pact-plugin/`. Each tier adds a layer of confidence that protocol changes have not introduced regressions.

**When to apply**: Any PR that modifies files under `pact-plugin/` (protocols, commands, agents, skills, hooks).

---

## Tier 1: Automated Verification

Run all verification scripts from the repository root. Every PR touching `pact-plugin/` must pass all four.

```bash
bash scripts/verify-protocol-extracts.sh
bash scripts/verify-scope-integrity.sh
bash scripts/verify-task-hierarchy.sh
bash scripts/verify-worktree-protocol.sh
```

**Expected output**: Each script prints one result line for each check, prefixed with `✓` or `✗`, then a summary block. `verify-protocol-extracts.sh` also prints a `VERIFY-CALL: <file>` line before each extract it compares. That line has no prefix and is not a result line. The other three scripts do not print it.

```
=== Summary ===
Passed: N
Failed: 0

VERIFICATION PASSED
```

Any script exiting with `VERIFICATION FAILED` (exit code 1) means the PR has broken a protocol invariant and must not be merged.

### Checklist

**How to read these counts.** Each number is the `Passed: N` value of a run that ends with `Failed: 0`. It is the number of checks the script runs. Three of the four counts do not change. The `verify-scope-integrity.sh` count moves with the number of files in `pact-plugin/agents/`, and its row gives the rule that makes it checkable. The four rows follow:

- [ ] `verify-protocol-extracts.sh` passes (19 checks) -- each SSOT extract agrees with its section, anchored by H2 heading text. FIXED count: one check for each `verify` call in the script. `pact-plugin/tests/test_canary_checklist_count.py` reads this number and compares it against a run, so an edit to this row alone reddens that test.
- [ ] `verify-scope-integrity.sh` passes (86 checks) -- cross-references, naming conventions, nesting limits, worktree integration, memory hooks, executor interface, agent persistent memory. THIS COUNT MOVES WITH THE AGENT DIRECTORY. It is 64 fixed checks, plus two loops across `pact-plugin/agents/`. The nesting-limit loop skips the 4 agents named in the `case` statement of the script and checks each remaining file. The `memory: user` loop checks each file. Today that directory holds 13 files, which gives 64 + 9 + 13 = 86. If you see a different number, count the agent files before you report a defect. `pact-plugin/tests/test_canary_checklist_count.py` reads the fixed-check count and the skip count from this row, predicts the total from a real count of the agent directory, and compares it against a run. Adding an agent file keeps that test green. Changing the fixed checks or the skip set without correcting this row reddens it.
- [ ] `verify-task-hierarchy.sh` passes (28 checks) -- task lifecycle patterns in all command files. FIXED count: no check comes from the contents of a directory. `pact-plugin/tests/test_canary_checklist_count.py` reads this number and compares it against a run, so an edit to this row alone reddens that test. Adding a command file does not move the count.
- [ ] `verify-worktree-protocol.sh` passes (20 checks) -- worktree skill existence, command references, path propagation. FIXED count: no check comes from the contents of a directory. `pact-plugin/tests/test_canary_checklist_count.py` reads this number and compares it against a run, so an edit to this row alone reddens that test. Adding a skill directory does not move the count.

### What failures mean

| Script | Common Failure Cause | Fix |
|--------|---------------------|-----|
| `verify-protocol-extracts.sh` | An extract file does not agree with its SSOT section. Or a heading sentinel in the script does not name an H2 heading in the SSOT | Regenerate the extract from its SSOT section. Or update the H2 heading sentinels in the script |
| `verify-scope-integrity.sh` | A cross-reference was broken, a required pattern was removed, or a new agent file is missing expected content | Trace the `✗` output to the specific check and restore the expected pattern |
| `verify-task-hierarchy.sh` | A command file's Task Hierarchy section is missing a lifecycle keyword (`TaskCreate`, `in_progress`, `completed`) | Add the missing lifecycle pattern to the command's Task Hierarchy section |
| `verify-worktree-protocol.sh` | A command file lost its worktree skill reference or a skill file is missing its frontmatter | Restore the worktree reference or skill frontmatter |

---

## Tier 2: Structural Review

Human reviewers verify structural properties that automated scripts cannot fully cover. These checks apply to every PR touching `pact-plugin/`.

### Checklist

- [ ] **Protocol extract heading sentinels stay valid** -- If the PR modifies `pact-protocols.md`, make sure the H2 heading sentinels in `verify-protocol-extracts.sh` (in the script itself) name the headings the SSOT carries now
- [ ] **Cross-references are intact** -- Protocol files that reference other protocols (e.g., `pact-scope-contract.md` referencing `rePACT.md`) still point to correct targets
- [ ] **SSOT extracts agree with their sources** -- Extracted protocol files are verbatim copies of their SSOT sections in `pact-protocols.md` (the automated script compares the bytes, and a reviewer must check that the heading sentinels themselves are correct)
- [ ] **No orphaned references** -- Search for references to renamed or deleted files; confirm no dead links remain
- [ ] **Agent definition consistency** -- All agent `.md` files under `pact-plugin/agents/` have matching frontmatter fields (`memory: user`, nesting limit, HANDOFF format)
- [ ] **Command file structure preserved** -- Command files retain their expected section headings (Task Hierarchy, phase sections, etc.)
- [ ] **Version numbers updated if needed** -- If the PR represents a version bump, both `plugin.json` and `marketplace.json` reflect the same version

---

## Tier 3: Behavioral Validation

Run a live PACT orchestration cycle to verify that the framework functions correctly end-to-end. Apply this tier at major milestones (version bumps, multi-step implementation rounds, or any PR that changes orchestration flow).

### Approach

Use the PACT framework on itself (dogfooding): run `/PACT:orchestrate` or `/PACT:comPACT` on a real task and observe whether the full lifecycle works.

### Checklist

- [ ] **Agent spawning works** -- Specialist agents are invoked and receive their prompts (check that the orchestrator delegates rather than acting directly)
- [ ] **Handoff format is correct** -- Agent responses end with the 5-item HANDOFF structure (Produced, Key decisions, Areas of uncertainty, Integration points, Open questions)
- [ ] **Memory saves succeed** -- The `pact-memory` skill saves context without errors; saved memories are retrievable via search
- [ ] **Worktree lifecycle completes** -- `worktree-setup` creates a worktree, agents work within it, and `worktree-cleanup` removes it after PR
- [ ] **Verification scripts pass in the worktree** -- All Tier 1 scripts pass when run from the worktree working directory
- [ ] **Task tracking is consistent** -- Task statuses follow the `pending -> in_progress -> completed` lifecycle without orphaned or stuck tasks
- [ ] **Phase transitions are clean** -- Each PACT phase completes with a handoff before the next begins; no phase is skipped without documented rationale

### When to run

- Before merging a version bump PR
- After completing a multi-step implementation round (e.g., all D1-D6 steps)
- When changing orchestration logic in `orchestrate.md`, `comPACT.md`, or `rePACT.md`
- Quarterly as a general regression check
