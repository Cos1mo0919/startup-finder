from datetime import datetime, timedelta, timezone
import pytest
from backend.app.dates import parse_date, priority, today_start, valid_date
from backend.app.detection import extractive_analysis, is_candidate, is_uzbek
from tests.conftest import sample_article

NOW = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value,archive,expected",
    [
        ("2021-12-31T23:59:59Z", True, False),
        ("2022-01-01T00:00:00Z", True, True),
        ("2022-01-01T00:00:00Z", False, False),
        ("2026-10-06T10:01:00Z", True, False),
        ("2026-10-06T09:30:00Z", False, True),
        ("2026-09-01T00:00:00Z", False, False),
        (None, True, False),
        ("invalid", False, False),
    ],
)
def test_publication_gate(value, archive, expected):
    assert valid_date(parse_date(value), NOW, archive) is expected


def test_uzbekistan_midnight():
    assert today_start(datetime(2026, 10, 6, 20, tzinfo=timezone.utc)) == datetime(
        2026, 10, 6, 19, tzinfo=timezone.utc
    )


def test_priority_windows():
    assert [priority(NOW - timedelta(hours=h), NOW) for h in [0.5, 2, 48, 240, 1000]] == [0, 1, 3, 4, 5]


def test_detector_requires_real_project_and_uzbekistan():
    a = sample_article()
    assert is_candidate(a)
    a.text = "O‘zbekiston uchun yangi g‘oya haqida o‘ylayapmiz."
    assert not is_candidate(a)
    a.title = "New platform"
    a.text = "A prototype launched in Canada."
    assert not is_candidate(a)


def test_keyless_extraction_preserves_name_and_quote():
    a = sample_article()
    result = extractive_analysis(a)
    assert result and result.name == "AgroKo‘mak"
    assert result.facts[0].quote in a.text
    assert result.analysis_mode == "extractive"
    assert not result.ai_analysis_uz


def test_foreign_language_waits_for_translation():
    a = sample_article()
    a.text = "В Узбекистане представили проект AgroKo‘mak для фермеров. Разработан прототип."
    assert is_candidate(a)
    assert extractive_analysis(a) is None
    assert not is_uzbek(a.text, "uz")


def test_keyless_does_not_publish_future_prototype_idea():
    a = sample_article()
    a.text = "O‘zbekiston uchun “AgroKo‘mak” loyihasi tomonidan yangi prototip yaratish rejalashtirilgan."
    assert extractive_analysis(a) is None


def test_keyless_named_bot_with_real_launch_evidence():
    a = sample_article()
    a.title = "Yangi chat-bot ishga tushirildi"
    a.text = "O‘zbekiston uchun yangi xizmat. @Example_bot Telegram-boti ommaviy foydalanish uchun test rejimida ishga tushgan."
    result = extractive_analysis(a)
    assert result is None  # A launch alone cannot supply the mandatory creator.
    from backend.app.fallback import pending_reason

    assert pending_reason(a) == "missing_creator"
