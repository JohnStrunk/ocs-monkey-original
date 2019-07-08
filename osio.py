"""
Randomized workload generator to mimic OSIO.

The workload can be started by instantiating a single Event of type Creator. The
Creator event re-queues itself indefinitiely to cause Workload deployments to be
repeatedly created according to a random distribution. For each Deployment (and
associated resources) that it creates, it schedules a Lifecycle Event to manage
the lifecycle of that workload instance. Lifecycle handles all milestones/phase
transitions for the workload. It also monitors the workload's health. The final
task of the Lifecycle event is to destroy the workload's resources.
"""


import logging
import random
import time
from typing import Any, Callable, Dict, List  # pylint: disable=unused-import

import kubernetes.client as k8s

import kube
from event import Event

LOGGER = logging.getLogger(__name__)

def start(interarrival: float,
          lifetime: float,
          active: float,
          idle: float) -> Event:
    """Start the workload."""
    print("Avg # of deployments (life/interrarival):", lifetime/interarrival)
    print("Pct of deployments active (active/(active+idle)):",
          active/(active+idle))
    print("Transitions per deployment (2(active+idle)/lifetime):",
          2*(active+idle)/lifetime)
    LOGGER.info("starting run iat:%f life:%f active:%f idle:%f",
                interarrival, lifetime, active, idle)
    return Creator(interarrival=interarrival, lifetime=lifetime, active=active,
                   idle=idle)

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
            "labels": {
                "ocs-monkey/controller": "osio"
            }
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
                        "readinessProbe": {
                            "exec": {
                                "command": ["touch", "/mnt/writable"]
                            },
                            "initialDelaySeconds": 5,
                            "periodSeconds": 10
                        },
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

class Creator(Event):
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
        manifests = _get_workload("monkey", "csi-rbd")
        # manifests = _get_workload("monkey2", "gp2")
        pvc = manifests["pvc"]
        deploy = manifests["deployment"]
        # Set necessary accotations on the Deployment
        anno = deploy["metadata"].setdefault("annotations", {})
        anno["ocs-monkey/osio-active"] = str(self._active)
        anno["ocs-monkey/osio-idle"] = str(self._idle)
        anno["ocs-monkey/osio-destroy-at"] = str(destroy_time)
        anno["ocs-monkey/osio-pvc"] = pvc["metadata"]["name"]
        deploy["metadata"]["annotations"] = anno
        LOGGER.info("Create: %s/%s, %s",
                    deploy["metadata"]["namespace"],
                    deploy["metadata"]["name"],
                    pvc["metadata"]["name"])
        core_v1 = k8s.CoreV1Api()
        kube.call(core_v1.create_namespaced_persistent_volume_claim,
                  namespace=pvc["metadata"]["namespace"],
                  body=pvc)
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.create_namespaced_deployment,
                  namespace=deploy["metadata"]["namespace"],
                  body=deploy)
        return [
            Lifecycle(when=0,  # execute asap
                      namespace=deploy["metadata"]["namespace"],
                      name=deploy["metadata"]["name"],
                      ),
            Creator(self._interarrival, self._lifetime, self._active,
                    self._idle)
        ]

