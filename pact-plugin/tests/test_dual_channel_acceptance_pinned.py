"""
Structural pin tests for the dual-channel acceptance rules.

Pins the reader-facing instruction surfaces that teach both channels of
teachback/HANDOFF acceptance — the notify SendMessage now carries the
canonical payload verbatim (message channel), while the raw task-metadata
read is demoted to the lead's DEFERRED audit (disk channel):

  teammate-side payload encoding (skills/pact-agent-teams/SKILL.md,
  skills/pact-teachback/SKILL.md):
    - HANDOFF-PAYLOAD-BEGIN / TEACHBACK-PAYLOAD-BEGIN delimiter tokens
      (grep-able payload boundaries in the notify templates).
    - The retired one-line-notify renderings stay retired (absence pins).
  lead-side acceptance keying (protocols/pact-completion-authority.md +
    its byte-mirrored region in protocols/pact-protocols.md):
    - T2: accept/reject on the message-carried payload; a missing or
      diverging disk copy is an integrity finding, never a basis for
      rejecting an already-acted-on submission.
    - T1 point 4: the deferred disk-vs-message audit runs at the lead's
      next turn boundary, BEFORE acting on that teammate's next
      submission.
  vocabulary (all six surfaces):
    - "deferred audit" per surface — count-free presence (no fixed
      recurrence intended), like the wake-ordering module's phrase pins.
  dispatch templates (commands/orchestrate.md):
    - both Task-A and Task-B description strings name the payload-carrying
      notify (per-site pins; the two sites carry different full phrases).

Inherited vocabulary guard (P9, no new case here): the NEW lead-side
prose is covered by the existing retired-"wake-send"/"wake send" absence
pin in test_wake_ordering_pinned.py, already parametrized over
completion-authority, the SSOT region, and the orchestrator persona —
the three surfaces this change edits lead-side. Reintroducing the retired
send-term through the new wording trips that pin; nothing here duplicates
it.

PRESENCE pins, not counts. None of these phrases is intended to recur a
fixed number of times per surface, so count pins would add
lockstep-maintenance cost without catching a real erosion shape. (The
Read-Trigger marker phrase keeps its own EXPECTED_COUNTS lockstep in
test_read_trigger_precondition_pinned.py; this change deliberately does
NOT quote that phrase — paraphrase keeps those counts byte-stable.)

PHRASES, not line shapes. Matching is backtick-and-whitespace-normalized
(see _phrase: strip backticks, then " ".join(text.split())) per the
wake-ordering convention — re-wrapping and inline-code rendering survive,
a re-WORD does not. Matching is CASE-SENSITIVE by design; the "deferred
audit" pin set uses per-surface casing (the completion-authority extract
and its SSOT mirror carry the T2 sentence's uppercase "DEFERRED audit",
every other surface carries the lowercase mid-sentence form) — do not
normalize case to unify them.

P4 anchoring rationale (phantom-green guard, same shape as the
wake-ordering postdating pin): the T2 sentence on the same surface
contains the LOWERCASE span "before acting on that teammate's next
submission". A case-insensitive or shorter pin would be satisfied by T2
alone and stay green if T1's point 4 regressed; the uppercase anchored
long form exists only at point 4.

Counter-test-by-revert (verified at authoring time, measured in a TEMP
COPY of the plugin tree — the live worktree is never mutated): with each
edited file individually restored to its pre-change state
(git show <pre-change-ref>:<path> over the copy) and this module run
against the copy, exactly that file's P-cases fail. The measured flip-set
per file and the total are recorded in the module-level comment at the
bottom of this file.
"""

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

AGENT_TEAMS_SKILL = PLUGIN_ROOT / "skills" / "pact-agent-teams" / "SKILL.md"
TEACHBACK_SKILL = PLUGIN_ROOT / "skills" / "pact-teachback" / "SKILL.md"
COMPLETION_AUTHORITY = PLUGIN_ROOT / "protocols" / "pact-completion-authority.md"
PROTOCOLS_SSOT = PLUGIN_ROOT / "protocols" / "pact-protocols.md"
ORCHESTRATOR = PLUGIN_ROOT / "agents" / "pact-orchestrator.md"
ORCHESTRATE = PLUGIN_ROOT / "commands" / "orchestrate.md"


