"""Test fixtures for pytest."""

import random

import kubernetes
import kubernetes.client as k8s
import pytest

import kube

def pytest_addoption(parser):
    """Add command-line options to pytest."""
    parser.addoption(
        "--run-kube-tests", action="store_true", default=False,
        help="run tests that require a Kubernetes or OpenShift cluster"
    )
    parser.addoption(
        "--run-benchmarks", action="store_true", default=False,
        help="run benchmark tests (also needs kubernetes)"
    )

def pytest_configure(config):
    """Define kube_required pytest mark."""
    config.addinivalue_line("markers", "kube_required: mark test as requiring kubernetes")

def pytest_collection_modifyitems(config, items):
    """Only run kube_required tests when --run-kube-tests is used."""
    if not config.getoption("--run-kube-tests"):
        skip_kube = pytest.mark.skip(reason="need --run-kube-tests option to run")
        for item in items:
            if "kube_required" in item.keywords:
                item.add_marker(skip_kube)
    if not config.getoption("--run-benchmarks"):
        skip_bench = pytest.mark.skip(reason="need --run-benchmarks option to run")
        for item in items:
            if "benchmark" in item.keywords:
                item.add_marker(skip_bench)



@pytest.fixture(scope="module")
def load_kubeconfig():
    """Load the kube configuration so we can contact the cluster."""
    kubernetes.config.load_kube_config()


@pytest.fixture(params=["csi-cephfs", "csi-rbd", "gp2"])
def storageclass_iterator(request):
    """Allow a test to iterate across a number of storage classes."""
    return request.param


@pytest.fixture
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
def unique_namespace(request, load_kubeconfig):
    """
    Create a namespace in which to run a test.

    This will create a namespace with a random name and automatically delete it
    at the end of the test.

    Returns:
        dict describing the namespace that has been created for this test.

    """
    core_v1 = k8s.CoreV1Api()
    ns_name = f"ns-{random.randrange(999999999)}"
    namespace = kube.call(core_v1.create_namespace,
                          body={
                              "metadata": {
                                  "name": ns_name
                                  }
                              })

    def teardown():
        kube.call(core_v1.delete_namespace,
                  name=namespace["metadata"]["name"],
                  body=k8s.V1DeleteOptions())
    request.addfinalizer(teardown)
    return namespace
