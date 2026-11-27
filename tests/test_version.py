# ABOUTME: Tests that the application title shows only the version number.
# ABOUTME: Run with: uv run python -m pytest tests/test_version.py -q
import re
from pathlib import Path

from main import AcordesApp

PROJECT = Path(__file__).parent.parent


def test_version_is_only_a_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+", AcordesApp.VERSION)


def test_version_matches_the_project_file():
    text = (PROJECT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)
    assert AcordesApp.VERSION == declared
