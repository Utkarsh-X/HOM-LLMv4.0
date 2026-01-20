"""Runtime logging utilities for consistent CLI output."""

import logging
from typing import Optional


def configure_logging(level: int = logging.INFO, logger_name: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger with the required format.

    Format: YYYY-MM-DD HH:MM:SS LEVEL message
    """
    logger = logging.getLogger(logger_name)

    if not logging.getLogger().handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(handler)
    else:
        # Ensure format is correct even if handlers already exist
        for handler in logging.getLogger().handlers:
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        logging.getLogger().setLevel(level)

    return logger
