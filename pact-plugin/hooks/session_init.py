#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/session_init.py
Summary: SessionStart hook that initializes PACT environment.
Used by: Claude Code settings.json SessionStart hook

Performs:
1. Creates plugin symlinks for @reference resolution
2. Detects active plans and notifies user
3. Updates ~/.claude/CLAUDE.md (merges/installs PACT Orchestrator)
4. Ensures project CLAUDE.md exists with memory sections
5. Checks for in_progress Tasks (resumption context via Task integration)

Note: Memory-related initialization (dependency installation, embedding
migration, pending embedding catch-up) is now lazy-loaded on first memory
operation via pact-memory/scripts/memory_init.py. This reduces startup
cost for non-memory users.

Input: JSON from stdin with session context
Output: JSON with `hookSpecificOutput.additionalContext` for status
"""

import json
import re
import subprocess
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Add hooks directory to path for shared package imports
_hooks_dir = Path(__file__).parent
if str(_hooks_dir) not in sys.path:
    sys.path.insert(0, str(_hooks_dir))

# Import shared Task utilities (DRY - used by multiple hooks)
from shared.task_utils import get_task_list


def setup_plugin_symlinks() -> str | None:
    """
    Create symlinks for plugin resources to ~/.claude/.

    Creates:
    1. ~/.claude/protocols/pact-plugin/ -> plugin/protocols/
       (enables @~/.claude/protocols/pact-plugin/... references in CLAUDE.md)
    2. ~/.claude/agents/pact-*.md -> plugin/agents/pact-*.md
       (enables non-prefixed agent names like "pact-memory-agent")

    Returns:
        Status message or None if successful
    """
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
    if not plugin_root.exists():
        return None

    claude_dir = Path.home() / ".claude"
    messages = []

    # 1. Symlink protocols/ directory
    protocols_src = plugin_root / "protocols"
    if protocols_src.exists():
        protocols_dst = claude_dir / "protocols" / "pact-plugin"
        protocols_dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            if protocols_dst.is_symlink():
                if protocols_dst.resolve() != protocols_src.resolve():
                    protocols_dst.unlink()
                    protocols_dst.symlink_to(protocols_src)
                    messages.append("protocols updated")
            elif not protocols_dst.exists():
                protocols_dst.symlink_to(protocols_src)
                messages.append("protocols linked")
        except OSError as e:
            messages.append(f"protocols failed: {str(e)[:20]}")

    # 2. Symlink individual agent files (enables non-prefixed agent names)
    agents_src = plugin_root / "agents"
    if agents_src.exists():
        agents_dst = claude_dir / "agents"
        agents_dst.mkdir(parents=True, exist_ok=True)

        agents_updated = 0
        agents_created = 0
        for agent_file in agents_src.glob("pact-*.md"):
            dst_file = agents_dst / agent_file.name
            try:
                if dst_file.is_symlink():
                    if dst_file.resolve() != agent_file.resolve():
                        dst_file.unlink()
                        dst_file.symlink_to(agent_file)
                        agents_updated += 1
                elif not dst_file.exists():
                    dst_file.symlink_to(agent_file)
                    agents_created += 1
                # Skip if real file exists (user override)
            except OSError:
                continue

        if agents_created:
            messages.append(f"{agents_created} agents linked")
        if agents_updated:
            messages.append(f"{agents_updated} agents updated")

    if not messages:
        return "PACT symlinks verified"
    return "PACT: " + ", ".join(messages)


def find_active_plans(project_dir: str) -> list:
    """
    Find plans with IN_PROGRESS status or uncompleted items.

    Args:
        project_dir: The project root directory path

    Returns:
        List of plan filenames that appear to be in progress
    """
    plans_dir = Path(project_dir) / "docs" / "plans"
    active_plans = []

    if not plans_dir.is_dir():
        return active_plans

    for plan_file in plans_dir.glob("*-plan.md"):
        try:
            content = plan_file.read_text(encoding='utf-8')
            in_progress_indicators = [
                "Status: IN_PROGRESS",
                "Status: In Progress",
                "status: in_progress",
                "Status: ACTIVE",
                "Status: Active",
            ]

            has_in_progress_status = any(
                indicator in content for indicator in in_progress_indicators
            )
            has_unchecked_items = "[ ] " in content
            is_completed = any(
                status in content for status in [
                    "Status: COMPLETED",
                    "Status: Completed",
                    "Status: DONE",
                    "Status: Done",
                ]
            )

            if has_in_progress_status or (has_unchecked_items and not is_completed):
                active_plans.append(plan_file.name)

        except (IOError, UnicodeDecodeError):
            continue

    return active_plans


def update_claude_md() -> str | None:
    """
    Update ~/.claude/CLAUDE.md with PACT content.

    Automatically merges or updates the PACT Orchestrator prompt in the user's
    CLAUDE.md file. Uses explicit markers to manage the PACT section without
    disturbing other user customizations.

    Strategy:
    1. If file missing -> create with PACT content in markers.
    2. If markers found -> replace content between markers.
    3. If no markers but "PACT Orchestrator" found -> assume manual install, warn.
    4. If no markers and no conflict -> append PACT content with markers.

    Returns:
        Status message or None if no change.
    """
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
    if not plugin_root.exists():
        return None

    source_file = plugin_root / "CLAUDE.md"
    if not source_file.exists():
        return None

    target_file = Path.home() / ".claude" / "CLAUDE.md"

    START_MARKER = "<!-- PACT_START: Managed by pact-plugin - Do not edit this block -->"
    END_MARKER = "<!-- PACT_END -->"

    try:
        source_content = source_file.read_text(encoding="utf-8")
        wrapped_source = f"{START_MARKER}\n{source_content}\n{END_MARKER}"

        # Case 1: Target doesn't exist
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(wrapped_source, encoding="utf-8")
            return "Created CLAUDE.md with PACT Orchestrator"

        target_content = target_file.read_text(encoding="utf-8")

        # Case 2: Markers found - update if changed
        if START_MARKER in target_content and END_MARKER in target_content:
            parts = target_content.split(START_MARKER)
            pre = parts[0]
            # Handle case where multiple markers might exist (take first and last valid)
            # but usually just one block.
            rest = parts[1]
            if END_MARKER in rest:
                post = rest.split(END_MARKER, 1)[1]
                new_full_content = f"{pre}{wrapped_source}{post}"

                if new_full_content != target_content:
                    target_file.write_text(new_full_content, encoding="utf-8")
                    return "PACT Orchestrator updated"
                return None

        # Case 3: No markers but content similar to PACT found
        if "PACT Orchestrator" in target_content:
            # Check if it looks roughly like what we expect, or just leave it
            # Returning a message prompts the user to check it
            return "PACT present but unmanaged (add markers to auto-update)"

        # Case 4: No markers, no specific PACT content -> Append
        # Ensure we append on a new line
        if not target_content.endswith("\n"):
            target_content += "\n"

        new_content = f"{target_content}\n{wrapped_source}"
        target_file.write_text(new_content, encoding="utf-8")
        return "PACT Orchestrator added to CLAUDE.md"

    except Exception as e:
        return f"PACT update failed: {str(e)[:30]}"


def ensure_project_memory_md() -> str | None:
    """
    Ensure project has a CLAUDE.md with memory sections.

    Creates a minimal project-level CLAUDE.md containing only the memory
    sections (Retrieved Context, Working Memory) if one doesn't exist.
    These sections are project-specific and managed by the pact-memory skill.

    If the project already has a CLAUDE.md, this function does nothing
    (preserves existing project configuration).

    Returns:
        Status message or None if no action taken.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        return None

    target_file = Path(project_dir) / "CLAUDE.md"

    # Don't overwrite existing project CLAUDE.md
    if target_file.exists():
        return None

    # Create minimal CLAUDE.md with memory sections
    memory_template = """# Project Memory

This file contains project-specific memory managed by the PACT framework.
The global PACT Orchestrator is loaded from `~/.claude/CLAUDE.md`.

## Retrieved Context
<!-- Auto-managed by pact-memory skill. Last 3 retrieved memories shown. -->

## Working Memory
<!-- Auto-managed by pact-memory skill. Last 5 memories shown. Full history searchable via pact-memory skill. -->
"""

    try:
        target_file.write_text(memory_template, encoding="utf-8")
        return "Created project CLAUDE.md with memory sections"
    except Exception as e:
        return f"Project CLAUDE.md failed: {str(e)[:30]}"


