import pytest

from tests.test_settings import settings_client  # noqa: F401  (Fixtures für mehrere Testdateien)
from tests.test_web import client  # noqa: F401
from ytdl import i18n


@pytest.fixture()
def english():
    """Meldungen auf Englisch – danach wieder Deutsch (Standard)."""
    i18n.configure("en")
    yield
    i18n.configure("de")
