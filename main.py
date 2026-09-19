from __future__ import annotations

import os
import uvicorn

from xmind_core import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "80"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
