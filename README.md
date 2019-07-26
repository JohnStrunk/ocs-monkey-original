# OCS-Monkey

[![Build Status](https://travis-ci.com/JohnStrunk/ocs-monkey.svg?branch=master)](https://travis-ci.com/JohnStrunk/ocs-monkey)

This repo is designed to provide a randomized load for "chaos testing".

## Status

- Generator container: [![Docker Repository on
  Quay](https://quay.io/repository/johnstrunk/ocs-monkey-generator/status
  "Docker Repository on
  Quay")](https://quay.io/repository/johnstrunk/ocs-monkey-generator)
- Workload container: [![Docker Repository on
  Quay](https://quay.io/repository/johnstrunk/osio-workload/status "Docker
  Repository on Quay")](https://quay.io/repository/johnstrunk/osio-workload)

Prioritization & project work are tracked in [Work
items](https://github.com/JohnStrunk/ocs-monkey/projects/1)

## Usage

The generator can be run from the command-line or via a Helm chart.

Command line invocation:

```
source setup-env.sh
KUBECONFIG=/path/to/your/kubeconfig workload_runner.py
```

A number of options are available:

```
$ ./workload_runner.py --help
usage: workload_runner.py [-h] [-l LOG_DIR] [-m {ReadWriteOnce,ReadWriteMany}]
                 [-n NAMESPACE] [--oc OC] [--ocs-namespace OCS_NAMESPACE]
                 [-s STORAGECLASS] [-z]

optional arguments:
  -h, --help            show this help message and exit
  -l LOG_DIR, --log-dir LOG_DIR
                        Path to use for log files
  -m {ReadWriteOnce,ReadWriteMany}, --accessmode {ReadWriteOnce,ReadWriteMany}
                        StorageClassName for the workload's PVCs
  -n NAMESPACE, --namespace NAMESPACE
                        Namespace to use for the workload
  --oc OC               Path/executable for the oc command
  --ocs-namespace OCS_NAMESPACE
                        Namespace where the OCS components are running
  -s STORAGECLASS, --storageclass STORAGECLASS
                        StorageClassName for the workload's PVCs
  -z, --sleep-on-error  On error, sleep forever instead of exit
```

Deployment via the Helm chart (using Helm v3):

```
$ KUBECONFIG=~/src/osio4/kubeconfig helm install foo helm/ocs-monkey-generator
NAME: foo
LAST DEPLOYED: 2019-07-25 15:31:07.04315199 -0400 EDT m=+0.615644812
NAMESPACE: default
STATUS: deployed

NOTES:
ocs-monkey workload generator has been deployed!

Generator is running in namespace: default
```

By default, the generator will create & destroy Deployments in the namespace
`ocs-monkey`, stopping and collecting logs when it detects a problem.
