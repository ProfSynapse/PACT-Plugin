"""
Doc-code drift check for the Pattern 8 section of the memory patterns page.

Location: pact-plugin/tests/test_memory_patterns_docs.py

WHAT THIS FILE CHECKS. Pattern 8 of
`skills/pact-memory/references/memory-patterns.md` teaches an agent how to
update a memory. This reads that section and asserts three things about each
fenced block in it:

  1. The block invokes the pact-memory CLI.
  2. Its verb is one the CLI parser accepts, DERIVED from the parser source.
  3. Its JSON payload parses.

🔴 WHAT THIS FILE STOPPED CHECKING, AND WHY THE CHANGE WAS NECESSARY.

An earlier form of this file sliced the same section, took its fenced PYTHON
blocks, and ran them against a fake memory object. That form did TWO jobs and
one of them was redundant:

  JOB 1, THE BEHAVIOUR of an additive merge and of a replace that clobbers.
  REDUNDANT, and measured rather than assumed: `tests/test_memory_database.py`
  holds that coverage, and it reads this page ZERO times. So the behavioural
  claim never depended on the doc.

  JOB 2, DOC-CODE DRIFT. Worth keeping. Its SUBJECT must move with the page.

THE PAGE NOW TEACHES THE CLI ROUTE, because the module-API route it taught
before is the route the store-access bar forbids. AN EXEC-BASED CHECK WOULD
PIN A SHIPPED PAGE TO THE FORBIDDEN ROUTE, in the one section a test provably
exercises. That is worse than no check: it enforces the contradiction the bar
exists to remove.

🔴 THE STATED BOUND, AND IT IS A LOSS RATHER THAN A TRADE.

AN EXEC PROVES A SNIPPET RUNS. THIS PROVES A SNIPPET IS WELL FORMED. That is
WEAKER and this file does not hide it. Named precisely, so a later reader can
measure the region rather than meet a vague caution, THIS FILE DOES NOT CATCH:

  * A verb the parser accepts and that FAILS at run time for this input, such
    as an update against an id that is not present.
  * A payload that parses and that carries a field the store rejects, or a
    field name the schema does not hold.
  * A flag that is spelled correctly and that the verb does not accept.
  * A snippet that is correct alone and incorrect in sequence with the one
    before it.

THE STRONGER FORM IS A SUBPROCESS AGAINST A TEMPORARY STORE. It does not ride
this branch, because it is a new behavioural harness for a page and this
branch is about a rule. A tracker item carries it with this loss named.

APPLY THE RULE THIS ARC PRODUCED: A STATED BOUND RECORDS A QUESTION NOBODY
THEN PUTS. The four items above are the excluded region, written so somebody
can measure it. Do not accept the bound without a measurement of them.

WHY THE VERB SET IS DERIVED AND NOT WRITTEN DOWN. A verb list in this file
goes stale on the day the CLI gains or renames one, and a stale list fails in
the direction that reads as a doc defect. This reads the parser source and
takes the names it declares. THE READ IS TEXT ONLY: this file imports no
module below `skills/pact-memory/scripts/` and runs no CLI, so it cannot reach
the live store.

Used by: pytest.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent

PATTERNS_MD = PLUGIN_DIR / "skills" / "pact-memory" / "references" / "memory-patterns.md"

# The parser this file reads for the accepted verbs. TEXT ONLY, no import.
CLI_SOURCE = PLUGIN_DIR / "skills" / "pact-memory" / "scripts" / "cli.py"

# The section under check. Sliced from its heading to the next top-level one.
SECTION_HEADING = r"^## Pattern 8:.*$"

# A block invokes the CLI when it names the CLI module. The page writes the
# path with a shell variable, so this matches the module name rather than the
# whole path, which the page is free to spell in more than one way.
CLI_MARKER = "cli.py"


def accepted_verbs() -> set:
    """Return the verb names the CLI parser declares.

    DERIVED FROM THE PARSER SOURCE rather than written here. A list in this
    file goes stale on the day the CLI renames a verb, and the stale form
    reports a doc defect for a tool change, which points a reader at the wrong
    file.
    """
    source = CLI_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r"add_parser\(\s*[\"']([a-z0-9_-]+)[\"']", source))


def pattern_8_section() -> str:
    """Return the Pattern 8 section, heading to the next top-level heading."""
    text = PATTERNS_MD.read_text(encoding="utf-8")
    start = re.search(SECTION_HEADING, text, flags=re.MULTILINE)
    assert start, (
        f"the heading {SECTION_HEADING!r} is absent from {PATTERNS_MD.name}. "
        f"EITHER the section was renamed, and this file must follow it, OR "
        f"the section went and this file must go with it. Do not repair this "
        f"by a wider slice: a slice that starts at the wrong place reports a "
        f"clean result over the wrong text."
    )
    tail = text[start.end():]
    end = re.search(r"^## ", tail, flags=re.MULTILINE)
    stop = start.end() + end.start() if end else len(text)
    return text[start.start():stop]


def fenced_blocks(section: str) -> list:
    """Return each fenced block in `section`, whatever its language tag."""
    return re.findall(r"```[a-z]*\n(.*?)```", section, flags=re.DOTALL)


def json_payloads(block: str) -> list:
    """Return each single-quoted JSON argument in a shell block.

    The page passes a payload as one shell-quoted argument. This takes the
    text between the first pair of single quotes that opens with a brace.
    """
    return re.findall(r"'(\{.*?\})'", block, flags=re.DOTALL)


def block_verb(block: str, verbs: set) -> str | None:
    """Return the CLI verb the block invokes, or None when it invokes none.

    🔴 THE VERB IS THE TOKEN THAT FOLLOWS THE CLI MODULE, AND NOT A
    VERB-SHAPED WORD ANYWHERE IN THE BLOCK. An earlier form of this function
    scanned the whole block, so a comment or a JSON value satisfied it.
    MEASURED: the word `setup` sits inside a payload of this page, in
    `"notes": "HA setup"`. With the whole-block scan, a block that invoked an
    UNKNOWN verb on the command line passed, because the payload supplied an
    accepted one. The arm reported a clean result over a broken command.

    THAT IS A WRONG ALPHABET RATHER THAN A WRONG QUERY: the subject is the
    command line, and the instrument read the whole document.
    """
    match = re.search(
        re.escape(CLI_MARKER) + r"\"?\s+([a-z][a-z0-9_-]*)",
        block,
    )
    if match is None:
        return None
    return match.group(1) if match.group(1) in verbs else None


class TestTheInstrumentIsLive:
    """Controls on the reader, and not rules about the page.

    AN EMPTY SECTION AGREES WITH EVERY RULE BELOW, so the first control
    asserts the slice returns text and the second asserts it returns blocks.
    """

    def test_the_section_is_present_and_not_empty(self):
        section = pattern_8_section()
        assert len(section.strip()) > 0, "the Pattern 8 slice is empty"

    def test_the_section_holds_fenced_blocks(self):
        blocks = fenced_blocks(pattern_8_section())
        assert blocks, (
            "no fenced block is in the Pattern 8 section, so each arm below "
            "passes over an empty set. EITHER the examples went, which is a "
            "page defect, OR the fence syntax changed, which is a reader "
            "defect. Read the section before you decide."
        )

    def test_the_verb_set_is_derived_and_not_empty(self):
        """Non-vacuity on the derivation. An empty set accepts no verb, and
        an arm that compares against it reports a defect for each block."""
        verbs = accepted_verbs()
        assert verbs, (
            f"no verb was derived from {CLI_SOURCE.name}. The parser shape "
            f"changed, so the pattern in `accepted_verbs` no longer finds the "
            f"declarations. Correct the pattern rather than write a list here."
        )
        for expected in ("save", "update", "search"):
            assert expected in verbs, (
                f"{expected!r} is absent from the derived verb set {sorted(verbs)}. "
                f"That is a control on the derivation rather than a rule about "
                f"the CLI: these three are load-bearing in the page today."
            )

    def test_the_payload_reader_finds_a_payload_and_refuses_prose(self):
        """A control on the matcher, and each half must do work."""
        assert json_payloads("""cli.py update abc '{"a": [1]}'""") == ['{"a": [1]}']
        assert json_payloads("cli.py list") == []

    def test_the_verb_reader_reads_the_command_line_and_not_the_payload(self):
        """🔴 THE DEFECT THIS PINS WAS LIVE AND IT PASSED A BROKEN COMMAND.

        An earlier form scanned the whole block for a verb-shaped word. The
        payload of this page holds `"notes": "HA setup"`, and `setup` is an
        accepted verb, so a block that invoked an UNKNOWN verb on the command
        line was accepted on the strength of a word in its data.

        THE TWO HALVES ARE THE ARM. The reader must take the verb after the
        CLI module, and it must NOT take one from a payload or a comment.
        """
        verbs = accepted_verbs()
        good = """python3 "path/cli.py" update abc '{"notes": "HA setup"}'"""
        assert block_verb(good, verbs) == "update"

        broken = """python3 "path/cli.py" upsert abc '{"notes": "HA setup"}'"""
        assert block_verb(broken, verbs) is None, (
            "the verb reader accepted a word from the payload. A block with "
            "an unknown verb on the command line then passes, which is the "
            "measured defect this arm exists to refuse."
        )

        commented = """# run update later\npython3 "path/cli.py" upsert abc"""
        assert block_verb(commented, verbs) is None


