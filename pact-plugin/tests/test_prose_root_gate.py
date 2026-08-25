"""Regression gate: LLM-facing prose must not hardcode the Claude config root.

Agents follow prose literally, not the Python resolver, so a `~/.claude/...`
literal in an instruction surface makes a non-default-root install read, write,
and in one case execute against the WRONG install's state tree.

Three arms, two prose assertions, one allowlist, and a control per direction.
Implemented in pathlib rather than shell grep as a PORTABILITY requirement:
ARM 1's lookahead is PCRE and BSD `/usr/bin/grep` rejects `-P`. Where `grep -P`
appears to work, an interactive shell function may be rewriting `grep` to
`ugrep` — that function does not exist in CI.
"""

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent

# The census population. NOT the nine dirs the model gate walks, and no
# top-level iterdir pass: that scope yields 357 out-of-population hits across
# 86 files (tests 227, hooks 100, README 21, telegram 6, reference 3).
CENSUS_DIRS = ("agents", "commands", "skills", "protocols")

# Suffix ALLOWLIST, and it is load-bearing rather than defence-in-depth: it is
# the only mechanism that excludes `__pycache__/*.pyc`. No (path, literal,
# count) triple can key a pycache path — the count is a property of the
# reader's installed interpreters and moved 0 -> 13 -> 0 -> 13 -> 17 during
# development while nobody edited anything. Filter by suffix, never by
# directory name; suffix fails closed.
SCANNED_SUFFIXES = (".py", ".md", ".json", ".txt", ".yml", ".yaml", ".toml")

# This file necessarily contains the banned literals in its own allowlist.
SELF_EXCLUDED_FILES = frozenset({"tests/test_prose_root_gate.py"})

# ⚠️ THE `(?=/)` LOOKAHEAD IS LOAD-BEARING — DO NOT "FIX" IT.
# It is the only reason this arm stays quiet on the migration's OWN output.
# The prescribed shell form is `"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/..."`,
# where `$HOME/.claude` is followed by `}` and not `/`. Broadening to
# `(?=[/}])`, or dropping the lookahead, REDS ON CORRECTLY MIGRATED CODE —
# including the CRITICAL registration site, and every file carrying the
# `{config_dir}` definition sentence (which writes a trailing backticked
# `~/.claude`). Measured three times independently. See the control
# `test_arm1_stays_quiet_on_the_migrations_own_output` below.
ARM1 = re.compile(r"(?:~|\$HOME|\$\{HOME\})/\.claude(?=/)")

# Same firing behaviour as ARM1, extended to capture the path tail so an
# allowlist entry keys on WHICH literal is allowed. Without the tail, every
# entry would key on the bare root prefix and a file could swap an allowed
# `~/.claude/pact-memory/memory.db` for a forbidden `~/.claude/tasks/` while
# holding its count. Occurrence granularity, not line granularity.
ARM1_KEY = re.compile(r"(?:~|\$HOME|\$\{HOME\})/\.claude/[^\s`\"'),*]*")

# ARM 1 stops at `.claude/` and is therefore blind to a BARE config root with
# no path after it - `cd ~/.claude`, `CONFIG=~/.claude`. ARM 3 closes that.
# The exclusion set is the whole design and each character earns its place:
#   /  ARM 1's job, and firing here too would double-count
#   `  the `{config_dir}` definition sentence writes a trailing backticked
#      `~/.claude`; without this, every carrier of that sentence needs a triple
#   }  the migrated shell form ends `$HOME/.claude}` - WITHOUT THIS, ARM 3 REDS
#      ON CORRECTLY MIGRATED CODE, the same trap as ARM 1's lookahead
#   \w and -  `.claude-zai`, `.claudex` are OTHER installs, not this root
# Measured on the migrated tree: 0 occurrences, so this costs no allowlist
# entries. It can acquire them if someone writes a bare root deliberately.
ARM3 = re.compile(r"(?:~|\$HOME|\$\{HOME\})/\.claude(?![/`\w}-])")

