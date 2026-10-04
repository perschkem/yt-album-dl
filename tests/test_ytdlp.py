import time
from typing import ClassVar

import pytest

from tests.test_botcheck import BOT, cookie_cfg  # noqa: F401  (Fixture)
from ytdl import ytdlp
from ytdl.auth import youtube


def test_progress_text():
    assert ytdlp.progress_text({"status": "finished"}) is None
    assert ytdlp.progress_text({"status": "downloading", "downloaded_bytes": 1_048_576,
                                "total_bytes": 4_194_304, "speed": 524_288}) == ("1.0 von 4.0 MB · 0.5 MB/s", 25.0)
    assert ytdlp.progress_text({"status": "downloading", "downloaded_bytes": 2_097_152}) == ("2.0 MB", None)
    estimate = {"status": "downloading", "downloaded_bytes": 300, "total_bytes_estimate": 200}
    assert ytdlp.progress_text(estimate)[1] == 100.0  # Schätzung zu klein → nie über 100 %


class FakeYDL:
    """Ersetzt YoutubeDL: merkt sich Optionen und Aufrufe, meldet Fortschritt, wirft auf Wunsch Fehler."""
    calls: ClassVar[list] = []
    errors: ClassVar[list] = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        FakeYDL.calls.append(("download", urls, self.opts))
        if FakeYDL.errors:
            raise FakeYDL.errors.pop(0)
        for hook in self.opts["progress_hooks"]:
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})

    def extract_info(self, url, download):
        FakeYDL.calls.append(("extract", url, self.opts, download))
        return {"id": "x"}


@pytest.fixture()
def fake_ydl(monkeypatch):
    FakeYDL.calls, FakeYDL.errors = [], []
    monkeypatch.setattr(ytdlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_download_builds_options_and_reports_progress(fake_ydl, tmp_path):
    seen = []
    ytdlp.download("https://youtu.be/x", tmp_path / "audio.%(ext)s", "bestaudio",
                   lambda detail, pct: seen.append((detail, pct)), writethumbnail=True)
    (_, urls, opts), = fake_ydl.calls
    assert urls == ["https://youtu.be/x"]
    assert opts["outtmpl"] == str(tmp_path / "audio.%(ext)s") and opts["format"] == "bestaudio"
    assert opts["writethumbnail"] and opts["concurrent_fragment_downloads"] == 4 and opts["ignoreerrors"] is False
    assert opts["quiet"] and opts["noplaylist"]  # Grundoptionen
    assert seen == [("0.0 von 0.0 MB", 50.0)]


def test_download_without_progress_has_no_hooks(fake_ydl, tmp_path):
    ytdlp.download("u", tmp_path / "v.%(ext)s", "best")
    assert fake_ydl.calls[0][2]["progress_hooks"] == []


def test_extract_info_passes_extra_options(fake_ydl):
    assert ytdlp.extract_info("u", extract_flat="in_playlist") == {"id": "x"}
    (_, url, opts, download), = fake_ydl.calls
    assert url == "u" and opts["extract_flat"] == "in_playlist" and download is False


def test_download_repeats_with_cookies_after_bot_check(fake_ydl, tmp_path, cookie_cfg):  # noqa: F811
    fake_ydl.errors.append(RuntimeError(BOT))
    ytdlp.download("u", tmp_path / "a.%(ext)s", "best")
    first, second = (c[2] for c in fake_ydl.calls)
    assert "cookiefile" not in first and "cookiefile" in second  # Optionen werden je Versuch neu gebaut
    assert youtube.cookies_active() and youtube.active_until > time.time()
