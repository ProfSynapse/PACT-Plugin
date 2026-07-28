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

         Deliberately paired:
           deliver_via_write_text     -> MUST flag (INBOX-WRITE)
           deliver_via_open_write     -> MUST flag (INBOX-WRITE, twice)
           deliver_via_atomic_replace -> MUST flag (INBOX-WRITE + INBOX-MOVE)
           deliver_via_send_api       -> MUST flag (SEND-CALL)
           read_only_inbox_probe      -> MUST NOT flag (reads an inbox path)
           unrelated_write            -> MUST NOT flag (writes a non-inbox path)
           archive_away_from_inbox    -> MUST NOT flag (moves OUT of an inbox)

         The negative controls are the load-bearing half. hooks/ contains real
         inbox-path construction that is read-only, so a scanner that flagged
         any inbox mention would be useless here -- it would fire on shipped
         code that is behaving correctly. Pairing the positive and negative
         legs in ONE file means neither can pass by absence.

         archive_away_from_inbox is the negative twin of the atomic-write leg
         specifically. It proves the move rule keys on the DESTINATION rather
         than on any argument: without it, an any-argument rule would look
         correct against the positive leg alone while calling every move OUT of
         an inbox a delivery.

         IDENTIFIERS IN THE NEGATIVE LEGS ARE PART OF THE TEST CONTRACT. The
         negative-control test locates each line it checks by searching this
         file for literal text spelled from those identifiers -- the local
         binding in read_only_inbox_probe and in archive_away_from_inbox, and
         the one in unrelated_write. Renaming one removes the anchor its row
         depends on. The test asserts every anchor is present, so a rename that
         breaks one fails with a message naming the missing marker; update the
         marker in the test alongside the rename.

         This note deliberately does NOT reproduce the marker strings. They are
         matched by substring against this whole file, prose included, so
         spelling one here would make it match this line instead of the code --
         the row would still pass while testing nothing.
Used by: pact-plugin/tests/test_concurrent_auditor_wake.py
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def deliver_via_write_text(team: str, name: str, payload: dict) -> None:
    """Delivery via Path.write_text on a path built in a prior statement.

    The inbox literal is NOT inside the write call -- it is in the assignment
    above it. A scanner that only inspects the call's own subtree misses this,
    which is how real delivery code is shaped.
    """
    dest = Path.home() / ".claude" / "teams" / team / "inboxes" / f"{name}.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")


def deliver_via_open_write(team: str, name: str, payload: dict) -> None:
    """Delivery via open(..., "w"), with the path built across TWO statements
    and bound to a name that does not itself contain the marker."""
    base = Path.home() / ".claude" / "teams" / team / "inboxes"
    target = base / f"{name}.json"
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))


def deliver_via_atomic_replace(team: str, name: str, payload: dict) -> None:
    """Delivery via the atomic-write idiom: mkstemp + write + os.replace.

    This is the shape the repo's own durable writers use, and it defeats a
    receiver-keyed rule twice over. The temp path arrives through a TUPLE
    target, which a Name-only target filter drops entirely; and the inbox path
    sits in an ARGUMENT of the move rather than as the receiver, so
    _receiver_root cannot see it.
    """
    dest_dir = Path.home() / ".claude" / "teams" / team / "inboxes"
    fd, tmp_path = tempfile.mkstemp(dir=str(dest_dir), suffix=".tmp")
    # The stream name here MUST NOT collide with the one in
    # deliver_via_open_write. Taint is module-flat, so reusing "handle" would
    # let this leg inherit that function's taint and fire even with tuple-target
    # binding reverted -- the leg would look like it proved the tuple fix while
    # actually proving nothing. Verified by mutation: with the binding reverted
    # and a distinct name, this write goes unflagged and the count assertion reddens.
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload))
    os.replace(tmp_path, str(dest_dir / f"{name}.json"))


def archive_away_from_inbox(team: str, name: str) -> None:
    """NEGATIVE control: a move whose SOURCE is an inbox and whose destination
    is not. Retiring a delivered message is not delivering one.

    Pairs with deliver_via_atomic_replace to pin the move rule to the
    destination position. An any-argument rule passes the positive leg and
    fails here.
    """
    inbox = Path.home() / ".claude" / "teams" / team / "inboxes" / f"{name}.json"
    os.replace(inbox, Path(tempfile.gettempdir()) / "archived.json")


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