# Targeted pin on known sites — NOT a class gate. Misses single-quoted
# '.claude', Path.home().joinpath(".claude"), os.path.expanduser("~/.claude"),
# and Path("~/.claude").expanduser(). Do not read it as covering the class.
ARM2 = re.compile(r"Path\.home\(\)\s*/\s*\"\.claude\"")

_DB_PIN = (
    "pact-memory DB, default-root-pinned by design at "
    "skills/pact-memory/scripts/config.py:186 (#1410)"
)
_DB_PIN_MIRRORED = (
    _DB_PIN + " — MIRRORED PAIR: this is the one allowlist entry with a SECOND "
    "mechanical detector. scripts/verify-protocol-extracts.sh reds if a future "
    "editor migrates one half without the other, so the count is not the sole "
    "guard here."
)
_TELEGRAM = (
    "a default-root-pinned code counterpart exists at telegram/config.py:35 "
    "(CONFIG_DIR = Path.home() / '.claude' / 'pact-telegram'). Migrating these "
    "would write the .env where the server never reads it."
)

# (path, literal, count, justification). The count closes the hole in BOTH
# directions: a new site pushes it above declared, a removed site drops it
# below, so a stale entry reds instead of outliving its reason.
ARM1_ALLOWLIST = [
    ("commands/telegram-setup.md", "~/.claude/pact-telegram", 2, _TELEGRAM),
    ("commands/telegram-setup.md", "~/.claude/pact-telegram/.env", 6, _TELEGRAM),
    ("protocols/pact-protocols.md", "~/.claude/pact-memory/memory.db", 1, _DB_PIN_MIRRORED),
    ("protocols/pact-state-recovery.md", "~/.claude/pact-memory/memory.db", 1, _DB_PIN_MIRRORED),
    ("skills/pact-memory/SKILL.md", "~/.claude/pact-memory/memory.db", 2, _DB_PIN),
    ("skills/pact-memory/scripts/cli.py", "~/.claude/pact-memory/...", 1,
     "illustrative, no consumer — a stderr-scrubbing comment. NOT 'pact-memory, "
     "by design': that reason is false here and would license the next bare "
     "pact-memory tail that DOES have a consumer."),
    ("skills/pact-memory/scripts/config.py", "~/.claude/pact-memory", 1, _DB_PIN),
    ("skills/pact-memory/scripts/database.py", "~/.claude/pact-memory/memory.db", 1, _DB_PIN),
]

ARM2_ALLOWLIST = [
    ("skills/pact-memory/scripts/config.py", 186, _DB_PIN),
    ("skills/pact-memory/scripts/pact_session.py", 48,
     "the resolver contract's mandated $HOME/.claude fallback — removing it "
     "breaks the contract. NOT 'unmigrated': that reads as an oversight and "
     "would invite deleting the fallback, silently reintroducing the "
     "wrong-root defect this gate exists to prevent."),
]


