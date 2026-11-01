import pytest

from apps.core.services.telegram import TelegramAlertService


@pytest.fixture(autouse=True)
def no_real_telegram(monkeypatch):
    """
    WHY: settings fall back to the developer's .env, so without this every test that
    creates a listing, lead or VIP slip would post a real alert into the team's
    Telegram group. Tests that need credentials patch get_credentials themselves.
    """
    monkeypatch.setattr(TelegramAlertService, 'get_credentials', classmethod(lambda cls: ('', '')))
