import os
import sys
import logging
import logging.handlers
from pathlib import Path


def setup_logging(level: str | None = None) -> None:
    """Configures centralized logging for the application.

    Writes to two destinations:
      1. stderr (console) — for live monitoring and systemd journal
      2. data/logs/server.log (rotating file) — for post-incident review

    If level is not provided, reads LOG_LEVEL environment variable,
    defaulting to INFO.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Map string level to logging integer constant
    log_level = getattr(logging, level, logging.INFO)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicate logs
    if root_logger.handlers:
        root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ── Console handler (stderr → systemd journal / terminal) ──────────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ── Rotating file handler (survives restarts, readable post-incident) ──
    # Rotates at 5 MB, keeps 3 backup files → max ~20 MB disk usage.
    try:
        log_dir = Path(__file__).resolve().parents[2] / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "server.log",
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as _log_exc:
        # Never crash the server because logging setup failed
        print(f"[WARNING] Could not set up file logging: {_log_exc}", file=sys.stderr)

    # Restrict third-party loggers verbosity
    for lib in ["urllib3", "openai", "httpx", "easyocr", "easyocr.easyocr", "PIL", "matplotlib", "fsspec", "supabase", "postgrest"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
