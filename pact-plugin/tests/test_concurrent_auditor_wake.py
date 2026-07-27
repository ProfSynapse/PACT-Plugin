"""
Location: pact-plugin/tests/test_concurrent_auditor_wake.py
Summary: Four pins guarding the concurrent-auditor wake fix. A concurrent
         auditor dispatched before its coders produce output went idle and
         never woke, so a mandated quality gate was lost in silence. The fix
         relays a wake from the orchestrator on coder stage-ready, replaces
         the instruction that caused the wait, corrects the protocol paragraph
         that authorised proceeding without the audit, and adds a phase-exit
         coverage check.

         Pin 1  the wait instruction never ships without naming the wake
         Pin 2  the orchestrator is instructed to send that wake
         Pin 3  the auditor is told not to end its turn depending on a
                background process
         Pin 4  the repo fact the guidance asserts is true of this repo:
                no PACT hook can deliver a message

WHAT THESE PINS DO NOT ESTABLISH -- read this before trusting a green run.

  Pins 1-3 are TIER 1. They establish that specific text is present or
  absent, that a required clause co-occurs with the instruction it qualifies
  at a pinned cardinality, and that the surfaces carrying it do not drift
  apart. They establish NOTHING about behaviour. In particular they do not
  establish that any agent reading the instruction acts on it.

  Every Tier-1 pin here is LITERAL-anchored. It cannot see a semantically
  equivalent PARAPHRASE introduced at a NEW site. This is not theoretical:
  the Phase C trigger already exhibits it, at literal occupancy 1 against
  semantic occupancy 3. Cardinality catches a paraphrase that REPLACES a
  known site; nothing here catches one that is ADDED elsewhere.

  Pin 4 is TIER 2. It establishes that a factual claim the shipped text makes
  is true of this repo at test time -- strictly more than presence, and still
  not behaviour. Its own limits are documented on the class.

  There is no coverage percentage. For a prose surface the number would
  itself be the overstatement.

Used by: pact-plugin test suite (standing merge gate).
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Set, Tuple

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent

AGENTS_DIR = PLUGIN_ROOT / "agents"
COMMANDS_DIR = PLUGIN_ROOT / "commands"
PROTOCOLS_DIR = PLUGIN_ROOT / "protocols"
HOOKS_DIR = PLUGIN_ROOT / "hooks"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

AUDITOR_AGENT = AGENTS_DIR / "pact-auditor.md"
AUDIT_PROTOCOL = PROTOCOLS_DIR / "pact-audit.md"
PROTOCOLS_SSOT = PROTOCOLS_DIR / "pact-protocols.md"
ORCHESTRATE_CMD = COMMANDS_DIR / "orchestrate.md"


# =============================================================================
# Shared helpers
# =============================================================================


def _all_markdown() -> List[Path]:
    """Every markdown surface in the plugin, sorted for stable diagnostics."""
    return sorted(PLUGIN_ROOT.rglob("*.md"))


def _occurrences(literal: str) -> List[Tuple[Path, int]]:
    """(path, count) for every markdown file containing `literal`."""
    hits = []
    for path in _all_markdown():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover - defensive
            continue
        count = text.count(literal)
        if count:
            hits.append((path, count))
    return hits


def _total(hits: List[Tuple[Path, int]]) -> int:
    return sum(count for _, count in hits)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(PLUGIN_ROOT).as_posix()
    except ValueError:  # pragma: no cover - defensive
        return path.as_posix()


def _enclosing_block(text: str, literal: str) -> Iterator[str]:
    """Yield the blank-line-delimited block around each occurrence of `literal`.

    Block, not line. Post-fix both wait-phrase occurrences happen to carry the
    relay clause in the SAME sentence, which would make a per-line conjunction
    very nearly a tautology -- and would silently stop meaning anything if the
    protocol text were later split across sentences. The block is the unit that
    keeps the conjunction honest under reformatting.
    """
    lines = text.splitlines()
    start = 0
    while start < len(lines):
        if not lines[start].strip():
            start += 1
            continue
        end = start
        while end < len(lines) and lines[end].strip():
            end += 1
        block = "\n".join(lines[start:end])
        if literal in block:
            yield block
        start = end


# =============================================================================
# Pin 1 -- the wait instruction never ships without naming the wake
# =============================================================================


class TestWaitInstructionCarriesTheWake:
    """The instruction to wait must always name what ends the wait.

    The defect had two halves. One surface told the auditor to wait and named
    no wake at all; a second told the lead that an absent audit signal means
    "not written yet, never no signal". An auditor that waits without a named
    wake is the failure, so the property worth pinning is a CONJUNCTION: every
    surviving wait instruction also names the relay that ends it.

    A bare conjunction is not enough, and the reason is the whole point of this
    class. "Every occurrence of X also carries Y" is vacuously TRUE when there
    are zero occurrences of X, so DELETING the instruction would pass it in
    silence. Cardinality is what closes that door.

    The cardinality is 2, and it is exact. Post-fix the wait phrase survives
    only in the two protocol copies; the agent body is a full replacement that
    names the relay instead of instructing a bare wait. Exactness is
    load-bearing rather than stylistic, and it can be checked: a floor of >= 2
    is TRUE before the fix (3 sites) and TRUE after (2 sites), so a floor
    cannot observe the change at all. Exact-2 is FALSE before and TRUE after.
    Use the weakest predicate that still discriminates -- here nothing weaker
    than exactness does.

    What this pin does NOT establish: that an auditor reading either surface
    acts on it, and that no NEW surface has introduced a paraphrased wait
    instruction under different words. The literal anchor is blind to that.
    """

    WAIT_PHRASE = "Wait for coders to produce initial output before observing"
    RELAY_CLAUSE = "orchestrator's stage-ready relay"

    # The two surfaces that legitimately retain the wait phrase post-fix.
    WAIT_PHRASE_SITES = {"protocols/pact-audit.md", "protocols/pact-protocols.md"}

    # Every surface that must name the relay -- the protocol pair PLUS the
    # agent body, which no longer carries the wait phrase and so is invisible
    # to the conjunction above. Without this leg, deleting the relay clause
    # from the agent body would leave the rest of this class green.
    RELAY_SITES = (
        "agents/pact-auditor.md",
        "protocols/pact-audit.md",
        "protocols/pact-protocols.md",
    )

    def test_markdown_sweep_is_not_empty(self):
        """Denominator guard: a sweep that resolves nothing would make every
        cardinality assertion below vacuously satisfiable."""
        surfaces = _all_markdown()
        assert len(surfaces) > 100, (
            f"markdown sweep resolved only {len(surfaces)} files under "
            f"{PLUGIN_ROOT} -- the cardinality pins below are measured against "
            f"this sweep and would be meaningless on a truncated one"
        )

    def test_wait_phrase_cardinality_is_exactly_two(self):
        hits = _occurrences(self.WAIT_PHRASE)
        total = _total(hits)
        assert total == 2, (
            f"wait-phrase cardinality is {total}, expected exactly 2.\n"
            f"found: {[(_rel(p), c) for p, c in hits]}\n"
            f"  {total} < 2 means a wait instruction was DELETED or "
            f"paraphrased -- the surfaces are drifting apart.\n"
            f"  {total} > 2 means a bare wait instruction was RE-ADDED "
            f"somewhere. That is the original defect returning: an auditor "
            f"told to wait with no named wake does not come back.\n"
            f"If a surface is being added or removed deliberately, change this "
            f"constant deliberately -- do not relax it to a floor. A floor is "
            f"TRUE both before and after the fix and cannot observe it."
        )

    def test_wait_phrase_lives_only_in_the_protocol_pair(self):
        """Pin the site identities, not just the count.

        Two occurrences that MOVED to different files would satisfy the count
        while relocating the instruction to a surface nobody audited.
        """
        sites = {_rel(p) for p, _ in _occurrences(self.WAIT_PHRASE)}
        assert sites == self.WAIT_PHRASE_SITES, (
            f"wait phrase site set is {sorted(sites)}, expected "
            f"{sorted(self.WAIT_PHRASE_SITES)}. The agent body must NOT carry "
            f"the bare wait phrase -- there it was replaced by an instruction "
            f"that names the relay."
        )

    @pytest.mark.parametrize("relpath", sorted(WAIT_PHRASE_SITES))
    def test_each_wait_block_names_the_relay(self, relpath):
        """The conjunction. Every block instructing a wait names the wake.

        Satisfied by the RELAY clause specifically, not by the poll fallback:
        a poll-only fix passes a laxer pin and does not close the gap, because
        an agent that has already ended its turn cannot poll.
        """
        path = PLUGIN_ROOT / relpath
        blocks = list(_enclosing_block(path.read_text(encoding="utf-8"), self.WAIT_PHRASE))
        assert blocks, f"{relpath}: wait phrase not found in any block"
        for block in blocks:
            assert self.RELAY_CLAUSE in block, (
                f"{relpath}: a block instructs the auditor to wait but does not "
                f"name {self.RELAY_CLAUSE!r} as the wake.\n"
                f"block:\n{block}\n"
                f"An instruction to wait that names no wake is the defect this "
                f"pin exists for. A bounded poll is a fallback, not the wake."
            )

    @pytest.mark.parametrize("relpath", RELAY_SITES)
    def test_relay_clause_present_at_every_named_surface(self, relpath):
        """Presence, not cardinality, and the asymmetry is deliberate.

        Presence is already FALSE before the fix (the clause existed nowhere)
        and TRUE after, so it discriminates on its own. An exact count would
        add no detection and would fire on a fourth surface legitimately
        naming the relay -- a false alarm, not a drift signal.

        This is the leg that covers the agent body, which the conjunction
        above cannot see: the fix REMOVED the wait phrase from that file, so
        deleting its relay clause is invisible to every other test here.
        """
        path = PLUGIN_ROOT / relpath
        assert path.is_file(), f"expected surface missing: {relpath}"
        text = path.read_text(encoding="utf-8")
        assert self.RELAY_CLAUSE in text, (
            f"{relpath} no longer names {self.RELAY_CLAUSE!r}. Every surface "
            f"that discusses the auditor's warm-up must name where the wake "
            f"comes from; otherwise a reader of THIS surface learns only that "
            f"it should wait."
        )


# =============================================================================
# Pin 2 -- the orchestrator is instructed to send the wake
# =============================================================================


class TestOrchestratorRelaysWakeOnStageReady:
    """The wake the auditor is told to expect must actually be instructed.

    Pin 1 makes the auditor's surfaces promise a relay. If nothing tells the
    orchestrator to send one, that promise is a dangling reference and the
    auditor waits for a message no one was asked to send.

    Anchored on "observe the staged diff", which had occupancy 0 before the
    fix. NOT anchored on "stage-ready": that string already occurs 8 times
    across 6 files, so a file-wide stage-ready pin would be satisfied by
    unrelated prose and could not observe this change at all.

    What this pin does NOT establish: that an orchestrator sends the relay.
    And it cannot -- by design. The fix pairs the relay (primary) with a
    phase-exit coverage check (backstop) that fires whenever the relay does
    not, so no run can distinguish "the relay worked" from "the relay was
    skipped and the gate caught it". That is the correct trade, since a
    silently-lost audit is far worse than an unmeasurable mechanism, but it is
    a KNOWN consequence rather than a gap someone forgot to close. Answering
    "is the relay working?" needs a deliberate probe with the gate disarmed.
    """

    RELAY_ANCHOR = "observe the staged diff"
    AUDITOR_DISPATCH = 'subagent_type="pact-auditor"'
    PHASE_EXIT_MARKER = "**Before next phase**"

    def test_relay_instruction_is_unique_across_the_plugin(self):
        hits = _occurrences(self.RELAY_ANCHOR)
        assert _total(hits) == 1 and [_rel(p) for p, _ in hits] == ["commands/orchestrate.md"], (
            f"relay instruction anchor {self.RELAY_ANCHOR!r} found at "
            f"{[(_rel(p), c) for p, c in hits]}, expected exactly one "
            f"occurrence in commands/orchestrate.md. Zero means the relay "
            f"instruction was deleted and the auditor's promised wake has no "
            f"sender; more than one means a second, possibly divergent, relay "
            f"instruction was introduced."
        )

    def test_relay_line_names_trigger_recipient_and_mechanism(self):
        """The line must be actionable on its own: WHEN, TO WHOM, and HOW.

        Discriminates against base, where no line in orchestrate.md paired
        "auditor" with "stage-ready" at all.
        """
        text = ORCHESTRATE_CMD.read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if self.RELAY_ANCHOR in ln)
        for element, label in (
            ("stage-ready", "the trigger"),
            ("auditor", "the recipient"),
            ("SendMessage", "the mechanism"),
        ):
            assert element in line, (
                f"relay instruction does not name {label} ({element!r}):\n"
                f"  {line}\n"
                f"An orchestrator reading this line must be able to act on it "
                f"without reconstructing the missing half from context."
            )

    def test_relay_sits_in_the_auditor_dispatch_region(self):
        """Placement is part of the instruction.

        The relay must live with the auditor dispatch, not inside the
        phase-exit checklist. That checklist already carries a separate
        coverage check which is a PRECONDITION of dispatching TEST; the relay
        is an action taken during CODE. Collapsing the two into the checklist
        would turn a continuous relay into a once-per-phase gate item.
        """
        text = ORCHESTRATE_CMD.read_text(encoding="utf-8")
        dispatch_at = text.index(self.AUDITOR_DISPATCH)
        relay_at = text.index(self.RELAY_ANCHOR)
        checklist_at = text.index(self.PHASE_EXIT_MARKER, dispatch_at)
        assert dispatch_at < relay_at < checklist_at, (
            f"relay instruction is outside the auditor dispatch region "
            f"(dispatch@{dispatch_at}, relay@{relay_at}, "
            f"checklist@{checklist_at}). It belongs with the auditor dispatch "
            f"during CODE, not in the phase-exit checklist."
        )


# =============================================================================
# Pin 3 -- the guardrail prohibits the posture, not the mechanism
# =============================================================================


class TestAuditorGuardrailProhibitsTurnEndingDependence:
    """The guardrail must prohibit the POSTURE, and be pinned where it lives.

    The hazard is ending a turn with a background process as the only route
    back. It is NOT backgrounding as such -- a long command backgrounded while
    the agent stays in its turn and polls it is fine, and the concurrent
    auditor for this very change did exactly that safely.

    This pin is anchored on the posture headline, deliberately NOT on the word
    "monitor". That word was removed from the guardrail when it was re-aimed
    from mechanism-form to posture-form, and now survives only in the protocol
    pair. An anti-"monitor" pin aimed at the agent body would therefore have
    PASSED while pointing at the wrong file -- green, and blind to the surface
    it was written to protect. Anchor occupancy is checked in the file the pin
    actually asserts against, which is what makes that failure impossible here.

    Presence suffices: the headline had occupancy 0 before the fix and 1 after,
    so it discriminates without a count.

    What this pin does NOT establish: that an auditor obeys the guardrail, or
    that the prohibition is correctly scoped in prose an agent will read the
    way it was meant. It establishes that the bullet is present, in the
    register that carries the agent's hard boundaries.
    """

    POSTURE_HEADLINE = "end your turn with a background process as your route back"
    BOUNDARY_REGISTER = "## WHAT YOU DO NOT DO"
    NEXT_SECTION = "## OBSERVATION PROTOCOL"

    def test_posture_headline_present_in_agent_body(self):
        text = AUDITOR_AGENT.read_text(encoding="utf-8")
        assert self.POSTURE_HEADLINE in text, (
            f"agents/pact-auditor.md no longer contains the posture guardrail "
            f"{self.POSTURE_HEADLINE!r}. Without it the agent body prohibits "
            f"nothing about turn-ending dependence, which is the mechanism by "
            f"which an auditor loses its route back."
        )

    def test_posture_headline_is_in_the_boundary_register(self):
        """Scope, not just presence.

        The same sentence relocated into explanatory prose stops being a hard
        boundary. Bullet-scanners read the register; they do not read prose.
        """
        text = AUDITOR_AGENT.read_text(encoding="utf-8")
        start = text.index(self.BOUNDARY_REGISTER)
        end = text.index(self.NEXT_SECTION, start)
        register = text[start:end]
        assert self.POSTURE_HEADLINE in register, (
            f"the posture guardrail is present in agents/pact-auditor.md but "
            f"NOT inside {self.BOUNDARY_REGISTER!r}. It must sit in the "
            f"boundary register to read as a prohibition rather than as "
            f"commentary."
        )

    def test_guardrail_permits_backgrounding_within_a_turn(self):
        """The narrowing is load-bearing and must not silently revert.

        The earlier draft prohibited a MECHANISM. Read literally it forbade a
        legitimate long-running command; read loosely it permitted the actual
        failure. If the permission clause disappears, the guardrail has slid
        back toward prohibiting the mechanism.
        """
        text = AUDITOR_AGENT.read_text(encoding="utf-8")
        start = text.index(self.BOUNDARY_REGISTER)
        end = text.index(self.NEXT_SECTION, start)
        register = text[start:end]
        assert "Backgrounding a long command is fine" in register, (
            "the guardrail no longer states that backgrounding within a turn "
            "is permitted. Without that clause the bullet reads as a ban on "
            "the mechanism, which forbids legitimate long-running commands "
            "and misidentifies the hazard."
        )


# =============================================================================
# Pin 4 -- the repo fact: no PACT hook can deliver a message
# =============================================================================
#
# The shipped guidance tells the auditor "no PACT hook sends a message". That
# is a claim ABOUT THIS REPO, and unlike the pins above it can be checked
# rather than merely located.
#
# The scan is AST-based, not textual, and it has to be: hooks/ mentions inbox
# paths in 8 files, all of them read-only probes. A text scan would flag every
# one of them. Structure is what separates a mention from a delivery.


INBOX_MARKER = "inbox"
WRITE_METHOD_NAMES = frozenset({"write", "write_text", "write_bytes", "writelines"})
WRITE_MODE_CHARS = ("w", "a", "x", "+")

# An ENUMERATION, and its limits are stated on the test class below. There is
# no Python send-message callable in this repo -- SendMessage is a platform
# tool with no hookable event -- so this set is a proxy for a construct that
# does not currently exist in any form.
SEND_CALLEE_NAMES = frozenset({
    "send_message",
    "sendmessage",
    "send_msg",
    "post_message",
    "deliver_message",
    "enqueue_message",
    "notify_teammate",
})


def hook_python_files() -> List[Path]:
    """The scanned denominator: every .py under hooks/, __pycache__ excluded.

    The basis is stated rather than implied, because it is the vacuity guard.
    An all-files walk would be wrong here: the repo's untracked runtime state
    (hook-errors.log, save-session.pid, .CLAUDE.md.lock) is written while a
    session runs, so an all-files count can change between two measurements
    minutes apart with nobody editing anything. A flaky control is worse than
    no control, because its red gets dismissed as noise and then its green
    stops being read.
    """
    return sorted(p for p in HOOKS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _receiver_root(node: ast.Call) -> str | None:
    """Root name of an attribute call's receiver: a.b.c.write_text() -> 'a'."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    cur = func.value
    while isinstance(cur, (ast.Attribute, ast.Subscript)):
        cur = cur.value
    return cur.id if isinstance(cur, ast.Name) else None


