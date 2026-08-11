"""Read-only instruments that inspect a pact-memory store file.

Location: pact-plugin/scripts/memory_repair/__init__.py

Each module here opens `sqlite3` directly and imports nothing from the
pact-memory scripts package. Keep each module here, and each module added
later, free of an import from that package. In that package, functions create
the live store directory as a side result of a path resolution, so an import
puts each of them one call away. This rule holds so that nobody must audit
which call is safe. Do not read an absent import as a guarantee, because a
subprocess reaches those functions with no import at all. These tools depend
on nothing from that package, so they run without it.
<!-- PACT_STORE_BAR_BEGIN -->
**STORE ACCESS.** A memory operation (save, search, get, list, update or
delete a record) goes through the pact-memory CLI. DO NOT USE `--db-path`,
for one verb or for one purpose. YOU DO NOT SELECT A STORE. A path you
choose is not the store the memory of the team lives in, so a save there is
lost rather than shared. STORE INSPECTION is different: a row count, a
column audit, a schema check, or any question about the file itself. To
inspect, do not run a CLI verb, do not import a module below
`skills/pact-memory/scripts/`, and do not open the store read-write. Check
that `memory.db-wal` and `memory.db-shm` are both absent by their full
names, then open the store with `mode=ro` and `immutable=1`. Without
`immutable=1` the open fails. If a sidecar is present, stop and report.
<!-- PACT_STORE_BAR_END -->
The `pact-memory` skill carries the full rule.
"""
from __future__ import annotations
