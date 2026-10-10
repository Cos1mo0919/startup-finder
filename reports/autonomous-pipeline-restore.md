# Autonomous pipeline pre-migration backup

A consistent SQLite backup was made before Stage A at
`/tmp/izlanish-autonomous-2026-10-10.sqlite3` using the SQLite backup API.
`PRAGMA integrity_check` returned `ok`; it contains 15 project rows. The file
is private to this execution environment and is not in Git. Preserve a private
copy outside the environment if long-term rollback is needed.

Stop the API and scheduler before restoring. This command replaces the current
SQLite contents, including any discoveries after the backup:

```bash
.venv/bin/python -c 'import sqlite3; source=sqlite3.connect("/tmp/izlanish-autonomous-2026-10-10.sqlite3"); target=sqlite3.connect("data/finder.sqlite3"); source.backup(target); target.close(); source.close()'
```

The previous v3.1 snapshot instructions remain in
`reports/pipeline-restore.md`. This backup is newer and is the rollback point
for the autonomous engine migration.
