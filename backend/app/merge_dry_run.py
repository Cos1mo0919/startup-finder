"""Offline, insert-only merge planning. No production connection or apply mode."""

import argparse
import hashlib
import json
import re
import sqlite3
import tempfile
from copy import deepcopy
from pathlib import Path

from sqlalchemy import Integer, UniqueConstraint, create_engine, func, select, text

from .sqlite_postgres_migration import (
    MigrationValidationError, canonical, fingerprint, key_for, source_row,
    tables_to_copy, validate_source,
)


def read_snapshot(path):
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        validate_source(db, tables_to_copy())
        return {table.name: [source_row(row, table) for row in db.execute(
            f'SELECT * FROM "{table.name}" ORDER BY ' + ",".join(
                f'"{column.name}"' for column in table.primary_key.columns
            ))] for table in tables_to_copy()}


def digest_snapshot(rows):
    digest = hashlib.sha256()
    for table in tables_to_copy():
        digest.update(table.name.encode())
        for row in sorted(rows[table.name], key=lambda item: repr(key_for(item, table))):
            digest.update(fingerprint(row, table).encode())
    return digest.hexdigest()


def name_key(name):
    return re.sub(r"[\W_]+", "", name.casefold())


def project_matches(source, target, decisions=None):
    """Only a shared evidence URL AND name identify a duplicate automatically.

    A common cohort article alone is insufficient. Similar names without a
    shared source require review; the existing target project is never changed.
    """
    def urls(data):
        result = {}
        for row in data["project_sources"]:
            result.setdefault(row["project_id"], set()).add(row["url"])
        return result

    source_urls, target_urls = urls(source), urls(target)
    mappings, matches, blockers = {}, [], []
    decisions = decisions or {}
    consumed = set()
    for row in source["projects"]:
        options = [item for item in target["projects"] if item["id"] != row["id"]
                   and name_key(item["name"]) == name_key(row["name"])]
        exact = [item for item in options if source_urls.get(row["id"], set()) & target_urls.get(item["id"], set())]
        if len(exact) == 1:
            item = exact[0]
            mappings[row["id"]] = item["id"]
            matches.append({"source_id": row["id"], "source_name": row["name"],
                            "target_id": item["id"], "target_name": item["name"],
                            "shared_urls": sorted(source_urls[row["id"]] & target_urls[item["id"]]),
                            "rule": "same_name_and_exact_source_url; retain_target; import_source_as_hidden_duplicate"})
        elif options:
            decision = decisions.get(row["id"])
            if decision is None:
                blockers.append({"type": "possible_project_duplicate", "source_id": row["id"],
                                 "source_name": row["name"], "target_ids": [item["id"] for item in options],
                                 "rule": "name_only_is_not_proof; manual_resolution_required"})
            elif decision == {"action": "keep_separate"}:
                consumed.add(row["id"])
            elif (set(decision) == {"action", "target_id"} and decision["action"] == "merge"
                  and decision["target_id"] in {item["id"] for item in options}):
                consumed.add(row["id"])
                mappings[row["id"]] = decision["target_id"]
                matches.append({"source_id": row["id"], "source_name": row["name"],
                                "target_id": decision["target_id"], "rule": "explicit_owner_decision; retain_target"})
            else:
                raise MigrationValidationError("Invalid project conflict decision")
    if consumed != set(decisions):
        raise MigrationValidationError("Decision does not correspond to a current unresolved match")
    return mappings, matches, blockers


