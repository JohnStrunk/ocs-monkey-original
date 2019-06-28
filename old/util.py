"""Helper functions."""

import time

import kubernetes
import kubernetes.client as k8s
from kubernetes.client.rest import ApiException


def handle_api(func, *args, **kwargs):
    """
    Call kubernetes.client APIs and handle Execptions.

    Params:
        func:  The API function
        codes: A dict of how to respond to exeception codes
        (other args are passed to func)

    Returns:
        The return value from calling func

    """
    fkwargs = kwargs.copy()
    codes = kwargs.get("codes")
    if codes is None:
        codes = {500: "retry"}
    else:
        del fkwargs["codes"]
    while True:
        try:
            result = func(*args, **fkwargs)
            break
        except ApiException as ex:
            action = codes.get(ex.status)
            if action == "ignore":
                return result
            if action == "retry":
                time.sleep(1)
                continue
            raise
    return result


def start_and_waitfor_pod(pod_dict):
    """
    Create a pod and wait for it to be Running.

    Params:
        pod_dict: A dict describing the pod to create

    Returns:
        A V1Pod that has achieved the "Running" status.phase

    """
    core_v1 = k8s.CoreV1Api()
    pod = handle_api(core_v1.create_namespaced_pod,
                     namespace=pod_dict["metadata"]["namespace"],
                     body=pod_dict)

    watch = kubernetes.watch.Watch()
    for event in watch.stream(
            func=core_v1.list_namespaced_pod,
            namespace=pod.metadata.namespace,
            field_selector=f"metadata.name={pod.metadata.name}"):
        if event["object"].status.phase == "Running":
            watch.stop()
    return pod
