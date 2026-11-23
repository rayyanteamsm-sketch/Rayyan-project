"""
نقطة تشغيل خادم ريّان.

    python -m backend.main            # http://127.0.0.1:8000
    RAYYAN_PORT=9000 python -m backend.main
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.factory import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("RAYYAN_HOST", "127.0.0.1")
    port = int(os.environ.get("RAYYAN_PORT", "8000"))
    print(f"\n  ريّان يعمل على: http://{host}:{port}\n  توثيق API:     http://{host}:{port}/api/docs\n")
    uvicorn.run(app, host=host, port=port, log_level="info")
