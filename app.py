from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "xmind" / "api.py"
ARCHIVE = ROOT / "xmind_deploy.zip"

if not PACKAGE.exists():
    if not ARCHIVE.exists():
        raise RuntimeError("xmind_deploy.zip is missing")
    with zipfile.ZipFile(ARCHIVE) as zf:
        zf.extractall(ROOT)

from xmind.api import app
