#!/usr/bin/env python3
"""
Archive a CLAUDE.md pin to pact-memory and report whether its bytes arrived.

Location: pact-plugin/scripts/archive_pin.py

Summary: Single-responsibility archival step for /PACT:prune-memory. Given
the index of a pin in the `evictable_pins` list that `check_pin_caps.py
--status` emits, this script extracts that pin's block VERBATIM from
CLAUDE.md, saves it to pact-memory via the memory CLI, re-fetches the saved
record by the returned `memory_id`, and asserts that the pin block is
present in the fetched record. It emits a three-outcome verdict as JSON on
stdout and ALWAYS exits 0.

**It never deletes anything.** The eviction Edit stays with the command, so
the destructive act remains visible to the curator and to the pin_caps_gate
PreToolUse hook. This script measures; it does not decide.

    The SCRIPT never refuses -- it measures and reports.
    The COMMAND refuses, in prose, on the reported verdict.

That split is why a fail-open here does not become a fail-open DECISION. A
hook fail-open would allow the destructive Edit; a script fail-open only
produces an UNEVALUABLE that the command must handle.

Usage:
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/archive_pin.py" --index N
  python3 archive_pin.py --index 0 --db-path /tmp/test.db   # tests only

Output (stdout, JSON, ALWAYS exit 0). `outcome`, `heading` and
`claude_md_path` are present in EVERY verdict. `heading` is null only when the
pin could not be resolved at all and is NEVER derived from the requested
index; `claude_md_path` is null only when resolution itself failed:

  {"outcome": "ARCHIVED",     "heading": str, "claude_md_path": str,
   "memory_id": str, "chars": int, "contained": true}
  {"outcome": "NOT_ARCHIVED", "heading": str, "claude_md_path": str,
   "memory_id": str|null, "reason": str}
  {"outcome": "UNEVALUABLE",  "heading": str|null,
   "claude_md_path": str|null, "reason": str}

`claude_md_path` names the file THIS RUN ACTUALLY READ. It exists because
resolution can succeed on the WRONG file: the order is CLAUDE_PROJECT_DIR ->
git common-dir parent -> CWD, and a miss at any step falls through silently,
so a CLAUDE_PROJECT_DIR naming a directory with no CLAUDE.md resolves to some
other project's file and reports a confident success. The command's heading
cross-check cannot catch it -- check_pin_caps.py uses the SAME resolver, so
the listing and the archival agree on the same wrong file. Emitting the path
is what makes a wrong file visible; `resolve_claude_md` additionally REFUSES
the cross-project case outright.

Anything but ARCHIVED means the command REFUSES the eviction. NOT_ARCHIVED
and UNEVALUABLE are kept distinct because collapsing "cannot tell" into
"definitely bad" is how a two-valued validator destroys by construction.

Used by:
  - commands/prune-memory.md: invoked before the removal Edit; the verdict
    gates whether the eviction proceeds
  - tests/test_archive_pin.py

Related:
  - scripts/check_pin_caps.py -- supplies the `--index` coordinate system
  - hooks/pin_caps.py -- parse_pins / Pin, the parser this reuses
  - skills/pact-memory/scripts/cli.py -- the save/get surface, reached by
    SUBPROCESS rather than import (keeps the process boundary the rest of
    the codebase keeps, and the CLI is the tested public surface)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load pin_caps and staleness from hooks/ by explicit file path. Identical
# rationale to check_pin_caps.py: `sys.path.insert(0, hooks_dir)` would
# PREPEND, so a future hooks/types.py or hooks/json.py would shadow the
# stdlib. Spec-loading binds by path, not by name resolution; hooks_dir is
# APPENDED (not prepended) only so staleness's `from shared.claude_md_manager`
# resolves, with the stdlib retaining priority on any name collision.
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.append(str(_HOOKS_DIR))

# The memory CLI. Reached by subprocess, never imported: skills/ is a
# separate surface from scripts/, and cli.py is the tested public contract.
_MEMORY_CLI = (
    Path(__file__).resolve().parent.parent
    / "skills" / "pact-memory" / "scripts" / "cli.py"
)

# Wall-clock ceiling for a single memory-CLI call. `save` spins the embedding
# backend; a hang must surface as UNEVALUABLE (refuse, pin survives) rather
# than blocking the curator's session indefinitely.
_CLI_TIMEOUT_SECONDS = 120

# Structured archive marker, written into `entities[].type`.
#
# THIS IS A NAMED CONSTANT ON PURPOSE, and any code that SCANS for archives
# must read THIS constant rather than re-typing the literal. `entities[].type`
# is unconstrained free text -- thousands of distinct values across the store,
# with nothing validating any of them -- so the field is structured by POSITION,
# not by SCHEMA. A typo or a second copy that drifts therefore ships SILENTLY:
# the scanner returns a smaller set and raises no error. A confident undercount
# is worse than a loud failure, which is why the value is pinned by a test.
#
# The value matches the one prior archive in the store that carries a type at
# all. Adopting it rather than inventing a second value avoids forking the
# convention -- which is the whole problem this marker exists to end, and
# forking it inside the fix would be the same defect one level up.
#
# SCOPE OF WHAT THIS BUYS -- discoverability GOING FORWARD, never enumeration.
# Archives written before this ships carry no marker at all, including ones
# that were folded into an existing record rather than saved standalone. Any
# count derived by scanning for archives is a FLOOR, not a total. Do not let a
# docstring, test name, or comment claim this marker identifies pin archives
# generally; it identifies the ones written after it ships.
ARCHIVE_ENTITY_TYPE = "pact_memory_archive"

# The memory CLI subcommand archival is permitted to use. See the STANDALONE
# invariant on `_build_record` / `archive_pin`: an `update` would create no new
# record and run no marker code, silently voiding the audit property.
_ARCHIVE_SUBCOMMAND = "save"


def _load_hook_module(name: str):
    """Load a module from hooks/ by explicit file path.

    Registers the loaded module in sys.modules under `name` before executing
    so modules loaded via this same helper resolve `from {name} import ...`
    against the already-loaded object (staleness does `from pin_caps import`).
    """
    module_path = _HOOKS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_pin_caps = _load_hook_module("pin_caps")
_staleness = _load_hook_module("staleness")

parse_pins = _pin_caps.parse_pins
_PIN_HEADING_RE = _pin_caps._PIN_HEADING_RE
_parse_pinned_section = _staleness._parse_pinned_section
get_project_claude_md_path = _staleness.get_project_claude_md_path
# The (path, base) form. `base` is the directory the resolver ACTUALLY found
# the file under, captured before descending into `.claude` -- a trusted
# pre-resolve anchor rather than a re-derivation from the returned path.
_resolve_project_claude_md_with_base = (
    _staleness._resolve_project_claude_md_with_base
)
_find_existing_claude_md = _staleness._find_existing_claude_md
# Lexical inverse of the resolver's base/CLAUDE.md construction. Purely
# lexical (pathlib .parent never follows symlinks), and already locked to
# the resolver's own shape by TestStalenessLexicalBaseParity -- so it is
# the right primitive for project attribution, not a second derivation.
_lexical_base_of = _staleness._lexical_base_of


class _Unevaluable(Exception):
    """Raised when the pin's state cannot be established at all.

    Distinct from a definite archival failure. Carries an optional heading
    for the cases where the pin WAS resolved before the failure occurred.
    """

    def __init__(self, reason: str, heading: str | None = None,
                 claude_md_path: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.heading = heading
        # The file this run read, when one was resolved before the failure.
        # None only when resolution itself failed -- there is genuinely no
        # path to name, and inventing one would be worse than null.
        self.claude_md_path = claude_md_path


def _span_start(pinned_content: str, heading_start: int, date_comment) -> int:
    """Offset where a pin's span begins: its date-comment LINE, else its heading.

    Extracted so the START of pin N and the END of pin N-1 are computed by the
    SAME rule. Deriving the end from the next HEADING instead would make the
    two asymmetric and let each block swallow the following pin's date comment.
    """
    if not date_comment:
        return heading_start
    preceding = pinned_content[:heading_start]
    # rfind takes the NEAREST preceding occurrence, so an identical comment
    # string inside an earlier pin's body cannot capture the span.
    comment_at = preceding.rfind(date_comment)
    if comment_at == -1:
        return heading_start
    # Back up to that LINE's first character, so indentation is inside the span.
    return preceding.rfind("\n", 0, comment_at) + 1


def extract_pin_block(pinned_content: str, index: int, pins) -> str:
    """Return the pin's block as a VERBATIM SLICE of `pinned_content`.

    THIS IS A SLICE, NOT A RECONSTRUCTION, and the distinction is the whole
    point. Rebuilding the block as `date_comment + "\\n" + heading + "\\n" +
    body` looks equivalent but is not: `parse_pins` walks BACKWARD over blank
    lines to find the date comment and stores it `.strip()`ed, so a rebuilt
    block silently drops any blank line between comment and heading and any
    trailing whitespace on the comment line. Measured across five plausible
    hand-written pin formats, a rebuild is verbatim in only 2 of 5.

    That matters because the archival success criterion asserts containment
    of THIS string in the re-fetched record. If this string is already a
    lossy rendering of the pin, all three conjuncts still hold and the
    verdict certifies a variant -- a check reporting success while measuring
    nothing, which is the exact defect this subsystem exists to remove. A
    slice makes the criterion meaningful by making the block verbatim BY
    CONSTRUCTION, so the containment test measures the only thing it ever
    could: whether the storage round-trip preserved the bytes.

    Span rule:
      - `end`   = the NEXT PIN'S SPAN START (its date-comment line, else its
                  heading), or end of section for the last pin. NOT the next
                  `### ` heading -- see the boundary note below; an earlier
                  revision of this docstring said heading-start and a reader
                  acted on it, which is why the rule is stated once, here.
      - `start` = walk backward from the heading start over blank lines; if the
                  first non-blank preceding line matches the date-comment
                  pattern, `start` is the offset of THAT LINE'S FIRST CHARACTER
                  (so leading indentation is inside the slice); otherwise
                  `start` is the heading start.
      - Take `source[start:end]` EXACTLY. Do not strip, rejoin, or normalize.

    The no-strip rule means the block carries the blank line(s) separating it
    from the next pin. That is safe and was measured rather than assumed:
    `context` is a scalar, so it escapes the string-list normalization, and a
    value with one trailing newline, two trailing newlines, or a trailing
    newline plus spaces all round-trip BYTE-EXACT through the real CLI. Had
    any of those been stripped in transit, containment would have returned
    false for every archive -- an over-block on the whole feature.

    THE END BOUNDARY IS THE NEXT PIN'S SPAN START, NOT THE NEXT HEADING.
    Running to the next `### ` would put the FOLLOWING pin's date comment
    inside this pin's block, because a span starts at the comment line, which
    sits BEFORE the heading. The archived record would then carry another
    pin's pinned-date -- still a verbatim substring, so the containment check
    could never notice, and still "correct" by every conjunct in the criterion.
    Computing both edges with `_span_start` makes the spans partition the
    section instead of overlapping.

    Args:
        pinned_content: The Pinned Context section body (what parse_pins ate).
        index: Position of the pin within that section.
        pins: The full parsed Pin list -- the NEXT pin's date_comment is needed
            to place this pin's end boundary.

    Raises:
        _Unevaluable: if the section's headings no longer agree with `index`.
    """
    starts = [m.start() for m in _PIN_HEADING_RE.finditer(pinned_content)]
    if index < 0 or index >= len(starts) or index >= len(pins):
        raise _Unevaluable(
            f"pin index {index} out of range (section has {len(starts)} pins)"
        )

    block_start = _span_start(pinned_content, starts[index], pins[index].date_comment)
    if index + 1 < len(starts) and index + 1 < len(pins):
        block_end = _span_start(
            pinned_content, starts[index + 1], pins[index + 1].date_comment
        )
    else:
        block_end = len(pinned_content)

    return pinned_content[block_start:block_end]


def _same_repository(env_dir: Path, base: Path) -> bool:
    """True when `base` is the main repo of the git checkout at `env_dir`.

    The discriminator between a LEGITIMATE fall-through and a wrong-project
    one. PACT's own primary workflow sets CLAUDE_PROJECT_DIR to a WORKTREE,
    where CLAUDE.md is gitignored and therefore absent; the resolver's
    git-common-dir step then finds the MAIN repo's file, which is the correct
    and intended answer. A blanket "env dir has no CLAUDE.md -> refuse" rule
    would break that flow on every invocation -- a cardinal over-block.
    Measured: this worktree has no CLAUDE.md and the main checkout does.

    So the question is not "did we fall through" but "did we fall through to
    somewhere that is still the same project". `--git-common-dir` answers it:
    every worktree of a repo shares one common dir, so its parent is the main
    root for both the worktree and the main checkout.

    Fail-safe: any git error, timeout, or non-repo directory returns False,
    which routes to a REFUSAL. On a destructive path declining to guess is the
    safe direction -- refusing costs a recoverable UNEVALUABLE, while guessing
    wrong archives and evicts from a project nobody named.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(env_dir), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    if result.returncode != 0 or not result.stdout.strip():
        return False
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = Path(env_dir) / common_dir
    try:
        return common_dir.resolve().parent == Path(base).resolve()
    except OSError:
        return False


