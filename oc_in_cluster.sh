#! /bin/bash

sa_dir=/var/run/secrets/kubernetes.io/serviceaccount

/oc --server=https://kubernetes.default.svc.cluster.local \
    --token="$(cat $sa_dir/token)" \
    --certificate-authority="$sa_dir/ca.crt" \
    "$@"
