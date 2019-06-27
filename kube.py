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
    return dict(result.to_dict())

def create_namespace(name: str) -> MANIFEST:
    body = {
        "metadata": {
            "name": name
        }
    }
    core_v1 = k8s.CoreV1Api()
    return call(core_v1.create_namespace, body=body)
