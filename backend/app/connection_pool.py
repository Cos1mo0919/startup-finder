"""PostgreSQL checkout hygiene without toggling autocommit on pooled connections."""

from sqlalchemy import create_engine, event, exc
from psycopg import InterfaceError, OperationalError
from psycopg.pq import TransactionStatus


def clean_postgres_checkout(connection, record, proxy):
    # Never try rollback/autocommit changes while libpq has a command in flight.
    status = connection.info.transaction_status
    if status in (TransactionStatus.ACTIVE, TransactionStatus.UNKNOWN) or connection.closed:
        raise exc.DisconnectionError("Discarding an unfinished PostgreSQL connection")
    try:
        if status != TransactionStatus.IDLE:
            connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        # SELECT begins a transaction in normal psycopg mode. End only this
        # checkout probe, BEFORE SQLAlchemy hands the connection to application code.
        connection.rollback()
    except (OperationalError, InterfaceError) as error:
        raise exc.DisconnectionError("PostgreSQL checkout probe failed") from error
    except BaseException as error:
        # A cancellation must not return an ACTIVE socket to the pool.
        record.invalidate(error)
        raise


def runtime_engine(parsed, *, statement_timeout_ms=None, **options):
    sqlite = parsed.get_backend_name() == "sqlite"
    kwargs = {
        "connect_args": {"check_same_thread": False, "timeout": 30} if sqlite else {"connect_timeout": 10},
        "pool_pre_ping": sqlite,
        "pool_reset_on_return": "rollback",
        **options,
    }
    engine = create_engine(parsed, **kwargs)
    if not sqlite:
        if statement_timeout_ms is not None:
            timeout = int(statement_timeout_ms)
            if not 1 <= timeout <= 120000:
                raise ValueError("Invalid PostgreSQL statement timeout")

            @event.listens_for(engine, "connect")
            def initialize(connection, record):
                # Fresh physical connection only, never an application transaction.
                with connection.cursor() as cursor:
                    cursor.execute(f"SET statement_timeout = {timeout}")
                connection.commit()

        event.listen(engine, "checkout", clean_postgres_checkout)
    return engine
