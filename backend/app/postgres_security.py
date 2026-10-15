"""Backend-owned PostgreSQL tables are not exposed through Supabase Data API."""

from sqlalchemy import inspect, text


def table_names(metadata):
    return sorted({"schema_migrations", *metadata.tables})


def enable_postgres_rls(connection, metadata):
    if connection.dialect.name != "postgresql":
        return
    quote = connection.dialect.identifier_preparer.quote_identifier
    roles = list(connection.execute(text(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
    )).scalars())
    for name in table_names(metadata):
        identifier = quote(name)
        connection.execute(text(f"ALTER TABLE {identifier} ENABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"REVOKE ALL ON TABLE {identifier} FROM PUBLIC"))
        for role in roles:
            connection.execute(text(f"REVOKE ALL ON TABLE {identifier} FROM {quote(role)}"))
    # No public policies, no FORCE RLS: the table owner / BYPASSRLS backend role
    # remains functional. Browser access goes through FastAPI, never PostgREST.


def validate_schema_ready(engine, metadata):
    with engine.connect() as connection:
        inspector = inspect(connection)
        present = set(inspector.get_table_names())
        expected = set(table_names(metadata))
        if not expected.issubset(present):
            raise RuntimeError("Database schema is not ready. Run python -m backend.app.schema before deployment.")
        for table in metadata.sorted_tables:
            columns = {column["name"] for column in inspector.get_columns(table.name)}
            if not set(table.columns.keys()).issubset(columns):
                raise RuntimeError("Database columns need migration. Run python -m backend.app.schema before deployment.")
        if engine.dialect.name == "postgresql":
            rows = connection.execute(text(
                "SELECT c.relname,c.relrowsecurity,(r.rolsuper OR r.rolbypassrls "
                "OR (c.relowner=r.oid AND NOT c.relforcerowsecurity)) AS backend_access "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "CROSS JOIN pg_roles r WHERE n.nspname=current_schema() AND r.rolname=current_user "
                "AND c.relkind='r'"
            )).mappings()
            protected = {row["relname"] for row in rows if row["relrowsecurity"] and row["backend_access"]}
            if not expected.issubset(protected):
                raise RuntimeError("Database needs RLS migration or a backend table-owner/BYPASSRLS role. "
                                   "Run python -m backend.app.schema with the database owner.")
