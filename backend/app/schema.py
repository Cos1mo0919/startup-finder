"""Explicit schema and RLS migration; never runs discovery or imports data."""

import sys

from .config import Settings
from .db import make_db, normalized_database_url


def main():
    try:
        settings = Settings()
        if normalized_database_url(settings.database_url).get_backend_name() != "postgresql":
            raise ValueError("Schema deployment requires PostgreSQL")
        engine, _ = make_db(settings.database_url, auto_migrate=True)
        engine.dispose()
        print("PostgreSQL schema and RLS migration completed. No discovery or data import executed.")
        return 0
    except Exception as exc:
        # Driver errors can contain URLs/SQL parameters; never print their text.
        print(f"Schema migration failed: {type(exc).__name__}. Check database configuration and owner permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
