from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


def get_logger(config: dict[str, Any]) -> logging.Logger:
    log_dir = Path(config["app"].get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("alex_stock_picker")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_dir / "ingestion.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
