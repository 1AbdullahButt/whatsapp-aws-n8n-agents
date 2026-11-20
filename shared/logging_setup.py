"""One place to set up logging the same way in both projects."""
import logging


def get_logger(name, level="INFO"):
    """Return a logger that prints time, level, name and message."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger(name)