class Lifecycle(Event):
    """Manage the lifecycle of a workload instance."""

    _health_interval = 10  # When already running
    _health_interval_initial = 60  # When pod starting

    def __init__(self, when: float, namespace: str, name: str) -> None:
        """
        Create a lifecycle event.

        Parameters:
            when: The time the event should execute
            namespace: The namespace of the workload's Deployment
            name: The name of the workload's Deployment

        """
        self._namespace = namespace
        self._name = name
        super().__init__(when)

    def _get_deployment(self) -> kube.MANIFEST:
        apps_v1 = k8s.AppsV1Api()
        v1dl = kube.call(apps_v1.list_namespaced_deployment,
                         namespace=self._namespace,
                         field_selector=f'metadata.name={self._name}')
        return v1dl["items"][0]  # type: ignore

    def _action_initialize(self, deploy: kube.MANIFEST) -> kube.MANIFEST:
        anno = deploy["metadata"]["annotations"]
        idle_mean = float(anno["ocs-monkey/osio-idle"])
        idle_time = time.time() + random.expovariate(1/idle_mean)
        anno["ocs-monkey/osio-idle-at"] = str(idle_time)
        health_time = time.time() + self._health_interval_initial
        anno["ocs-monkey/osio-health-at"] = str(health_time)
        return deploy

    def _action_destroy(self, deploy: kube.MANIFEST) -> None:
        anno = deploy["metadata"]["annotations"]
        pvc_name = anno["ocs-monkey/osio-pvc"]
        LOGGER.info("Destroy: %s/%s, %s",
                    self._namespace,
                    self._name,
                    pvc_name)
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.delete_namespaced_deployment,
                  namespace=self._namespace,
                  name=self._name,
                  body=k8s.V1DeleteOptions())
        core_v1 = k8s.CoreV1Api()
        kube.call(core_v1.delete_namespaced_persistent_volume_claim,
                  namespace=self._namespace,
                  name=pvc_name,
                  body=k8s.V1DeleteOptions())

    def _action_health(self, deploy: kube.MANIFEST) -> kube.MANIFEST:
        if deploy["spec"]["replicas"] == 1:  # active
            if deploy["status"].get("ready_replicas") != 1:
                LOGGER.warning("Unhealthy: %s/%s", self._namespace, self._name)
        anno = deploy["metadata"]["annotations"]
        health_time = time.time() + self._health_interval
        anno["ocs-monkey/osio-health-at"] = str(health_time)
        return deploy

    def _action_idle(self, deploy: kube.MANIFEST) -> kube.MANIFEST:
        anno = deploy["metadata"]["annotations"]
        if deploy["spec"]["replicas"] == 0:  # idle -> active
            deploy["spec"]["replicas"] = 1
            active_mean = float(anno["ocs-monkey/osio-active"])
            idle_time = time.time() + random.expovariate(1/active_mean)
            health_time = time.time() + self._health_interval_initial
            LOGGER.info("idle->active: %s/%s", self._namespace, self._name)
        else:  # active -> idle
            deploy["spec"]["replicas"] = 0
            idle_mean = float(anno["ocs-monkey/osio-idle"])
            idle_time = time.time() + random.expovariate(1/idle_mean)
            health_time = time.time() + self._health_interval
            LOGGER.info("active->idle: %s/%s", self._namespace, self._name)
        anno["ocs-monkey/osio-idle-at"] = str(idle_time)
        anno["ocs-monkey/osio-health-at"] = str(health_time)
        return deploy

    def _update_and_schedule(self, deploy: kube.MANIFEST) -> List[Event]:
        """
        Update (patch) the Deployment and schedule the next Event.

        This assumes proper changes have been made to the Deployment manifest
        and the next times for each lifecycle event have been set in the proper
        annotation.
        """
        anno = deploy["metadata"]["annotations"]
        destroy_time = float(anno["ocs-monkey/osio-destroy-at"])
        idle_time = float(anno["ocs-monkey/osio-idle-at"])
        health_time = float(anno["ocs-monkey/osio-health-at"])
        next_time = min(destroy_time, idle_time, health_time)
        anno["ocs-monkey/osio-next-time"] = str(next_time)
        if next_time == destroy_time:
            anno["ocs-monkey/osio-next-action"] = "destroy"
        elif next_time == idle_time:
            anno["ocs-monkey/osio-next-action"] = "idle"
        else:
            anno["ocs-monkey/osio-next-action"] = "health"
        apps_v1 = k8s.AppsV1Api()
        kube.call(apps_v1.patch_namespaced_deployment,
                  namespace=self._namespace,
                  name=self._name,
                  body=deploy)
        return [Lifecycle(next_time, self._namespace, self._name)]

    def execute(self) -> List[Event]:
        """Execute the lifecycle event."""
        # Retrieve the Deployment object
        deploy = self._get_deployment()
        anno = deploy["metadata"].setdefault("annotations", {})
        # If lifecycle annotations are missing, initialize them
        if "ocs-monkey/osio-next-action" not in anno:
            deploy = self._action_initialize(deploy)
            return self._update_and_schedule(deploy)

        etime = float(anno["ocs-monkey/osio-next-time"])
        if etime > time.time():  # we ran too early... reschedule
            return [Lifecycle(etime, self._namespace, self._name)]

        # Lifecycle actions
        eaction = anno["ocs-monkey/osio-next-action"]
        if eaction == "destroy":
            self._action_destroy(deploy)
            return []  # Stop here since we destroyed the resources
        if eaction == "health":
            self._action_health(deploy)
        elif eaction == "idle":
            self._action_idle(deploy)
        else:
            assert False, f'Unknown next action: {eaction}'
        return self._update_and_schedule(deploy)