"""
Location: pact-plugin/hooks/shared/failure_cause.py
Summary: Render a caught exception as a CLOSED-VOCABULARY cause token that
         cannot carry a filesystem path.
Used by: every producer whose return value session_init routes into
         system_messages on a substring test -- shared/session_resume.py,
         shared/claude_md_manager.py, shared/symlinks.py and staleness.py.

WHY THIS IS ITS OWN MODULE. The six routed status producers live in four
files at three levels of the import graph. `session_resume` and `staleness`
import `claude_md_manager`, so `claude_md_manager` cannot import back from
them, and `symlinks` imports neither. A single definition therefore needs a
module BELOW all four. Duplicating the predicate instead would give each
copy its own drift.
"""

from __future__ import annotations

import errno

# Bound for the exception class name. Follows the convention of bounding
# every interpolated value. It is NOT a security control -- a class name in
# this population is a stdlib constant, not caller data.
_CAUSE_NAME_LIMIT = 40


def failure_cause(exc: BaseException) -> str:
    """Render a file-layer failure as a CLOSED-VOCABULARY cause token.

    Returns the exception class name, plus the symbolic errno name in
    parentheses when the exception carries a mapped integer errno:
    `PermissionError (EACCES)`, `OSError (ENOSPC)`, or a bare
    `UnicodeDecodeError`. No rendering in this population contains "/".

    BUILD THIS STRING FROM A CLOSED VOCABULARY. Do NOT interpolate
    `str(exc)` or `exc.args`. MEASURED: an exception message can carry a
    path with NO filename attribute behind it --
    `OSError("bare message with a path in it")` has `filename is None` and
    `errno is None` while its `str()` carries the path. So stripping the
    filename attribute, or filtering the message for that attribute's
    value, leaves the leak open. The repair is to read the caller's message
    NOT AT ALL, which is why this helper takes nothing from it.

    A LENGTH BOUND IS NOT A REPAIR EITHER, AND THAT IS MEASURED TOO. A cut
    keeps the LEADING characters, and an OSError renders as
    `[Errno NN] <strerror>: '<path>'`, so the path survives every cut wide
    enough to be useful. A short cut only narrows the shapes that leak: at
    20 characters a 13-character strerror hides the path and a
    1-character strerror does not.

    THE CLASS NAME IS THE TOTAL PART, THE ERRNO SYMBOL IS OPTIONAL.
    UnicodeDecodeError and UnicodeEncodeError carry no errno, and a
    platform can leave a code unmapped in `errno.errorcode`.

    TOTAL BY CONSTRUCTION, AND THAT IS LOAD-BEARING. Each caller runs this
    INSIDE a handler arm, so a raise here would escape to an outer handler
    and reach the caller. `type(exc).__name__` cannot fail, `getattr` with
    a default cannot raise, and `dict.get` on an int cannot raise.
    """
    name = type(exc).__name__[:_CAUSE_NAME_LIMIT]
    code = getattr(exc, "errno", None)
    symbol = errno.errorcode.get(code) if isinstance(code, int) else None
    return f"{name} ({symbol})" if symbol else name
