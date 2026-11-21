from __future__ import annotations
import logging, os, sys
from pathlib import Path
import eel

USER_DIR = Path(__file__).resolve().parent
for folder in (USER_DIR / "py", USER_DIR / "db", USER_DIR / "core" / "py"):
    sys.path.insert(0, str(folder))
from database import initialize_database
from api import configure_api

def main():
    log_dir = USER_DIR / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=os.getenv("YTA_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_dir / "application.log", encoding="utf-8"), logging.StreamHandler()],
    )
    initialize_database()
    eel.init(str(USER_DIR))
    configure_api(USER_DIR)
    eel.start("web/index.html", mode=os.getenv("YTA_BROWSER_MODE", "chrome"),
              size=(1480, 960), position=(80, 50), port=0,
              close_callback=lambda page, sockets: logging.getLogger(__name__).info(
                  "Eel window closed: %s; remaining=%s", page, sockets))

if __name__ == "__main__":
    main()