def _mentions_inbox(node: ast.AST, tainted: Set[str]) -> bool:
    """True if the subtree names an inbox path -- as a string literal, as an
    identifier, or by reading a name already known to hold one."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if INBOX_MARKER in sub.value.lower():
                return True
        elif isinstance(sub, ast.Name):
            if INBOX_MARKER in sub.id.lower() or sub.id in tainted:
                return True
        elif isinstance(sub, ast.Attribute):
            if INBOX_MARKER in sub.attr.lower():
                return True
    return False


def _tainted_names(tree: ast.AST) -> Set[str]:
    """Names bound to an expression that mentions an inbox path.

    Iterated to a fixpoint so multi-step path construction propagates. Real
    delivery code builds the path in one statement and writes in another, so a
    scanner that only inspected the write call's own subtree would miss it
    entirely -- which is exactly what the fixture's first positive leg proves.
    """
    tainted: Set[str] = set()
    for _ in range(8):
        grew = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if node.value is None:
                    continue
                targets, value = [node.target], node.value
            elif isinstance(node, ast.withitem):
                if node.optional_vars is None:
                    continue
                targets, value = [node.optional_vars], node.context_expr
            else:
                continue
            if not _mentions_inbox(value, tainted):
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in tainted:
                    tainted.add(target.id)
                    grew = True
        if not grew:
            break
    return tainted


def _is_write_mode(call: ast.Call) -> bool:
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
        if isinstance(mode, str) and any(c in mode for c in WRITE_MODE_CHARS):
            return True
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            mode = keyword.value.value
            if isinstance(mode, str) and any(c in mode for c in WRITE_MODE_CHARS):
                return True
    return False


def scan_source(source: str) -> Tuple[List[Tuple[str, int, str]], Set[str]]:
    """Return (findings, tainted-names) for one module's source.

    A finding is (rule, lineno, callee). Two rules:
      INBOX-WRITE  a write-capable call on an inbox-derived path
      SEND-CALL    a call to a name in the send enumeration
    """
    findings: List[Tuple[str, int, str]] = []
    tree = ast.parse(source)
    tainted = _tainted_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node)
        if name is None:
            continue
        if name in SEND_CALLEE_NAMES:
            findings.append(("SEND-CALL", node.lineno, name))
        elif name in WRITE_METHOD_NAMES:
            root = _receiver_root(node)
            rooted = root is not None and (root in tainted or INBOX_MARKER in root.lower())
            if rooted or _mentions_inbox(node, tainted):
                findings.append(("INBOX-WRITE", node.lineno, name))
        elif name == "open" and _is_write_mode(node) and _mentions_inbox(node, tainted):
            findings.append(("INBOX-WRITE", node.lineno, name))
    return findings, tainted


class TestNoPactHookCanDeliverAMessage:
    """The claim "no PACT hook sends a message" is TRUE of this repo.

    WHAT THIS DOES NOT ESTABLISH, and the first item is the important one:

    1. The instruction's force rests on a CONJUNCTION -- PACT provides no wake
       AND the platform provides none. This pin covers the PACT conjunct only.
       If the platform later gained wake-on-process-exit, the pinned sentence
       would remain TRUE and this pin would stay GREEN while the guidance
       became misleading. Named, not closed; it is not pytest-testable.

    2. SEND_CALLEE_NAMES is an ENUMERATION the author wrote, and there is no
       Python send-message callable in this repo to calibrate it against. The
       fixture proves the scanner runs and flags -- it validates the PIPELINE,
       not the PATTERN. Delivery routed through an indirection the enumeration
       does not anticipate (a subprocess invocation, a dynamically-built
       attribute, a helper in a module the sweep does not cover) would not be
       caught. Read a green here as "no delivery construct of a KNOWN SHAPE",
       never as proof of impossibility.

    3. Taint propagation is intra-module and assignment-based. A path passed
       through a function boundary and written on the far side is not tracked.
    """

    FIXTURE = FIXTURES_DIR / "message_delivering_hook.py"

    # Derived from the fixture's own structure, not copied from a run:
    # write_text (1) + open(...,"w") (1) + handle.write (1) = 3 INBOX-WRITE,
    # send_message (1) = 1 SEND-CALL.
    EXPECTED_FIXTURE_FINDINGS = 4

    def test_denominator_is_non_empty_and_stated(self):
        """Vacuity guard. A scan of zero files reports zero findings."""
        files = hook_python_files()
        assert len(files) >= 25, (
            f"hooks/ sweep resolved only {len(files)} python files -- the "
            f"zero-findings assertion below would be vacuous. Basis: "
            f"hooks/**/*.py excluding __pycache__."
        )

    def test_every_scanned_file_parses(self):
        """Parse-success must equal file count.

        A file that fails to parse is silently absent from the walk, so its
        contents would never be examined and the scan would report a clean
        zero over a tree it had not actually read.
        """
        files = hook_python_files()
        unparsed = []
        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                unparsed.append(f"{_rel(path)}: {exc}")
        assert not unparsed, (
            f"{len(unparsed)} of {len(files)} scanned files failed to parse; a "
            f"file the scanner cannot parse is a file it cannot clear:\n"
            + "\n".join(unparsed)
        )

    def test_scanner_is_live_on_the_real_tree(self):
        """The zero below is informative only if the scanner engages here.

        hooks/ really does construct inbox paths -- read-only, as witnesses
        that a teammate was dispatched. If that construction disappeared, a
        zero-findings result would degrade from "the scanner examined real
        inbox handling and found no writes" to "the scanner found nothing to
        look at", without any test going red. This is the control that keeps
        the two distinguishable, and it is drawn from the shipped tree rather
        than from the fixture, so it cannot pass by the fixture's construction.
        """
        live = [
            _rel(path)
            for path in hook_python_files()
            if scan_source(path.read_text(encoding="utf-8"))[1]
        ]
        assert live, (
            "no file under hooks/ constructs an inbox-derived path any more. "
            "The scanner's taint machinery is therefore never exercised "
            "against shipped code, and 'zero delivery constructs' no longer "
            "distinguishes a clean tree from an inert scanner. Re-establish a "
            "liveness control before trusting this class."
        )

    def test_no_hook_delivers_a_message(self):
        """The pin itself."""
        files = hook_python_files()
        findings = []
        for path in files:
            for rule, lineno, callee in scan_source(path.read_text(encoding="utf-8"))[0]:
                findings.append(f"{_rel(path)}:{lineno}: {rule} via {callee!r}")
        assert not findings, (
            f"{len(findings)} message-delivery construct(s) found in hooks/ "
            f"(basis: hooks/**/*.py excluding __pycache__, {len(files)} "
            f"files). The auditor guidance states that no PACT hook sends a "
            f"message, and an auditor relies on that when deciding it cannot "
            f"wake itself. If a hook now delivers messages, the guidance is "
            f"false and must change with it:\n" + "\n".join(findings)
        )

    def test_positive_control_fixture_is_flagged(self):
        """The scanner detects delivery it is pointed at -- on every run.

        Asserted quantitatively, by rule and by count derived from the
        fixture's structure. "Non-empty" would pass if only one of the two
        rules worked, which is precisely the failure this control exists to
        exclude: an authoring-time check of the scanner caught INBOX-WRITE
        failing to fire while SEND-CALL fired, and a non-emptiness assertion
        would have reported that broken scanner as healthy.
        """
        assert self.FIXTURE.is_file(), f"positive-control fixture missing: {self.FIXTURE}"
        findings, _ = scan_source(self.FIXTURE.read_text(encoding="utf-8"))
        rules = sorted({rule for rule, _, _ in findings})
        assert rules == ["INBOX-WRITE", "SEND-CALL"], (
            f"positive-control fixture fired rules {rules}, expected both "
            f"['INBOX-WRITE', 'SEND-CALL']. A rule that never fires cannot "
            f"clear the shipped tree of anything."
        )
        assert len(findings) == self.EXPECTED_FIXTURE_FINDINGS, (
            f"positive-control fixture produced {len(findings)} findings, "
            f"expected {self.EXPECTED_FIXTURE_FINDINGS}: "
            f"{findings}"
        )

    def test_negative_control_reads_and_unrelated_writes_are_not_flagged(self):
        """The scanner distinguishes mention from delivery.

        Two ways to be uselessly loud: flag an inbox path that is only READ
        (hooks/ does this legitimately, so the pin would fire on correct
        shipped code), or flag any write at all. Both negative legs live in
        the same fixture as the positive ones, so neither side can pass by
        the feature being absent.
        """
        source = self.FIXTURE.read_text(encoding="utf-8")
        findings, _ = scan_source(source)
        lines = source.splitlines()
        flagged = {lineno for _, lineno, _ in findings}

        for marker, why in (
            ("inbox.read_text(", "an inbox path that is only read"),
            ("inbox.is_file()", "an inbox existence probe"),
            ("log.write_text(", "a write to a path that is not an inbox"),
        ):
            lineno = next(i for i, ln in enumerate(lines, start=1) if marker in ln)
            assert lineno not in flagged, (
                f"scanner flagged {why} at fixture line {lineno} ({marker!r}). "
                f"Over-flagging makes this pin fire on correct code, and a pin "
                f"that fires on correct code gets relaxed rather than heeded."
            )
