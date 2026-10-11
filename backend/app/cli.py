import argparse
import json
import sys
from datetime import date
from pathlib import Path
from .config import Settings
from .db import make_db
from .catalog_pipeline import CatalogPipeline
from .registry import seed_registry
from .db import RegistrySource, SourceBlock
from .evidence import audit_existing
from .radar_api import source_json
from sqlalchemy import select


def main():
    parser = argparse.ArgumentParser(description="Run izlanish discovery once")
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
    parser.add_argument("--inspect-raw", help="Inspect raw discovery by numeric ID or URL")
    parser.add_argument(
        "--list-candidates", action="store_true", help="List candidates with exact reasons (default: pending)"
    )
    parser.add_argument(
        "--candidate-status",
        default="pending",
        choices=["all", "queued", "pending", "review_required", "rejected", "published", "problem", "error", "event", "ecosystem"],
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
    parser.add_argument("--reanalyze-problems", action="store_true", help="Recheck stored projects against cached source quotes")
    parser.add_argument("--reclassify-candidates", action="store_true", help="Queue a bounded batch of rejected candidates for the current classifier")
    parser.add_argument("--reclassify-url", help="Reprocess one stored candidate URL with current rules, without fetching sources")
    parser.add_argument("--process-url", help="Fetch and process one public URL from an enabled registered source")
    parser.add_argument("--local-problems", action="store_true", help="Run due Uzbekistan local problem scan")
    parser.add_argument("--global-trends", action="store_true", help="Run due monthly cross-country problem scan")
    parser.add_argument("--source-id")
    parser.add_argument("--only-source", help="Check only one enabled source during discovery")
    toggle = parser.add_mutually_exclusive_group()
    toggle.add_argument("--enable-source", action="store_true")
    toggle.add_argument("--disable-source", action="store_true")
    toggle.add_argument("--block-source", action="store_true", help="Disable a single source ID with audit reason")
    toggle.add_argument("--restore-source", action="store_true", help="Restore a previously blocked source ID")
    parser.add_argument("--block-reason", default="")
    parser.add_argument(
        "--audit", action="store_true", help="Re-evaluate all stored project evidence and feed visibility"
    )
    parser.add_argument(
        "--backfill", action="store_true", help="Bounded archive discovery, separate run for every year"
    )
    parser.add_argument("--from-date", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--to-date", type=date.fromisoformat, default=date(2026, 9, 30))
    parser.add_argument("--report", type=Path, help="Write structured results to this JSON file")
    parser.add_argument("--llm-live-eval", action="store_true", help="Explicit live-provider benchmark on saved sources")
    parser.add_argument("--llm-smoke", action="store_true", help="One explicit live-provider schema check on a saved source")
    parser.add_argument("--autonomous-audit", action="store_true", help="Read-only baseline, yield and sample audit")
    parser.add_argument(
        "--drain", action="store_true", help="Process durable backlog without rediscovering sources"
    )
    parser.add_argument("--reprocess-review", action="store_true",
                        help="Bounded recheck of legacy pending/review candidates from cached text")
    parser.add_argument("--recheck-noise", action="store_true",
                        help="Bounded conservative noise recheck for existing review rows")
    args = parser.parse_args()
    settings = Settings()
    engine, factory = make_db(settings.database_url)
    try:
        if args.recheck_noise:
            from .raw_discovery import recheck_obvious_noise
            result = recheck_obvious_noise(factory, limit=max(500, settings.max_candidates))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.autonomous_audit:
            from .autonomous_audit import audit
            result = audit(factory)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.llm_live_eval or args.llm_smoke:
            from .catalog_eval import evaluate, smoke
            result = smoke(settings, factory) if args.llm_smoke else evaluate(settings, factory)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "completed" or (
                args.llm_live_eval and result["status"] == "llm_unavailable") else 1
        if args.debug_report or args.list_candidates or args.inspect_url or args.inspect_raw:
            from .diagnostics import debug_report, list_candidates, inspect_candidate, inspect_raw

            with factory() as session:
                result = (
                    debug_report(session, settings)
                    if args.debug_report
                    else list_candidates(session, args.candidate_status)
                    if args.list_candidates
                    else inspect_raw(session, args.inspect_raw)
                    if args.inspect_raw
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
        if args.enable_source or args.disable_source or args.block_source or args.restore_source:
            if not args.source_id:
                parser.error("--source-id is required")
            if args.block_source and not args.block_reason.strip():
                parser.error("--block-reason is required")
            with factory.begin() as session:
                source = session.get(RegistrySource, args.source_id)
                if not source:
                    parser.error("Unknown source ID")
                if args.restore_source:
                    last = session.scalar(select(SourceBlock).where(SourceBlock.source_id == source.id)
                                          .order_by(SourceBlock.id.desc()))
                    if not last or last.action != "BLOCK":
                        parser.error("Source is not blocked")
                if args.enable_source:
                    last = session.scalar(select(SourceBlock).where(SourceBlock.source_id == source.id)
                                          .order_by(SourceBlock.id.desc()))
                    if last and last.action == "BLOCK":
                        parser.error("Source is blocked; use --restore-source")
                source.enabled = args.enable_source or args.restore_source
                if args.block_source or args.restore_source:
                    session.add(SourceBlock(source_id=source.id, action="BLOCK" if args.block_source else "RESTORE",
                                            actor="cli_admin", reason=args.block_reason or "operator_restore"))
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
        if args.reanalyze_problems:
            from .intelligence import migrate_existing_problems

            migrate_existing_problems(factory)
            print("Stored project problem gates rechecked")
            return 0
        if args.reclassify_candidates:
            from .db import Candidate

            with factory.begin() as session:
                rows = session.scalars(select(Candidate).where(
                    Candidate.status == "rejected", Candidate.processing_version < 6
                ).order_by(Candidate.updated_at).limit(settings.max_candidates)).all()
                for row in rows:
                    row.status = "queued"
                    row.processing_version = 6
            print(json.dumps({"queued_for_reclassification": len(rows)}))
            return 0
        if args.reclassify_url:
            from .db import Candidate
            from .network import canonical_url

            url = canonical_url(args.reclassify_url)
            with factory() as session:
                if session.get(Candidate, url) is None:
                    parser.error("Candidate URL not stored")
            pipeline = CatalogPipeline(settings, factory)
            try:
                result = pipeline.run(archive=True, discover=False, only_urls=[url])
            finally:
                pipeline.close()
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in ("completed", "partial") else 1
        if args.process_url:
            from .db import Candidate
            from .network import FetchError, canonical_url
            from .registry import source_for_url

            try:
                url = canonical_url(args.process_url)
            except FetchError as exc:
                parser.error(str(exc))
            with factory.begin() as session:
                source = source_for_url(session, url)
                if source is None or not source.enabled or source.collection_method == "search":
                    parser.error("URL must belong to an enabled registered public source")
                row = session.get(Candidate, url)
                if row is None:
                    session.add(Candidate(
                        url=url, article={"_queued": True, "_fetch_url": url},
                        status="queued", source_id=source.id, origin="manual",
                    ))
                elif row.status != "published":
                    row.article = {"_queued": True, "_fetch_url": url}
                    row.status = "queued"
                    row.reason = ""
            pipeline = CatalogPipeline(settings, factory)
            try:
                result = pipeline.run(archive=True, discover=False, only_urls=[url])
            finally:
                pipeline.close()
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in ("completed", "partial") else 1
        if args.local_problems or args.global_trends:
            from .scheduler import run_deep_scan

            result = run_deep_scan(settings, factory, "local_weekly" if args.local_problems else "global_monthly")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in ("completed", "partial", "not_due", "not_configured") else 1
        if args.archive and not args.backfill and not args.drain:
            print(
                "--archive permits old publication dates but searches current listings only. "
                "For yearly archives use --backfill --from-date 2022-01-01 --to-date 2026-09-30. "
                "--force-sources bypasses source schedules, not archive coverage limits.",
                file=sys.stderr,
            )
        pipeline = CatalogPipeline(settings, factory)
        pipeline.discovery.force = args.force_sources
        if args.only_source:
            with factory() as session:
                source = session.get(RegistrySource, args.only_source)
                if source is None or not source.enabled:
                    parser.error("--only-source requires an enabled registered source ID")
            pipeline.discovery.allowed_source_ids = {args.only_source}
        try:
            if args.reprocess_review:
                result = pipeline.run(archive=True, discover=False, reanalyze=False, review_only=True)
            elif args.backfill:
                from .queries import archive_windows

                results = []
                for window in archive_windows(args.from_date, args.to_date):
                    pipeline.discovery.window = window
                    result = pipeline.run(archive=True, discover=not args.drain,
                                          force_sources=args.force_sources, only_source=args.only_source)
                    results.append(result)
                    print(json.dumps({"year": window[0].year, **result}, ensure_ascii=False), flush=True)
                result = {
                    "status": "partial" if any(r["status"] != "completed" for r in results) else "completed",
                    "runs": results,
                }
            else:
                result = pipeline.run(archive=args.archive, discover=not args.drain,
                                      force_sources=args.force_sources, only_source=args.only_source)
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