def resolve_claude_md():
    """Resolve the CLAUDE.md to operate on, refusing a cross-project fallback.

    Returns (path, base). RAISES `_Unevaluable` rather than silently operating
    on a file the invocation never named.

    THE DEFECT THIS CLOSES. Resolution order is CLAUDE_PROJECT_DIR -> git
    common-dir parent -> CWD, and a miss at any step falls through SILENTLY.
    So CLAUDE_PROJECT_DIR naming a directory with no CLAUDE.md does not fail --
    it resolves to a DIFFERENT project's file and reports a confident success.
    Reproduced deliberately: with the env var naming project_b and the CWD in
    project_a, the resolver returns project_a's CLAUDE.md.

    Step 3's heading cross-check cannot see this. `check_pin_caps.py` uses the
    SAME resolver, so the listing step and the archival step agree on the same
    wrong file and every heading matches. That check catches an index shift
    WITHIN a file; nothing catches a wrong FILE.

    THE REFUSAL IS NARROW BY CONSTRUCTION. It fires only when
    CLAUDE_PROJECT_DIR is explicitly set, names a directory with no CLAUDE.md,
    AND the resolver landed outside that directory's own repository. The
    worktree fall-through -- the case PACT itself depends on -- stays inside
    the same repository and is allowed through.
    """
    # Resolve through `get_project_claude_md_path` -- the seam the rest of the
    # suite already patches -- and derive the base LEXICALLY from the result,
    # rather than taking the with-base form directly. Same answer in
    # production (the with-base call is what this wraps), but it keeps one
    # resolution seam for the whole codebase instead of introducing a second
    # that fixtures would have to know about separately.
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    path = get_project_claude_md_path()
    if path is None:
        raise _Unevaluable("CLAUDE.md not found")
    base = _lexical_base_of(path)

    if env_dir:
        env_path = Path(env_dir)
        if (_find_existing_claude_md(env_path) is None
                and not _same_repository(env_path, base)):
            raise _Unevaluable(
                f"CLAUDE_PROJECT_DIR={env_dir} contains no CLAUDE.md, and "
                f"resolution fell through to {path} in a different project. "
                f"Refusing rather than archiving a pin the invocation never "
                f"named. Set CLAUDE_PROJECT_DIR to the project that owns the "
                f"pin, or unset it to resolve from the working directory."
            )
    return path, base


