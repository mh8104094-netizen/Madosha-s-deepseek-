from __future__ import annotations

import os
import sys
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

# Existing Railway public domain targets container port 80.
# Keep this fixed so the old VELA URL now serves X-MIND directly.
port = "80"
os.execvp(sys.executable, [sys.executable, "-m", "uvicorn", "xmind.api:app", "--host", "0.0.0.0", "--port", port])
