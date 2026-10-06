import argparse
import json
from .config import Settings
from .db import make_db
from .scheduler import run_once


def main():
    parser = argparse.ArgumentParser(description="Run Uzbekistan discovery once")
    parser.add_argument("--archive", action="store_true", help="Allow publication dates from 2022 onward")
    args = parser.parse_args()
    settings = Settings()
    engine, factory = make_db(settings.database_url)
    try:
        result = run_once(settings, factory, archive=args.archive)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] in ("failed", "partial") else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
