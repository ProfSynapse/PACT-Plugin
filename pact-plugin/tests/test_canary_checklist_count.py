"""The canary checklist states a check count that an instrument reads.

WHY THIS ARM IS THE REPAIR AND THE CORRECTED NUMBER IS NOT. The checklist said
the extract gate performs 16 checks. It performs 19. Correcting the digit fixes
today and repairs nothing: A PROSE CLAIM THAT NO INSTRUMENT READS GOES STALE IN
SILENCE, and the silence is the defect. Somebody adds a call to the script, no
test reads the checklist, and a reviewer follows a number that describes a
script from before.

THE POPULATION COMES FROM WHAT THE SCRIPT DID, NOT FROM ITS SOURCE TEXT, AND
THAT CHOICE IS THE LOAD-BEARING ONE. The obvious rule is to count the `verify`
call sites with a regular expression over the script. THAT RULE IS DEFECTIVE
AND IT WAS MEASURED DEFECTIVE ON THIS BRANCH, in two directions that a reader
of the rule cannot see:
  1. A line at COLUMN ZERO inside an ordinary heredoc, for example a usage
     message that shows a sample invocation, is counted as a call. The script
     is correct, and the count is one too high.
  2. Changing the first argument of each call from double to single quotes is
     identical to bash and makes the rule match NOTHING. The count falls to
     zero, which reads as a broken harness rather than as a defect in the rule.
A shell script is not reliably parsed by a line-oriented pattern. NEITHER a
line at column zero NOR a quote style can change what a script EMITS when it
runs, so the run is the sound source.

THE TWO SIDES ARE INDEPENDENT, WHICH IS WHAT MAKES THE COMPARISON EVIDENCE. One
side is a document a person maintains by hand. The other is the behaviour of a
script at run time. They can disagree, and the whole point is that they DO
disagree when somebody edits one alone. Nothing here derives both sides from
one source, which would make the comparison a tautology that always holds.

WHY `Passed + Failed` AND NOT `Passed`. The sum is the number of comparisons
the script performed. A genuinely failing extract moves a unit from one column
to the other and leaves the sum alone, so this arm stays on its own subject: it
counts CHECKS, and a byte difference between an extract and its section is the
subject of the extract-gate arms in `test_audit_protocol.py`.

SCOPE, STATED BECAUSE THE CHECKLIST CARRIES FOUR SUCH ROWS. This arm covers the
extract-gate row alone. The other three Tier 1 rows state counts for three other
scripts and no arm reads them. Their presence beside an armed row must not be
read as evidence that they are checked.

THE AXIS THIS ARM CANNOT SEE. It counts comparisons, not what each comparison
compares. A call that names the wrong heading pair is counted here and caught
by the byte comparison inside the script, which the exit-code arm in
`test_audit_protocol.py` reports.
"""
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_CHECKLIST = _REPO_ROOT / "testing" / "canary-checklist.md"
_SCRIPT = _REPO_ROOT / "scripts" / "verify-protocol-extracts.sh"

# The checklist row: a bullet naming the script, then its count in brackets.
_CHECKLIST_COUNT_RE = re.compile(
    r"`verify-protocol-extracts\.sh`\s+passes\s+\((\d+)\s+checks\)"
)


class TestCanaryChecklistCheckCount:
    """The stated number of checks must agree with the checks the gate runs."""

    def _stated_count(self):
        if not _CHECKLIST.exists():
            pytest.skip("testing/canary-checklist.md not present")
        text = _CHECKLIST.read_text(encoding="utf-8")
        match = _CHECKLIST_COUNT_RE.search(text)
        # NON-VACUITY ON THE PROSE SIDE. A row that was reworded out of this
        # shape gives `None`, and a comparison against `None` is not a check.
        # This fails LOUDLY rather than skipping, because a silent skip here
        # returns the file to the unread state this arm exists to end.
        assert match, (
            "no check count parsed from the canary checklist row for "
            "verify-protocol-extracts.sh. The row was reworded, and the count "
            "it states is now unread again."
        )
        return int(match.group(1))

    def _checks_the_gate_ran(self):
        """Return the number of comparisons the script performed.

        The summary line is the emitted evidence. A parse of it depends on the
        summary FORMAT, and a format change makes the assertion below fire
        rather than the count assertion, which is the safe direction and is a
        dependency a reader should know about.
        """
        if not _SCRIPT.exists():
            pytest.skip("scripts/verify-protocol-extracts.sh not present")
        result = subprocess.run(
            ["bash", str(_SCRIPT)], cwd=str(_REPO_ROOT),
            capture_output=True, text=True,
        )
        passed = re.search(r"^Passed:\s*(\d+)$", result.stdout, re.MULTILINE)
        failed = re.search(r"^Failed:\s*(\d+)$", result.stdout, re.MULTILINE)
        assert passed and failed, (
            "the script printed no Passed/Failed summary, so this arm has no "
            f"number to read.\nstdout:\n{result.stdout}"
        )
        return int(passed.group(1)) + int(failed.group(1))

    def test_control_the_gate_runs_and_compares_a_non_empty_population(self):
        """THE CONTROL, and it validates the INSTRUMENT rather than the claim.

        A gate that performed ZERO comparisons reports `Passed: 0, Failed: 0`
        and exits 0. Against an empty population the count comparison below
        would hold for any checklist number that happened to read 0, and a
        deleted script would skip. This arm asserts the gate did work.
        """
        assert self._checks_the_gate_ran() > 0, (
            "the extract gate performed no comparison, so the count arm below "
            "would describe an empty population"
        )

    def test_the_checklist_count_agrees_with_the_gate_it_describes(self):
        """The ruled property: the prose number equals the checks that ran.

        WHAT THIS PROVES AND WHAT IT DOES NOT. It proves the two sides agree.
        It does NOT prove that a reviewer who follows the checklist reaches a
        correct outcome, because no instrument drove a reviewer.
        """
        stated = self._stated_count()
        ran = self._checks_the_gate_ran()
        assert ran > 0, "the extract gate performed no comparison"

        assert stated == ran, (
            f"testing/canary-checklist.md states {stated} checks for "
            f"verify-protocol-extracts.sh and the script ran {ran}.\n"
            "One of the two moved without the other. Correct the checklist "
            "row, or restore the check the script lost."
        )
