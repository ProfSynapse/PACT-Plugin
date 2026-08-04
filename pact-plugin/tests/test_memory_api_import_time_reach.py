"""
Location: pact-plugin/tests/test_memory_api_import_time_reach.py

Summary: Tripwire asserting that nothing in the plugin calls into the memory API
at import time. While that holds, the collection-window gap in the test-isolation
guards is LATENT rather than live, and the conftest scrub may stay a per-test
fixture. The day this fails, the window is live and the scrub must become an
unconditional module-level scrub at conftest import.

Used by/with:
- tests/conftest.py: holds the per-test scrub whose sufficiency this guards.
- skills/pact-memory/scripts/pact_session.py: holds the PYTEST_CURRENT_TEST
  refusal, which pytest does not set during collection.

WHY THIS IS A TEST AND NOT A COMMENT. Both isolation guards are blind in the
same window: pytest sets PYTEST_CURRENT_TEST per test, around setup/call/
teardown, so it is absent while modules are imported; and a per-test fixture
cannot undo an import that already happened during collection.

AND THE CONSEQUENCE IS DESTRUCTION, NOT ONLY DISCLOSURE — STATED AT FULL
STRENGTH BECAUSE EARLIER WORDINGS HERE WERE WRONG IN DEGREE TWICE. An import-time
resolution does not leak once and stop: the id is resolved before the guards can
refuse, so **the exposure lasts FOR THE LIFE OF THE PROCESS**, not for the
collection window alone.

And the harm is not that a name is read. `clear_embedding_marker()` resolves the
SESSION-SCOPED marker path and unlinks it. It has no production caller and no CLI
surface, but any process that imports the module can call it — and "no caller" is
a different claim from "no primitive". **A wrongly created marker suppresses a
sweep; a wrongly deleted one destroys a live session's state.** So a test process
that resolves a real session id past a bypassed guard can DESTROY that session's
marker, not merely learn its name.

Nothing enters
that window today. A note asking a future reader to remember this has no failure
mode; this test has exactly one, and it is loud.

BOUND, AND IT IS THE REASON THE ANSWER IS "LATENT" AND NOT "IMPOSSIBLE": the
scan resolves calls BY NAME. An alias, a getattr, or a dynamic import evades it.
Treat a pass as evidence about the code as written, not as a proof of absence.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Names that mean "the memory API". Reaching any of these at import time is what
# would make the collection window live.
_MEMORY_API_NAMES = frozenset({
    "PACTMemory",
    "save_memory",
    "search_memories",
    "ensure_memory_ready",
    "maybe_embed_pending",
    "_ensure_ready",
    "_get_embedding_attempted_path",
    "get_session_id_from_context_file",
})

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _import_time_calls(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, name) for every call that executes at import time.

    Module scope and class bodies execute on import. So do decorator
    expressions and default-argument expressions, even though both sit
    syntactically inside a `def` — that is the case a naive "is it inside a
    function?" walk gets wrong, and it is the one most likely to hide a reach.
    """
    found: list[tuple[int, str]] = []

    def call_names(node: ast.AST) -> list[tuple[int, str]]:
        hits = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name in _MEMORY_API_NAMES:
                    hits.append((sub.lineno, name))
        return hits

    def visit(node: ast.AST, at_import_time: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # The body is deferred, but decorators and defaults are not.
                for dec in child.decorator_list:
                    found.extend(call_names(dec))
                for default in child.args.defaults + [
                    d for d in child.args.kw_defaults if d is not None
                ]:
                    found.extend(call_names(default))
                visit(child, at_import_time=False)
            elif isinstance(child, ast.ClassDef):
                for dec in child.decorator_list:
                    found.extend(call_names(dec))
                # A class body executes on import even inside a function only
                # when that function runs, so inherit the enclosing context.
                visit(child, at_import_time)
                if at_import_time:
                    for stmt in child.body:
                        if not isinstance(
                            stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                        ):
                            found.extend(call_names(stmt))
            else:
                if at_import_time:
                    found.extend(call_names(child))
                visit(child, at_import_time)

    visit(tree, at_import_time=True)
    return found


def _python_files() -> list[Path]:
    # Do NOT filter on ".worktrees": the plugin is routinely checked out inside
    # a worktree, so that filter excludes the entire population and the scan
    # passes at zero files. The non-empty control below exists because this
    # exact mistake makes the tripwire permanently and silently green.
    return [p for p in _PLUGIN_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


class TestNoImportTimeReachIntoMemoryAPI:
    def test_population_is_not_empty(self):
        """Control: a zero-file scan would pass vacuously."""
        files = _python_files()
        assert len(files) > 100, f"scan population implausibly small: {len(files)}"

    def test_walker_detects_decorator_and_default_arg_calls(self):
        """Control: the walker must catch the two cases a naive walk misses.

        Without this, a walker that treated everything inside a `def` as
        deferred would report zero for the wrong reason and the tripwire would
        be permanently green.
        """
        src = (
            "def deco(x):\n"
            "    return x\n"
            "\n"
            "@deco(PACTMemory())\n"
            "def decorated():\n"
            "    pass\n"
            "\n"
            "def defaulted(arg=save_memory()):\n"
            "    pass\n"
            "\n"
            "def deferred():\n"
            "    return PACTMemory()\n"
        )
        hits = {name for _, name in _import_time_calls(ast.parse(src))}
        assert "PACTMemory" in hits, "decorator expression not detected"
        assert "save_memory" in hits, "default-argument expression not detected"

        deferred_only = "def f():\n    return PACTMemory()\n"
        assert _import_time_calls(ast.parse(deferred_only)) == [], (
            "a function body must NOT count as import time"
        )

    def test_no_module_scope_reach_into_memory_api(self):
        """The tripwire itself. Passes at zero today.

        A failure means some module now calls the memory API at import time, so
        the collection window is live and the conftest scrub must be converted
        to an unconditional module-level scrub.
        """
        offenders = []
        for path in _python_files():
            if path.name == Path(__file__).name:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for lineno, name in _import_time_calls(tree):
                offenders.append(f"{path.relative_to(_PLUGIN_ROOT)}:{lineno} calls {name}()")

        assert offenders == [], (
            "import-time reach into the memory API detected; the collection "
            "window is now LIVE. Convert the conftest scrub to an unconditional "
            "module-level scrub. Offenders:\n  " + "\n  ".join(offenders)
        )
