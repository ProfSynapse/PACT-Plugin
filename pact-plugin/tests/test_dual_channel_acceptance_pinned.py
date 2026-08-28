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
  write order + flow surface (added at TEST-phase review):
    - P10: the HANDOFF-path On Completion ordering invariant (metadata
      write → notify → intentional_wait SET) — the teachback-path twin is
      pinned in test_skill_loading_agent_teams.py; the HANDOFF-path triple
      had no pin anywhere before this case.
    - P11: the ct-teachback Flow step-3 payload-carrying-notify reference
      (extract + SSOT mirror) — its lockstep revert kept both this module
      and the byte-mirror gate green before this case.
    - P12: the payload compactness envelope (<5KB + silent-truncation
      mechanism) on both teammate notify surfaces — unpinned before this
      case; the dual-channel design carries the payload on the measured
      message channel AND the silently-truncating metadata channel.

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
# P10 — HANDOFF-path teammate write order (On Completion ordering invariant).
# ---------------------------------------------------------------------------

# The teachback-path write order (metadata write → SendMessage →
# intentional_wait SET) is pinned inline by test_skill_loading_agent_teams.py
# (TestOnStartTeachbackGateSendMessageVisible). The HANDOFF-path twin — the
# On Completion ordering-invariant blockquote — had no pin anywhere: deleting
# the whole triple from that blockquote left every plausible guarding module
# green (measured: test_skill_loading_agent_teams.py,
# test_dual_channel_acceptance_pinned.py, test_agents_structure.py,
# test_wake_ordering_pinned.py — all green with the triple removed). This
# case closes that gap; the acceptance contract "teammate write order
# unchanged" names exactly this sequence.
WRITE_ORDER_PINS = [
    (
        AGENT_TEAMS_SKILL,
        "metadata.handoff write FIRST, then notify SendMessage to "
        "team-lead, then intentional_wait SET",
    ),
]


@pytest.mark.parametrize(
    "doc_path, phrase",
    WRITE_ORDER_PINS,
    ids=[f"{p.name}::write-order" for p, _ in WRITE_ORDER_PINS],
)
def test_handoff_path_write_order_pinned(doc_path: Path, phrase: str):
    """The On Completion ordering invariant must keep naming the full
    three-step sequence — metadata.handoff write FIRST, then the notify
    SendMessage, then the intentional_wait SET. The dual-channel change
    edits this exact blockquote (it appends the payload-carrying clauses);
    nothing else in the suite guards the HANDOFF-path ordering, so a reword
    that drops the triple would silently unpin the teammate write order this
    arc's acceptance criteria require to stay unchanged."""
    assert _phrase(phrase) in _normalized(doc_path), (
        f"{doc_path.name}: HANDOFF-path write-order triple {phrase!r} not "
        f"found in the On Completion ordering invariant. The teammate write "
        f"order (metadata write → notify → intentional_wait SET) must stay "
        f"pinned; if the invariant was reworded intentionally, update this "
        f"pin in lockstep."
    )


# ---------------------------------------------------------------------------
# P11 — ct-teachback Flow step 3 notify wording (extract + SSOT mirror).
# ---------------------------------------------------------------------------

# The ct-teachback extract teaches the teachback notify shape to protocol
# readers and was edited by this arc (its retired one-line notify template
# became the payload-carrying reference). Measured gap before this pin: a
# revert of that edit — extract and SSOT region together, which keeps the
# byte-mirror gate green — left this module and the mirror gate green. Both
# surfaces are pinned (same lockstep-revert rationale as T2/P4/P5).
CT_TEACHBACK_NOTIFY_PHRASE = (
    "carrying the canonical payload verbatim (per pact-teachback Step 2)"
)

CT_TEACHBACK_SURFACES = [
    PLUGIN_ROOT / "protocols" / "pact-ct-teachback.md",
    PROTOCOLS_SSOT,
]


@pytest.mark.parametrize(
    "doc_path",
    CT_TEACHBACK_SURFACES,
    ids=lambda p: p.name,
)
def test_ct_teachback_flow_names_payload_carrying_notify(doc_path: Path):
    """The ct-teachback Flow step 3 must keep directing the reader to the
    payload-carrying notify (pact-teachback Step 2), not back to the retired
    one-line notice. The extract and its byte-mirrored SSOT region each get
    a witness so a lockstep revert of the pair — which satisfies the
    protocol-extract mirror gate — still trips this pin."""
    assert (
        _phrase(CT_TEACHBACK_NOTIFY_PHRASE) in _normalized(doc_path)
    ), (
        f"{doc_path.name}: ct-teachback Flow step-3 payload-carrying notify "
        f"phrase {CT_TEACHBACK_NOTIFY_PHRASE!r} not found. The Flow must "
        f"reference the payload-carrying notify, not the retired one-line "
        f"notice; if reworded intentionally, update this pin in lockstep on "
        f"both mirrored surfaces."
    )


