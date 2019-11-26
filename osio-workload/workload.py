"""OSIO workload simulator."""

import argparse
import logging
import os
import random
import signal
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, NoReturn

# Times per hour we sample for an event
_HOURLY_DRAW_RATE: float = 3600
_CONTINUE = True

def get_slots(path: str, max_slots: int) -> Dict[str, List[str]]:
    """
    Return a list of directories that are either in-use or free.

    The untar/rm operations work on "slots" (i.e., directories) that are either
    full or empty. This function scans the (potential) directories in `path` and
    determines whether the slots are `used` or `free`.

    Parameters:
        path: The base path that holds the slot directories
        max_slots: The maximum number of slot directories that could exist

    Returns:
        A dict with 2 keys: `used` and `free`. Each key maps to a list of slot
        directories (full path to the directory). For `used`, these directories
        exist and are in use. For `free`, the directories do not exist.

    """
    summary: Dict[str, List[str]] = {"used": [], "free": []}
    for slot in range(max_slots):
        slot_dir = os.path.join(path, f'slot-{slot}')
        if os.path.exists(slot_dir):
            summary["used"].append(slot_dir)
        else:
            summary["free"].append(slot_dir)
    return summary

def do_untar(image: str, data_dir: str) -> bool:
    """Untar the kerner src into a slot directory."""
    logging.info("Untar %s into %s", image, data_dir)
    os.mkdir(data_dir)
    completed = subprocess.run(f'tar -C "{data_dir}" -xJf "{image}"',
                               shell=True, check=False)
    return completed.returncode == 0

def do_rm(data_dir: str) -> bool:
    """Remove a slot directory."""
    logging.info("Deleting %s", data_dir)
    shutil.rmtree(data_dir)
    return True

def rate_to_probability(rate_per_hour: float, draw_rate: float) -> float:
    """
    Determine the probability for a single draw.

    Given an hourly random draw rate and a targeted mean times per hour that an
    event should happen, determing the probability that a single draw should
    succeed.

    >>> rate_to_probability(10, 100)
    0.1
    >>> rate_to_probability(5, 40)
    0.125
    >>> rate_to_probability(100, 2)  # capped at 1.0
    1.0
    """
    return min(rate_per_hour/draw_rate, 1.0)

def _sig_handler(signum: int, stack: Any) -> None:  # pylint: disable=unused-argument
    global _CONTINUE  # pylint: disable=global-statement
    _CONTINUE = False

def main() -> NoReturn:
    """Run the workload."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir",
                        type=str,
                        default="/data",
                        help="Directory to use for workload I/O")
    parser.add_argument("--kernel-slots",
                        type=int,
                        default=4,
                        help="Max # of kernel sources to have at once")
    parser.add_argument("--rm-rate",
                        type=float,
                        default=30,
                        help="Rate to invoke rm of kernel tree (#/hr)")
    parser.add_argument("--untar-image",
                        type=str,
                        default="/kernel.tar.xz",
                        help="Full path to the kernel tar image")
    parser.add_argument("--untar-rate",
                        type=float,
                        default=30,
                        help="Rate to invoke untar of kernel tree (#/hr)")
    cli_args = parser.parse_args()

    logging.info("Workload generator started")
    logging.info("program arguments: %s", cli_args)

    # Register signal handler so we can cleanly shutdown
    signal.signal(signal.SIGINT, _sig_handler)

    while _CONTINUE:
        time.sleep(_HOURLY_DRAW_RATE/3600)
        if random.random() < rate_to_probability(cli_args.untar_rate,
                                                 _HOURLY_DRAW_RATE):
            logging.info("try untar")
            slots = get_slots(cli_args.data_dir, cli_args.kernel_slots)
            try:
                slot_dir = random.choice(slots["free"])
                if not do_untar(cli_args.untar_image, slot_dir):
                    logging.error("untar failed")
                    sys.exit(1)
            except IndexError:
                logging.info("No free slots")
            continue
        if random.random() < rate_to_probability(cli_args.rm_rate,
                                                 _HOURLY_DRAW_RATE):
            logging.info("try rm")
            slots = get_slots(cli_args.data_dir, cli_args.kernel_slots)
            try:
                slot_dir = random.choice(slots["used"])
                if not do_rm(slot_dir):
                    logging.error("rm failed")
                    sys.exit(2)
            except IndexError:
                logging.info("No used slots")
            continue

    logging.info("Workload generator exiting")
    sys.exit(os.EX_OK)

if __name__ == '__main__':
    main()
