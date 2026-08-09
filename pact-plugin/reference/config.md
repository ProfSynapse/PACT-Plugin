# PACT Configuration Reference

> **Purpose**: The single reference for every PACT runtime option — how to set it, what it does, and the two `settings.json` gotchas.
>
> **Usage**: Read this when enabling greedy-fix or autonomous scope detection, tuning the dispatch gates, or persisting PACT config across sessions.

---

## Options

All PACT options are `PACT_*` environment variables, resolved once per session by `hooks/shared/pact_config.py`. Because the resolver reads `os.environ`, any env-var source works.

| Option | Type | Default | Consumer | Effect |
|---|---|---|---|---|
| `PACT_PR_GREEDY_FIX` | bool | `0` (off) | orchestrator (peer-review) | When on, peer-review greedily auto-delegates **all** minor + future reviewer findings as reversible fixes. `merge` / `close` / `push` stay user-gated; SACROSANCT is never overridden; findings that are widely out of scope, extremely expansive, or pattern-violating are surfaced (not silently dropped). Off = the default per-finding review gate. |
| `PACT_AUTONOMOUS_SCOPE_DETECTION` | bool | `0` (off) | orchestrator (scope detection) | When on, scope detection may auto-decompose a multi-scope task **without** user confirmation when all strong signals fire and no counter-signals are present. Off = the Confirmed tier (the orchestrator proposes; the user confirms). |
| `PACT_DISPATCH_INLINE_MISSION_MODE` | enum | `warn` | hook (`dispatch_gate`) | Disposition of the dispatch-gate inline-mission heuristic: `warn` (advisory `additionalContext`), `deny` (block the spawn), `shadow` (journal only — observed but neither warns nor denies). Any unrecognized value falls back to `warn`. |
| `PACT_DISPATCH_VARIETY_MODE` | enum | `deny` | hook (`handoff_ordering_gate`) | Disposition of the dispatch-variety enforcement, and the one option shipping ENFORCING: a dispatch-wiring `TaskUpdate` whose Task B carries no resolvable `metadata.variety` is blocked. Opt DOWN with `warn` (advisory) or `shadow` (journal only). An UNSET variable resolves to `deny`; an UNRECOGNIZED one resolves to the row's declared `invalid_fallback` of `warn`, with a stderr line naming the resolved value. The two paths are deliberately distinct: absence is consent to the shipped posture, whereas a value the resolver cannot parse is not a request to enforce — and the only consumers who reach that branch are ones trying to opt down. |

**Bool parsing**: `1` / `true` / `yes` / `on` (case-insensitive) → **on**; everything else — including `0`, an unrecognized value, and an unset variable → **off**. This is exact-membership, not truthiness: `0` is off.

**Consumer** distinguishes two runtimes. **LLM-consumed** options (`PACT_PR_GREEDY_FIX`, `PACT_AUTONOMOUS_SCOPE_DETECTION`) are surfaced to the orchestrator at session start in an injected **PACT Runtime Config** block, because markdown flows cannot read environment variables. **Hook-consumed** options (the two `*_MODE` gates) are read directly by the Python hooks at hook load.

## `PACT_TEST_MEMORY_DIR`: for tests only

**It moves the memory database and nothing else.** It does NOT move `session-tracking/`, which is in the same root but resolves through `get_claude_config_dir()` and thus follows `CLAUDE_CONFIG_DIR`. If you set only this variable, the database moves and the `session-tracking/` data stays where it was. This divides one set of memory data between two trees. The boundary comes first here because that division is the risk.

**It is there so that a test process cannot touch the live database. It is not a supported procedure to move your data.** A general procedure of that type is not available at this time. The test harness sets this variable. Do not set it to move a database of your own.

**It is missing from the Options table above, and that is on purpose.** Each row in that table resolves one time for each session, through `hooks/shared/pact_config.py`. This variable resolves at use time, in `get_memory_dir()` in `skills/pact-memory/scripts/config.py`, and it is a test-harness variable, not a control on behavior. A row in that table can tell the reader three things that are incorrect.

If you find the variable in a process list or in the source, these are its mechanics:

- **Controls** the memory database: `get_memory_dir()` and each path derived from it, which is `memory.db`.
- **Default**, if unset: `~/.claude/pact-memory`.
- **An empty value counts as unset.** Thus `PACT_TEST_MEMORY_DIR=""` cannot move the database to the current directory by accident.
- **The resolver redirects. It does not refuse.** It cannot tell a test path from a live one. It sees only if you set the variable.

## Where to set the options

Any env-var source works. In order of persistence:

- **Recommended — the `settings.json` `env` block** (launch-method-independent). Claude Code applies it at startup regardless of how `claude` was launched:
  ```json
  { "env": { "PACT_PR_GREEDY_FIX": "1", "PACT_AUTONOMOUS_SCOPE_DETECTION": "1" } }
  ```
- **Shell rc export.** Use `~/.zshenv` to cover every zsh invocation; `~/.zshrc` covers only interactive shells (GUI/dock launchers, `cron`/`launchd`, and some IDE integrations will not source it):
  ```bash
  export PACT_PR_GREEDY_FIX=1
  ```
- **One-shot launch prefix**, valid only when the variable is not pinned in the `env` block (see gotcha 1):
  ```bash
  PACT_PR_GREEDY_FIX=1 claude …
  ```

## Precedence

Claude Code merges the settings tiers into the process environment before a hook subprocess starts, so the resolver sees one already-merged `os.environ`:

```
managed settings → command-line args → env vars → settings files (local → project → user) → defaults
```

## Two gotchas

1. **The `env` block overrides a same-named shell variable.** A value pinned in `settings.json`'s `env` block wins over a shell export of the same name — so a one-shot `PACT_PR_GREEDY_FIX=0 claude …` will **not** override a `"PACT_PR_GREEDY_FIX": "1"` pinned in the `env` block. A one-shot override works only when the variable is not pinned there.
2. **A malformed `settings.json` is dropped WHOLESALE in headless mode.** In `-p` / headless mode, a syntax error anywhere in `settings.json` makes Claude Code silently ignore the **entire** file — including the whole `env` block, so every PACT option persisted there stops applying. `session_init` warns at startup if it reads a malformed `settings.json`. Keep the file valid JSON.

**Namespace guardrail**: name every PACT option `PACT_*`. Never reuse a `CLAUDE_CODE_*` identity variable — Claude Code strips those from the `env` block.

## Migration — `autonomous-scope-detection` marker → env var

Earlier versions enabled autonomous scope detection with an `autonomous-scope-detection: enabled` line in `CLAUDE.md`. **That marker is no longer read.** To keep autonomous scope detection on, set `PACT_AUTONOMOUS_SCOPE_DETECTION=1` (via the `settings.json` `env` block or a shell export). An existing `CLAUDE.md` marker is now a no-op — remove it at your convenience.

## Telegram

Telegram notifications are configured separately (their own `.env` with credentials), outside this resolver.
