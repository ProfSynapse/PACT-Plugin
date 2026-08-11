"""
Doc-code drift check for the memory patterns page.

Location: pact-plugin/tests/test_memory_patterns_docs.py

WHAT THIS FILE CHECKS, AND THE TWO POPULATIONS ARE DIFFERENT ON PURPOSE.
`skills/pact-memory/references/memory-patterns.md` teaches an agent to reach
the store. The arms below split into two groups, and the group decides the
population.

WHOLE PAGE, because a defect in one example is a defect wherever it sits:
  1. Each shell block parses as a shell command, adjudicated by `bash -n`.
  2. The payload argument THE SHELL BUILDS is valid JSON.
  3. Each python block RUNS to completion against a stub CLI.

THE INCREMENTAL LEARNING SECTION ALONE, because the CLI-route rule is what
that section teaches:
  4. The block invokes the pact-memory CLI.
  5. Its verb is one the CLI parser accepts, DERIVED from the parser source.

ITEMS 1 AND 2 ARE ONE CLAIM READ FROM ONE STRING. A block must parse as a
command and hand that command valid JSON. Read those two from two different
strings, as a regex over the source text does, and a repair to one half can
break the other with no arm going red. `shlex` gives the two halves the word
rule the shell uses, so the trade has nowhere to hide.

🔴 WHY ITEMS 1 AND 2 READ THE WHOLE PAGE AND NOT ONE SECTION. MEASURED: the
save examples sit in Phase Completion Memory, Blocker Documentation, Session
Wrap-Up and Anti-Patterns. THE INCREMENTAL LEARNING SECTION HOLDS NO SAVE
EXAMPLE. A payload with an apostrophe is a save-example defect, so a
section-scoped arm can not reach the class at all. The widening is what turns
that class from unguarded into caught.

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

🔴 THE STATED BOUND, RE-DERIVED FROM THE ARMS ABOVE AND NOT EDITED.

WHAT EACH ARM DECIDES, stated at the grain the arm can support:
  * `bash -n` decides that a shell block PARSES. It runs nothing.
  * The payload arm decides that the argument THE SHELL BUILDS is valid JSON.
    An earlier form said "a snippet is well formed", which overstated: it
    decided that a JSON SUBSTRING of the source text parsed, which is a
    different string whenever a quote does work.
  * The execution arm decides that a python block RUNS TO COMPLETION ON THE
    INTERPRETER THAT RUNS THE TESTS, against a stub CLI. It does NOT decide
    that the block runs on the DECLARED FLOOR, which is `requires-python`
    in `pyproject.toml`. THE SOURCE IS NAMED AND ITS VALUE IS NOT QUOTED
    HERE, because a quoted floor goes stale the day somebody corrects it,
    and a stale bound reads as a measurement.

🔴 THE FLOOR CLAIM IS THE ONE TO REFUSE, AND REFUSING IT IS THE POINT. This
file holds ONE interpreter and cannot speak for another. `ast.parse` with
`feature_version` looks like the tool for a floor claim and is not: it gave
two reviewers a clean pass on this page. A CI matrix decides the floor. An
arm here can not.

🔴 A PARSER IS NOT THE JUDGE OF THE CLASS THAT HIT THIS PAGE TWICE. MEASURED
on the python blocks, before the repair against after it:

    compile()   3 of 3 parse   ->   3 of 3 parse     (moves nothing)
    execution   0 of 3 run     ->   3 of 3 run       (separates fully)

An unexpanded `${CLAUDE_SKILL_DIR}` inside a string literal PARSES PERFECTLY.
A parse-only arm reports it absent, with a live instrument and a true result.
That is why the execution arm exists and why `compile()` stays a cheap first
gate rather than the judge.

🔴 THE EXECUTION ARM CLOSES ONE OF THE TWO CLASSES AND NOT THE OTHER, AND THE
DIFFERENCE IS THE INTERPRETER. MEASURED by mutation against this file:

    unexpanded `${CLAUDE_SKILL_DIR}`   ->  the execution arm REDS
    PEP 701 nested f-string            ->  NOTHING HERE REDS

The second result is correct rather than a hole in the arm. PEP 701 syntax is
VALID from 3.12, this file ran on 3.14.6, and a valid construct cannot fail a
parse or a run. So no arm in this file can decide it, and `compile()` cannot
either. ONLY AN INTERPRETER BELOW 3.12 DECIDES THAT CLASS, which makes it a
CI-matrix question and not a question for any arm here.

DO NOT READ A GREEN FROM THE EXECUTION ARM AS COVER FOR THE F-STRING CLASS.
Reading it that way removes the reason to keep an old interpreter in the
matrix, which is the only instrument that reports it.

🔴 THE FIRST FORM OF THIS BOUND UNDERSTATED ITS OWN REGION, and a reviewer
measured it rather than accept it. That form named four items as the excluded
region. SHELL VALIDITY WAS ALSO OUTSIDE, and it was broken on this page at the
time. A bound that names its region and omits a live member is the same defect
as a bound nobody measures, committed by the author who wrote it honestly.

🔴 AND THE INSTRUMENT THAT MISSED IT WENT ON TO REFUSE ITS OWN CURE. The
payload reader was a regex over the source text. MEASURED: it called the
broken command's payload valid, and it called the ORDINARY REPAIR of that
command, an apostrophe escaped as `'"'"'`, a broken payload. So the first
instrument accepted the defect and then reported a defect against the fix. An
instrument with the wrong subject does not merely miss. It points.

Named precisely, so a later reader can measure the region rather than meet a
vague caution, THIS FILE DOES NOT CATCH:

  * A verb the parser accepts and that FAILS at run time for this input, such
    as an update against an id that is not present.
  * A payload that parses and that carries a field the store rejects, or a
    field name the schema does not hold. THE STUB ANSWERS EVERY KEY THE
    BLOCKS READ, derived from the blocks, so this arm cannot decide that the
    CLI returns those keys. That choice is deliberate: a hand-written stub
    goes stale and reds a correct page, which is the worse failure.
  * A flag that is spelled correctly and that the verb does not accept.
  * A snippet that is correct alone and incorrect in sequence with the one
    before it.
  * A behaviour that depends on the REAL CLI. The stub returns one record and
    exits 0, so nothing here reaches the store or the network.
  * 🔴 THE MARKED REGION MOVED INTO A CODE FENCE. MEASURED by a reviewer over
    a ten-cell mutation matrix: eight cells fire and this is one of the two
    that do not, at a copy and at the source alike. DISCLOSED AND NOT CLOSED,
    by ruling. Its severity is low because an LLM reads raw bytes, so a fenced
    rule keeps its words. That severity rests on the raw-byte reading. If a
    consumer ever renders this text instead, the cell becomes a defect and
    belongs on the tracker rather than in this list.

🔴 AND THE LIST ABOVE IS A MEASURED FLOOR RATHER THAN A CLOSED SET. A bound
records a question nobody then puts, so measure the region it excludes before
you accept it. That is how shell validity was found, and a later reader must
assume one more member sits outside this list.

APPLY THE RULE THIS ARC PRODUCED: A STATED BOUND RECORDS A QUESTION NOBODY
THEN PUTS. The items above are written so somebody can measure them. Do not
accept the bound without that measurement, and do not read the list as closed.

WHY THE VERB SET IS DERIVED AND NOT WRITTEN DOWN. A verb list in this file
goes stale on the day the CLI gains or renames one, and a stale list fails in
the direction that reads as a doc defect. This reads the parser source and
takes the names it declares, BY A TEXT READ and with no import.

🔴 HOW THE EXECUTION ARM STAYS AWAY FROM THE STORE, and the mechanism is the
page's own code rather than a promise. Each python block builds its command
from `os.environ["CLAUDE_SKILL_DIR"]`. The arm points that variable at a
temporary directory holding a STUB `cli.py`. So the path the block builds
resolves inside the temporary directory, and the real CLI is unreachable BY
CONSTRUCTION rather than by care. This file imports no module below
`skills/pact-memory/scripts/` and runs no real CLI verb.

Used by: pytest.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent

PATTERNS_MD = PLUGIN_DIR / "skills" / "pact-memory" / "references" / "memory-patterns.md"

# The parser this file reads for the accepted verbs. TEXT ONLY, no import.
CLI_SOURCE = PLUGIN_DIR / "skills" / "pact-memory" / "scripts" / "cli.py"

# The section the CLI-route arms read. Sliced from its heading to the next
# top-level one.
#
# 🔴 ANCHORED ON THE TITLE AND NOT ON THE NUMBER, and that is a repair rather
# than a preference. An earlier form held `^## Pattern 8:`. The page skipped
# Pattern 4, and the repair for that skip renumbers the later headings, which
# renames the section this file reads. SO THIS FILE BLOCKED A CORRECT PAGE
# EDIT: an author fixing the numbering met a red gate and had to choose
# between the fix and the test.
#
# THE NUMBER BELONGS TO THE PAGE AND THE TITLE IS THE STABLE PART. A test that
# pins the volatile half of a heading reds on a correct repair, which is the
# failure this file argues against everywhere else.
SECTION_HEADING = r"^## Pattern \d+: Incremental Learning\s*$"

# A block invokes the CLI when it names the CLI module. The page writes the
# path with a shell variable, so this matches the module name rather than the
# whole path, which the page is free to spell in more than one way.
CLI_MARKER = "cli.py"

# The fence tags this file classifies. An unknown tag must go red rather than
# be skipped: a skipped block is a block no arm reads, and the arms below then
# report a clean result over a set that lost a member.
SHELL_TAGS = frozenset({"bash", ""})
PYTHON_TAGS = frozenset({"python"})
KNOWN_TAGS = SHELL_TAGS | PYTHON_TAGS

# The environment name the page's python examples read to find the CLI. The
# execution arm points this at a temporary directory, which is what keeps the
# run away from the real CLI.
SKILL_DIR_VAR = "CLAUDE_SKILL_DIR"

# Keys the stub record answers whatever the blocks ask for. Membership is
# DERIVED from the blocks, so a block that reads a new key does not red a
# correct page. The cost is stated in the bound: this arm cannot decide that
# the CLI returns these keys.
LIST_VALUED_KEYS = frozenset({"decisions", "entities", "lessons_learned"})

# A run that hangs is a failed run, not a slow one.
BLOCK_TIMEOUT_SECONDS = 60


def accepted_verbs() -> set:
    """Return the verb names the CLI parser declares.

    DERIVED FROM THE PARSER SOURCE rather than written here. A list in this
    file goes stale on the day the CLI renames a verb, and the stale form
    reports a doc defect for a tool change, which points a reader at the wrong
    file.
    """
    source = CLI_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r"add_parser\(\s*[\"']([a-z0-9_-]+)[\"']", source))


def incremental_learning_section() -> str:
    """Return the Incremental Learning section, heading to the next heading.

    NAMED FOR THE TITLE AND NOT THE NUMBER, for the reason recorded at
    `SECTION_HEADING`: the number belongs to the page and moves with it.
    """
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


def page_text() -> str:
    """Return the whole page.

    THE SHELL AND EXECUTION ARMS READ THIS, and not a section. A defect in an
    example is a defect wherever the example sits, and the save examples that
    carry the apostrophe risk sit outside the Incremental Learning section.
    """
    return PATTERNS_MD.read_text(encoding="utf-8")


def stub_record(blocks: list) -> dict:
    """Return one memory-shaped record that answers each key the blocks read.

    DERIVED FROM THE BLOCKS BY DESIGN. A hand-written record goes stale on the
    day an example reads a new field, and it then reds a CORRECT page and sends
    the author to the page rather than to this file. MEASURED while this arm
    was built: a first form scanned only `mem['...']` and missed the nested
    `alternatives`, so a correct block failed on a hole in the stub.

    THE COST IS REAL AND THE BOUND NAMES IT: a stub that answers each key
    cannot detect a block that reads a key the CLI does not return.
    """
    keys = set()
    for body in blocks:
        keys |= set(re.findall(r"\[\s*[\"'](\w+)[\"']\s*\]", body))
    keys -= {SKILL_DIR_VAR}
    keys |= {"context", "goal", "created_at"}

    def leaf(key: str) -> str:
        return "2026-01-01T00:00:00Z" if key.endswith("_at") else f"stub-{key}"

    inner = {k: (["stub"] if k in LIST_VALUED_KEYS else leaf(k)) for k in keys}
    return {k: ([inner] if k in LIST_VALUED_KEYS else leaf(k)) for k in keys}


def run_python_block(body: str, skill_dir: Path) -> subprocess.CompletedProcess:
    """Run one python block with the CLI path pointed at `skill_dir`."""
    environment = dict(os.environ)
    environment[SKILL_DIR_VAR] = str(skill_dir)
    return subprocess.run(
        ["python3", "-c", body],
        capture_output=True,
        text=True,
        env=environment,
        cwd=str(skill_dir),
        timeout=BLOCK_TIMEOUT_SECONDS,
    )


def write_stub_cli(skill_dir: Path, record: dict) -> Path:
    """Write a stub `cli.py` that prints one record and exits 0."""
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    target = scripts / "cli.py"
    target.write_text(
        "import json\nprint(json.dumps(" + json.dumps([record]) + "))\n",
        encoding="utf-8",
    )
    return target


def tagged_blocks(section: str) -> list:
    """Return each fenced block in `section` as a (tag, body) pair.

    THE TAG IS PART OF THE READING. An arm that adjudicates a shell command
    must not receive a python block, and an unknown tag must reach an arm that
    refuses it rather than a filter that drops it.
    """
    return re.findall(r"```([a-z]*)\n(.*?)```", section, flags=re.DOTALL)


def fenced_blocks(section: str) -> list:
    """Return the body of each fenced block, whatever its tag."""
    return [body for _, body in tagged_blocks(section)]


def shell_blocks(section: str) -> list:
    """Return the body of each block a shell reads."""
    return [body for tag, body in tagged_blocks(section) if tag in SHELL_TAGS]


def payload_arguments(block: str) -> list:
    """Return each brace-leading ARGUMENT the shell hands to the command.

    🔴 THE SUBJECT IS THE ARGUMENT THE COMMAND RECEIVES, AND NOT THE SOURCE
    TEXT THAT SPELLS IT. An earlier form took the text between a pair of
    single quotes with a regex. Those are two different strings the moment a
    quote does work, and the difference is not cosmetic. MEASURED on four
    fixtures, with the regex against this function:

      | fixture                          | bash -n | regex payload | this |
      |----------------------------------|---------|---------------|------|
      | apostrophe inside single quotes  | rc=2    | VALID json    | red  |
      | trailing comma in the payload    | rc=0    | red           | red  |
      | apostrophe escaped as `'"'"'`    | rc=0    | RED, FALSELY  | pass |
      | clean                            | rc=0    | pass          | pass |

    ROW 1 AND ROW 3 ARE THE WHOLE REASON THIS FUNCTION IS NOT A REGEX. Row 1
    is a command that does not parse, and the regex called its payload clean.
    Row 3 is the ORDINARY REPAIR of row 1, and the regex called it broken. So
    the regex accepted the defect and then refused its own cure, which sends a
    reader to the payload when the instrument is at fault.

    `shlex` applies the word rule the shell applies, so the two halves you
    must keep true at once, a command that parses and a payload that parses,
    are read from ONE string rather than two that can be traded. It is a
    tokenizer: it runs nothing and reaches no store.

    An unbalanced quote raises `ValueError`. Let it out. The shell-parse arm
    is the place that reports it, and a caught-and-dropped quote fault here
    is the silent half of the trade this function must close.
    """
    return [
        word for word in shlex.split(block, comments=True)
        if word.lstrip().startswith("{")
    ]


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
        section = incremental_learning_section()
        assert len(section.strip()) > 0, "the Incremental Learning slice is empty"

    def test_the_section_holds_fenced_blocks(self):
        blocks = fenced_blocks(incremental_learning_section())
        assert blocks, (
            "no fenced block is in the Incremental Learning section, so the "
            "section arms below "
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

    def test_every_block_carries_a_tag_this_file_classifies(self):
        """🔴 THE FILTER IS THE HAZARD, AND THIS IS ITS NET.

        The shell arm reads the blocks tagged `bash` or untagged. A block with
        a tag no arm claims is a block NO ARM READS, and the suite then reports
        a clean result over a set that quietly lost a member.

        MEASURED on the page today: 15 blocks, 12 `bash`, 3 `python`, none
        untagged. So the filter drops nothing now. This arm is what makes that
        stay true rather than a fact somebody once checked.

        🔴 THIS READS THE WHOLE PAGE AND NOT THE SECTION. It must cover the
        population the widest arm reads, and the shell and execution arms read
        the page. A section-scoped tag control leaves each block outside the
        section free to carry a tag no arm claims.
        """
        unknown = {
            tag for tag, _ in tagged_blocks(page_text())
            if tag not in KNOWN_TAGS
        }
        assert not unknown, (
            f"the page holds a fenced block tagged {sorted(unknown)}, "
            f"which this file does not classify. Known: {sorted(KNOWN_TAGS)}. "
            f"DO NOT ADD THE TAG TO `SHELL_TAGS` WITHOUT A READING: `bash -n` "
            f"is the adjudicator for a shell block and it is the wrong "
            f"instrument for another kind. Decide which arms own the new tag."
        )

    def test_the_payload_reader_reads_the_argument_and_not_the_source_text(self):
        """🔴 A SEPARATION MATRIX, AND EACH ROW MUST DO WORK ONLY IT DOES.

        Row 3 is the row that matters. `'"'"'` is the ordinary way to put an
        apostrophe inside a single-quoted shell argument, and it is the repair
        for row 1. The regex this replaced reported row 3 as a broken payload,
        so it refused the cure for the defect it had accepted.
        """
        clean = """python3 "$D/cli.py" update abc '{"a": [1]}'"""
        assert payload_arguments(clean) == ['{"a": [1]}']

        # An escaped apostrophe: the shell hands the command `it's fine`.
        escaped = """python3 "$D/cli.py" update abc '{"note": "it'"'"'s fine"}'"""
        assert payload_arguments(escaped) == ['{"note": "it\'s fine"}'], (
            "the payload reader returned the source text rather than the "
            "argument. It is a regex again, and a correctly escaped apostrophe "
            "now reports as a broken payload."
        )
        json.loads(payload_arguments(escaped)[0])

        # A bare apostrophe ends the argument early. The reader must not
        # invent a payload the command does not receive.
        with pytest.raises(ValueError):
            payload_arguments("""python3 "$D/cli.py" update abc '{"n": "redis-py's"}'""")

        assert payload_arguments("cli.py list") == []

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


