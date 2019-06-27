from copy import deepcopy
import random
import time
from typing import Any, Callable, Dict, List  # pylint: disable=unused-import

import kubernetes.client as k8s

import kube
from event import Event

def _get_workload(ns_name: str, sc_name: str) -> Dict[str, kube.MANIFEST]:
    """
    Generate a workload description.

    The description contains "uniquified" manifests suitable for giving to the
    kubernetes API.
    """
    manifests = {}
    unique_id = str(time.perf_counter_ns())

    manifests["deployment"] = {
        "metadata": {
            "name": f"osio-worker-{unique_id}",
            "namespace": ns_name,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "deployment-id": unique_id
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "deployment-id": unique_id
                    }
                },
                "spec": {
                    "containers": [{
                        "name": "busybox",
                        "image": "busybox",
                        "command": ["sleep", "99999"],
                        "volumeMounts": [{
                            "name": "data",
                            "mountPath": "/mnt"
                        }]
                    }],
                    "volumes": [{
                        "name": "data",
                        "persistentVolumeClaim": {
                            "claimName": f"pvc-{unique_id}"
                        }
                    }]
                }
            }
        }
    }

    manifests["pvc"] = {
        "metadata": {
            "name": f"pvc-{unique_id}",
            "namespace": ns_name
        },
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "resources": {
                "requests": {
                    "storage": "1Gi"
                }
            },
            "storageClassName": sc_name
        }
    }
    return manifests

class ExponentialDeployment(Event):
    """
    Create Expontitially distributed Deployments.

    This Event creates a Deployment and also schedules its future deletion (via
    DeploymentDestroyer). The interarrival time of creation events, active &
    idle times, and Deployment lifetime are all drawn from an Exponential
    distribution with the supplied means.

    """

    def __init__(self,
                 interarrival: float,
                 lifetime: float,
                 active: float,
                 idle: float) -> None:
        """
        Deployments are created and destroyed at some random rate.

        Given some mean interarrival time, a, and lifetime, l, the average
        number of Deployments that would be expected to exist is (l/a) according
        to Little's Law.

        Parameters:
            interarrival: The mean interrarival time (seconds) between
                Deployment creations.
            lifetime: The mean lifetime (in seconds) of a Deployment once it has
                been created.
            active: The mean active time for the Deployment's pod before it
                becomes idle.
            idle: The mean idle time for the Deployment before it becomes
                active.

        """
        self._interarrival = interarrival
        self._lifetime = lifetime
        self._active = active
        self._idle = idle
        super().__init__(when=time.time() +
                         random.expovariate(1/self._interarrival))

    def execute(self) -> 'List[Event]':
        """Create a new Deployment & schedule it's destruction."""
        destroy_time = time.time() + random.expovariate(1/self._lifetime)
        manifests = _get_workload("monkey", "gp2")
        pvc = manifests["pvc"]
        deploy = manifests["deployment"]
        # Set necessary labels, etc. on the Deployment
        labels = deploy["metadata"].setdefault("labels", {})
        labels["ocs-monkey/controller"] = "exponential"
        labels["ocs-monkey/exponential-active"] = str(self._active)
        labels["ocs-monkey/exponential-idle"] = str(self._idle)
        labels["ocs-monkey/destroy-at"] = str(destroy_time)
        deploy["metadata"]["labels"] = labels
        print('New deployment:',
              f'{deploy["metadata"]["namespace"]}',
              f'{deploy["metadata"]["name"]}')
        core_v1 = k8s.CoreV1Api()
        kube.call(core_v1.create_namespaced_persistent_volume_claim,
                  namespace=pvc["metadata"]["namespace"],
                  body=pvc)
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.create_namespaced_deployment,
                  namespace=deploy["metadata"]["namespace"],
                  body=deploy)
        return [
            DeploymentDestroyer(when=destroy_time,
                                namespace=deploy["metadata"]["namespace"],
                                deployment=deploy["metadata"]["name"],
                                pvc=pvc["metadata"]["name"]),
            ExponentialDeployment(self._interarrival, self._lifetime,
                                  self._active, self._idle)
        ]

class DeploymentDestroyer(Event):
    """Destroy a Deployment at some time in the future."""

    def __init__(self, when: float, namespace: str, deployment: str, pvc: str):
        self._namespace = namespace
        self._deployment = deployment
        self._pvc = pvc
        super().__init__(when)

    def execute(self) -> 'List[Event]':
        print(f"Smackdown! {self._namespace}/{self._deployment}")
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.delete_namespaced_deployment,
                  name=self._deployment,
                  namespace=self._namespace,
                  body=k8s.V1DeleteOptions())
        core_v1 = k8s.CoreV1Api()
        kube.call(core_v1.delete_namespaced_persistent_volume_claim,
                  namespace=self._namespace,
                  name=self._pvc,
                  body=k8s.V1DeleteOptions())

        return []
