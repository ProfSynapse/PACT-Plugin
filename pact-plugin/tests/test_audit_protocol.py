"""
Tests for the pact-audit.md protocol and pact-auditor agent definition.

Tests cover:
1. Audit signal format validation (GREEN/YELLOW/RED with required fields)
2. Audit request format (dispatch conditions, completion lifecycle)
3. Auditor dispatch threshold consistency (protocol vs orchestrate.md)
4. Auditor agent definition structure
5. Completion lifecycle: signal-type with audit_summary
"""
import sys
from pathlib import Path, PurePosixPath

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

PROTOCOLS_DIR = Path(__file__).parent.parent / "protocols"
COMMANDS_DIR = Path(__file__).parent.parent / "commands"
AGENTS_DIR = Path(__file__).parent.parent / "agents"
SKILLS_DIR = Path(__file__).parent.parent / "skills"

AUDIT_PROTOCOL = PROTOCOLS_DIR / "pact-audit.md"
ORCHESTRATE_CMD = COMMANDS_DIR / "orchestrate.md"
AUDITOR_AGENT = AGENTS_DIR / "pact-auditor.md"


# =============================================================================
# The extract population declaration
# =============================================================================
#
# THE RULE, IN ONE SENTENCE: a file in pact-plugin/protocols is an extract
# unless it is the SSOT itself or it is named below. MEMBERSHIP READS NO BYTES
# OF A CANDIDATE, and that content-blindness is the whole point of the rule.
#
# WHY NO CONTENT PREDICATE MAY DECIDE MEMBERSHIP. A rule that inferred
# membership from a file's first line REMOVED that file at the instant its
# first line drifted, so the file left the population and the comparison below
# stopped covering it. THE GATE THEN WENT SILENT IN THE ONE STATE IT EXISTS TO
# REPORT. MEASURED on pact-agent-stall.md: a heading drift moved it from
# in-population to out-of-population; a drift in the body did not move it. Do
# not soften this into "read the first line as a hint". A hint that can REMOVE
# a candidate re-opens that hole by a second route.
#
# THE COST THIS BUYS, RECORDED SO IT IS NOT REDISCOVERED AS A DEFECT. A new
# STANDALONE document added to that directory joins the population by default
# and reddens the set arm until it is declared here. That red lands on correct
# work. It is accepted because it fires at the moment the file is added, by
# the person who holds the context, and because the failure message names the
# one-line repair. The alternative, an INCLUSION manifest, answers the same
# mistake with a permanent silent hole in the gate's own subject: a file added
# with no bookkeeping at all is simply absent from the manifest and nothing
# ever reports it.
#
# THIS SET MUST NOT BE DERIVED FROM THE SCRIPT. Not from its verify list, not
# generated from it by a build step or a hook, and not parsed from its
# run-time output. The two sides of the comparison are the GIT INDEX and the
# SCRIPT RUN, and a declaration taken from the script collapses them into one
# source that cannot disagree with itself.
EXCLUDED_STANDALONES = frozenset(
    {
        # The algedonic signal protocol: its own document, not a slice of
        # pact-protocols.md.
        "algedonic.md",
        # The team communication charter: its own document, not a slice of
        # pact-protocols.md.
        "pact-communication-charter.md",
    }
)


class ExtractPopulationError(RuntimeError):
    """The candidate oracle could not name a population, so it refuses.

    A DEDICATED TYPE, so an arm that requires this refusal cannot pass on an
    unrelated exception raised somewhere else in the same call.
    """


# =============================================================================
# Audit protocol structure
# =============================================================================


class TestAuditProtocolExists:
    """Verify pact-audit.md exists and has required content."""

    @pytest.fixture
    def audit_content(self):
        return AUDIT_PROTOCOL.read_text(encoding="utf-8")

    def test_protocol_file_exists(self):
        assert AUDIT_PROTOCOL.exists()

    def test_has_concurrent_audit_heading(self, audit_content):
        # Wiring check: protocol must define the concurrent audit section
        assert "Concurrent Audit Protocol" in audit_content

    def test_has_dispatch_conditions(self, audit_content):
        # Wiring check: protocol must specify when to deploy auditor
        assert "Dispatch Conditions" in audit_content

    def test_has_observation_model(self, audit_content):
        # Wiring check: protocol must define observation approach
        assert "Hybrid Observation Model" in audit_content or "Observation" in audit_content

    def test_has_signal_format(self, audit_content):
        # Wiring check: protocol must define how auditor reports findings
        assert "Signal Format" in audit_content

    def test_has_signal_levels(self, audit_content):
        # Wiring check: protocol must define signal severity tiers
        assert "Signal Levels" in audit_content

    def test_has_completion_lifecycle(self, audit_content):
        # Wiring check: protocol must define signal-type completion
        assert "Completion Lifecycle" in audit_content or "completion_type" in audit_content


# =============================================================================
# Signal format validation
# =============================================================================


class TestAuditSignalFormat:
    """Validate audit signal format matches spec."""

    @pytest.fixture
    def audit_content(self):
        return AUDIT_PROTOCOL.read_text(encoding="utf-8")

    def test_signal_levels_present(self, audit_content):
        # Wiring check: protocol must define all three signal levels
        assert "GREEN" in audit_content
        assert "YELLOW" in audit_content
        assert "RED" in audit_content

    def test_signal_format_has_reference_field(self, audit_content):
        # Wiring check: signal must include file/component reference
        assert "Reference" in audit_content

    def test_signal_format_has_scope_field(self, audit_content):
        # Wiring check: signal must specify observation scope
        assert "Scope" in audit_content

    def test_signal_format_has_finding_field(self, audit_content):
        # Wiring check: signal must describe the finding
        assert "Finding" in audit_content

    def test_signal_format_has_evidence_field(self, audit_content):
        # Wiring check: signal must cite evidence
        assert "Evidence" in audit_content

    def test_signal_format_has_action_field(self, audit_content):
        # Wiring check: signal must recommend action
        assert "Action" in audit_content

    def test_green_means_on_track(self, audit_content):
        """GREEN signal means implementation is on track."""
        # The protocol should define GREEN as meaning on-track
        lower = audit_content.lower()
        assert "green" in lower and "on track" in lower

    def test_red_means_intervene(self, audit_content):
        """RED signal means orchestrator should intervene."""
        lower = audit_content.lower()
        assert "red" in lower and "intervene" in lower


# =============================================================================
# Dispatch threshold consistency
# =============================================================================


