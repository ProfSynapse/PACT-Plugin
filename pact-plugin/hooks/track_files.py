#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/track_files.py
Summary: PostToolUse hook that tracks files modified during the session.
Used by: Claude Code settings.json PostToolUse hook (Edit, Write tools)

Extracts file paths from Edit/Write tool usage and records them
for the memory system's graph network.

Input: JSON from stdin with tool_name, tool_input, tool_response
Output: None (writes to tracking file for later memory association)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from shared.error_output import hook_error_json
import shared.pact_context as pact_context
from shared.pact_context import get_session_id
from shared.paths import get_claude_config_dir

# Suppress false "hook error" display in Claude Code UI on bare exit paths
_SUPPRESS_OUTPUT = json.dumps({"suppressOutput": True})

try:
    import fcntl
    HAS_FLOCK = True
except ImportError:
    HAS_FLOCK = False


# Directory for tracking data. Accessor (B1) — resolves $CLAUDE_CONFIG_DIR at
# CALL time via the shared resolver, so a non-default config dir is honored and
# the import-time freeze (a #924-class inert trap) is avoided.
def get_tracking_dir() -> Path:
    return get_claude_config_dir() / "pact-memory" / "session-tracking"


def ensure_tracking_dir():
    """Ensure the tracking directory exists."""
    get_tracking_dir().mkdir(parents=True, exist_ok=True)


def get_session_tracking_file() -> Path:
    """Get the tracking file for the current session.

    Requires pact_context.init() to have been called so get_session_id()
    reads from the correct session-scoped context file.
    """
    session_id = get_session_id() or "unknown"
    return get_tracking_dir() / f"{session_id}.json"