def _scanned_files():
    for subdir in CENSUS_DIRS:
        for path in sorted((PLUGIN_ROOT / subdir).rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            rel = path.relative_to(PLUGIN_ROOT).as_posix()
            if rel in SELF_EXCLUDED_FILES:
                continue
            yield rel, path.read_text(encoding="utf-8", errors="replace")


def _arm1_counts():
    found = {}
    for rel, text in _scanned_files():
        for match in ARM1_KEY.finditer(text):
            found[(rel, match.group(0))] = found.get((rel, match.group(0)), 0) + 1
    return found


# --------------------------------------------------------------------------
# ARM 1 — the census population


def test_arm1_finds_no_unallowlisted_config_root_literal():
    declared = {(p, lit): n for p, lit, n, _ in ARM1_ALLOWLIST}
    found = _arm1_counts()
    over = {k: (found[k], declared.get(k, 0)) for k in found if found[k] > declared.get(k, 0)}
    assert not over, (
        "LLM-facing prose hardcodes the Claude config root. Agents follow prose "
        "literally, so each of these misdirects a non-default-root install. "
        f"Migrate to `{{config_dir}}` (narrative) or "
        '`"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/..."` (shell), or add an '
        f"allowlist entry WITH a justification. found>declared: {over}"
    )


def test_arm1_allowlist_has_no_stale_entry():
    """A fixed site must red on its stale entry rather than leave a silent hole."""
    found = _arm1_counts()
    stale = {(p, lit): (found.get((p, lit), 0), n) for p, lit, n, _ in ARM1_ALLOWLIST
             if found.get((p, lit), 0) < n}
    assert not stale, (
        "Allowlist entries declare more occurrences than exist. The site was "
        f"fixed or moved; delete the entry rather than leave the hole: {stale}"
    )


def test_every_allowlist_entry_states_a_justification():
    """A wrong-but-plausible reason is more dangerous than a missing one."""
    thin = [(p, lit) for p, lit, _, why in ARM1_ALLOWLIST if len(why.strip()) < 40]
    thin += [(p, ln) for p, ln, why in ARM2_ALLOWLIST if len(why.strip()) < 40]
    assert not thin, f"allowlist entries without a real justification: {thin}"


# --------------------------------------------------------------------------
# ARM 2 — Path.home() in code


def test_arm2_finds_no_unallowlisted_home_join():
    declared = {(p, ln) for p, ln, _ in ARM2_ALLOWLIST}
    found = set()
    for subdir in CENSUS_DIRS:
        for path in sorted((PLUGIN_ROOT / subdir).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(PLUGIN_ROOT).as_posix()
            if rel in SELF_EXCLUDED_FILES:
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ARM2.search(line):
                    found.add((rel, i))
    assert not found - declared, f"undeclared Path.home()/'.claude' sites: {found - declared}"
    assert not declared - found, (
        f"stale ARM 2 entries — the site moved or was fixed: {declared - found}"
    )


def test_arm3_finds_no_bare_config_root():
    """A bare `~/.claude` with no path after it - `cd ~/.claude`, `X=~/.claude`.

    ARM 1 cannot see these: it requires a trailing slash. Measured at zero on
    the migrated tree, so there is no allowlist for this arm; if a deliberate
    bare root ever lands, add one here with a justification.
    """
    hits = [(rel, i) for rel, text in _scanned_files()
            for i, line in enumerate(text.splitlines(), 1) if ARM3.search(line)]
    assert not hits, (
        "bare config-root literal in LLM-facing prose. An agent told to `cd` "
        f"here lands in the wrong install on a non-default root: {hits}"
    )


# --------------------------------------------------------------------------
# Prose assertions


PLACEHOLDER_TOKENS = ("{team_name}", "{session_dir}", "{plugin_root}", "{config_dir}")
PAIR = ("commands/bootstrap.md", "agents/pact-orchestrator.md")


def test_placeholder_declaration_present_in_both_carriers():
    """Keyed on the TOKEN SET, never on a sentence.

    The two declarations have never been byte-identical — bootstrap says
    "use ... as literal brace-wrapped placeholders", the orchestrator says
    "contain literal ... strings" and is a markdown bullet. A substring pin on
    either phrasing matches the file it was written against and is VACUOUSLY
    SILENT on the file it exists to protect.
    """
    for rel in PAIR:
        text = (PLUGIN_ROOT / rel).read_text(encoding="utf-8")
        assert any(all(t in line for t in PLACEHOLDER_TOKENS) for line in text.splitlines()), (
            f"{rel} no longer declares the placeholder token set. Both carriers "
            "must name all four tokens together; substitution is manual textual "
            "replacement and an agent reading only one file must still learn it."
        )


def test_config_dir_is_defined_where_it_is_used():
    """Conditional on TOKEN PRESENCE, never on file-was-touched, and NOT on
    adjacency. Measured gaps across carriers run 0 to 4 and are all correct, so
    an adjacency predicate reds correct files; and a migrated file that carries
    no `{config_dir}` at all (pact-auditor.md) must pass, not fail.
    """
    undefined = []
    for rel, text in _scanned_files():
        if "{config_dir}" not in text or not rel.endswith(".md"):
            continue
        lines = text.splitlines()
        first_use = next(i for i, l in enumerate(lines, 1) if "{config_dir}" in l)
        defs = [i for i, l in enumerate(lines, 1) if "CLAUDE_CONFIG_DIR" in l]
        # ponytail: 20-line window, measured max is 4 — generous headroom, still
        # catches "defined in an unrelated section" and "never defined at all".
        if not defs or min(abs(d - first_use) for d in defs) > 20:
            undefined.append((rel, first_use, defs[:1]))
    assert not undefined, (
        "files use `{config_dir}` without defining it near first use. An agent "
        "reading the instruction cannot resolve the placeholder: " + str(undefined)
    )


# --------------------------------------------------------------------------
# Controls — every assertion shown able to fire, in all three directions


def test_control_arm1_fires_on_each_spelling():
    for spelling in ("~/.claude/x/", "$HOME/.claude/x/", "${HOME}/.claude/x/"):
        assert ARM1.search(spelling), f"ARM 1 blind to {spelling}"


def test_control_arm1_stays_quiet_on_a_different_root():
    for quiet in ("$CLAUDE_PROJECT_DIR/.claude/CLAUDE.md",  # project dir, not config root
                  "`.claude/` as a file category",           # narrative
                  "~/.claude-zai/tasks/",                    # a different install
                  "~/.claude"):                              # bare root, no path
        assert not ARM1.search(quiet), f"ARM 1 over-fires on {quiet}"


def test_control_arm1_stays_quiet_on_the_migrations_own_output():
    """The direction that is easiest to omit: the gate must not red on the cure.

    Quiet ONLY because of the `(?=/)` lookahead. If this test fails, someone
    broadened or removed it — restore it rather than allowlisting the fallout.
    """
    for cured in ("{config_dir}/tasks/{team}/{id}.json",
                  'python3 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/protocols/x.py"',
                  'python3 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/protocols/x.py'):
        assert not ARM1.search(cured), (
            f"ARM 1 reds on correctly migrated code: {cured}. The `(?=/)` "
            "lookahead is load-bearing; see the comment at its definition."
        )


def test_control_arm3_fires_on_a_bare_root():
    for bare in ("~/.claude", "cd ~/.claude", "CONFIG=$HOME/.claude", 'set "~/.claude"'):
        assert ARM3.search(bare), f"ARM 3 blind to {bare}"


def test_control_arm3_stays_quiet_on_everything_it_must_not_claim():
    for quiet in ("~/.claude/tasks/",
                  "`~/.claude`",
                  "~/.claude-zai/x", "~/.claudex",
                  'python3 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/x"',
                  '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}"'):
        assert not ARM3.search(quiet), (
            f"ARM 3 over-fires on {quiet}. Every character in its exclusion set "
            "is load-bearing; see the comment at its definition."
        )


def test_control_arm2_fires_and_discriminates():
    assert ARM2.search('Path.home() / ".claude" / "pact-memory"')
    assert not ARM2.search("get_claude_config_dir() / 'pact-memory'")


def test_control_scan_population_is_non_empty():
    """An empty walk produces zero hits, which is byte-identical to a clean
    tree. Without this, a broken CENSUS_DIRS reads as a passing gate."""
    files = list(_scanned_files())
    assert len(files) > 50, f"scan reached only {len(files)} files — walk is broken"
    assert any(ARM1_KEY.search(t) for _, t in files), (
        "no allowlisted site was reached; the walk or the pattern is dead"
    )