def check_resumption_context(tasks: list[dict[str, Any]]) -> str | None:
    """
    Check if there are in_progress Tasks indicating work to resume.

    This helps users understand the current state when starting a new session
    with a persistent task list (CLAUDE_CODE_TASK_LIST_ID set).

    Args:
        tasks: List of all tasks

    Returns:
        Status message describing resumption context, or None if nothing to report
    """
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    pending = [t for t in tasks if t.get("status") == "pending"]
    completed = [t for t in tasks if t.get("status") == "completed"]

    if not in_progress and not pending:
        return None

    # Count by type
    feature_tasks = []
    phase_tasks = []
    agent_tasks = []
    blocker_tasks = []

    for task in in_progress:
        subject = task.get("subject", "")
        metadata = task.get("metadata", {})

        if metadata.get("type") in ("blocker", "algedonic"):
            blocker_tasks.append(task)
        elif any(subject.startswith(p) for p in ("PREPARE:", "ARCHITECT:", "CODE:", "TEST:")):
            phase_tasks.append(task)
        elif any(subject.lower().startswith(p) for p in ("pact-",)):
            agent_tasks.append(task)
        else:
            # Assume it's a feature task
            feature_tasks.append(task)

    parts = []

    if feature_tasks:
        names = [t.get("subject", "unknown")[:30] for t in feature_tasks[:2]]
        if len(feature_tasks) > 2:
            parts.append(f"Features: {', '.join(names)} (+{len(feature_tasks)-2} more)")
        else:
            parts.append(f"Features: {', '.join(names)}")

    if phase_tasks:
        phases = [t.get("subject", "").split(":")[0] for t in phase_tasks]
        parts.append(f"Phases: {', '.join(phases)}")

    if agent_tasks:
        parts.append(f"Active agents: {len(agent_tasks)}")

    if blocker_tasks:
        parts.append(f"**Blockers: {len(blocker_tasks)}**")

    if parts:
        summary = f"Resumption context: {' | '.join(parts)}"
        if pending:
            summary += f" ({len(pending)} pending)"
        return summary

    return None