class TestDispatchThresholdConsistency:
    """Verify auditor dispatch conditions match between protocol and orchestrate.md."""

    @pytest.fixture
    def audit_content(self):
        return AUDIT_PROTOCOL.read_text(encoding="utf-8")

    @pytest.fixture
    def orchestrate_content(self):
        return ORCHESTRATE_CMD.read_text(encoding="utf-8")

    def test_protocol_has_variety_threshold(self, audit_content):
        """Protocol specifies variety >= 7 as dispatch condition."""
        # Wiring check: variety threshold must be defined
        assert ">= 7" in audit_content or "7" in audit_content

    def test_protocol_has_parallel_coders_condition(self, audit_content):
        """Protocol specifies parallel coders as dispatch condition."""
        # Wiring check: parallel-coders condition must be defined
        lower = audit_content.lower()
        assert "parallel" in lower and "coder" in lower

    def test_protocol_has_security_condition(self, audit_content):
        """Protocol specifies security-sensitive code as dispatch condition."""
        # Wiring check: security condition must be defined
        lower = audit_content.lower()
        assert "security" in lower

    def test_orchestrate_references_auditor(self, orchestrate_content):
        """orchestrate.md includes auditor dispatch instructions."""
        # Wiring check: orchestrate must reference auditor agent
        assert "pact-auditor" in orchestrate_content

    def test_orchestrate_has_variety_threshold(self, orchestrate_content):
        """orchestrate.md specifies variety >= 7 for auditor dispatch."""
        # Wiring check: orchestrate threshold must match protocol
        assert "variety >= 7" in orchestrate_content or "variety 7" in orchestrate_content.lower()

    def test_orchestrate_has_completion_type_signal(self, orchestrate_content):
        """orchestrate.md sets completion_type: signal for auditor tasks."""
        # Wiring check: orchestrate must use signal-type completion for auditor
        assert "completion_type" in orchestrate_content
        assert "signal" in orchestrate_content


# =============================================================================
# Auditor agent definition
# =============================================================================


class TestAuditorAgentDefinition:
    """Verify pact-auditor.md agent definition structure."""

    @pytest.fixture
    def agent_content(self):
        return AUDITOR_AGENT.read_text(encoding="utf-8")

    def test_agent_file_exists(self):
        assert AUDITOR_AGENT.exists()

    def test_has_frontmatter_name(self, agent_content):
        # Wiring check: agent must declare correct name in frontmatter
        assert "name: pact-auditor" in agent_content

    def test_has_observation_protocol(self, agent_content):
        """Agent has observation phases (A, B, C)."""
        # Wiring check: agent must define all three observation phases
        assert "Phase A" in agent_content
        assert "Phase B" in agent_content
        assert "Phase C" in agent_content

    def test_has_behavioral_rules(self, agent_content):
        # Wiring check: agent must include behavioral constraints
        lower = agent_content.lower()
        assert "behavioral rules" in lower or "behavioural rules" in lower

    def test_has_audit_criteria(self, agent_content):
        # Wiring check: agent must define what it evaluates
        assert "AUDIT CRITERIA" in agent_content or "Audit Criteria" in agent_content

    def test_has_signal_format(self, agent_content):
        # Wiring check: agent must define its output format
        assert "Signal Format" in agent_content or "AUDIT SIGNAL" in agent_content

    def test_has_completion_section(self, agent_content):
        # Wiring check: agent must define signal-type completion lifecycle
        assert "COMPLETION" in agent_content or "Completion" in agent_content
        assert "completion_type" in agent_content or "audit_summary" in agent_content

    def test_has_algedonic_escalation(self, agent_content):
        # Wiring check: agent must reference algedonic escalation path
        assert "algedonic" in agent_content.lower()

    def test_does_not_write_code_boundary(self, agent_content):
        """Agent explicitly states it does not write code."""
        # Wiring check: read-only observer boundary must be stated
        lower = agent_content.lower()
        assert "do not write" in lower or "do not modify" in lower


# =============================================================================
# Structural Verification Discipline (#502)
# =============================================================================