class TestPattern8TeachesTheCliRoute:
    """The drift check. Its subject is the CLI route, which is what the page
    now teaches."""

    def test_each_block_invokes_the_cli(self):
        blocks = fenced_blocks(pattern_8_section())
        silent = [b for b in blocks if CLI_MARKER not in b]
        assert not silent, (
            f"{len(silent)} fenced block(s) in Pattern 8 do not name "
            f"{CLI_MARKER!r}. The page teaches store access, and the store-"
            f"access rule sends a memory operation through the CLI. A block "
            f"that reaches the store another way teaches the route the rule "
            f"forbids. Blocks: {silent}"
        )

    def test_each_block_uses_a_verb_the_parser_accepts(self):
        verbs = accepted_verbs()
        unknown = []
        for block in fenced_blocks(pattern_8_section()):
            verb = block_verb(block, verbs)
            if verb is None:
                unknown.append(block)
        assert not unknown, (
            f"{len(unknown)} fenced block(s) in Pattern 8 name no verb the "
            f"CLI parser accepts. Accepted today, derived from "
            f"{CLI_SOURCE.name}: {sorted(verbs)}. EITHER the page teaches a "
            f"verb that went, which is a doc defect, OR the CLI renamed one "
            f"and the page did not follow, which is a drift. Read the two "
            f"before you repair one. Blocks: {unknown}"
        )

    def test_each_payload_parses(self):
        bad = []
        for block in fenced_blocks(pattern_8_section()):
            for payload in json_payloads(block):
                try:
                    json.loads(payload)
                except json.JSONDecodeError as exc:
                    bad.append(f"{payload[:60]}... ({exc})")
        assert not bad, (
            f"a JSON payload in Pattern 8 does not parse: {bad}. An agent "
            f"that copies the block gets a parse error rather than a memory "
            f"update. THIS ARM READS THE PAYLOAD AND DOES NOT SEND IT, so a "
            f"payload that parses can still be refused by the store. That "
            f"gap is named in the stated bound at the top of this file."
        )