# ---------------------------------------------------------------------------
# P12 — payload compactness envelope (both teammate notify surfaces).
# ---------------------------------------------------------------------------

# The <5KB envelope keeps the payload inside the channel's measured
# territory AND inside the metadata write's non-truncating range (the
# TaskUpdate silent-truncation sibling failure is live). Measured before
# this pin: the compactness sentence had no pin on either surface — a
# revert was caught only by review. The anchored span covers both the
# instruction and its mechanism; "under 5KB" alone would stay green under
# a reword that kept the number but dropped the silent-truncation reason.
COMPACTNESS_PINS = [
    (
        AGENT_TEAMS_SKILL,
        "Keep the payload under 5KB — the metadata write silently "
        "truncates oversize payloads",
    ),
    (
        TEACHBACK_SKILL,
        "Keep the payload under 5KB — the metadata write silently "
        "truncates oversize payloads",
    ),
]


@pytest.mark.parametrize(
    "doc_path, phrase",
    COMPACTNESS_PINS,
    ids=[f"{p.name}::compactness" for p, _ in COMPACTNESS_PINS],
)
def test_payload_compactness_envelope_pinned(doc_path: Path, phrase: str):
    """Both teammate notify templates must keep teaching the payload
    compactness envelope — the dual-channel design carries the payload on
    two channels, and only one of them (the message) was measured
    non-truncating through 32KB; the metadata write silently truncates
    oversize payloads. Dropping the envelope instruction re-opens the
    silent-truncation path the <5KB discipline exists to bound."""
    assert _phrase(phrase) in _normalized(doc_path), (
        f"{doc_path.name}: payload compactness envelope {phrase!r} not "
        f"found. The notify template must keep the <5KB envelope with its "
        f"silent-truncation mechanism; if the envelope was reworded "
        f"intentionally, update this pin in lockstep on both surfaces."
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
#   protocols/pact-protocols.md        -> 5 failed (P3 x2, P4, P5, P11)
#   protocols/pact-ct-teachback.md     -> 1 failed  (P11)
#   agents/pact-orchestrator.md        -> 1 failed  (P5)
#   commands/orchestrate.md            -> 2 failed (P8 x2)
#
# Measured: 19 of the module's 20 cases flip under exactly one file's
# revert; the all-edited state is 20/20 green. Absence pins flip RED on
# revert because the retired renderings are present pre-change, by design.
# P10 is the one case file-revert does NOT flip: the On Completion
# write-order triple pre-dates this arc (the arc appended clauses to the
# blockquote), so the pre-change file already carries the pinned wording —
# P10 flips under the in-place deletion below instead.
#
# P12 (added after the compactness envelope landed): the envelope sentence
# post-dates e2afa3e5, so a file revert to e2afa3e5 also flips it — per-file
# revert counts become agent-teams 4 (P1, P5, P7-absence, P12) and teachback
# 4 (P2, P5, P6-absence, P12), total 22 cases. Verified by targeted
# mutation: deleting the envelope sentence from either surface flips
# exactly that surface's P12 case (1 failed per single-surface deletion,
# 2 failed under both-surface deletion).
#
# Targeted in-place mutations (file otherwise at HEAD), measured in the same
# temp copy — predicted cardinalities all confirmed:
#   point-4 "BEFORE" reworded            -> 1 failed (P4)
#   T2 sentence reverted in place        -> 2 failed (P3 phrase-2, P5);
#     P3 phrase-1 stays green — point 4 carries "data-integrity finding"
#     too, so phrase-1 is pair-level protection, not T2-anchored
#   T2 "DEFERRED audit" lowercased       -> 1 failed (P5)
#   retired teachback framing re-added   -> 1 failed (P6)
#   retired 1-2-sentences shape re-added -> 1 failed (P7)
#   orchestrate Task-B phrase reworded   -> 1 failed (P8 Task-B case)
#   HANDOFF-PAYLOAD-BEGIN renamed        -> 1 failed (P1)
#   "wake-send" planted in new T2 prose  -> 1 failed in
#     test_wake_ordering_pinned.py (P9 inherited guard, verified live)
#   On Completion write-order deleted    -> 1 failed (P10; was 0 before
#     the pin — the gap this case closes)
#   ct-teachback Flow edit reverted BOTH sides (extract + SSOT, mirror
#     gate green)                          -> 2 failed (P11; was 0 before
#     the pin — the gap this case closes)
# ---------------------------------------------------------------------------
