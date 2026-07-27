"""
Location: pact-plugin/tests/fixtures/message_delivering_hook.py
Summary: Synthetic NON-SHIPPED fixture for the message-delivery scanner in
         test_concurrent_auditor_wake.py. It is never imported and never
         executed -- it is read as text and parsed as an AST, exactly like a
         real hook under the sweep.

         It is the scanner's standing positive control. The auditor guidance
         asserts a repo fact ("no PACT hook sends a message"), and a scanner
         that reports zero findings over hooks/ is indistinguishable from a
         scanner that cannot detect anything at all. This file makes that
         distinction observable on every suite run instead of once, by hand,
         at authoring time.

         Four functions, deliberately paired:
           deliver_via_write_text  -> MUST flag (INBOX-WRITE)
           deliver_via_open_write  -> MUST flag (INBOX-WRITE, twice)
           deliver_via_send_api    -> MUST flag (SEND-CALL)
           read_only_inbox_probe   -> MUST NOT flag (reads an inbox path)
           unrelated_write         -> MUST NOT flag (writes a non-inbox path)

         The two negative controls are the load-bearing half. hooks/ contains
         real inbox-path construction that is read-only, so a scanner that
         flagged any inbox mention would be useless here -- it would fire on
         shipped code that is behaving correctly. Pairing the positive and
         negative legs in ONE file means neither can pass by absence.
Used by: pact-plugin/tests/test_concurrent_auditor_wake.py
"""
from __future__ import annotations

import json
from pathlib import Path


def deliver_via_write_text(team: str, name: str, payload: dict) -> None:
    """Delivery via Path.write_text on a path built in a prior statement.

    The inbox literal is NOT inside the write call -- it is in the assignment
    above it. A scanner that only inspects the call's own subtree misses this,
    which is how real delivery code is shaped.
    """
    inbox = Path.home() / ".claude" / "teams" / team / "inboxes" / f"{name}.json"
    inbox.write_text(json.dumps(payload), encoding="utf-8")


def deliver_via_open_write(team: str, name: str, payload: dict) -> None:
    """Delivery via open(..., "w"), with the path built across TWO statements
    and bound to a name that does not itself contain the marker."""
    base = Path.home() / ".claude" / "teams" / team / "inboxes"
    target = base / f"{name}.json"
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))


def deliver_via_send_api(recipient: str, body: str) -> None:
    """Delivery via a send API call.

    `send_message` is intentionally unbound -- this file is never executed, and
    binding it would only add an import the scanner does not read.
    """
    send_message(to=recipient, message=body)  # noqa: F821  # fixture: never executed


def read_only_inbox_probe(team: str, name: str) -> bool:
    """NEGATIVE control: constructs an inbox path and only READS it.

    Mirrors the shape of real shipped hook code, which uses the inbox file as a
    witness that a teammate was dispatched. Flagging this would make the pin
    fire on correct code.
    """
    inbox = Path.home() / ".claude" / "teams" / team / "inboxes" / f"{name}.json"
    if inbox.is_file():
        return bool(inbox.read_text(encoding="utf-8"))
    return False


def unrelated_write(tmp_dir: str, blob: str) -> None:
    """NEGATIVE control: a genuine write to a path that is not an inbox.

    Separates "writes a file" from "delivers a message". Without this leg, a
    scanner that flagged every write would look correct against the positive
    legs alone.
    """
    log = Path(tmp_dir) / "hook-errors.log"
    log.write_text(blob, encoding="utf-8")