def project_dir_for(claude_md: Path) -> Path:
    """Return the project directory that owns `claude_md`.

    CLAUDE.md lives at either `<project>/.claude/CLAUDE.md` (preferred) or
    `<project>/CLAUDE.md` (legacy), so the project root is one or two levels
    up depending on which form resolved.

    This is the INVERSE of `shared.claude_md_manager.resolve_project_claude_md_path`
    (project dir -> CLAUDE.md); no existing helper goes this direction, which
    is why it is defined here rather than reused. The two-layout knowledge is
    owned by that module's `_DOT_CLAUDE_RELATIVE` / `_LEGACY_RELATIVE`; if a
    THIRD location is ever supported, this function must be swept too. It is
    deliberately NOT a sixth CLAUDE.md resolver -- it never probes the
    filesystem for CLAUDE.md, it only maps a path already resolved by one of
    the five, so `test_claude_md_resolver_parity.py` does not cover it.

    This is load-bearing for WHERE the archived pin is filed. The memory
    layer detects `project_id` from CLAUDE_PROJECT_DIR, else from git, else
    by walking UP from the CWD to the nearest project marker -- and `.claude`
    IS such a marker. So running the memory CLI from the plugin's own
    directory files a consumer's archived pin under project `.claude`
    (measured), because the installed plugin lives beneath `~/.claude/`.
    Deriving the CWD from the CLAUDE.md we actually read keeps the pin and
    its archive agreeing on the project by construction.
    """
    parent = claude_md.resolve().parent
    return parent.parent if parent.name == ".claude" else parent


