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


import concurrent.futures
import copy
import logging
import random
import time
from typing import Any, Callable, Dict, List  # pylint: disable=unused-import

import kubernetes
import kubernetes.client as k8s

import kube
from event import Event

LOGGER = logging.getLogger(__name__)
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=100)
WORKAROUND_MIN_RUNTIME = True

class UnhealthyDeployment(Exception):
    """Exception raised when a workload instance fails its health check.

    Attributes:
        namespace: The namespace that contains the pod
        name: The name of the Deployment

    """

    def __init__(self, namespace: str, name: str):
        """Create an exception for an unhealthy Deployment instance."""
        self.namespace = namespace
        self.name = name
        super().__init__(self, namespace, name)


def start(namespace: str,  # pylint: disable=too-many-arguments
          storage_class: str,
          access_mode: str,
          interarrival: float,
          lifetime: float,
          active: float,
          idle: float) -> Event:
    """
    Start the workload.

    Parameters:
        namespace: The namespace where objects should be placed/managed
        storage_class: The StorageClass name to use in PVCs
        access_mode: The access mode to request for the PVC. Available options:
            ReadWriteOnce, ReadWriteMany
        interarrival: The mean interarrival time (in seconds) for creating new
            workloads
        lifetime: The mean lifetime (in seconds) of a Deployment once it has
            been created.
        active: The mean active time for the Deployment's pod before it
            becomes idle.
        idle: The mean idle time for the Deployment before it becomes
            active.

    Returns:
        The initial Event that starts the workload. This Event should be queued
        into the Dispatcher.

    """
    LOGGER.info("starting run iat:%.1f life:%.1f active:%.1f idle:%.1f",
                interarrival, lifetime, active, idle)
    LOGGER.info("namespace: %s", namespace)
    LOGGER.info("storageclass: %s", storage_class)
    LOGGER.info("pvc access mode: %s", access_mode)
    LOGGER.info("Average # of deployments: %.1f", lifetime/interarrival)
    LOGGER.info("Fraction of deployments active: %.2f", active/(active+idle))
    LOGGER.info("Transitions per deployment: %.1f", 2*(active+idle)/lifetime)
    if WORKAROUND_MIN_RUNTIME:
        LOGGER.warning("Workaround enabled: min pod runtime")

    return Creator(namespace=namespace,
                   storage_class=storage_class,
                   access_mode=access_mode,
                   interarrival=interarrival,
                   lifetime=lifetime,
                   active=active,
                   idle=idle)

def resume(namespace: str) -> List[Event]:
    """
    Re-adopt deployments that were previously created.

    If the workload generator exits, Deployments that were created from the
    previous instance will still be present in the cluster. If the workload
    generator is subsequently restarted, this function can be used to locate and
    "adopt" those alread-present deployments, resuming their scheduled lifecycle
    events.

    Some lifecycle events may have been missed while the generator was down, but
    they will be processed immediately once the deployments are adopted.

    Parameters:
        namespace: The namespace containing the deployments

    Returns:
        a list of Events to be enqueued onto the Dispatcher

    """
    events: List[Event] = []
    apps_v1 = k8s.AppsV1Api()
    deployments = kube.call(apps_v1.list_namespaced_deployment,
                            namespace=namespace,
                            label_selector='ocs-monkey/controller=osio')
    for deployment in deployments["items"]:
        LOGGER.info("Found: %s/%s", deployment["metadata"]["namespace"],
                    deployment["metadata"]["name"])
        events.append(Lifecycle(when=0,
                                namespace=deployment["metadata"]["namespace"],
                                name=deployment["metadata"]["name"]))
    return events

def _matchlabel_from_deployment(deployment: kube.MANIFEST) -> str:
    selector = deployment["spec"]["selector"]
    if "matchLabels" in selector:  # when created as a dict
        did = selector["matchLabels"]["deployment-id"]
    else:  # when object converted to dict
        did = selector["match_labels"]["deployment-id"]
    return f'deployment-id={did}'

def _pod_start_watcher(deployment: kube.MANIFEST) -> None:
    namespace = deployment["metadata"]["namespace"]
    name = deployment["metadata"]["name"]
    full_name = f'{namespace}/{name}'
    label = _matchlabel_from_deployment(deployment)
    LOGGER.debug("watcher for %s", full_name)
    start_time = time.time()
    watch = kubernetes.watch.Watch()
    core_v1 = k8s.CoreV1Api()
    for event in watch.stream(func=core_v1.list_namespaced_pod,
                              namespace=namespace,
                              label_selector=label,
                              timeout_seconds=60):
        if event["object"].status.phase == "Running":
            watch.stop()
            end_time = time.time()
            LOGGER.info("%s started in %0.2f sec", full_name, end_time-start_time)
            return
        # event.type: ADDED, MODIFIED, DELETED
        if event["type"] == "DELETED":
            # Pod was deleted while we were waiting for it to start.
            LOGGER.debug("%s deleted before it started", full_name)
            watch.stop()
            return
    LOGGER.warning("Gave up waiting for start of %s", full_name)

