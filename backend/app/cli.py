import argparse
import json
import sys
from datetime import date
from pathlib import Path
from .config import Settings
from .db import make_db
from .pipeline import Pipeline
from .registry import seed_registry
from .db import RegistrySource
from .evidence import audit_existing
from .radar_api import source_json
from sqlalchemy import select


def main():
    parser = argparse.ArgumentParser(description="Run Uzbekistan discovery once")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Allow old dates in current listings/queue; does not traverse yearly archives (use --backfill)",
    )
    parser.add_argument(
        "--inspect-url",
        "--inspect-candidate",
        help="Read candidate/project status by URL or sha256: ID without discovery",
    )
    parser.add_argument(
        "--list-candidates", action="store_true", help="List candidates with exact reasons (default: pending)"
    )
    parser.add_argument(
        "--candidate-status",
        default="pending",
        choices=["all", "queued", "pending", "rejected", "published", "error", "event", "ecosystem"],
    )
    parser.add_argument(
        "--debug-report",
        action="store_true",
        help="Export pending candidates, archive configuration and run failures without discovery or secret values",
    )
    parser.add_argument(
        "--force-sources", action="store_true", help="Manually check enabled sources regardless of frequency"
    )
    parser.add_argument(
        "--repair-archive-config",
        action="store_true",
        help="Add missing archive adapters for matching source endpoints; preserve enabled flags, existing options and health",
    )
    parser.add_argument("--seed-sources", action="store_true", help="Import missing source registry entries")
    parser.add_argument(
        "--update-sources",
        action="store_true",
        help="Explicitly apply seed configuration changes, preserving health",
    )
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--source-id")
    toggle = parser.add_mutually_exclusive_group()
    toggle.add_argument("--enable-source", action="store_true")
    toggle.add_argument("--disable-source", action="store_true")
    parser.add_argument(
        "--audit", action="store_true", help="Re-evaluate all stored project evidence and feed visibility"
    )
    parser.add_argument(
        "--backfill", action="store_true", help="Bounded archive discovery, separate run for every year"
    )
    parser.add_argument("--from-date", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--to-date", type=date.fromisoformat, default=date(2026, 9, 30))
    parser.add_argument("--report", type=Path, help="Write structured results to this JSON file")
    parser.add_argument(
        "--drain", action="store_true", help="Process durable backlog without rediscovering sources"
    )
    args = parser.parse_args()
    settings = Settings()
    engine, factory = make_db(settings.database_url)
    try:
        if args.debug_report or args.list_candidates or args.inspect_url:
            from .diagnostics import debug_report, list_candidates, inspect_candidate

            with factory() as session:
                result = (
                    debug_report(session, settings)
                    if args.debug_report
                    else list_candidates(session, args.candidate_status)
                    if args.list_candidates
                    else inspect_candidate(session, args.inspect_url)
                )
                output = json.dumps(result, ensure_ascii=False, indent=2)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(output)
                print(output)
            return 0
        if args.repair_archive_config:
            from .registry import repair_archive_config

            try:
                result = repair_archive_config(factory, settings.sources_file, args.source_id)
            except ValueError as exc:
                parser.error(str(exc))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.seed_sources or args.update_sources:
            print(
                json.dumps(
                    {"added": seed_registry(factory, settings.sources_file, update=args.update_sources)}
                )
            )
            return 0
        if args.enable_source or args.disable_source:
            if not args.source_id:
                parser.error("--source-id is required")
            with factory.begin() as session:
                source = session.get(RegistrySource, args.source_id)
                if not source:
                    parser.error("Unknown source ID")
                source.enabled = args.enable_source
            return 0
        if args.list_sources:
            with factory() as session:
                print(
                    json.dumps(
                        [source_json(s) for s in session.scalars(select(RegistrySource))],
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return 0
        if args.audit:
            audit_existing(factory, settings.evidence_min_score)
            print("Evidence and visibility updated")
            return 0
        if args.archive and not args.backfill and not args.drain:
            print(
                "--archive permits old publication dates but searches current listings only. "
                "For yearly archives use --backfill --from-date 2022-01-01 --to-date 2026-09-30. "
                "--force-sources bypasses source schedules, not archive coverage limits.",
                file=sys.stderr,
            )
        pipeline = Pipeline(settings, factory)
        pipeline.discovery.force = args.force_sources
        try:
            if args.backfill:
                from .queries import archive_windows

                results = []
                for window in archive_windows(args.from_date, args.to_date):
                    result = pipeline.run(archive=True, window=window, discover=not args.drain)
                    results.append(result)
                    print(json.dumps({"year": window[0].year, **result}, ensure_ascii=False), flush=True)
                result = {
                    "status": "partial" if any(r["status"] != "completed" for r in results) else "completed",
                    "runs": results,
                }
            else:
                result = pipeline.run(archive=args.archive, discover=not args.drain)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            pipeline.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] in ("failed", "partial") else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
