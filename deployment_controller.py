from copy import deepcopy
import random
import time
from typing import Any, Callable, Dict, List  # pylint: disable=unused-import

from event import Event
import kube
import kubernetes.client as k8s

def uniquify_deployment(deploy: kube.MANIFEST) -> kube.MANIFEST:
    """
    Make a deployment unique.

    Deployments need to be unique in name and label selector(s) for the
    controlled pods.
    """
    out = deepcopy(deploy)
    uid = time.perf_counter_ns()
    # Unique name for the Deployment
    out["metadata"]["name"] = f'{out["metadata"]["name"]}-{uid}'
    # Set up the label selector on the Deployment
    out["spec"]["selector"] = {
        "matchLabels": {
            "deployment-id": str(uid)
        }
    }
    # Set up the correcponding label on the Pod template
    out["spec"]["template"].setdefault("metadata", {})
    labels = out["spec"]["template"]["metadata"].setdefault("labels", {})
    labels["deployment-id"] = str(uid)
    out["spec"]["template"]["metadata"]["labels"] = labels
    return out

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
                 idle: float,
                 deployment: kube.MANIFEST) -> None:
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
            deployment: A dict describing the deployment object to create

        """
        self._interarrival = interarrival
        self._lifetime = lifetime
        self._active = active
        self._idle = idle
        self._deployment = deepcopy(deployment)
        super().__init__(when=time.time() +
                         random.expovariate(1/self._interarrival))

    def execute(self) -> 'List[Event]':
        """Create a new Deployment & schedule it's destruction."""
        destroy_time = time.time() + random.expovariate(1/self._lifetime)
        deploy = uniquify_deployment(self._deployment)
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
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.create_namespaced_deployment,
                  namespace=deploy["metadata"]["namespace"],
                  body=deploy)
        return [
            DeploymentDestroyer(when=destroy_time,
                                namespace=deploy["metadata"]["namespace"],
                                name=deploy["metadata"]["name"]),
            ExponentialDeployment(self._interarrival, self._lifetime,
                                  self._active, self._idle, self._deployment)
        ]

class DeploymentDestroyer(Event):
    """Destroy a Deployment at some time in the future."""

    def __init__(self, when: float, namespace: str, name: str):
        self._namespace = namespace
        self._name = name
        super().__init__(when)

    def execute(self) -> 'List[Event]':
        print(f"Smackdown! {self._namespace}/{self._name}")
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.delete_namespaced_deployment,
                  name=self._name,
                  namespace=self._namespace,
                  body=k8s.V1DeleteOptions())
        return []