def _pod_stop_watcher(deployment: kube.MANIFEST) -> None:
    namespace = deployment["metadata"]["namespace"]
    name = deployment["metadata"]["name"]
    full_name = f'{namespace}/{name}'
    label = _matchlabel_from_deployment(deployment)
    LOGGER.debug("watcher for %s", full_name)
    start_time = time.time()
    watch = kubernetes.watch.Watch()
    core_v1 = k8s.CoreV1Api()
    for event in watch.stream(func=core_v1.list_namespaced_pod,
                              namespace=namespace,
                              label_selector=label,
                              timeout_seconds=60):
        # event.type: ADDED, MODIFIED, DELETED
        if event["type"] == "DELETED":
            end_time = time.time()
            watch.stop()
            LOGGER.info("%s stopped in %0.2f sec", full_name, end_time-start_time)
            return
    LOGGER.warning("Gave up waiting for termination of %s", full_name)

def _get_workload(ns_name: str,
                  sc_name: str,
                  access_mode: str) -> Dict[str, kube.MANIFEST]:
    """
    Generate a workload description.

    The description contains "uniquified" manifests suitable for giving to the
    kubernetes API.
    """
    manifests = {}
    unique_id = str(random.randrange(999999999))

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
                        "name": "osio-workload",
                        "image": "quay.io/johnstrunk/osio-workload",
                        "args": [
                            "--untar-rate", "10",
                            "--rm-rate", "10",
                            "--kernel-slots", "3"
                        ],
                        "readinessProbe": {
                            "exec": {
                                "command": ["/health.sh"]
                            },
                            "initialDelaySeconds": 5,
                            "periodSeconds": 10
                        },
                        "volumeMounts": [{
                            "name": "temp",
                            "mountPath": "/status"
                        }, {
                            "name": "data",
                            "mountPath": "/data"
                        }]
                    }],
                    "volumes": [{
                        "name": "temp",
                        "emptyDir": {
                            "medium": "Memory"
                        }
                    }, {
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
            "accessModes": [access_mode],
            "resources": {
                "requests": {
                    # kernel src is 656 MB * 4 slots < 3 Gi
                    "storage": "3Gi"
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

    def __init__(self,  # pylint: disable=too-many-arguments
                 namespace: str,
                 storage_class: str,
                 access_mode: str,
                 interarrival: float,
                 lifetime: float,
                 active: float,
                 idle: float) -> None:
        """
        Deployments are created and destroyed at some random rate.

        Given some mean interarrival time, a, and lifetime, l, the average
        number of Deployments that would be expected to exist is (l/a) according
        to Little's Law.
        """
        self._namespace = namespace
        self._storage_class = storage_class
        self._access_mode = access_mode
        self._interarrival = interarrival
        self._lifetime = lifetime
        self._active = active
        self._idle = idle
        super().__init__(when=time.time() +
                         random.expovariate(1/self._interarrival))

    def execute(self) -> 'List[Event]':
        """Create a new Deployment & schedule it's destruction."""
        destroy_time = time.time() + random.expovariate(1/self._lifetime)
        manifests = _get_workload(self._namespace, self._storage_class,
                                  self._access_mode)
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
        EXECUTOR.submit(_pod_start_watcher, deploy)
        return [
            Lifecycle(when=0,  # execute asap
                      namespace=deploy["metadata"]["namespace"],
                      name=deploy["metadata"]["name"],
                      ),
            Creator(self._namespace,
                    self._storage_class,
                    self._access_mode,
                    self._interarrival,
                    self._lifetime,
                    self._active,
                    self._idle)
        ]

class Lifecycle(Event):
    """Manage the lifecycle of a workload instance."""

    _health_interval = 10  # When already running
    _health_interval_initial = 90  # When pod starting

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
        idle_duration = random.expovariate(1/idle_mean)
        if WORKAROUND_MIN_RUNTIME:
            idle_duration = max(idle_duration, self._health_interval_initial)
        idle_time = time.time() + idle_duration
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
        EXECUTOR.submit(_pod_stop_watcher, copy.deepcopy(deploy))
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
                LOGGER.error("Unhealthy: %s/%s", self._namespace, self._name)
                raise UnhealthyDeployment(self._namespace, self._name)
        anno = deploy["metadata"]["annotations"]
        health_time = time.time() + self._health_interval
        anno["ocs-monkey/osio-health-at"] = str(health_time)
        return deploy

    def _action_idle(self, deploy: kube.MANIFEST) -> kube.MANIFEST:
        anno = deploy["metadata"]["annotations"]
        if deploy["spec"]["replicas"] == 0:  # idle -> active
            deploy["spec"]["replicas"] = 1
            active_mean = float(anno["ocs-monkey/osio-active"])
            active_duration = random.expovariate(1/active_mean)
            if WORKAROUND_MIN_RUNTIME:
                active_duration = max(active_duration, self._health_interval_initial)
            idle_time = time.time() + active_duration
            health_time = time.time() + self._health_interval_initial
            LOGGER.info("idle->active: %s/%s", self._namespace, self._name)
            EXECUTOR.submit(_pod_start_watcher, copy.deepcopy(deploy))
        else:  # active -> idle
            deploy["spec"]["replicas"] = 0
            idle_mean = float(anno["ocs-monkey/osio-idle"])
            idle_duration = random.expovariate(1/idle_mean)
            if WORKAROUND_MIN_RUNTIME:
                idle_duration = max(idle_duration, self._health_interval_initial)
            idle_time = time.time() + idle_duration
            health_time = time.time() + self._health_interval
            LOGGER.info("active->idle: %s/%s", self._namespace, self._name)
            EXECUTOR.submit(_pod_stop_watcher, copy.deepcopy(deploy))
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