def _run_memory_cli(args, db_path=None, stdin_data=None, cwd=None):
    """Invoke the memory CLI and return (returncode, stdout, stderr).

    STREAMS ARE KEPT SEPARATE AND MUST STAY THAT WAY. `save` writes an
    embedding progress bar (`Fetching 10 files: ...`) to STDERR on SUCCESS
    -- measured at ~130 bytes -- so merging the streams would splice that
    bar into the JSON envelope and corrupt every parse. Never `2>&1` here.

    Errors also go to stderr (cli.py's `_error`), which is why a failed call
    presents as EMPTY STDOUT: NOT_FOUND, PREFIX_TOO_SHORT and an outright
    crash are indistinguishable on stdout alone. The caller must classify
    from the stderr envelope, whose key is `error` (NOT `error_type`).

    Raises:
        _Unevaluable: if the CLI is missing, hangs, or cannot be launched.
    """
    if not _MEMORY_CLI.exists():
        raise _Unevaluable(f"memory CLI not found at {_MEMORY_CLI}")

    argv = [sys.executable, str(_MEMORY_CLI), *args]
    if db_path:
        argv += ["--db-path", db_path]

    # Pin the project for the child process. CLAUDE_PROJECT_DIR is the memory
    # layer's PRIMARY detection strategy and is deterministic, unlike the git
    # and CWD-walk fallbacks. An existing value is the platform's own
    # statement of the project and is left alone; we only fill the gap.
    env = None
    if cwd is not None:
        env = dict(os.environ)
        env.setdefault("CLAUDE_PROJECT_DIR", str(cwd))

    try:
        proc = subprocess.run(
            argv,
            input=stdin_data,
            capture_output=True,   # separate pipes -- NOT merged
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
            # CWD is the PROJECT that owns the pin, never the plugin's own
            # directory -- see project_dir_for(). #935 residual: an unpinned
            # CWD silently files the archive under the wrong project.
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise _Unevaluable(
            f"memory CLI timed out after {_CLI_TIMEOUT_SECONDS}s"
        )
    except OSError as exc:
        raise _Unevaluable(f"could not launch memory CLI: {type(exc).__name__}")

    return proc.returncode, proc.stdout, proc.stderr


def _parse_envelope(stdout: str):
    """Parse a success envelope from stdout, or return None.

    Returns the `result` payload on a well-formed `{"ok": true, ...}`
    envelope. Returns None for empty stdout, malformed JSON, or ok=false --
    all of which the caller must treat as "the call did not succeed",
    classifying the reason from stderr rather than from this absence.
    """
    if not stdout.strip():
        return None
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(envelope, dict) or not envelope.get("ok"):
        return None
    return envelope.get("result")


def _classify_cli_error(stderr: str) -> str:
    """Render a short reason from the memory CLI's stderr error envelope.

    The envelope key is `error` (NOT `error_type`). Falls back to a trimmed
    raw stderr when the payload is not a parseable envelope -- a crash
    traceback still tells the curator more than a bare "failed" would.
    """
    text = stderr.strip()
    if not text:
        return "memory CLI failed with no diagnostic output"
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("error"):
            message = payload.get("message", "")
            return f"{payload['error']}: {message}".strip().rstrip(":")
    except json.JSONDecodeError:
        pass
    return text.splitlines()[-1][:300]


def _build_record(block: str, heading: str) -> dict:
    """Build the pact-memory record for an archived pin.

    THE PIN BODY GOES IN `context`, AND NEVER IN A LIST FIELD. This is a
    prohibition, not a preference. String-list fields (lessons_learned,
    reasoning_chains, ...) `.strip()` and NFC-normalize their items, so a
    pin stored there comes back ALTERED and the containment check returns
    FALSE for a perfectly good archive -- an OVER-BLOCK that refuses a
    legitimate eviction, which is the cardinal error direction here.
    Scalars escape that normalization and round-trip byte-exact.

    This is not hypothetical: the one pin-archive record already in the
    store asserts "Content preserved verbatim" while holding its content in
    `lessons_learned`, a field that cannot deliver that guarantee.

    `entities` carries the curation tags; `goal` carries the orienting
    label. Curation and verbatim occupy DIFFERENT columns, so a queryable
    archive and byte-exact preservation coexist with no trade-off.

    STANDALONE ONLY. This record is always CREATED, never merged into an
    existing one. The invariant is load-bearing rather than incidental: an
    additive `update` creates no new record and runs no marker code, so a
    folded archive is invisible to a marker scan -- which has already happened
    to prior demotions. A future maintainer adding a fold path for a good
    reason (dedup, retrieval quality) would void the audit property WITHOUT
    TOUCHING THIS FUNCTION, and nothing would fail at runtime; the symptom is a
    missing record in somebody's later audit. If a fold path is ever genuinely
    wanted, write the marker on the update path too, or withdraw the
    auditability claim in the same change.
    """
    archived_on = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "context": block,
        "goal": f"Archived pin: {heading}",
        "entities": [{
            "name": heading,
            "type": ARCHIVE_ENTITY_TYPE,
            "notes": (
                f"demoted from CLAUDE.md Pinned Context on {archived_on}"
            ),
        }],
    }


