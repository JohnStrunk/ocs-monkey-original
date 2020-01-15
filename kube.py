"""
Helper module for using the Python Kubernetes library.

This module is structured so that only dict objects are used in both calls and
responses in order to make working with the API more straightforward.
"""

import os
import time
from typing import Any, Callable, Dict  # pylint: disable=unused-import

import kubernetes
import kubernetes.client as k8s
from kubernetes.client.rest import ApiException


MANIFEST = Dict[str, Any]

# Load the kubernetes config so we can interact w/ the API
if os.getenv('KUBERNETES_SERVICE_HOST'):
    kubernetes.config.load_incluster_config()
else:
    kubernetes.config.load_kube_config()


def call(api: 'Callable[..., Any]', *args: Any, **kwargs: Any) -> MANIFEST:
    """
    Call the kubernetes client APIs and handle the exceptions.

    Parameters:
        api: The api function to call
        codes: A dict describing how to handle exception codes
        (other args are passed to the API function)

    Returns:
        The response from the API function as a dict

    """
    fkwargs = kwargs.copy()
    codes = kwargs.get("codes")
    if codes is None:
        codes = {500: "retry"}
    else:
        del fkwargs["codes"]
    while True:
        try:
            result = api(*args, **fkwargs)
            break
        except ApiException as ex:
            action = codes.get(ex.status)
            if action == "ignore":
                return dict()
            if action == "retry":
                time.sleep(1)
                continue
            raise
    if isinstance(result, dict):
        return result
    return dict(result.to_dict())

def create_namespace(name: str, existing_ok: bool = False) -> MANIFEST:
    """
    Create a namespace.

    Parameters:
        name: The name for the namespace to create
        existing_ok: True if it is ok for the namespace to already exist

    Returns:
        A dict describing the namespace that was created

    """
    body = {
        "metadata": {
            "name": name
        }
    }
    core_v1 = k8s.CoreV1Api()
    try:
        return call(core_v1.create_namespace, body=body)
    except ApiException as ex:
        if ex.status != 409 or not existing_ok:
            raise

    ns_list = call(core_v1.list_namespace,
                   field_selector=f'metadata.name={name}')
    return ns_list["items"][0]  # type: ignore

def deployment_is_ready(namespace: str, name: str) -> bool:
    """Determine if a Deployment's pods are passing readiness check."""
    apps_v1 = k8s.AppsV1Api()
    deployments = call(apps_v1.list_namespaced_deployment,
                       namespace=namespace,
                       field_selector=f'metadata.name={name}')
    if not deployments["items"]:
        return False
    deployment = deployments["items"][0]
    if deployment["spec"]["replicas"] == deployment["status"].get("ready_replicas"):
        return True
    return False
