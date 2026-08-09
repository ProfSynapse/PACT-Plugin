"""Read-only instruments that inspect a pact-memory store file.

Location: pact-plugin/scripts/memory_repair/__init__.py

Every module in this package opens `sqlite3` directly. No module here
imports `cli.py` or `memory_api.py` from the pact-memory scripts package.
An import of that package EXECUTES code that creates the live store
directory, so an import is a write. These tools must run before that
package is safe to import.
"""
from __future__ import annotations