def archive_pin(index: int, db_path=None) -> dict:
    """Archive the pin at `index` and return a verdict dict.

    Sequence: resolve CLAUDE.md -> parse pins -> slice the block verbatim ->
    save -> re-fetch by the returned memory_id -> assert containment.

    Raises:
        _Unevaluable: whenever the pin's state cannot be established.
    """
    # Refuses a cross-project fall-through rather than silently operating on
    # a file the invocation never named. `resolved_base` is the resolver's own
    # trusted anchor, used for the archive's project attribution instead of
    # re-deriving it from the leaf path (which followed symlinks).
    claude_md, resolved_base = resolve_claude_md()
    # Every verdict from here on names the file actually read, so a wrong-file
    # resolution is visible rather than silent.
    claude_md_path = str(claude_md)

    try:
        content = claude_md.read_text(encoding="utf-8")
    except (IOError, OSError, UnicodeDecodeError) as exc:
        raise _Unevaluable(f"CLAUDE.md unreadable ({type(exc).__name__})",
                           claude_md_path=claude_md_path)

    parsed = _parse_pinned_section(content)
    if parsed is None:
        raise _Unevaluable("no Pinned Context section",
                           claude_md_path=claude_md_path)

    _, _, pinned_content = parsed
    try:
        pins = parse_pins(pinned_content)
    except Exception as exc:  # noqa: BLE001 -- parse fault is unevaluable
        raise _Unevaluable(f"pin parse failed ({type(exc).__name__})",
                           claude_md_path=claude_md_path)

    if index < 0 or index >= len(pins):
        raise _Unevaluable(
            f"pin index {index} out of range ({len(pins)} pins parsed)",
            claude_md_path=claude_md_path,
        )

    pin = pins[index]
    # The pin's ACTUAL heading, read from the parse. Never echoed back from
    # the requested index: the caller cross-checks this value against the
    # curator's selection to catch an index shift between listing and
    # archival, and an echo would make that check compare the index against
    # itself and pass unconditionally.
    heading = pin.heading[4:] if pin.heading.startswith("### ") else pin.heading

    block = extract_pin_block(pinned_content, index, pins)
    if not block.strip():
        raise _Unevaluable("pin block is empty", heading=heading,
                           claude_md_path=claude_md_path)

    # Source-side tripwire. The slice makes this true BY CONSTRUCTION, so it
    # costs nothing in the normal case -- it exists to fail loudly if the
    # extractor ever regresses into a lossy rebuild. Checked BEFORE the save,
    # so a broken extractor writes nothing.
    if block not in content:
        raise _Unevaluable(
            "extracted block is not verbatim in CLAUDE.md (extractor bug)",
            heading=heading, claude_md_path=claude_md_path,
        )

    # --- conjunct 1: save returned a memory_id -----------------------------
    # Passed on STDIN rather than argv: the record embeds arbitrary curator
    # text, and an argv-borne payload would be bounded by ARG_MAX and would
    # surface the pin body in the process table.
    project_dir = resolved_base
    payload = json.dumps(_build_record(block, heading))
    # STANDALONE: always `save` (create), never `update` (fold). See
    # _build_record -- a fold runs no marker code and is invisible to an
    # archive scan.
    _, stdout, stderr = _run_memory_cli(
        [_ARCHIVE_SUBCOMMAND, "--stdin"], db_path=db_path, stdin_data=payload,
        cwd=project_dir,
    )
    result = _parse_envelope(stdout)
    memory_id = result.get("memory_id") if isinstance(result, dict) else None
    if not memory_id:
        # A definite failure of the save itself: the store was reachable and
        # said no. NOT_ARCHIVED, not UNEVALUABLE.
        return {
            "outcome": "NOT_ARCHIVED",
            "heading": heading,
            "claude_md_path": claude_md_path,
            "memory_id": None,
            "reason": f"save returned no memory_id -- {_classify_cli_error(stderr)}",
        }

    # --- conjunct 2: the record is retrievable by that id ------------------
    _, stdout, stderr = _run_memory_cli(
        ["get", memory_id], db_path=db_path, cwd=project_dir
    )
    fetched = _parse_envelope(stdout)
    if not isinstance(fetched, dict):
        # The id came back but the record will not re-read. We cannot tell
        # whether the bytes are safe, so we must not claim they are -- and we
        # must not claim they are lost either.
        raise _Unevaluable(
            f"saved as {memory_id} but re-fetch failed -- "
            f"{_classify_cli_error(stderr)}",
            heading=heading, claude_md_path=claude_md_path,
        )

    # --- conjunct 3: the pin block is present AT THE DESTINATION -----------
    # SUBSTRING, never equality. `context` may legitimately carry more than
    # the block (a provenance preamble, say), and an equality assertion would
    # return false for a correct archive -- an over-block in the one control
    # whose entire purpose is not destroying content.
    #
    # This is the conjunct the old criterion lacked. A returned memory_id
    # proves a record EXISTS (persistence); only this proves the record
    # carries the PIN (fidelity). The founding data loss satisfied the former
    # at the moment it occurred.
    context = fetched.get("context")
    if not isinstance(context, str) or block not in context:
        return {
            "outcome": "NOT_ARCHIVED",
            "heading": heading,
            "claude_md_path": claude_md_path,
            "memory_id": memory_id,
            "reason": (
                "saved record does not contain the pin block verbatim "
                "(fidelity check failed)"
            ),
        }

    return {
        "outcome": "ARCHIVED",
        "heading": heading,
        "claude_md_path": claude_md_path,
        "memory_id": memory_id,
        "chars": len(block),
        "contained": True,
    }


