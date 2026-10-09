# v3.1 pre-migration backup

Before any v3.1 migration, the local SQLite database was backed up to
`/tmp/izlanish-v31-pre-migration.sqlite3` using `sqlite3.Connection.backup`.
`PRAGMA integrity_check` returned `ok`. The backup is outside Git and this
execution environment; copy it to durable private storage if it must survive
workspace replacement.

Stop the backend and scheduler before restoring. Then, from the repository root,
run exactly:

```bash
.venv/bin/python -c 'import sqlite3; source=sqlite3.connect("/tmp/izlanish-v31-pre-migration.sqlite3"); target=sqlite3.connect("data/finder.sqlite3"); source.backup(target); target.close(); source.close()'
```

The backup API replaces the database contents, including rows that may have
been added after this snapshot. Keep any later data separately before restoring.
