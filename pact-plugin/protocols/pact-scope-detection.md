## Scope Detection

> **Purpose**: Detect multi-scope tasks during orchestration so the orchestrator can propose
> decomposition before committing to a single-scope execution plan.
> Evaluated after PREPARE phase output is available, before ARCHITECT phase begins.

### Detection Heuristics

The orchestrator evaluates PREPARE output against these heuristic signals to determine whether a task warrants decomposition into sub-scopes.

| Signal | Strength | Description |
|--------|----------|-------------|
| **Multiple distinct domains** | Strong (2 pts) | Task touches 2+ independent service boundaries or technology domains (e.g., backend API + frontend UI + database migration) |
| **Independent file clusters** | Strong (2 pts) | File changes cluster into groups with no shared files between them — each cluster maps to a separate specialist domain |
| **High specialist count** | Supporting (1 pt) | Task would require 4+ specialists across different domains to implement |
| **Prior complexity flags** | Supporting (1 pt) | pact-memory retrieval shows previous multi-scope flags or complexity warnings for this area |
| **Plan references different services** | Supporting (1 pt) | Architecture or plan calls for changes in separate service directories (e.g., `services/auth/` and `services/billing/`) |

### Counter-Signals

Counter-signals argue against decomposition. Each counter-signal present reduces the detection score by 1 point. Counter-signals **demote confidence** — they do not veto decomposition outright.

| Counter-Signal | Reasoning |
|----------------|-----------|
| **Shared data models across domains** | Sub-scopes would need constant coordination on shared types — single scope is simpler |
| **Small total scope despite multiple domains** | A one-line API change + one-line frontend change does not warrant sub-scope overhead |
| **User explicitly invoked comPACT** | User is signaling lightweight handling — respect the intent |

### Scoring Model

```
Score = sum(detected heuristic points) - count(counter-signals present)
```

- **Strong** signals contribute **2 points** each
- **Supporting** signals contribute **1 point** each
- **Counter-signals** reduce score by **1 point** each (floor of 0)
- **Decomposition threshold**: Score >= 3

The threshold and point values are tunable. Adjust based on observed false-positive and false-negative rates during canary workflows.

### Activation Tiers

| Tier | Trigger | Behavior |
|------|---------|----------|
| **Manual** | User invokes `/rePACT` explicitly | Always available — bypasses detection entirely |
| **Confirmed** (default) | Score >= threshold | Orchestrator proposes decomposition via S5 decision framing; user confirms, rejects, or adjusts boundaries |
| **Autonomous** | ALL strong signals fire AND no counter-signals AND autonomous mode enabled | Orchestrator auto-decomposes without user confirmation |

**Autonomous mode** is opt-in. Enable by adding to `CLAUDE.md`:

```markdown
autonomous-scope-detection: enabled
```

When autonomous mode is not enabled, all detection-triggered decomposition uses the Confirmed tier.

### Evaluation Timing

1. **PREPARE** phase runs in single scope (always — research output is needed to evaluate signals)
2. Orchestrator evaluates PREPARE output against heuristics
3. Score **below threshold** → proceed with single-scope execution (today's default behavior)
4. Score **at or above threshold** → activate the appropriate tier (Confirmed or Autonomous)

### Bypass Rules

- **comPACT** bypasses scope detection entirely — it is inherently single-domain
- **Manual `/rePACT`** bypasses detection — user has already decided to decompose
- **Ongoing sub-scope execution** does not re-evaluate detection (no recursive detection within sub-scopes)

---
