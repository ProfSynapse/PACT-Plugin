# Unattended PACT Runs

> **Purpose**: Keep a hands-off (unattended) PACT session from stalling while the lead is idle.
>
> **Usage**: Read this when you saw the startup notice about in-process teammate mode, or before leaving a PACT run unattended.
>
> **Created**: 2026-05-29

---

## TL;DR — use tmux for unattended runs

Relaunch Claude Code with tmux teammate delivery:

```bash
claude --teammate-mode tmux
```

In tmux mode, teammate wake signals are delivered natively and reliably even
when the lead has been idle for a long time. In **in-process** mode, the lead
can sit idle waiting for a wake that needs a manual nudge — fine when you are
watching the session, a stall risk when you walk away.

You can also set it permanently in `~/.claude/settings.json`:

```json
{ "teammateMode": "tmux" }
```

> **In tmux mode, set the task-tools value too.** A teammate in its own split
> pane is a separate Claude Code process, so the tools it gets follow its own
> model. A lead can hold the task tools while a teammate does not. The `env`
> block that restores them sits in the same `~/.claude/settings.json` shown
> above, which each Claude Code process reads at start, so one entry is
> sufficient for the lead and the teammate. See
> [If specialist agents will not spawn](https://github.com/Synaptic-Labs-AI/PACT-Plugin#if-specialist-agents-will-not-spawn).

## If you must stay on in-process mode

Keep a lightweight external heartbeat in another terminal so you periodically
return to nudge the lead:

```bash
while sleep 300; do printf '\a'; done   # bell every 5 min as a "check the session" cue
```

This does not fix delivery — it just reminds you to glance at the run. For
truly hands-off operation, prefer `--teammate-mode tmux`.
