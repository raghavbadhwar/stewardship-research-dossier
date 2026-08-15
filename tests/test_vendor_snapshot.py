from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
VENDOR = PROJECT_ROOT / "third_party" / "last30days"
MANIFEST = PROJECT_ROOT / "third_party" / "last30days.manifest.json"


def test_last30days_vendor_tree_matches_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["repository"] == "https://github.com/mvanhorn/last30days-skill"
    assert manifest["version"] == "3.21.0"
    assert manifest["commit"] == "c7460f6114449ddfe6ea3fc2f23c3d910c0e740c"
    actual = {
        str(path.relative_to(VENDOR)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in VENDOR.rglob("*")
        if path.is_file()
    }
    assert actual == manifest["files"]


def test_last30days_vendor_tree_excludes_machine_state() -> None:
    forbidden = {".git", ".pytest_cache", "__pycache__", ".venv", "node_modules"}

    assert VENDOR.is_dir()
    assert (VENDOR / "tests").is_dir()
    assert (VENDOR / "fixtures").is_dir()
    assert (VENDOR / "docs" / "reference").is_dir()
    assert (VENDOR / "uv.lock").is_file()
    assert not any(
        forbidden.intersection(path.relative_to(VENDOR).parts) for path in VENDOR.rglob("*")
    )