def _raw(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _phrase(text: str) -> str:
    """Phrase-matching normalization: strip backticks, then collapse any
    whitespace run to a single space. Tool language is inline-code
    formatted in the shipped markdown, so a pinned phrase must match a
    subject rendered with backticks inside the phrase span. Applied to
    BOTH sides (file text and pinned phrase) per the wake-ordering
    module's convention."""
    return " ".join(text.replace("`", "").split())


def _normalized(path: Path) -> str:
    return _phrase(_raw(path))


# ---------------------------------------------------------------------------
# P1/P2 — payload delimiter tokens (teammate-side notify templates).
# ---------------------------------------------------------------------------

PAYLOAD_DELIMITER_PINS = [
    (AGENT_TEAMS_SKILL, "HANDOFF-PAYLOAD-BEGIN"),
    (TEACHBACK_SKILL, "TEACHBACK-PAYLOAD-BEGIN"),
]


@pytest.mark.parametrize(
    "doc_path, token",
    PAYLOAD_DELIMITER_PINS,
    ids=[f"{p.name}::{t}" for p, t in PAYLOAD_DELIMITER_PINS],
)
def test_payload_delimiter_present(doc_path: Path, token: str):
    """The notify template must carry its payload's grep-able BEGIN
    delimiter — the boundary marker the lead's message-side acceptance
    keys on. Delimiters are plain text (no backtick or wrap variance), so
    normalized matching is equivalent to raw here; the normalized form is
    used for uniformity."""
    assert _phrase(token) in _normalized(doc_path), (
        f"{doc_path.name}: payload delimiter {token!r} not found. The "
        f"notify template must carry the canonical payload verbatim inside "
        f"its BEGIN/END delimiters; if the encoding was changed "
        f"intentionally, update this pin in lockstep."
    )


# ---------------------------------------------------------------------------
# P3 — T2 acceptance-keying sentence (extract + byte-mirrored SSOT region).
# ---------------------------------------------------------------------------

T2_PHRASES = [
    # The classification sentence: divergence or a missing disk copy is an
    # integrity finding ("data-integrity finding" carries the pinned span).
    "integrity finding",
    # The never-a-rejection clause: the deferred audit must not convert a
    # disk/message divergence into a false rejection of an acted-on
    # submission.
    "never a basis for rejecting",
]

T2_SURFACES = [COMPLETION_AUTHORITY, PROTOCOLS_SSOT]

T2_PINS = [(p, ph) for p in T2_SURFACES for ph in T2_PHRASES]


@pytest.mark.parametrize(
    "doc_path, phrase",
    T2_PINS,
    ids=[f"{p.name}::{ph[:40]}" for p, ph in T2_PINS],
)
def test_t2_acceptance_keying_phrase_present(doc_path: Path, phrase: str):
    """The T2 rewrite keys acceptance on the message-carried payload and
    classifies disk/message divergence as an integrity finding — never as
    a rejection basis. Pinned on the extract AND its byte-mirrored SSOT
    region: a lockstep revert of the pair leaves them mutually
    byte-equal (the protocol-extract audit stays green), so each surface
    gets its own witness."""
    assert _phrase(phrase) in _normalized(doc_path), (
        f"{doc_path.name}: T2 acceptance-keying phrase {phrase!r} not "
        f"found. The lead accepts on the payload the notify carries; a "
        f"missing or diverging disk copy is an integrity finding, never "
        f"a rejection. If reworded intentionally, update this pin in "
        f"lockstep on both mirrored surfaces."
    )


# ---------------------------------------------------------------------------
# P4 — T1 point 4 deferred-audit trigger (anchored long form).
# ---------------------------------------------------------------------------

P4_TRIGGER = "BEFORE acting on that teammate's next submission"

P4_SURFACES = [COMPLETION_AUTHORITY, PROTOCOLS_SSOT]


@pytest.mark.parametrize("doc_path", P4_SURFACES, ids=lambda p: p.name)
def test_t1_deferred_audit_trigger_present(doc_path: Path):
    """The deferred-audit deadline: the disk-vs-message comparison runs at
    the lead's next turn boundary, BEFORE acting on that teammate's next
    submission. The anchored uppercase long form exists only at T1's
    point 4 — the T2 sentence on the same surface carries the lowercase
    span, which would phantom-green a case-insensitive or shorter pin
    (see module docstring)."""
    assert _phrase(P4_TRIGGER) in _normalized(doc_path), (
        f"{doc_path.name}: deferred-audit trigger {P4_TRIGGER!r} not "
        f"found. The audit deadline is pinned to the teammate's next "
        f"submission; if the trigger was reworded intentionally, update "
        f"this pin in lockstep on both mirrored surfaces."
    )


# ---------------------------------------------------------------------------
# P5 — "deferred audit" vocabulary, count-free presence per surface.
# ---------------------------------------------------------------------------

# Per-surface casing is deliberate (see module docstring): the extract
# and its SSOT mirror carry the T2 sentence's uppercase "DEFERRED audit";
# every other surface carries the lowercase mid-sentence form.
DEFERRED_AUDIT_PINS = [
    (COMPLETION_AUTHORITY, "DEFERRED audit"),
    (PROTOCOLS_SSOT, "DEFERRED audit"),
    (ORCHESTRATOR, "deferred audit"),
    (AGENT_TEAMS_SKILL, "deferred audit"),
    (TEACHBACK_SKILL, "deferred audit"),
]


@pytest.mark.parametrize(
    "doc_path, phrase",
    DEFERRED_AUDIT_PINS,
    ids=[f"{p.name}::{ph}" for p, ph in DEFERRED_AUDIT_PINS],
)
def test_deferred_audit_vocabulary_present(doc_path: Path, phrase: str):
    """Every surface this change touched must keep teaching the
    disk-read's new role by name — the deferred audit — so no reader-
    facing surface silently reverts to acceptance-time raw reads while
    others move on. Count-free: the vocabulary legitimately recurs a
    variable number of times per surface; only its presence is the
    contract."""
    assert _phrase(phrase) in _normalized(doc_path), (
        f"{doc_path.name}: deferred-audit vocabulary ({phrase!r}, "
        f"per-surface casing) not found. The surface must name the raw "
        f"read's role as the deferred audit; if the term was retired "
        f"intentionally, update this pin in lockstep across all surfaces."
    )


# ---------------------------------------------------------------------------
# P6/P7 — retired one-line-notify renderings (absence pins).
# ---------------------------------------------------------------------------

RETIRED_FRAMING_PINS = [
    # The teachback Step 2 heading's retired framing: the notify was a
    # lightweight notice, explicitly NOT the payload. The dual-channel
    # design makes the payload-carrying notify the contract; the retired
    # framing must not return as instruction text.
    (TEACHBACK_SKILL, "lightweight prose, NOT the full payload"),
    # The agent-teams HANDOFF Step 2 retired one-line-notify format
    # ("1-2 sentences: what was done"). The template now carries the
    # HANDOFF payload verbatim; the one-line summary slot must not be
    # taught as the notify's content shape again.
    (AGENT_TEAMS_SKILL, "1-2 sentences: what was done"),
]


@pytest.mark.parametrize(
    "doc_path, retired",
    RETIRED_FRAMING_PINS,
    ids=[f"{p.name}::{r[:40]}" for p, r in RETIRED_FRAMING_PINS],
)
def test_retired_one_line_notify_framing_absent(doc_path: Path, retired: str):
    """Regression guard: the notify is payload-carrying by contract.
    Reintroducing either retired rendering — the "lightweight prose"
    framing on the teachback step or the "1-2 sentences" content shape on
    the HANDOFF step — would resurrect the one-line notify as taught
    behavior on a runtime-loaded surface. Normalized matching so a
    re-wrapped or backticked reintroduction cannot slip past."""
    assert _phrase(retired) not in _normalized(doc_path), (
        f"{doc_path.name}: retired notify framing {retired!r} present. "
        f"The notify carries the canonical payload verbatim; the one-line "
        f"notice is the retired shape (if a future rule genuinely needs "
        f"it, update this guard deliberately)."
    )


# ---------------------------------------------------------------------------
# P8 — dispatch-template payload-carrying notify (orchestrate.md, per site).
# ---------------------------------------------------------------------------

# The two sites carry different full phrases (Task-A names the teachback
# payload; Task-B names the HANDOFF payload), so each site gets its own
# anchored pin — a revert of either description string flips exactly its
# own case.
ORCHESTRATE_PINS = [
    "send the notify SendMessage carrying the canonical payload verbatim (pact-teachback Step 2)",
    "send notify SendMessage carrying the canonical HANDOFF payload (pact-agent-teams On Completion Step 2)",
]


@pytest.mark.parametrize("phrase", ORCHESTRATE_PINS, ids=lambda ph: ph[:48])
def test_orchestrate_dispatch_names_payload_carrying_notify(phrase: str):
    """Both dispatch description strings name the payload-carrying notify
    (and the Task-A string teaches notify-before-wait, matching the
    skill's ordering invariant). The commands are templates the lead
    copies at dispatch time; a template that reverts to the bare
    "send notify SendMessage" wording dispatches teammates who never
    carry the payload."""
    assert _phrase(phrase) in _normalized(ORCHESTRATE), (
        f"orchestrate.md: dispatch-template phrase {phrase!r} not found. "
        f"The dispatch text must name the payload-carrying notify; if the "
        f"template was reworded intentionally, update this pin in "
        f"lockstep."
    )


# ---------------------------------------------------------------------------
# Counter-test flip-set record (measured at authoring time in a TEMP COPY
# of the plugin tree; see module docstring). Each edited file restored
# individually to its pre-change state (git show e2afa3e5:<path> over the
# copy), module run against the copy, then the edited version restored:
#
#   skills/pact-agent-teams/SKILL.md   -> 3 failed (P1, P5, P7-absence)
#   skills/pact-teachback/SKILL.md     -> 3 failed (P2, P5, P6-absence)
#   protocols/pact-completion-authority.md
#                                      -> 4 failed (P3 x2, P4, P5)
#   protocols/pact-protocols.md        -> 4 failed (P3 x2, P4, P5)
#   agents/pact-orchestrator.md        -> 1 failed  (P5)
#   commands/orchestrate.md            -> 2 failed (P8 x2)
#
# Measured total flip-set: 17 of the module's 17 cases (every case flips
# under exactly one file's revert); the all-edited state is 17/17 green.
# Absence pins flip RED on revert because the retired renderings are
# present pre-change, by design.
# ---------------------------------------------------------------------------
