"""Test fixtures for pytest."""

import random

import kubernetes
import kubernetes.client as k8s
import pytest

import util


@pytest.fixture(scope="module")
def load_kubeconfig():
    """Load the kube configuration so we can contact the cluster."""
    kubernetes.config.load_kube_config()


@pytest.fixture(params=["csi-cephfs", "csi-rbd", "gp2"])
def storageclass_iterator(request):
    """Allow a test to iterate across a number of storage classes."""
    return request.param


@pytest.fixture
def unique_namespace(request, load_kubeconfig):
    """
    Create a namespace in which to run a test.

    This will create a namespace with a random name and automatically delete it
    at the end of the test.

    Returns:
        V1Namespace object describing the namespace that has been created for
        this test.

    """
    core_v1 = k8s.CoreV1Api()
    ns_name = f"ns-{random.randrange(999999999)}"
    namespace = util.handle_api(core_v1.create_namespace,
                                body={
                                    "metadata": {
                                        "name": ns_name
                                    }
                                })

    def teardown():
        util.handle_api(core_v1.delete_namespace,
                        name=namespace.metadata.name,
                        body=k8s.V1DeleteOptions())
    request.addfinalizer(teardown)
    return namespace