class TestThePagePatternNumbering:
    """🔴 THIS ARM IS THE OTHER HALF OF THE ANCHOR REPAIR.

    `SECTION_HEADING` reads a `\\d+` because the number belongs to the page. A
    mutant that renumbers the section reddens NOTHING, which is the correct
    result for the anchor AND which leaves the numbering itself unguarded. A
    hand check of the numbering does not survive the next editor.

    SO THE COUPLING IS REPLACED RATHER THAN REMOVED. The arm below is about
    the PROPERTY, that the headings run 1 to N with no hole and no repeat,
    and not about one number that a later edit is free to move.

    THE DEFECT THIS REFUSES IS A MOVED HOLE, NOT A MISSING NUMBER. The page
    ran 1, 2, 3, 5, 6, 7, 8, and a partial repair gives 1, 2, 3, 4, 5, 6, 8.
    That reads as progress and carries the hole to the end.
    """

    def test_the_pattern_headings_run_one_to_n_with_no_hole(self):
        numbers = [
            int(m.group(1))
            for m in re.finditer(r"^## Pattern (\d+):", page_text(), flags=re.MULTILINE)
        ]
        assert numbers, (
            "no `## Pattern N:` heading is on the page, so this arm walks an "
            "empty set and passes for that reason alone. EITHER the headings "
            "were renamed, and this arm must follow, OR the page changed shape."
        )
        assert numbers == list(range(1, len(numbers) + 1)), (
            f"the pattern headings read {numbers} and must read "
            f"{list(range(1, len(numbers) + 1))}. A hole or a repeat sends a "
            f"reader to a section that is absent. REPAIR THE WHOLE RUN AT "
            f"ONCE: a partial renumber moves the hole to the end rather than "
            f"closes it, and it reads as progress while it does so."
        )