# Staleness detection constants
PINNED_STALENESS_DAYS = 30
PINNED_CONTEXT_TOKEN_BUDGET = 1200


def _get_project_claude_md_path() -> Optional[Path]:
    """
    Get the path to the project-level CLAUDE.md.

    Checks CLAUDE_PROJECT_DIR env var first, then falls back to git
    worktree/repo root detection via `git rev-parse --show-toplevel`.

    Returns:
        Path to project CLAUDE.md if found, None otherwise.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        path = Path(project_dir) / "CLAUDE.md"
        if path.exists():
            return path

    # Fallback: detect git root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            git_root = result.stdout.strip()
            path = Path(git_root) / "CLAUDE.md"
            if path.exists():
                return path
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return None


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count using word count * 1.3 approximation.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def check_pinned_staleness() -> Optional[str]:
    """
    Detect stale pinned context entries in the project CLAUDE.md.

    A pinned entry is considered stale if it references a merged PR with a
    date older than PINNED_STALENESS_DAYS. Stale entries get a
    <!-- STALE: Last relevant YYYY-MM-DD --> comment prepended before their
    heading (if not already marked).

    Also checks if the total pinned content exceeds the token budget and
    adds a warning comment if so (does NOT auto-delete pins).

    Returns:
        Informational message about stale pins found, or None.
    """
    claude_md_path = _get_project_claude_md_path()
    if claude_md_path is None:
        return None

    try:
        content = claude_md_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError):
        return None

    # Find the Pinned Context section
    pinned_match = re.search(r'^## Pinned Context\s*\n', content, re.MULTILINE)
    if not pinned_match:
        return None

    pinned_start = pinned_match.end()

    # Find the end of pinned section (next H1 or H2 heading, or EOF)
    next_section = re.search(r'^#{1,2}\s', content[pinned_start:], re.MULTILINE)
    if next_section:
        pinned_end = pinned_start + next_section.start()
    else:
        pinned_end = len(content)

    pinned_content = content[pinned_start:pinned_end]
    if not pinned_content.strip():
        return None

    # Parse individual pinned entries (each starts with ###)
    entry_pattern = re.compile(r'^### ', re.MULTILINE)
    entry_starts = [m.start() for m in entry_pattern.finditer(pinned_content)]

    if not entry_starts:
        return None

    now = datetime.now()
    stale_threshold = now - timedelta(days=PINNED_STALENESS_DAYS)
    stale_count = 0
    modified = False

    # Pattern to match "PR #NNN, merged YYYY-MM-DD" in entry text
    pr_merged_pattern = re.compile(
        r'PR\s*#\d+,?\s*merged\s+(\d{4}-\d{2}-\d{2})'
    )
    # Pattern to detect existing staleness marker
    stale_marker_pattern = re.compile(r'<!-- STALE: Last relevant \d{4}-\d{2}-\d{2} -->')

    # Process entries in reverse order so string offsets remain valid
    for i in range(len(entry_starts) - 1, -1, -1):
        start = entry_starts[i]
        if i + 1 < len(entry_starts):
            end = entry_starts[i + 1]
        else:
            end = len(pinned_content)

        entry_text = pinned_content[start:end]

        # Skip entries already marked stale
        if stale_marker_pattern.search(entry_text):
            stale_count += 1
            continue

        # Look for PR merged date
        pr_match = pr_merged_pattern.search(entry_text)
        if not pr_match:
            continue

        try:
            merged_date = datetime.strptime(pr_match.group(1), "%Y-%m-%d")
        except ValueError:
            continue

        if merged_date < stale_threshold:
            # Mark as stale by inserting comment after the ### heading line.
            # The marker must be inside the entry_text (which starts at ###)
            # so that subsequent runs find it and skip re-marking.
            stale_marker = f"<!-- STALE: Last relevant {pr_match.group(1)} -->\n"
            heading_end = entry_text.index("\n") + 1
            new_entry = entry_text[:heading_end] + stale_marker + entry_text[heading_end:]
            pinned_content = (
                pinned_content[:start] + new_entry + pinned_content[end:]
            )
            stale_count += 1
            modified = True

    # Check token budget for pinned content
    pinned_tokens = _estimate_tokens(pinned_content)
    budget_warning = ""
    if pinned_tokens > PINNED_CONTEXT_TOKEN_BUDGET:
        budget_warning_comment = (
            f"<!-- WARNING: Pinned context ~{pinned_tokens} tokens "
            f"(budget: {PINNED_CONTEXT_TOKEN_BUDGET}). "
            f"Consider archiving stale pins. -->\n"
        )
        # Add budget warning at the top of pinned section if not present
        if "<!-- WARNING: Pinned context" not in pinned_content:
            pinned_content = budget_warning_comment + pinned_content
            modified = True
        budget_warning = f", ~{pinned_tokens} tokens (budget: {PINNED_CONTEXT_TOKEN_BUDGET})"

    # Write back if modified
    if modified:
        new_content = content[:pinned_start] + pinned_content + content[pinned_end:]
        try:
            claude_md_path.write_text(new_content, encoding="utf-8")
        except (IOError, OSError) as e:
            logger_msg = f"Failed to update pinned staleness: {e}"
            return logger_msg

    if stale_count > 0:
        return f"Pinned context: {stale_count} stale pin(s) detected{budget_warning}"
    if budget_warning:
        return f"Pinned context{budget_warning}"

    return None


def main():
    """
    Main entry point for the SessionStart hook.

    Performs PACT environment initialization:
    1. Creates plugin symlinks for @reference resolution
    2. Checks for active plans
    3. Updates ~/.claude/CLAUDE.md (merges/installs PACT Orchestrator)
    4. Ensures project CLAUDE.md exists with memory sections
    5. Checks for stale pinned context entries in project CLAUDE.md
    6. Checks for in_progress Tasks (resumption context via Task integration)

    Memory initialization (dependencies, migrations, embedding catch-up) is
    now lazy-loaded on first memory operation to reduce startup cost for
    non-memory users.
    """
    try:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            input_data = {}

        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
        context_parts = []
        system_messages = []

        # 1. Set up plugin symlinks (enables @~/.claude/protocols/pact-plugin/ references)
        symlink_result = setup_plugin_symlinks()
        if symlink_result and "failed" in symlink_result.lower():
            system_messages.append(symlink_result)
        elif symlink_result:
            context_parts.append(symlink_result)

        # 2. Check for active plans
        active_plans = find_active_plans(project_dir)
        if active_plans:
            plan_list = ", ".join(active_plans[:3])
            if len(active_plans) > 3:
                plan_list += f" (+{len(active_plans) - 3} more)"
            context_parts.append(f"Active plans: {plan_list}")

        # 3. Updates ~/.claude/CLAUDE.md (merges/installs PACT Orchestrator)
        claude_md_msg = update_claude_md()
        if claude_md_msg:
            if "failed" in claude_md_msg.lower() or "unmanaged" in claude_md_msg.lower():
                system_messages.append(claude_md_msg)
            else:
                context_parts.append(claude_md_msg)

        # 4. Ensure project has CLAUDE.md with memory sections
        project_md_msg = ensure_project_memory_md()
        if project_md_msg:
            if "failed" in project_md_msg.lower():
                system_messages.append(project_md_msg)
            else:
                context_parts.append(project_md_msg)

        # 5. Check for stale pinned context
        staleness_msg = check_pinned_staleness()
        if staleness_msg:
            context_parts.append(staleness_msg)

        # 6. Check for in_progress Tasks (resumption context via Task integration)
        tasks = get_task_list()
        if tasks:
            resumption_msg = check_resumption_context(tasks)
            if resumption_msg:
                # Blockers are critical - put in system message for visibility
                if "**Blockers:" in resumption_msg:
                    system_messages.append(resumption_msg)
                else:
                    context_parts.append(resumption_msg)

        # Build output
        output = {}

        if context_parts or system_messages:
            output["hookSpecificOutput"] = {
                "hookEventName": "SessionStart",
                "additionalContext": " | ".join(context_parts) if context_parts else "Success"
            }

        if system_messages:
            output["systemMessage"] = " | ".join(system_messages)

        if output:
            print(json.dumps(output))

        sys.exit(0)

    except Exception as e:
        print(f"Hook warning (session_init): {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
