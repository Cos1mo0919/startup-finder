"""Bounded diagnostics: never stringify SQLAlchemy statements/parameters or locals."""

import re
from pathlib import Path

from .diagnostics import candidate_id

ROOT = Path(__file__).resolve().parent


def safe_error(exc, *, function, candidate_url=None):
    original = getattr(exc, "orig", exc)
    # DBAPIError.__str__ includes SQL and bound parameters. Never call it.
    primary = getattr(getattr(original, "diag", None), "message_primary", None)
    if not primary:
        lines = str(original).splitlines()
        primary = lines[0][:2000] if lines else type(original).__name__
    primary = re.split(r"\[SQL|\[parameters|DETAIL:|CONTEXT:|STATEMENT:", primary, maxsplit=1)[0]
    primary = re.sub(r"\S+://\S+", "[connection redacted]", primary)
    primary = re.sub(
        r"""(['"])(?:\\.|(?!\1).)*?\1""",
        lambda match: match[0] if match[0][1:-1] in {"dict", "list", "%s", "%b", "%t"} else "[redacted]",
        primary,
    )
    primary = re.sub(
        r"(?i)\b(password|passwd|token|api[_-]?key|database_url|dbname|user|host)\s*[=:]\s*\S+",
        r"\1=[redacted]",
        primary,
    )
    primary = re.sub(r"\b[A-Za-z0-9_+/=-]{24,}\b", "[redacted]", primary)
    # Only DBAPI diagnostics are useful verbatim; arbitrary application exceptions
    # may interpolate whole payloads. Keep a neutral message for those.
    if not (getattr(exc, "orig", None) is not None or type(original).__module__.startswith("psycopg")):
        primary = "Application operation failed; inspect the recorded function and exception class"
    location = function
    tb = exc.__traceback__
    while tb:
        path = Path(tb.tb_frame.f_code.co_filename).resolve()
        if path.is_relative_to(ROOT):
            location = path.stem + "." + tb.tb_frame.f_code.co_name
        tb = tb.tb_next
    result = {
        "code": type(exc).__name__,
        "exception_class": type(exc).__name__,
        "driver_class": type(original).__name__,
        "message": primary[:300],
        "function": location,
        "candidate_id": candidate_id(candidate_url) if candidate_url else None,
    }
    sqlstate = getattr(original, "sqlstate", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
        result["sqlstate"] = sqlstate
    return result
