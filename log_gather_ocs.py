"""Log gathering routines for OCS."""

import os
import subprocess

import log_gather

# pylint: disable=too-few-public-methods
class MustGather(log_gather.Collector):
    """Log collector that runs must-gather."""

    def __init__(self, oc: str) -> None:
        """Create a log-collector using must-gather."""
        super().__init__("must-gather")
        self._oc = oc
    def gather(self, path: str) -> bool:
        """Run must-gather and notify of success."""
        mg_dir = os.path.join(path, 'must-gather')
        completed = subprocess.run(f'{self._oc} adm must-gather'
                                   f' --dest-dir {mg_dir}', shell=True,
                                   check=False)
        return completed.returncode == 0

class OcsMustGather(log_gather.Collector):
    """Log collector that runs ocs-must-gather."""

    def __init__(self, oc: str) -> None:
        """Create a log-collector using ocs-must-gather."""
        super().__init__("OCS must-gather")
        self._oc = oc
    def gather(self, path: str) -> bool:
        """Run must-gather and notify of success."""
        mg_dir = os.path.join(path, 'ocs-must-gather')
        completed = subprocess.run(f'{self._oc} adm must-gather'
                                   f' --image=quay.io/ocs-dev/ocs-must-gather'
                                   f' --dest-dir {mg_dir}', shell=True,
                                   check=False)
        return completed.returncode == 0

class OcsImageVersions(log_gather.Collector):
    """Grab the images & tags from the OCS namespace."""

    def __init__(self, oc: str, ocs_namespace: str) -> None:
        """Create a log-collector that scrapes images tags."""
        self._oc = oc
        self._ns = ocs_namespace
        super().__init__("OCS image versions")
    def gather(self, path: str) -> bool:
        """Scrape the names of the pod images."""
        completed = subprocess.run(f'{self._oc} -n {self._ns} get po -oyaml'
                                   ' | grep -E "(image:|imageID:)" | sort -u '
                                   f'> {path}/ocs_images.log', shell=True,
                                   check=False)
        return completed.returncode == 0
