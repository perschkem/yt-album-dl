"""Frontend-Logik (ytdl/static/js) mit dem eingebauten Testrunner von Node prüfen – übersprungen ohne Node."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "ytdl" / "static"


@pytest.fixture(scope="module")
def node():
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node nicht installiert")
    return exe


def test_js_unit_tests(node):
    tests = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
    proc = subprocess.run([node, "--test", *tests], capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("script", sorted(p.relative_to(STATIC).as_posix() for p in STATIC.rglob("*.js")))
def test_scripts_are_valid_modules(node, script):
    """Syntax prüfen (als ES-Modul, wie im Browser geladen)."""
    source = (STATIC / script).read_text(encoding="utf-8")
    proc = subprocess.run([node, "--input-type=module", "--check"], input=source, capture_output=True, text=True,
                          check=False)
    assert proc.returncode == 0, proc.stderr


def test_relative_imports_exist():
    import re

    for script in STATIC.rglob("*.js"):
        for target in re.findall(r'from "(\.[^"]+)"', script.read_text(encoding="utf-8")):
            assert (script.parent / target).resolve().is_file(), f"{script.name}: {target}"


def test_imported_names_are_used():
    import re

    for script in STATIC.rglob("*.js"):
        source = script.read_text(encoding="utf-8")
        for names in re.findall(r"import \{([^}]+)\}\s*from", source):
            for name in names.split(","):
                local = name.split(" as ")[-1].strip()
                if local:
                    uses = len(re.findall(rf"(?<![\w$.]){re.escape(local)}(?![\w$])", source))
                    assert uses > 1, f"{script.name}: {local} wird importiert, aber nicht verwendet"
