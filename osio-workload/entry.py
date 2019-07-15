"""OSIO workload simulator."""

import logging
import os
import sys
from typing import NoReturn

def main() -> NoReturn:
    """Run the workload."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s - %(levelname)s - %(message)s")
    logging.info("Workload generator started")
    logging.info("Workload generator exiting")
    sys.exit(os.EX_OK)

if __name__ == '__main__':
    main()
