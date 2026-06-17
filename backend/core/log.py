import logging
import sys


def create_logger(name: str) -> logging.Logger:
    """Create a structured logger."""
    logger = logging.getLogger(f"openbox.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger
