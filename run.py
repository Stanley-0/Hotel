"""Start Staysheet locally with one command:

    python run.py

Installs missing requirements, starts the web server and opens it in your browser.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_MODULES = ("flask", "selenium")


def ensure_requirements() -> None:
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if not missing:
        return
    print(f"Installing missing packages ({', '.join(missing)})...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]
    )


def main() -> None:
    os.chdir(ROOT)
    ensure_requirements()

    from server import app

    port = int(os.environ.get("PORT", "5000"))
    url = f"http://localhost:{port}"
    print(f"\n  Staysheet is running at {url}  (press Ctrl+C to stop)\n")

    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()

    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