class TestStructuralVerificationDiscipline:
    """Verify STRUCTURAL VERIFICATION DISCIPLINE is present in agent body and protocol.

    Each assertion targets a specific load-bearing property of the discipline
    (canonical term, MUST voice, named failure modes, prior-art citation, incident
    citation, Evidence-field upgrade, BEHAVIORAL RULES integration). A failing
    assertion names the specific erosion shape rather than a generic "rule missing".
    Baseline-fail on b0e3f7e is required — these tests do not pass on pre-#502 HEAD.
    """

    @pytest.fixture
    def agent_content(self):
        return AUDITOR_AGENT.read_text(encoding="utf-8")

    @pytest.fixture
    def audit_content(self):
        return AUDIT_PROTOCOL.read_text(encoding="utf-8")

    def test_agent_has_discipline_section(self, agent_content):
        """Agent body declares the discipline section by canonical name."""
        assert "STRUCTURAL VERIFICATION DISCIPLINE" in agent_content

    def test_protocol_has_discipline_section(self, audit_content):
        """Protocol anchor mirrors the discipline section (H3-cased)."""
        assert "Structural Verification Discipline" in audit_content

    def test_agent_uses_must_voice(self, agent_content):
        """Discipline section uses MUST voice, not 'should' or 'recommended'."""
        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "MUST" in section, "Discipline section must use MUST voice"

    def test_agent_references_git_diff_verification(self, agent_content):
        """Discipline requires git diff as the verification substrate."""
        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "git diff" in section

    def test_agent_names_failure_modes(self, agent_content):
        """Discipline names the canonical failure modes for LLM-reader at execution time."""
        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "PHANTOM-SYMMETRIC-CLAIM" in section
        assert "VAGUE-DIFF-CITATION" in section
        assert "STRUCTURAL-DRESSING-ON-JUDGMENT-CALL" in section

    @pytest.mark.parametrize(
        "filename,path",
        [
            ("pact-auditor.md", AUDITOR_AGENT),
            ("pact-audit.md", AUDIT_PROTOCOL),
            ("pact-protocols.md", PROTOCOLS_DIR / "pact-protocols.md"),
        ],
    )
    def test_phantom_symmetric_claim_bullet_enumerates_all_layers(
        self, filename, path
    ):
        """PHANTOM-SYMMETRIC-CLAIM bullet enumerates all four canonical layers
        in every rule-carrying surface.

        Each of the three rule carriers (agent body, protocol anchor, SSOT) has
        a section that asserts "Four internally-consistent layers of prose can
        all be wrong together" in its preamble. The PHANTOM-SYMMETRIC-CLAIM
        bullet in that section must enumerate four named layers, not three.
        Arithmetic inconsistency here (3 enumerated, 4 claimed by the
        preamble) is the same failure shape the rule is installed to prevent:
        prose that self-contradicts on a countable fact. Without this guard,
        a future edit that drops a layer from the bullet on any one carrier
        would stay green on `test_agent_names_failure_modes` (which only
        checks the failure-mode NAMES, not their body text) and survive to
        a blind review — the exact under-propagation pattern #502 B1 caught
        across the protocol mirrors after T1 only fixed the agent body.
        """
        content = path.read_text(encoding="utf-8")
        # Section header form differs across files:
        #   pact-auditor.md uses "### Failure modes to avoid" (H3)
        #   pact-audit.md / pact-protocols.md use "**Failure modes to avoid**:"
        # The bare phrase is present in all three; use it as a uniform marker.
        # Guarded lookup: if a heading is renamed, fail with a pointed
        # diagnostic instead of an uncaught ValueError.
        for marker in (
            "Failure modes to avoid",
            "PHANTOM-SYMMETRIC-CLAIM",
            "VAGUE-DIFF-CITATION",
        ):
            if marker not in content:
                pytest.fail(
                    f"{filename}: section marker '{marker}' missing — "
                    f"heading may have been renamed or section deleted"
                )
        failure_modes_start = content.index("Failure modes to avoid")
        phantom_start = content.index("PHANTOM-SYMMETRIC-CLAIM", failure_modes_start)
        # The bullet ends at the next list item (VAGUE-DIFF-CITATION).
        bullet_end = content.index("VAGUE-DIFF-CITATION", phantom_start)
        bullet = content[phantom_start:bullet_end]
        for layer in (
            "HANDOFF prose",
            "commit message",
            "coder self-attestation",
            "audit signal",
        ):
            assert layer in bullet, (
                f"{filename}: PHANTOM-SYMMETRIC-CLAIM bullet missing canonical "
                f"layer '{layer}' — bullet's section preamble claims 'four "
                f"layers' but enumeration must list all four (see #502 T1/B1)"
            )

    def test_discipline_section_has_structural_ac_table(self, agent_content):
        """The 'What counts as a structural AC' disambiguation table is present.

        A future edit that deletes or drastically trims this table (e.g.,
        below 4 yes-rows / 4 no-rows) leaves the MUST rule without its
        disambiguation substrate. The auditor at execution time needs
        concrete examples for each side to classify a novel AC.
        """
        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "### What counts as a structural acceptance criterion" in section, (
            "Disambiguation table subsection missing"
        )
        # The table uses "| yes |" / "| **no** |" cells. Count presence as a
        # structural-erosion guard: at least 4 of each required.
        assert section.count("| yes |") >= 4, (
            "Disambiguation table has fewer than 4 structural-yes example rows"
        )
        assert section.count("| **no** |") >= 4, (
            "Disambiguation table has fewer than 4 non-structural example rows"
        )

    def test_discipline_section_has_five_step_verification_procedure(
        self, agent_content
    ):
        """The Verification procedure is a numbered 5-step list, not prose.

        Dropping the numbered-list structure or reducing the step count
        erodes the procedure's operational teeth. Step 4 in particular
        ('If count/location does NOT match → RED, not GREEN') is the
        enforcement hinge the rule is installed around.
        """
        import re

        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "### Verification procedure" in section, (
            "Verification procedure subsection missing"
        )
        proc_start = section.index("### Verification procedure")
        proc_end = section.index("### Failure modes to avoid", proc_start)
        procedure = section[proc_start:proc_end]
        step_count = len(re.findall(r"^\d+\. ", procedure, re.MULTILINE))
        assert step_count == 5, (
            f"Verification procedure must be exactly 5 numbered steps; "
            f"found {step_count}"
        )

    def test_step_4_requires_red_on_count_mismatch(self, agent_content):
        """Step 4 prose requires RED on count mismatch, not YELLOW.

        The RED-vs-YELLOW disambiguation was added by M5 (cycle 1) to close
        a severity-assignment escape hatch — an auditor under coordination
        pressure could silently downgrade a clear count violation to YELLOW.
        Step 4 must name both 'RED' and 'count mismatch' explicitly so the
        disambiguation is load-bearing at the decision point.
        """
        import re

        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        proc_start = section.index("### Verification procedure")
        proc_end = section.index("### Failure modes to avoid", proc_start)
        procedure = section[proc_start:proc_end]
        # Extract step 4: from "^4\. " to "^5\. " or end of procedure.
        step4_match = re.search(
            r"^4\. .*?(?=^5\. |\Z)", procedure, re.MULTILINE | re.DOTALL
        )
        assert step4_match is not None, "Step 4 not found in Verification procedure"
        step4 = step4_match.group(0)
        assert "RED" in step4 and "count mismatch" in step4, (
            "Step 4 must name both 'RED' and 'count mismatch' to carry the "
            "RED-vs-YELLOW disambiguation (see #502 M5)"
        )

    def test_agent_cites_prior_art(self, agent_content):
        """Discipline cites file inspection beats HANDOFF inference rationale."""
        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "file inspection beats HANDOFF inference" in section

    def test_agent_cites_phantom_symmetric_claim_discipline(self, agent_content):
        """Discipline cites the triggering incident so the rule's context survives compaction.

        The behavioral anchor `PHANTOM-SYMMETRIC-CLAIM` names the failure-mode
        shape (four-layer agreement on a fabricated structural claim) that
        motivated the rule. The name survives planning-artifact scrubs and
        is the durable discipline content; provenance SHAs / PR refs are
        incidental and forbidden in `agents/*.md` per the LLM-load distinction.
        """
        start = agent_content.index("STRUCTURAL VERIFICATION DISCIPLINE")
        end = agent_content.index("## SIGNAL FORMAT", start)
        section = agent_content[start:end]
        assert "PHANTOM-SYMMETRIC-CLAIM" in section

    def test_agent_signal_format_evidence_field_upgraded(self, agent_content):
        """Agent's Evidence field requires structural ACs be cited via git diff."""
        start = agent_content.index("## SIGNAL FORMAT")
        end = agent_content.index("## SIGNAL LEVELS", start)
        section = agent_content[start:end]
        assert "structural" in section.lower()
        assert "git diff" in section

    def test_protocol_signal_format_evidence_field_upgraded(self, audit_content):
        """Protocol's Evidence field requires structural ACs be cited via git diff."""
        start = audit_content.index("### Signal Format")
        end = audit_content.index("### Signal Levels", start)
        section = audit_content[start:end]
        assert "structural" in section.lower()
        assert "git diff" in section

    def test_agent_has_behavioral_rule_for_structural_verification(self, agent_content):
        """BEHAVIORAL RULES table references the discipline."""
        start = agent_content.index("## BEHAVIORAL RULES")
        end = agent_content.index("## AUDIT CRITERIA", start)
        section = agent_content[start:end]
        assert "STRUCTURAL VERIFICATION DISCIPLINE" in section

    def test_verify_protocol_extracts_concurrent_audit_still_matches(self):
        """verify-protocol-extracts.sh exits 0 with every extract pair MATCH.

        Strict-pass semantics: asserts exit-code 0 from the verify script. Every
        extract pair — including Concurrent Audit (edited by #502) and State
        Recovery (re-extracted by #505) — must be in sync with its SSOT region.
        This test fails deterministically if any future edit to pact-protocols.md
        or any extract file desyncs the pair.

        Inserting content into the SSOT carries no separate bookkeeping
        obligation. The script anchors each section by its H2 heading text plus
        the next H2 heading as the end sentinel, NOT by line numbers, precisely
        so that adding or removing lines cannot shift a region out from under
        it. What this gate checks is byte-identity between an extract and its
        SSOT region; an edit to one half that is not mirrored into the other is
        the only way to break it.
        """
        import subprocess

        repo_root = Path(__file__).parent.parent.parent
        script = repo_root / "scripts" / "verify-protocol-extracts.sh"
        if not script.exists():
            pytest.skip("verify-protocol-extracts.sh not present")

        result = subprocess.run(
            ["bash", str(script)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"verify-protocol-extracts.sh exited {result.returncode}; expected 0. "
            f"One or more extract pairs have desynced from their SSOT region.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    # -- The corpus of the extracts gate --------------------------------
    #
    # THE GATE ABOVE ASSERTS AN EXIT CODE AND READS NOTHING ELSE. The script
    # exits 0 when its FAILED count is 0, and an EMPTY corpus satisfies that.
    # MEASURED: with all nineteen `verify` calls removed the script prints
    # `Passed: 0, Failed: 0, VERIFICATION PASSED`, exits 0, and the gate above
    # stays GREEN. With ONE call removed it prints `Passed: 18, Failed: 0` and
    # the gate stays GREEN, so the extract that call covered goes unverified.
    #
    # A COUNT DERIVED FROM THE SCRIPT CANNOT CLOSE THAT. Remove one call and
    # the counted invocations and the reported PASS both read 18, so the two
    # agree and the arm passes. Two sides derived from ONE source cannot
    # disagree. THE INDEPENDENT ORACLE IS THE GIT INDEX, so the arms below
    # derive the population from the files git TRACKS in the protocols
    # directory and compare that against what the script names.
    #
    # AND THE SCRIPT IS ASKED WHAT IT DID, NOT WHAT ITS SOURCE TEXT LOOKS LIKE.
    # A rule that read the script SOURCE for `verify "<file>"` was MEASURED to
    # over-block twice against a CORRECT script, one that exits 0 with
    # `Passed: 19, Failed: 0`:
    #   * an ordinary usage message, a heredoc carrying one line at column zero
    #     of that shape, added a PHANTOM name and reddened the set comparison;
    #   * single quotes on the first argument, which bash treats identically to
    #     double quotes, emptied the parse and fired the NON-VACUITY assertion,
    #     which reads as a broken harness rather than as a defect in the rule.
    # NEITHER A TEXT LINE AT COLUMN ZERO NOR A QUOTE STYLE CAN CHANGE WHAT A
    # SCRIPT EMITS WHEN IT RUNS, so the verified set is now parsed from the
    # `VERIFY-CALL:` lines of a real run.
    #
    # THE INDEPENDENCE THIS RESTS ON, STATED SO A LATER EDIT CANNOT SPEND IT
    # WITHOUT NOTICING. THE TWO SIDES ARE THE GIT INDEX (with a filesystem
    # walk as the fall back) AND THE SCRIPT RUN. The script emits the literal
    # first argument of each call, so its side stays derived from the call
    # ARGUMENTS, and the population side is derived from what git TRACKS. A
    # git index cannot be changed by an edit to a shell script, and a shell
    # script cannot be changed by an edit to the index, so the two sides can
    # disagree and the comparison is therefore evidence.
    #
    # THE INDEPENDENCE MUST BE SPENDABLE ONLY ON PURPOSE, so here are the
    # three edits that spend it, each of which looks like a tidy-up:
    #   1. THE SCRIPT NAMES ITS FILES FROM A GLOB of the protocols directory.
    #      Both sides then derive from the directory and this comparison
    #      becomes a tautology that cannot disagree. The same obligation is
    #      recorded at the emission site in the script.
    #   2. THE DECLARATION IS GENERATED from the script by a build step or a
    #      hook, or the script is made to read the declaration.
    #   3. THE POPULATION IS PARSED FROM THE SCRIPT RUN-TIME OUTPUT. That
    #      route is newly available now that the script emits a file name for
    #      each comparison, so it is newly attractive. Do not take it.
    # THE INVARIANT BEHIND ALL THREE: NO SINGLE EDIT MAY REMOVE A FILE FROM
    # BOTH SIDES AT ONE TIME.

    # THE PROTOCOLS DIRECTORY, AS ONE STRING, because it is both a git
    # pathspec and a path segment and the two must not drift apart.
    PROTOCOLS_REL = "pact-plugin/protocols"
    SSOT_NAME = "pact-protocols.md"

    @classmethod
    def _protocol_candidates(cls, repo_root):
        """Name every file in the protocols directory. Return (names, source).

        THE KEY SHAPE IS A JOINT CONTRACT WITH THE SCRIPT, so it is fixed here
        rather than chosen. Each name is THE PATH RELATIVE TO THE PROTOCOLS
        DIRECTORY, which is the same string the script prints, because the
        script is given that string as the first argument of a `verify` call
        and resolves it as `$PROTOCOLS_DIR/$file`. A key of any other shape
        (an absolute path, the repo-root-relative path, or a bare basename for
        a nested file) makes the two sets incomparable, and the comparison
        below then reddens against a CORRECT tree. MEASURED at 522a5129: `git
        ls-files -z pact-plugin/protocols` run from the repo root prints 22
        names of the form `pact-plugin/protocols/<name>`, unquoted, and after
        the prefix is removed the keys differ from the 19 emitted names by
        precisely the SSOT and the two declared standalone documents.

        THE GIT INDEX IS THE ORACLE, AND A FILESYSTEM WALK IS THE FALL BACK.
        MEASURED: with ONE UNTRACKED SCRATCH FILE in that directory, git
        reports 22 and a walk reports 23, and the walk therefore reddens a
        contributor's local run while CI stays green. That is a NEW OVER-BLOCK
        and this rule does not open one.

        A GIT-LESS TREE MUST NOT YIELD A SILENT EMPTY POPULATION. MEASURED:
        `git ls-files` in a tree with no repository returns 128 WITH EMPTY
        STDOUT and writes to stderr, so a reader that parses stdout alone gets
        a clean EMPTY population, and an empty population makes every set
        comparison pass. That is the tautology these arms exist to escape, and
        it renders as GREEN. So stdout is DISCARDED on a non-zero return code,
        the walk runs instead, and a zero-candidate route RAISES.

        THE FALL BACK IS A FALL BACK AND NOT A SKIP, and the cause is
        measured: in a `git archive` export the verify script itself continues
        to run and reports `Passed: 19, Failed: 0`, so a skip there would
        silence a live comparison.

        `-z` IS LOAD-BEARING. Without it, `core.quotePath` wraps a name
        carrying a non-ASCII or special character in double quotes with
        C-style escapes, and the key would then be a string nobody wrote.

        WHAT THIS ORACLE CANNOT SEE, named rather than left for a later
        reader to find:
          1. AN UNTRACKED FILE, IN BOTH DIRECTIONS. A scratch file does not
             redden, which is the point, and a new extract that is not yet
             staged does not redden either, which is the price. Staging
             bounds the window, so a committed tree and CI always see it.
          2. THE INDEX AGAINST DISK. A tracked file removed from the working
             tree stays in the population, and the count arm reddens because
             the script reports one comparison fewer. The report is correct
             and its cause is the index.
          3. A FILE OUTSIDE THIS DIRECTORY. An extract copied elsewhere is
             not a candidate and nothing here reports it.
          4. CASE-FOLDING FILESYSTEMS. Two names differing only in case are
             one file on some platforms and two on others. NOT MEASURED.
        """
        import subprocess

        protocols = repo_root / "pact-plugin" / "protocols"
        returncode = None
        names = None
        provenance = "git-index"
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z", cls.PROTOCOLS_REL],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
            )
            returncode = result.returncode
            if returncode == 0:
                # `relative_to` RAISES on a path outside the pathspec rather
                # than skipping it, because a silent skip would drop a file
                # from the population, which is the failure direction this
                # whole rule is built against.
                names = {
                    str(PurePosixPath(entry).relative_to(cls.PROTOCOLS_REL))
                    for entry in result.stdout.split("\0")
                    if entry
                }
        except OSError:
            # git absent from PATH. Fall back, do not fail open.
            returncode = None

        if names is None:
            provenance = "filesystem"
            # RECURSIVE and EXTENSION-AGNOSTIC on purpose. A `*.md` glob at one
            # level was MEASURED to drop a file in a SUBDIRECTORY and a file
            # with another extension, and each dropped file leaves the
            # comparison with nothing to report it.
            names = {
                path.relative_to(protocols).as_posix()
                for path in protocols.rglob("*")
                if path.is_file()
            }

        if not names:
            raise ExtractPopulationError(
                "the extract population oracle named NO candidate in "
                f"{cls.PROTOCOLS_REL} (source: {provenance}, git return code: "
                f"{returncode}). THIS REFUSES RATHER THAN REPORTS A GREEN: an "
                "empty population makes every set comparison below pass, so a "
                "silent empty here would report success while nothing at all "
                "was checked."
            )
        return names, provenance

    @classmethod
    def _population_from_candidates(cls, candidates, protocols_dir):
        """Subtract the SSOT and the declared standalone documents. Nothing else.

        `protocols_dir` IS PASSED AND DELIBERATELY UNUSED, and that is the
        point of the signature. Every predicate this rule may apply is a
        predicate on a NAME. THE DIRECTORY IS IN SCOPE SO THAT A LATER EDIT
        WHICH REACHES FOR A CANDIDATE'S BYTES IS VISIBLE AS AN EDIT AT THIS
        SITE rather than hidden behind a helper, and so the arms that drive
        this function drive the same seam a regression would land on.
        READING A CANDIDATE HERE RE-OPENS THE HOLE: a file removed from the
        population by its own content leaves the comparison at the instant it
        drifts.
        """
        del protocols_dir
        return {
            name
            for name in candidates
            if name != cls.SSOT_NAME and name not in EXCLUDED_STANDALONES
        }

    def _extract_population(self):
        repo_root = Path(__file__).parent.parent.parent
        protocols = repo_root / "pact-plugin" / "protocols"
        # THE SSOT SITS AMONG ITS OWN EXTRACTS, so an enumeration of this
        # directory selects it too. Subtract it by name, or the SSOT is
        # compared against itself.
        ssot_text = (protocols / self.SSOT_NAME).read_text(encoding="utf-8")
        candidates, _provenance = self._protocol_candidates(repo_root)
        return self._population_from_candidates(candidates, protocols), ssot_text

    # -- Driving the population rule against a built tree -------------------
    #
    # THE ARMS BELOW BUILD THEIR OWN protocols DIRECTORY, because the shapes
    # that defeated the previous rule (a byte-order mark, a subdirectory, a
    # file with another extension) are ABSENT from the repository today. A
    # rule proven only against the shapes that happen to be present is proven
    # against the easy case. Each arm names the mutant that fails it.

    @staticmethod
    def _build_protocols_tree(root, files, git=True):
        """Build a repo-shaped tree and return its root.

        `files` maps a path RELATIVE TO THE PROTOCOLS DIRECTORY to its bytes.
        With `git` true the tree is a repository and each named file is added
        to the INDEX, so a file written afterwards is untracked.
        """
        import subprocess

        protocols = root / "pact-plugin" / "protocols"
        protocols.mkdir(parents=True, exist_ok=True)
        for rel, data in files.items():
            target = protocols / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if git:
            subprocess.run(
                ["git", "init", "-q"], cwd=str(root), capture_output=True,
                text=True, check=True,
            )
            subprocess.run(
                ["git", "add", "-A"], cwd=str(root), capture_output=True,
                text=True, check=True,
            )
        return root

    def test_control_the_population_rule_separates_declared_from_undeclared(
        self, tmp_path
    ):
        """CONTROL, asserted BEFORE the population arms below run.

        THIS CONTROL REPLACES ONE THAT WATCHED A RETIRED PREDICATE. The old
        control drove a first-line classifier across a standalone document and
        an extract. That classifier is gone, because membership must read no
        bytes. The separation that decides membership NOW is `declared in
        EXCLUDED_STANDALONES` against `not declared`, so that is what this
        drives, and it drives it across two files with IDENTICAL CONTENT so
        the only thing that can separate them is the declaration.

        A CONTROL THAT CANNOT RETURN THE OPPOSITE VERDICT IS NOT EVIDENCE, so
        the arm requires the separation in both directions in one run.
        """
        same_bytes = b"# Identical Content\n\nbody\n"
        declared = sorted(EXCLUDED_STANDALONES)[0]
        root = self._build_protocols_tree(
            tmp_path,
            {
                "pact-protocols.md": b"# Title\n\n## A Section\n\nbody\n",
                declared: same_bytes,
                "an-undeclared-file.md": same_bytes,
            },
        )
        candidates, provenance = self._protocol_candidates(root)
        population = self._population_from_candidates(
            candidates, root / "pact-plugin" / "protocols"
        )

        assert provenance == "git-index"
        # THE TWO FILES CARRY THE SAME BYTES, so a content predicate cannot
        # tell them apart and only the declaration can.
        assert "an-undeclared-file.md" in population
        assert declared not in population
        # AND THE SSOT IS SUBTRACTED BY NAME, because it sits among its own
        # extracts and would otherwise be compared against itself.
        assert self.SSOT_NAME not in population

    def test_the_population_keeps_a_file_that_has_drifted(self, tmp_path):
        """THE TRAP ARM. A DRIFTED FILE MUST STAY IN THE POPULATION.

        THIS IS THE ARM THE REJECTED DIRECTION WOULD HAVE DESTROYED, and it is
        the whole cause of the content-blind rule. A rule that required a
        candidate to BE a slice of the SSOT, or to open with a heading the
        SSOT carries, REMOVED the file at the instant it drifted. The file
        left the population, the comparison stopped covering it, and the gate
        went silent in the one state it exists to report.

        THE TWO FILES HERE DIFFER ONLY IN THAT ONE HAS DRIFTED. Both must be
        in the population. MUTANT: reintroduce any content predicate into
        membership, for example `first line is an H2 the SSOT carries`, and
        the drifted file leaves and this arm goes RED.
        """
        ssot = b"# Title\n\n## A Section\n\nbody\n\n## Another\n\nmore\n"
        root = self._build_protocols_tree(
            tmp_path,
            {
                "pact-protocols.md": ssot,
                # A faithful slice of the SSOT.
                "pristine.md": b"## A Section\n\nbody\n",
                # THE SAME EXTRACT AFTER A DRIFT IN ITS FIRST LINE, which is
                # the precondition MEASURED to move a file out of the old
                # population. A drift in the body did not move it.
                "drifted.md": b"## A Section That Drifted\n\nbody\n",
            },
        )
        candidates, _provenance = self._protocol_candidates(root)
        population = self._population_from_candidates(
            candidates, root / "pact-plugin" / "protocols"
        )

        assert "pristine.md" in population
        assert "drifted.md" in population, (
            "a DRIFTED extract left the population, so the comparison no "
            "longer covers it and the gate is silent in the one state it "
            "exists to report. Membership must read no bytes of a candidate."
        )

    def test_the_population_holds_the_shapes_a_glob_drops(self, tmp_path):
        """A byte-order mark, a subdirectory and another extension all count.

        MEASURED as three separate HOLES in the rule this replaces: each of
        the three shapes dropped out of the population, so the file could
        drift with nothing to report it. D4 and D5 are reachable as a RENAME
        or a REORGANISATION of the directory, and in that form the gate goes
        silent for every moved file at once.

        MUTANT for the subdirectory and the extension: replace the enumeration
        with `glob("*.md")` at one level. Predict RED on two names.
        MUTANT for the byte-order mark: reintroduce a first-line predicate.
        Predict RED on that name.

        THE KEY SHAPE IS ASSERTED HERE TOO, and it is asserted against a
        LITERAL and not against the script, so this arm can go red while the
        set comparison is green. A nested file must read as `sub/name.md`: a
        bare basename would not resolve as `$PROTOCOLS_DIR/$file` on the
        script side, so the two sides would diverge on the very file the
        subdirectory repair exists to catch.
        """
        root = self._build_protocols_tree(
            tmp_path,
            {
                "pact-protocols.md": b"# Title\n\n## A Section\n\nbody\n",
                "plain.md": b"## A Section\n\nbody\n",
                "with-bom.md": b"\xef\xbb\xbf## A Section\n\nbody\n",
                "sub/nested.md": b"## A Section\n\nbody\n",
                "other-extension.txt": b"## A Section\n\nbody\n",
            },
        )
        candidates, _provenance = self._protocol_candidates(root)

        assert "with-bom.md" in candidates
        assert "sub/nested.md" in candidates
        assert "other-extension.txt" in candidates
        # THE KEY SHAPE, against literals. No key carries the directory
        # prefix, no key is absolute, and a nested file keeps its path.
        for name in candidates:
            assert not name.startswith(self.PROTOCOLS_REL)
            assert not name.startswith("/")
            assert not name.startswith("./")

    def test_an_untracked_scratch_file_does_not_join_the_population(
        self, tmp_path
    ):
        """THE OVER-BLOCK CONTROL. A local scratch file must not redden.

        MEASURED: with one untracked file in the protocols directory, `git
        ls-files` reports 22 and a filesystem walk reports 23, so the walk
        reddens a contributor's local run while CI stays green. OVER-BLOCK IS
        CARDINAL in this repository, and this repair must not open a new one.

        THIS ARM HAS A SECOND FACE, AND IT IS THE PRICE OF THE FIRST. The
        index is blind to an untracked file in BOTH directions, so a NEW
        EXTRACT that has been written but not yet staged is also invisible,
        and the gate stays green until it is staged. THE TWO ARE ONE
        PROPERTY: no rule can ignore an untracked scratch file and at the
        same time catch an untracked extract. MEASURED end to end: the same
        new unverified extract gives 57 passed while untracked and reddens
        two arms once `git add` has run. THE WINDOW IS THEREFORE BOUNDED BY
        STAGING, so every committed tree and every CI run sees the file, and
        the contributor meets the red in the change that adds it.

        MUTANT: take the population from the walk when git is available.
        Predict RED.
        """
        root = self._build_protocols_tree(
            tmp_path,
            {
                "pact-protocols.md": b"# Title\n\n## A Section\n\nbody\n",
                "tracked.md": b"## A Section\n\nbody\n",
            },
        )
        # WRITTEN AFTER `git add`, so it is present on disk and absent from
        # the index. That is what a contributor's scratch file looks like.
        (root / "pact-plugin" / "protocols" / "SCRATCH-notes.md").write_bytes(
            b"## A Section\n\nscratch\n"
        )
        candidates, provenance = self._protocol_candidates(root)

        assert provenance == "git-index"
        assert "tracked.md" in candidates
        assert "SCRATCH-notes.md" not in candidates, (
            "an UNTRACKED scratch file joined the population, which reddens a "
            "contributor's local run while CI stays green. That is a new "
            "over-block, and the git index is the oracle to prevent it."
        )

    def test_a_tree_with_no_repository_falls_back_and_never_returns_empty(
        self, tmp_path
    ):
        """A git-less tree falls back to the walk, and an empty one RAISES.

        MEASURED: `git ls-files` in a tree with no repository returns 128 WITH
        EMPTY STDOUT. A reader that parses stdout alone therefore gets a clean
        EMPTY population, and an empty population makes every set comparison
        below pass. THAT IS THE TAUTOLOGY THESE ARMS EXIST TO ESCAPE, and it
        renders as GREEN, which is the one failure a suite does not report.

        THE POSITIVE ARM IS FIRST AND IT IS NOT DECORATION. A refusal arm on
        its own cannot tell a working fall back apart from a route that fails
        for any cause at all, so the fall back is required to RETURN NAMES
        before the empty case is required to refuse.

        FALL BACK RATHER THAN SKIP, and the cause is measured: in a `git
        archive` export the verify script itself continues to run and reports
        `Passed: 19, Failed: 0`, so a skip would silence a live comparison.

        MUTANT: parse `git ls-files` stdout with no return-code check. Predict
        a silent EMPTY population, which fails the positive arm below.
        """
        populated = self._build_protocols_tree(
            tmp_path / "populated",
            {
                "pact-protocols.md": b"# Title\n\n## A Section\n\nbody\n",
                "plain.md": b"## A Section\n\nbody\n",
                "sub/nested.md": b"## A Section\n\nbody\n",
            },
            git=False,
        )
        names, provenance = self._protocol_candidates(populated)
        assert provenance == "filesystem"
        assert names == {"pact-protocols.md", "plain.md", "sub/nested.md"}

        empty = self._build_protocols_tree(tmp_path / "empty", {}, git=False)
        with pytest.raises(ExtractPopulationError) as excinfo:
            self._protocol_candidates(empty)
        # THE MESSAGE IS PART OF THE CONTRACT: a refusal that does not say the
        # route it took sends the next reader to the wrong repair.
        assert "filesystem" in str(excinfo.value)

    def test_each_declared_exclusion_is_present_and_is_not_a_slice(self):
        """The declaration must name files that are here and are not extracts.

        TWO FAILURE DIRECTIONS, and each is silent without this arm.
        A name declared for a file that no longer exists protects nothing and
        reads as maintained. A name declared for a GENUINE extract silences
        the gate for that extract.

        THIS GUARD IS ONE-DIRECTIONAL BY CONSTRUCTION. It can only REPORT an
        incorrectly declared name. IT MUST NOT REMOVE A NAME FROM THE
        POPULATION, because a guard that removes one is a content predicate
        deciding membership by a second route, which is the hole the whole
        rule is built against.

        WHAT IT CANNOT SEE, named rather than left implicit: it compares
        against the SSOT as it is now, so it catches the pristine mistake and
        goes quiet once an incorrectly declared file has drifted.
        """
        repo_root = Path(__file__).parent.parent.parent
        protocols = repo_root / "pact-plugin" / "protocols"
        ssot_text = (protocols / self.SSOT_NAME).read_text(encoding="utf-8")
        candidates, _provenance = self._protocol_candidates(repo_root)

        assert EXCLUDED_STANDALONES, "the declaration is empty"
        for name in sorted(EXCLUDED_STANDALONES):
            assert name in candidates, (
                f"EXCLUDED_STANDALONES declares {name!r}, which is not in "
                "pact-plugin/protocols. A declaration for an absent file "
                "protects nothing and reads as maintained. Remove the entry."
            )
            text = (protocols / name).read_text(encoding="utf-8")
            assert text.strip() not in ssot_text, (
                f"EXCLUDED_STANDALONES declares {name!r}, but that file IS a "
                "literal slice of pact-protocols.md, so it is an extract and "
                "the declaration silences the gate for it. Remove the entry "
                "and give the file a verify call in "
                "scripts/verify-protocol-extracts.sh."
            )

    def test_the_gate_verifies_every_extract_file_that_exists(self):
        """The script must name each extract in the protocols directory.

        THE TWO SIDES COME FROM DIFFERENT SOURCES ON PURPOSE. The population
        is derived from the FILES. The verified set is what the SCRIPT DID: it
        announces one `VERIFY-CALL:` line for each comparison it performed, and
        that line carries the literal file name the call was given. A call
        removed from the script leaves a file in the population and out of the
        verified set, so this reddens where a count derived from the script
        alone would agree with itself.

        A NEW EXTRACT FILE ALSO REDDENS THIS, with no edit here, which is what
        keeps the arm from needing maintenance every time the surface grows.

        WHY A RUN AND NOT THE SOURCE TEXT. Reading the script source for
        `verify "<file>"` was measured to redden twice against a CORRECT
        script: a usage heredoc with one line at column zero added a phantom
        name, and a change of quote style, which bash treats identically,
        emptied the parse. The corpus comment above this class carries the
        detail. What a script EMITS is immune to both.

        THE AXIS THIS ARM CANNOT SEE, NAMED RATHER THAN LEFT IMPLICIT: it
        checks that each extract IS compared. It does not check that the
        heading pair each `verify` call passes is the correct pair, and it does
        not check the OUTCOME of the comparison. The byte-comparison inside the
        script is what checks the pair, and the exit-code arm above is what
        reports the outcome. So an extract that genuinely differs from its
        slice stays in this set and reddens the other two arms instead.
        """
        import re
        import subprocess

        repo_root = Path(__file__).parent.parent.parent
        script = repo_root / "scripts" / "verify-protocol-extracts.sh"
        if not script.exists():
            pytest.skip("verify-protocol-extracts.sh not present")

        population, _ssot = self._extract_population()
        result = subprocess.run(
            ["bash", str(script)], cwd=str(repo_root),
            capture_output=True, text=True,
        )
        verified = set(
            re.findall(r"^VERIFY-CALL: (.+)$", result.stdout, re.MULTILINE)
        )

        # THE SCRIPT REACHED ITS END, CHECKED BEFORE THE SET IS READ. An empty
        # verified set has TWO causes now, and they call for different repairs:
        # the script ran and compared nothing, or THE SCRIPT NEVER GOT THERE.
        # It exits 1 before the first comparison when its SSOT source file is
        # absent. Separating the two here stops an aborted run from reading as
        # an empty corpus.
        assert re.search(r"^Passed:\s*\d+$", result.stdout, re.MULTILINE), (
            "the gate script did not reach its summary, so it aborted before "
            "it compared anything and this arm has no run to read.\n"
            f"exit code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        # NON-VACUITY, BOTH SIDES. An empty population makes the comparison
        # pass for the wrong cause, and so does a run that announced no call.
        assert population, "no extract file classified in pact-plugin/protocols/"
        assert verified, (
            "the gate script ran to its summary and announced no VERIFY-CALL, "
            "so its corpus is empty and every extract goes uncompared.\n"
            f"stdout:\n{result.stdout}"
        )

        assert population == verified, (
            "the set of extract FILES and the set the gate script VERIFIES "
            "have diverged.\n"
            f"  files not verified: {sorted(population - verified)}\n"
            f"  verified but not a file: {sorted(verified - population)}\n"
            "A file in the first list is an extract that can drift from its "
            "SSOT region with nothing to report it.\n"
            "\n"
            "TWO REPAIRS, AND WHICH ONE DEPENDS ON WHAT THE FILE IS. THIS "
            "GATE CANNOT TELL THE TWO APART, which is why it asks rather "
            "than guesses:\n"
            "  * IT IS AN EXTRACT (a verbatim slice of pact-protocols.md): "
            "give it a `verify` call in scripts/verify-protocol-extracts.sh.\n"
            "  * IT IS A STANDALONE DOCUMENT that happens to live in this "
            "directory: add its name to EXCLUDED_STANDALONES at the top of "
            "pact-plugin/tests/test_audit_protocol.py, with a one-line "
            "reason. That is the whole repair, one line.\n"
            "THE NAME IS THE PATH RELATIVE TO pact-plugin/protocols, so a "
            "file in a subdirectory reads as `sub/name.md` on both sides."
        )

    def test_the_gate_reports_a_pass_for_every_extract_and_no_failure(self):
        """The reported counts must account for the whole population.

        THIS IS THE ARM THAT REFUSES AN EMPTY CORPUS. `Passed: 0, Failed: 0`
        with exit 0 satisfies the exit-code gate above and means nothing was
        compared. Here the PASS count must equal the number of extract files.
        """
        import re
        import subprocess

        repo_root = Path(__file__).parent.parent.parent
        script = repo_root / "scripts" / "verify-protocol-extracts.sh"
        if not script.exists():
            pytest.skip("verify-protocol-extracts.sh not present")

        population, _ssot = self._extract_population()
        assert population, "no extract file classified in pact-plugin/protocols/"

        result = subprocess.run(
            ["bash", str(script)], cwd=str(repo_root),
            capture_output=True, text=True,
        )
        passed = re.search(r"^Passed:\s*(\d+)$", result.stdout, re.MULTILINE)
        failed = re.search(r"^Failed:\s*(\d+)$", result.stdout, re.MULTILINE)

        # NON-VACUITY: a summary the script did not print would make the two
        # reads below `None`, and a comparison against `None` is not a count.
        assert passed and failed, (
            "the script printed no Passed/Failed summary, so this arm has no "
            f"number to check.\nstdout:\n{result.stdout}"
        )

        assert int(passed.group(1)) == len(population), (
            f"the gate reported {passed.group(1)} passing comparisons against "
            f"{len(population)} extract files. A shortfall means an extract "
            f"was not compared at all, which the exit code cannot report."
        )
        assert int(failed.group(1)) == 0, (
            f"the gate reported {failed.group(1)} failing comparisons.\n"
            f"stdout:\n{result.stdout}"
        )

    def test_verify_protocol_extracts_script_is_present(self):
        """The extracts-sync gate must not silently no-op.

        The companion test above (test_verify_protocol_extracts_concurrent_
        audit_still_matches) SKIPS when the script is absent — a portability
        affordance that also means a future deletion of the script would
        turn the byte-sync gate into a vacuous skip (it would pass without
        verifying anything). This test asserts the script EXISTS in this
        repo so its disappearance is caught as a failure rather than masked
        as a skip — the #972/#966 hardening added byte-identical blockquotes
        to pact-protocols.md / pact-state-recovery.md / pact-variety.md whose
        sync this gate is the only guard for.
        """
        repo_root = Path(__file__).parent.parent.parent
        script = repo_root / "scripts" / "verify-protocol-extracts.sh"
        assert script.exists(), (
            f"verify-protocol-extracts.sh missing at {script} — the protocol "
            "extracts sync gate would silently no-op (skip) without it, "
            "leaving SSOT/extract drift undetected."
        )


class TestTeachbackBlockingSemanticGuard:
    """Semantic-regression guard for the teachback-doc reconciliation to ONE
    blocking model.

    The byte-mirror gate (test_verify_protocol_extracts_* above) guards
    extract<->SSOT BYTE-IDENTITY: it catches a DESYNC of a mirrored pair but is
    BLIND to the blocking-vs-non-blocking SEMANTIC. A future edit that
    re-introduces GEN-1 non-blocking phrasing IDENTICALLY on both the extract and
    its SSOT mirror stays byte-identical and passes the byte-gate. This guard
    asserts the reconciled teachback surface does not re-introduce the specific
    GEN-1 phrases the reconciliation removed.

    False-positive safety: this is a DENYLIST of high-specificity phrases
    distinctive to the removed GEN-1 teachback prose (each verified to appear
    NOWHERE in the current sources). It deliberately does NOT denylist the
    generic word "non-blocking", which legitimately occurs in these files (e.g.
    pact-protocols.md: "The auditor is **non-blocking**", plus hook fail-open /
    HANDOFF-processing contexts) and would false-positive. Phrase-specificity is
    what lets this assert file-wide without region-bounding the multi-topic SSOT.

    Bounded-completeness residual (intentional): a phrase denylist catches a
    copy-paste REVERT to the old GEN-1 wording (the likely regression) but NOT a
    re-worded non-blocking model expressed in fresh prose. Guarding the latter
    would require the generic word + region-bounding + context exclusions, which
    is fragile and false-positive-prone; that completeness is out of scope by
    design (copy-paste-revert is the valuable, false-positive-safe coverage).
    """

    # The reconciled teachback surface (the reconciliation's edited file set).
    RECONCILED_FILES = [
        PROTOCOLS_DIR / "pact-ct-teachback.md",
        PROTOCOLS_DIR / "pact-protocols.md",
        PROTOCOLS_DIR / "pact-completion-authority.md",
        SKILLS_DIR / "pact-teachback" / "SKILL.md",
        AGENTS_DIR / "pact-orchestrator.md",
        COMMANDS_DIR / "peer-review.md",
    ]

    # High-specificity GEN-1 (non-blocking) phrases the reconciliation removed.
    # Distinctive enough that legitimate current prose never contains them, so a
    # match means a GEN-1 regression re-entered the teachback surface. Matched
    # case-insensitively so a re-cased revert is still caught. Note: "stays
    # hidden" is the least-specific entry (it guards the corrected false
    # blockedBy-visibility claim); the other three are unmistakably GEN-1
    # teachback prose. The generic word "non-blocking" is intentionally EXCLUDED
    # (it occurs legitimately, e.g. the auditor description in pact-protocols.md).
    GEN1_REGRESSION_PHRASES = [
        "Why Non-Blocking",                 # removed section heading
        "Proceeding unless corrected",      # removed proceed-optimistically clause
        "proceed with work after sending",  # removed non-blocking flow line
        "stays hidden",                     # corrected false blockedBy claim
    ]

    def test_no_gen1_nonblocking_phrase_in_reconciled_surface(self):
        for path in self.RECONCILED_FILES:
            assert path.is_file(), f"reconciled surface file missing: {path}"
            text = path.read_text(encoding="utf-8").lower()
            for phrase in self.GEN1_REGRESSION_PHRASES:
                assert phrase.lower() not in text, (
                    f"GEN-1 non-blocking phrase {phrase!r} re-introduced into "
                    f"{path.name} — the teachback surface reconciliation moved it "
                    f"to ONE blocking model. The byte-mirror gate cannot catch "
                    f"this (it guards byte-identity, not blocking-vs-non-blocking "
                    f"semantics). If this phrasing is intentionally returning, the "
                    f"reconciliation is being reverted; update this guard "
                    f"deliberately."
                )
