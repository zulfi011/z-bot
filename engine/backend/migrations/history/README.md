# Migration history

The 25 steps the schema went through before the public release, from the first paper-trading table to the shared
pot. Only databases created before the release run them, to upgrade in place. A new install never does: it loads
`../schema.sql`, the same schema in one readable file. `tests/test_schema_baseline.py` checks the two match.