def load_tracked_files() -> dict:
    """Load existing tracked files for this session.

    Uses shared (LOCK_SH) file locking on platforms that support fcntl
    to prevent reading while another process is mid-write.
    """
    default = {"files": [], "session_id": get_session_id() or "unknown"}
    tracking_file = get_session_tracking_file()
    if not tracking_file.exists():
        return default

    if HAS_FLOCK:
        try:
            with open(tracking_file, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    content = f.read()
                    return json.loads(content) if content.strip() else default
                except json.JSONDecodeError:
                    return default
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except IOError:
            return default
    else:
        try:
            with open(tracking_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default


def save_tracked_files(data: dict):
    """Save tracked files for this session.

    Uses exclusive (LOCK_EX) file locking on platforms that support fcntl
    to prevent concurrent write corruption. Unlock is in a finally block
    to ensure release even on exceptions.
    """
    ensure_tracking_dir()
    tracking_file = get_session_tracking_file()

    if HAS_FLOCK:
        try:
            with open(tracking_file, "a+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    f.truncate()
                    json.dump(data, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except IOError as e:
            print(f"Warning: Could not save tracking data: {e}", file=sys.stderr)
    else:
        try:
            with open(tracking_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save tracking data: {e}", file=sys.stderr)


def extract_file_path(tool_input: dict) -> str:
    """Extract file path from tool input."""
    # Both Edit and Write use file_path parameter
    return tool_input.get("file_path", "")


def _update_data(data: dict, file_path: str, tool_name: str) -> dict:
    """Update tracking data with a file entry (pure function, no I/O).

    Separated from I/O so that the read-modify-write cycle can be done
    under a single lock.
    """
    existing_paths = [f["path"] for f in data["files"]]
    if file_path in existing_paths:
        for f in data["files"]:
            if f["path"] == file_path:
                f["last_modified"] = datetime.now(timezone.utc).isoformat()
                f["tool"] = tool_name
                break
    else:
        data["files"].append({
            "path": file_path,
            "tool": tool_name,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_modified": datetime.now(timezone.utc).isoformat(),
        })
    return data


def track_file(file_path: str, tool_name: str):
    """Add a file to the tracking list.

    Uses a single exclusive lock for the entire read-modify-write cycle
    to prevent TOCTOU race conditions between concurrent hook invocations.
    """
    if not file_path:
        return

    ensure_tracking_dir()
    tracking_file = get_session_tracking_file()
    default = {"files": [], "session_id": get_session_id() or "unknown"}

    if HAS_FLOCK:
        try:
            with open(tracking_file, "a+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    content = f.read()
                    try:
                        data = json.loads(content) if content.strip() else default
                    except json.JSONDecodeError:
                        data = default
                    data = _update_data(data, file_path, tool_name)
                    f.seek(0)
                    f.truncate()
                    json.dump(data, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except IOError as e:
            print(f"Warning: Could not track file: {e}", file=sys.stderr)
    else:
        data = load_tracked_files()
        data = _update_data(data, file_path, tool_name)
        save_tracked_files(data)


# The token that identifies the archive command inside a Bash payload. The
# archive runs as `python3 ".../scripts/archive_pin.py" --index N`, so the
# script filename is the cheapest thing that separates it from every other
# shell call.
_ARCHIVE_SCRIPT_TOKEN = "archive_pin.py"


def clear_pin_staleness_marker_if_resolved(
    tool_name: str, tool_input: dict
) -> None:
    """Drop the stale-pins marker once the staleness signal has cleared.

    WHY THIS LIVES HERE AND NOT IN THE GATE. `pin_staleness_gate.py` is a
    PreToolUse REFUSAL and it is READ ONLY on that marker, which the design
    holds SACROSANCT. A refusal that removed its own trigger would make the
    trap vanish by deleting the evidence of it rather than by repair, and the
    suite would go green while that happened. The clear belongs on the
    PostToolUse side, which is here.

    THE TRAP IT CLOSES. The marker is written and removed at SessionStart only.
    The deny text tells a user to archive stale pins BEFORE editing, so a user
    who obeys inside a session stays denied until the next session. That is a
    cardinal over-block on the user's own file, and it is reached by OBEYING
    the message.

    THE TRIGGER SET IS A UNION, AND BINDING ONE MEMBER IS THE FAILURE THAT
    READS AS A REPAIR. The pinned region changes across two routes:
      ROUTE 1, a hand edit, which arrives as `Edit` or `Write`.
      ROUTE 2, THE ARCHIVE ITSELF, which arrives as `Bash`. The archive command
        runs a script that writes the file directly, so it emits NO `Edit` or
        `Write` event. A clear bound to route 1 alone misses the very route the
        deny text recommends, which is the worst of the outcomes available
        here.
    ROUTE 2 IS `Bash` AND NOT `Skill`. An earlier reading bound it to `Skill`
    on the belief that the pin command archives. It does not: the archiving
    command runs the script through a shell, so `Bash` is the event that
    carries the write.

    THE COST OF THE WIDENED MATCHER, STATED RATHER THAN HIDDEN. This hook is
    registered for `Bash` as well now, so it runs one subprocess for EACH shell
    call in each consumer session. That is the same per-event cost a new
    registration would carry, so cost is NOT what chose this shape. OWNERSHIP
    chose it: one hook owning one concern across the two routes, rather than
    two hooks owning one concern between them. THE `Bash` LEG TESTS THE COMMAND
    STRING FIRST, so an ordinary shell call costs one substring test and no
    file read.

    Fail-safe: this never raises and never reports. File tracking is the
    caller's job and a fault here must not disturb it.
    """
    try:
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            if not isinstance(command, str):
                return
            if _ARCHIVE_SCRIPT_TOKEN not in command:
                return
        else:
            # Route 1. Gate on the edited path resolving to the managed
            # CLAUDE.md, so an edit to any other file costs one resolve.
            from shared import match_project_claude_md

            file_path = tool_input.get("file_path", "")
            if not file_path or match_project_claude_md(file_path) is None:
                return

        from pin_staleness_gate import PIN_STALENESS_MARKER_NAME
        from shared.pact_context import get_session_dir
        from staleness import check_pinned_block_signal

        session_dir = get_session_dir()
        if not session_dir:
            return
        marker = Path(session_dir) / PIN_STALENESS_MARKER_NAME
        if not marker.exists():
            return

        # RE-READ THE SIGNAL RATHER THAN ASSUME THE EDIT RESOLVED IT. An edit
        # to the managed file, and an archive run, are both REASONS TO LOOK.
        # Neither is proof that the condition cleared. A clear that skipped
        # this read would drop the marker while stale pins remain.
        if check_pinned_block_signal() is not None:
            return

        try:
            marker.unlink()
        except OSError:
            pass
    except Exception:  # noqa: BLE001 — marker management is best-effort
        return


def main():
    """Main entry point for the PostToolUse hook."""
    try:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            print(_SUPPRESS_OUTPUT)
            sys.exit(0)

        pact_context.init(input_data)
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # THE CLEAR RUNS BEFORE THE TRACKING GATE, because it serves `Bash`
        # too and the gate below drops every tool that is not Edit or Write.
        clear_pin_staleness_marker_if_resolved(tool_name, tool_input)

        # Only track Edit and Write tools
        if tool_name not in ("Edit", "Write"):
            print(_SUPPRESS_OUTPUT)
            sys.exit(0)

        # Extract and track the file path
        file_path = extract_file_path(tool_input)
        if file_path:
            track_file(file_path, tool_name)

        print(_SUPPRESS_OUTPUT)
        sys.exit(0)

    except Exception as e:
        # Don't block on errors
        print(f"Hook warning (track_files): {e}", file=sys.stderr)
        print(hook_error_json("track_files", e))
        sys.exit(0)


if __name__ == "__main__":
    main()
