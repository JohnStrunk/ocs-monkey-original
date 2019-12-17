"""Utility functions for ocs-monkey."""

import logging
import os
import time

def setup_logging(log_dir: str) -> None:
    """Initializes logging to file & stdout."""
    os.mkdir(log_dir)

    handlers = [
        logging.FileHandler(os.path.join(log_dir, "runner.log")),
        logging.StreamHandler()
    ]
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logging.Formatter.converter = time.gmtime
    formatter = \
        logging.Formatter("%(asctime)s %(name)s - %(levelname)s - %(message)s")
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