class TestThePageTeachesTheCliRoute:
    """The drift check. Its subject is the CLI route, which is what the page
    now teaches.

    🔴 TWO POPULATIONS IN ONE CLASS, AND THE SPLIT IS DELIBERATE. The shell and
    execution arms read the WHOLE PAGE, because a defect in an example is a
    defect wherever it sits. The CLI-route arms read the Incremental Learning
    SECTION, because that is the section whose subject is the route.

    🔴 EACH ARM HOLDS A MUTANT ONLY IT CATCHES. Measured against a copy of the
    plugin tree, with the unmutated copy green first, so a red below is the
    mutation and not the copy:

      | mutation of the page or the reader    | shell | payload | tag | reader |
      |---------------------------------------|-------|---------|-----|--------|
      | bare apostrophe in a payload          |  RED  |   RED   |  .  |   .    |
      | unterminated `if`, payload untouched  |  RED  |    .    |  .  |   .    |
      | trailing comma, quoting untouched     |   .   |   RED   |  .  |   .    |
      | a block retagged `console`            |   .   |    .    | RED |   .    |
      | the payload reader put back to a regex|   .   |    .    |  .  |  RED   |
      | each shell fence retagged             |  RED  |   RED   |  .  |   .    |
      | THE CURE, apostrophe as `'"'"'`       | green |  green  |green| green  |

    THE LAST TWO ROWS ARE THE ONES THAT ARE EASY TO LEAVE OUT. The retag row
    is the vacuity arm: it empties the population and the arms must refuse an
    empty set rather than pass over it. THE CURE ROW IS A COUNTER-TEST: a
    guard that reds on the correct repair is worse than absent, because it
    argues against the fix while looking like diligence.

    THE EXECUTION ARM HOLDS ITS OWN SEPARATION, recorded at its own docstring,
    because a parser and a run disagree about the class that hit this page.
    """

    def test_each_block_in_the_section_invokes_the_cli(self):
        blocks = fenced_blocks(incremental_learning_section())
        silent = [b for b in blocks if CLI_MARKER not in b]
        assert not silent, (
            f"{len(silent)} fenced block(s) in the Incremental Learning "
            f"section do not name {CLI_MARKER!r}. The page teaches store "
            f"access, and the store-access rule sends a memory operation "
            f"through the CLI. A block that reaches the store another way "
            f"teaches the route the rule forbids. Blocks: {silent}"
        )

    def test_each_block_in_the_section_uses_a_verb_the_parser_accepts(self):
        verbs = accepted_verbs()
        unknown = []
        for block in fenced_blocks(incremental_learning_section()):
            verb = block_verb(block, verbs)
            if verb is None:
                unknown.append(block)
        assert not unknown, (
            f"{len(unknown)} fenced block(s) in the Incremental Learning "
            f"section name no verb the CLI parser accepts. Accepted today, "
            f"derived from {CLI_SOURCE.name}: {sorted(verbs)}. EITHER the page "
            f"teaches a verb that went, which is a doc defect, OR the CLI "
            f"renamed one and the page did not follow, which is a drift. Read "
            f"the two before you repair one. Blocks: {unknown}"
        )

    def test_every_shell_block_parses_as_a_shell_command(self):
        """🔴 THE ADJUDICATOR OF A PARSE CLAIM IS THE PARSER.

        This file claims each block invokes the CLI. A regex answers a
        DIFFERENT question and can agree with the shell by luck. MEASURED on
        this page: a payload holding `redis-py's` terminates the single-quoted
        shell argument, so the command does not parse, while a regex reports
        the payload clean.

        THIS WALKS EACH SHELL BLOCK IN THE SLICE rather than a block somebody
        found broken, and it reports the count that parse against the count
        that exist. A named block is a defect that was repaired once. A count
        is a property that holds.

        `bash -n` reads the syntax and runs nothing, so this reaches no store.
        """
        blocks = shell_blocks(page_text())
        assert blocks, (
            f"no shell block is on the page, so this arm walks an empty set "
            f"and passes for that reason alone. Tags read as shell: "
            f"{sorted(SHELL_TAGS)}."
        )
        broken = []
        for index, block in enumerate(blocks):
            result = subprocess.run(
                ["bash", "-n"], input=block, capture_output=True, text=True
            )
            if result.returncode != 0:
                broken.append(f"block {index}: {result.stderr.strip()[:120]}")
        assert not broken, (
            f"{len(blocks) - len(broken)} of {len(blocks)} shell block(s) in "
            f"the page parse. These do not: {broken}. An agent that copies "
            f"one gets a shell syntax error. THE COMMON CAUSE IS AN APOSTROPHE "
            f"inside a single-quoted payload, which ends the argument early. "
            f"THE REPAIR IS `'\"'\"'`, and the payload arm accepts it: that arm "
            f"reads the argument the shell builds, so the two arms cannot be "
            f"traded against each other."
        )

    def test_every_shell_block_hands_the_command_a_payload_that_parses(self):
        """🔴 THE TWO HALVES ARE ONE ARM, BECAUSE A TRADE BETWEEN THEM IS
        SILENT. A block must parse as a command AND hand that command valid
        JSON. Read those from two different strings and a repair to one half
        can break the other with no arm going red.

        This reads the ARGUMENT, through `shlex`, so the two halves come from one
        string. The command that does not parse has no argument to read, and
        this arm names it rather than skip it.
        """
        blocks = shell_blocks(page_text())
        assert blocks, "no shell block is on the page"
        bad = []
        checked = 0
        for index, block in enumerate(blocks):
            try:
                payloads = payload_arguments(block)
            except ValueError as exc:
                bad.append(
                    f"block {index}: the shell cannot split it ({exc}), so no "
                    f"argument reaches the command. Repair the quoting first."
                )
                continue
            for payload in payloads:
                checked += 1
                try:
                    json.loads(payload)
                except json.JSONDecodeError as exc:
                    bad.append(f"block {index}: {payload[:60]}... ({exc})")
        assert not bad, (
            f"{checked} payload argument(s) read across {len(blocks)} shell "
            f"block(s), and these are not valid JSON: {bad}. An agent that "
            f"copies the block gets a parse error rather than a memory update. "
            f"THIS ARM READS THE PAYLOAD AND DOES NOT SEND IT, so a payload "
            f"that parses can be refused by the store. That gap is named "
            f"in the stated bound at the top of this file."
        )

    def test_each_python_block_runs_to_completion(self):
        """🔴 THE PARSER IS NOT THE JUDGE OF THIS CLASS. A RUN IS.

        MEASURED on this page, the repair before against after:

            compile()   3 of 3 parse  ->  3 of 3 parse    (moves nothing)
            execution   0 of 3 run    ->  3 of 3 run      (separates fully)

        An unexpanded `${CLAUDE_SKILL_DIR}` inside a string literal PARSES
        PERFECTLY and fails at the moment the command runs. PEP 701 nested
        f-strings parse on an interpreter at 3.12 or above. Each defect class
        that hit this page is invisible to a parse-only arm, which reports a
        true result with a live instrument and answers a question nobody
        asked.

        WHAT THIS DECIDES: the block runs on THE INTERPRETER THAT RUNS THE
        TESTS. It does NOT decide the declared floor. A CI matrix decides
        that, and the stated bound at the top of this file says so.

        THE RUN CANNOT REACH THE STORE, and the mechanism is the page's own
        code. Each block builds its command from the `CLAUDE_SKILL_DIR`
        environment variable, so pointing that at a temporary directory makes
        the real CLI unreachable by construction.
        """
        blocks = [b for tag, b in tagged_blocks(page_text()) if tag in PYTHON_TAGS]
        assert blocks, (
            f"no python block is on the page, so this arm walks an empty set "
            f"and passes for that reason alone. Tags read as python: "
            f"{sorted(PYTHON_TAGS)}. EITHER the examples went, which is a page "
            f"defect, OR the tag changed, which is a reader defect."
        )
        failed = []
        with tempfile.TemporaryDirectory() as work_dir:
            skill_dir = Path(work_dir)
            stub = write_stub_cli(skill_dir, stub_record(blocks))
            # A control on the harness. If the stub is absent, each block below
            # fails for a harness reason and the message points at the page.
            assert stub.is_file(), f"the stub CLI was not written at {stub}"
            for index, body in enumerate(blocks):
                result = run_python_block(body, skill_dir)
                if result.returncode != 0:
                    tail = result.stderr.strip().splitlines()
                    failed.append(
                        f"block {index}: rc={result.returncode} "
                        f"{tail[-1][:160] if tail else '(no stderr)'}"
                    )
        assert not failed, (
            f"{len(blocks) - len(failed)} of {len(blocks)} python block(s) run "
            f"to completion. These do not: {failed}. AN AGENT THAT COPIES ONE "
            f"GETS THAT ERROR. Read the failure before you reach for the "
            f"harness: a `${{{SKILL_DIR_VAR}}}` that survives into a command "
            f"is the page writing a variable name where it must read the "
            f"variable, and no parser reports it. DO NOT REPAIR THIS BY A "
            f"CHANGE TO THE STUB unless the block reads a key no CLI returns."
        )
