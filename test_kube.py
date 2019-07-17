"""Tests for kubernetes helper functions."""

import random

import kubernetes.client as k8s
from kubernetes.client.rest import ApiException
import pytest

import kube

@pytest.mark.kube_required
def test_create_namespace():
    """We can create a new namespace."""
    ns_name = f"ns-{random.randrange(999999999)}"
    res = kube.create_namespace(ns_name)
    assert res["metadata"]["name"] == ns_name
    _delete_namespace(ns_name)

@pytest.mark.kube_required
def test_exclusive_ns_create():
    """Namespace creation fails by default if it already exists."""
    ns_name = f"ns-{random.randrange(999999999)}"
    kube.create_namespace(ns_name)
    with pytest.raises(ApiException):
        kube.create_namespace(ns_name)
    _delete_namespace(ns_name)

@pytest.mark.kube_required
def test_existing_ns_create():
    """Namespace creation succeeds with existing if existing_ok."""
    ns_name = f"ns-{random.randrange(999999999)}"
    res = kube.create_namespace(ns_name)
    res2 = kube.create_namespace(ns_name, existing_ok=True)
    assert res["metadata"]["name"] == ns_name
    assert res2["metadata"]["name"] == ns_name
    _delete_namespace(ns_name)

def _delete_namespace(ns_name: str) -> None:
    core_v1 = k8s.CoreV1Api()
    kube.call(core_v1.delete_namespace,
              name=ns_name,
              body=k8s.V1DeleteOptions())
