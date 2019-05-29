#! /usr/bin/env python3
"""Ensure we can create namespaces."""

import kubernetes.client as k8s
import pytest
from util import handle_api


@pytest.mark.usefixtures("load_kubeconfig")
def test_can_create_namespace():
    """Test whether we can create a namespace."""
    import time

    core_v1 = k8s.CoreV1Api()
    ns_name = f"ns-{time.perf_counter_ns()}"
    namespace = handle_api(core_v1.create_namespace,
                           body={
                               "metadata": {
                                   "name": ns_name
                               }
                           })
    assert namespace.metadata.name == ns_name

    handle_api(core_v1.delete_namespace,
               name=namespace.metadata.name,
               body=k8s.V1DeleteOptions())


if __name__ == '__main__':
    pytest.main([__file__])