def build_verdict(index: int, db_path=None) -> dict:
    """Run the archival and return a verdict dict — never raises.

    The single place where an unevaluable state becomes an UNEVALUABLE
    verdict, so `main` only has to serialize. Keeping the mapping here
    (rather than inline in `main`) is what lets tests exercise the
    degradation paths without going through argv and stdout.
    """
    try:
        return archive_pin(index, db_path=db_path)
    except _Unevaluable as exc:
        return {
            "outcome": "UNEVALUABLE",
            "heading": exc.heading,
            "claude_md_path": exc.claude_md_path,
            "reason": exc.reason,
        }
    except Exception as exc:  # noqa: BLE001 -- never crash the curator's flow
        return {
            "outcome": "UNEVALUABLE",
            "heading": None,
            "claude_md_path": None,
            "reason": f"internal error: {type(exc).__name__}",
        }


def main(argv=None) -> int:
    """Entry point. ALWAYS returns 0; the verdict is carried in-band."""
    parser = argparse.ArgumentParser(
        prog="archive_pin",
        description=(
            "Archive one CLAUDE.md pin to pact-memory and report, "
            "mechanically, whether its bytes arrived."
        ),
    )
    parser.add_argument(
        "--index",
        type=int,
        required=True,
        help="Position of the pin in check_pin_caps --status evictable_pins",
    )
    parser.add_argument("--db-path", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    verdict = build_verdict(args.index, db_path=args.db_path)
    sys.stdout.write(json.dumps(verdict) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