def plan_merge(source, target, decisions=None):
    project_map, matches, blockers = project_matches(source, target, decisions)
    mapping, additions, tables, conflicts, remaps = {}, {}, {}, [], []
    for table in tables_to_copy():
        name = table.name
        additions[name] = []
        pk = list(table.primary_key.columns)
        integer_pk = name != "schema_migrations" and len(pk) == 1 and isinstance(pk[0].type, Integer)
        maximum = max([row[pk[0].name] for row in source[name] + target[name]], default=0) if integer_pk else 0
        occupied = {key_for(row, table): row for row in target[name]}
        unique_columns = [tuple(column.name for column in constraint.columns)
                          for constraint in table.constraints if isinstance(constraint, UniqueConstraint)]
        unique = {columns: {tuple(row[col] for col in columns): row for row in target[name]
                            if all(row[col] is not None for col in columns)} for columns in unique_columns}
        stats = {"source_rows": len(source[name]), "target_before": len(target[name]),
                 "added": 0, "duplicate_keys": 0, "exact_duplicates": 0,
                 "conflicting_rows_kept_target": 0, "remapped_integer_ids": 0}
        for original in source[name]:
            row = deepcopy(original)
            original_key = key_for(original, table)
            for column in table.columns:
                for fk in column.foreign_keys:
                    value = row[column.name]
                    if fk.column.table.name == "projects":
                        row[column.name] = project_map.get(value, value)
                    else:
                        row[column.name] = mapping.get((fk.column.table.name, (value,)), (value,))[0]
            if name == "candidates":
                row["project_ids"] = [project_map.get(value, value) for value in row["project_ids"]]
                value = row["last_run_id"]
                row["last_run_id"] = mapping.get(("runs", (value,)), (value,))[0]
            if name == "projects" and row["id"] in project_map:
                row["publication_status"] = "DUPLICATE"
                row["visible"] = False
                row["publication_reason"] = "migration_duplicate_preserved"
                row["status_history"].append({"action": "migration_duplicate_preserved",
                                              "previous_status": original["publication_status"],
                                              "canonical_project_id": project_map[row["id"]]})
            existing = None
            for columns, index in unique.items():
                candidate = index.get(tuple(row[col] for col in columns))
                if candidate is not None:
                    if existing is not None and key_for(existing, table) != key_for(candidate, table):
                        raise MigrationValidationError(f"Multiple unique-key targets in {name}")
                    existing = candidate
            # Integer IDs in independent stores denote unrelated observations.
            # Natural keys above take precedence; otherwise allocate a free ID.
            if existing is None and integer_pk and key_for(row, table) in occupied:
                maximum += 1
                old_id = row[pk[0].name]
                row[pk[0].name] = maximum
                stats["remapped_integer_ids"] += 1
                remaps.append({"table": name, "source_id": old_id, "planned_id": maximum})
            if existing is None:
                existing = occupied.get(key_for(row, table))
            if existing is not None:
                stats["duplicate_keys"] += 1
                mapping[(name, original_key)] = key_for(existing, table)
                differences = [col.name for col in table.columns if canonical(row[col.name]) != canonical(existing[col.name])]
                if not differences:
                    stats["exact_duplicates"] += 1
                else:
                    stats["conflicting_rows_kept_target"] += 1
                conflicts.append({"table": name, "source_key": list(original_key),
                                  "target_key": list(key_for(existing, table)), "different_fields": differences,
                                  "rule": "keep_target_unchanged; retain_source_version_in_original_snapshot",
                                  "source_fingerprint": fingerprint(original, table)})
                continue
            mapping[(name, original_key)] = key_for(row, table)
            additions[name].append(row)
            occupied[key_for(row, table)] = row
            for columns, index in unique.items():
                if all(row[col] is not None for col in columns):
                    index[tuple(row[col] for col in columns)] = row
            stats["added"] += 1
        stats["target_after"] = stats["target_before"] + stats["added"]
        if stats["source_rows"] != stats["added"] + stats["duplicate_keys"]:
            raise MigrationValidationError(f"Unaccounted source rows: {name}")
        tables[name] = stats
    report = {"mode": "offline_merge_dry_run", "production_modified": False,
              "source_digest": digest_snapshot(source), "target_digest": digest_snapshot(target),
              "tables": tables, "project_duplicates": matches, "blockers": blockers,
              "conflicts": conflicts, "integer_id_remaps": remaps,
              "protected_projects": [{"id": row["id"], "name": row["name"]} for row in target["projects"]],
              "ready_for_live_merge": not blockers, "decisions": decisions or {},
              "notes": ["Counts are an insert-only plan; the separate executor requires explicit approval of this report.",
                        "All target rows remain unchanged. Losing source versions remain in the immutable input snapshot.",
                        "Project duplicate source IDs/dates survive as hidden DUPLICATE rows; target IDs stay canonical.",
                        "Resolve blockers and approve source-conflict retention before live execution.",
                        "Live execution must recheck both digests under table locks, use one transaction and abort on any mismatch."]}
    report["totals"] = {key: sum(item[key] for item in tables.values()) for key in next(iter(tables.values()))}
    return report, additions


def simulate(target_path, target, report, additions):
    """Strictly insert on a disposable copy in ONE transaction; always rollback.

    Production execution is intentionally not exposed. No ON CONFLICT/UPDATE
    can hide a dropped row. Both counts and all original target values are checked.
    """
    with tempfile.TemporaryDirectory(prefix="izlanish-merge-") as folder:
        copy = Path(folder) / "simulation.sqlite3"
        with sqlite3.connect(f"file:{target_path.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(copy) as dst:
            src.backup(dst)
        engine = create_engine(f"sqlite:///{copy}")
        try:
            with engine.connect() as connection:
                connection.execute(text("PRAGMA foreign_keys=ON"))
                connection.commit()
                transaction = connection.begin()
                try:
                    for table in tables_to_copy():
                        for offset in range(0, len(additions[table.name]), 300):
                            connection.execute(table.insert(), additions[table.name][offset:offset + 300])
                    for table in tables_to_copy():
                        count = connection.scalar(select(func.count()).select_from(table))
                        if count != report["tables"][table.name]["target_after"]:
                            raise MigrationValidationError(f"Merge count mismatch: {table.name}")
                        actual = {key_for(row, table): fingerprint(row, table)
                                  for row in connection.execute(select(table)).mappings()}
                        for row in target[table.name] + additions[table.name]:
                            if actual.get(key_for(row, table)) != fingerprint(row, table):
                                raise MigrationValidationError(f"Merge value mismatch: {table.name}")
                    if connection.execute(text("PRAGMA foreign_key_check")).fetchone():
                        raise MigrationValidationError("Merge foreign key check failed")
                finally:
                    transaction.rollback()
            if digest_snapshot(read_snapshot(copy)) != report["target_digest"]:
                raise MigrationValidationError("Simulation rollback failed")
        finally:
            engine.dispose()
    return {"passed": True, "transaction_rolled_back": True, "all_target_rows_unchanged": True,
            "counts_and_values_verified": True, "foreign_keys_verified": True,
            "backend": "temporary_sqlite; PostgreSQL merge not executed"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, help="Explicit owner decisions; never inferred from name alone")
    args = parser.parse_args(argv)
    source, target = read_snapshot(args.source), read_snapshot(args.target_snapshot)
    decisions = json.loads(args.decisions.read_text()) if args.decisions else None
    report, additions = plan_merge(source, target, decisions)
    report["simulation"] = simulate(args.target_snapshot, target, report, additions)
    # Refuse overwriting an existing report or either input file.
    with args.report.open("x") as output:
        json.dump(canonical(report), output, ensure_ascii=False, indent=2)
    print(json.dumps(report["totals"], indent=2))
    print(f"Report: {args.report}. Unresolved project matches: {len(report['blockers'])}. No live writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
