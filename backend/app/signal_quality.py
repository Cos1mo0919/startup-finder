"""Preserve historical signals while excluding irrelevant ones from intelligence."""

from sqlalchemy import select
from .db import EcosystemSignal
from .detection import IRRELEVANT_NOTICE, MARKET_SIGNAL


def signal_status(title: str, quote: str = "") -> str:
    text = title + " " + quote[:600]
    if IRRELEVANT_NOTICE.search(title):
        return "IGNORED"
    if not MARKET_SIGNAL.search(text):
        return "IGNORED"
    return "ACTIVE"


def audit_signals(factory):
    with factory.begin() as session:
        for signal in session.scalars(select(EcosystemSignal)):
            signal.intelligence_status = signal_status(signal.title, signal.quote)
