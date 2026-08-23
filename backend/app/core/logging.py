import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure basic structured-ish logging to stdout for the whole app."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
