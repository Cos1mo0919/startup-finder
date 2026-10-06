import argparse
import json
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
    parser.add_argument("--archive", action="store_true", help="Allow publication dates from 2022 onward")
    parser.add_argument(
        "--force-sources", action="store_true", help="Manually check enabled sources regardless of frequency"
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
    args = parser.parse_args()
    settings = Settings()
    engine, factory = make_db(settings.database_url)
    try:
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
        pipeline = Pipeline(settings, factory)
        pipeline.discovery.force = args.force_sources
        try:
            result = pipeline.run(archive=args.archive)
        finally:
            pipeline.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] in ("failed", "partial") else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
