import io

import pytest
from PIL import Image

from ytdl import covers
from ytdl.covers import cover_jpeg


def png_bytes(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "green").save(buf, format="PNG")
    return buf.getvalue()


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def read(self, n=-1):
        return self.data[:n] if n >= 0 else self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def serve(monkeypatch):
    calls = []

    def setup(data):
        def urlopen(req, timeout):
            calls.append(req.full_url)
            return FakeResponse(data)
        monkeypatch.setattr(covers.urllib.request, "urlopen", urlopen)
        return calls
    return setup


def test_check_cover_reports_size(serve):
    serve(png_bytes(600, 400))
    assert covers.check_cover("https://example.org/a.png") == {"width": 600, "height": 400, "format": "PNG", "square": False}


def test_rejects_non_image(serve):
    serve(b"<html>keine Bilddatei</html>")
    with pytest.raises(covers.CoverError, match="kein Bild"):
        covers.check_cover("https://example.org/seite")


def test_rejects_too_large(serve, monkeypatch):
    monkeypatch.setattr(covers, "MAX_BYTES", 100)
    serve(png_bytes(200, 200))
    with pytest.raises(covers.CoverError, match="10 MB"):
        covers.check_cover("https://example.org/gross.png")


def test_rejects_other_schemes():
    with pytest.raises(covers.CoverError, match="http"):
        covers.check_cover("file:///etc/passwd")


def test_fetch_cover_is_cached(serve, tmp_path):
    calls = serve(png_bytes(300, 300))
    first = covers.fetch_cover("https://example.org/c.png", tmp_path)
    second = covers.fetch_cover("https://example.org/c.png", tmp_path)
    assert first == second and first.suffix == ".jpg" and len(calls) == 1


def test_cover_crop_only_on_request(tmp_path):
    path = tmp_path / "c.png"
    path.write_bytes(png_bytes(1600, 900))
    cropped = Image.open(io.BytesIO(cover_jpeg(path, crop=True)))
    kept = Image.open(io.BytesIO(cover_jpeg(path, crop=False)))
    assert cropped.size == (900, 900)
    assert kept.size == (1000, 563)  # Seitenverhältnis bleibt, auf max. 1000 px verkleinert


def test_trim_black_side_bars(tmp_path):
    from ytdl.covers import trim_bars

    img = Image.new("RGB", (1280, 720), (3, 3, 3))  # fast schwarz wie bei JPEG
    img.paste(Image.new("RGB", (720, 720), (200, 40, 40)), (280, 0))
    trimmed = trim_bars(img)
    assert trimmed.size == (720, 720)


def test_trim_letterbox_and_keep_dark_artwork():
    from ytdl.covers import trim_bars

    letterbox = Image.new("RGB", (1280, 720), "black")
    letterbox.paste(Image.new("RGB", (1280, 540), (40, 120, 200)), (0, 90))
    assert trim_bars(letterbox).size == (1280, 540)
    dark = Image.new("RGB", (1280, 720), (5, 5, 5))
    assert trim_bars(dark).size == (1280, 720)  # komplett dunkles Bild bleibt


def test_cover_jpeg_thumbnail_with_bars_becomes_artwork(tmp_path):
    img = Image.new("RGB", (1280, 720), "black")
    img.paste(Image.new("RGB", (720, 720), (10, 200, 10)), (280, 0))
    path = tmp_path / "thumb.png"
    img.save(path)
    out = Image.open(io.BytesIO(cover_jpeg(path, crop=True)))
    assert out.size == (720, 720)
    assert out.getpixel((5, 360))[1] > 150  # Rand ist grün, nicht schwarz


def test_center_square():
    img = Image.new("RGB", (400, 100))
    img.paste(Image.new("RGB", (100, 100), "white"), (150, 0))
    square = covers.center_square(img)
    assert square.size == (100, 100) and square.getpixel((50, 50)) == (255, 255, 255)
    assert covers.center_square(Image.new("RGB", (50, 80))).size == (50, 50)


def test_to_jpeg_respects_size_and_crop():
    img = Image.new("RGB", (800, 400), "blue")
    assert Image.open(io.BytesIO(covers.to_jpeg(img, 100, quality=80))).size == (100, 100)
    assert Image.open(io.BytesIO(covers.to_jpeg(img, 100, quality=80, crop=False))).size == (100, 50)


def test_thumbnail_preview_matches_embedded_cover(serve):
    img = Image.new("RGB", (1280, 720), "black")
    img.paste(Image.new("RGB", (720, 720), (10, 200, 10)), (280, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    serve(buf.getvalue())
    preview = Image.open(io.BytesIO(covers.thumbnail_preview("https://i.ytimg.com/vi/x/hq.jpg")))
    assert preview.size == (300, 300) and preview.format == "JPEG"
    assert preview.getpixel((3, 150))[1] > 150  # schwarze Balken entfernt
