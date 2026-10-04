"""Übersetzungen: Funktion t() und die Wörterbücher in ytdl/locales/ (gemeinsam für Backend und Oberfläche)."""

import re
from pathlib import Path

import pytest

from ytdl import i18n

ROOT = Path(__file__).resolve().parent.parent
CODE = ROOT / "ytdl"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def german():
    yield
    i18n.configure("de")


def test_t_with_placeholders_plural_and_fallbacks(monkeypatch):
    monkeypatch.setitem(i18n._catalogs, "de", {"x.hello": "Hallo {name}", "x.n": {"one": "{count} Titel",
                                                                                   "other": "{count} Titel insgesamt"},
                                               "x.only_de": "nur deutsch"})
    monkeypatch.setitem(i18n._catalogs, "en", {"x.hello": "Hello {name}"})
    assert i18n.t("x.hello", name="Welt") == "Hallo Welt"
    assert i18n.t("x.n", count=1) == "1 Titel" and i18n.t("x.n", count=2) == "2 Titel insgesamt"
    assert i18n.t("x.hello") == "Hallo {name}"  # fehlender Parameter bleibt sichtbar
    i18n.configure("en")
    assert i18n.t("x.hello", name="World") == "Hello World"
    assert i18n.t("x.only_de") == "nur deutsch"  # fehlt in Englisch → Deutsch
    assert i18n.t("x.gibts.nicht") == "x.gibts.nicht"
    assert i18n.t("x.hello", lang="de", name="Welt") == "Hallo Welt"


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError, match="fr"):
        i18n.configure("fr")


# ---------- Wörterbücher ----------

def _texts(value) -> list[str]:
    return list(value.values()) if isinstance(value, dict) else [value]


def test_catalogs_have_the_same_keys():
    de, en = i18n.messages("de"), i18n.messages("en")
    assert sorted(set(de) - set(en)) == [], "fehlt in en.json"
    assert sorted(set(en) - set(de)) == [], "fehlt in de.json"


@pytest.mark.parametrize("lang", list(i18n.LANGUAGES))
def test_values_are_complete(lang):
    for key, value in i18n.messages(lang).items():
        if isinstance(value, dict):
            assert set(value) == {"one", "other"}, key
        assert all(isinstance(text, str) and text.strip() for text in _texts(value)), key


def _placeholders(value) -> set[str]:
    return {name for text in _texts(value) for name in PLACEHOLDER.findall(text)}


def test_placeholders_match_between_languages():
    de, en = i18n.messages("de"), i18n.messages("en")
    for key in de:
        assert _placeholders(de[key]) == _placeholders(en[key]), key


# ---------- Verwendung im Code ----------

def _sources() -> list[str]:
    files = [*CODE.glob("*.py"), *(CODE / "static").rglob("*.js"), *(CODE / "static").glob("*.html")]
    return [f.read_text(encoding="utf-8") for f in files if f.name != "i18n.py"]


def _used_keys():
    static, prefixes = set(), set()
    for text in _sources():
        static |= set(re.findall(r"""\bt\(\s*["']([\w.]+)["']""", text))
        static |= set(re.findall(r'data-i18n(?:-[a-z-]+)?="([\w.]+)"', text))
        prefixes |= set(re.findall(r"\bt\(\s*f[\"']([\w.]+)\{", text))  # Python: t(f"status.{code}")
        prefixes |= set(re.findall(r"\bt\(\s*`([\w.]+)\$\{", text))  # JS: t(`status.${code}`)
    return static, prefixes


def test_every_used_key_exists():
    static, prefixes = _used_keys()
    catalog = i18n.messages("de")
    assert sorted(k for k in static if k not in catalog) == []
    for prefix in prefixes:
        assert any(k.startswith(prefix) for k in catalog), prefix


def test_no_unused_keys():
    """Benutzt ist ein Schlüssel, wenn er irgendwo im Code als Text steht – auch als Wert, der später an t() geht
    (z.B. SOURCES in albumvideo oder t("a" if x else "b"))."""
    _, prefixes = _used_keys()
    mentioned = {k for text in _sources() for k in re.findall(r"""["'`]([a-z_]+\.[\w.]+)["'`]""", text)}
    mentioned |= {k for text in _sources() for k in re.findall(r'data-i18n(?:-[a-z-]+)?="([\w.]+)"', text)}
    unused = [k for k in i18n.messages("de") if k not in mentioned and not any(k.startswith(p) for p in prefixes)]
    assert unused == []


def test_mentioned_keys_exist():
    """Jeder Text, der wie ein Schlüssel eines vorhandenen Bereichs aussieht, steht auch im Wörterbuch."""
    sections = {k.split(".")[0] for k in i18n.messages("de")}
    catalog = i18n.messages("de")
    missing = {k for text in _sources() for k in re.findall(r"""["'`]([a-z_]+\.[\w.]+)["'`]""", text)
               if k.split(".")[0] in sections and k not in catalog}
    assert sorted(missing) == []


def test_api_serves_the_configured_catalog(client):
    data = client.get("/api/i18n").json()
    assert data["language"] == "de" and data["languages"] == {"de": "Deutsch", "en": "English"}
    assert data["messages"]["status.done"] == "fertig"


# ---------- Keine festen Texte mehr in der Oberfläche ----------

GERMAN = re.compile(r"[äöüÄÖÜß]|\b(?:und|oder|nicht|bitte|Titel|Fehler|alle|laden|keine?|Ordner)\b")


def test_no_german_literals_in_scripts():
    """Texte für die Oberfläche kommen aus dem Wörterbuch – deutsche Literale im JS wären unübersetzt."""
    for script in (CODE / "static").rglob("*.js"):
        code = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", script.read_text(encoding="utf-8"))
        for literal in re.findall(r'"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`', code):
            assert not GERMAN.search(literal), f"{script.name}: {literal}"


def test_html_texts_have_keys():
    from html.parser import HTMLParser

    allowed = {"yt-album-dl", "MP3", "M4A", "cookies.txt", "↺", "▶"}

    class Check(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.problems = [], []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            for attr in ("title", "placeholder", "aria-label", "alt"):
                value = attrs.get(attr)
                if value and re.search(r"[A-Za-zÄÖÜäöü]{3}", value) and not value.startswith("https://") \
                        and f"data-i18n-{attr}" not in attrs:
                    self.problems.append(f"{tag} {attr}={value!r}")
            if tag not in ("meta", "link", "img", "input", "br"):
                self.stack.append("data-i18n" in attrs or "data-i18n-html" in attrs)

        def handle_endtag(self, tag):
            if tag not in ("meta", "link", "img", "input", "br") and self.stack:
                self.stack.pop()

        def handle_data(self, data):
            text = data.strip()
            if re.search(r"[A-Za-zÄÖÜäöü]{2}", text) and text not in allowed and not any(self.stack):
                self.problems.append(text)

    for page in ("index.html", "historie.html"):
        check = Check()
        check.feed((CODE / "static" / page).read_text(encoding="utf-8"))
        assert check.problems == [], page
