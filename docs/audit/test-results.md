# Initial test record

The original v3 tests were copied into `packages/engine/tests` with imports
updated to the monorepo package. The new contract and exporter tests cover the
shared synthetic fixture, provenance rejection, rank-bound validation, stable
hashing, and atomic export. The browser validator tests cover the same fixture
and two invalid cases.

Observed on 2026-09-30 in the Linux execution environment:

```text
PYTHONPATH=packages/engine/src python -m unittest discover -s packages/engine/tests -q
Ran 94 tests ... OK

(cd apps/site && npm test)
3 tests passed, 0 failed
```

No live site request, Sites deployment, LaunchAgent registration, or production
database operation is part of this record.
