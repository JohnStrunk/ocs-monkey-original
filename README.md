# OCS-Monkey

[![Build Status](https://travis-ci.com/JohnStrunk/ocs-monkey.svg?branch=master)](https://travis-ci.com/JohnStrunk/ocs-monkey)

This repo is designed to provide a randomized load for "chaos testing".

## Usage

```
source setup-env.sh
KUBECONFIG=/path/to/your/kubeconfig runner.py
```

## Status

Currently, lots of things are hard coded:
- The namespace used: `monkey`
- The StorageClass: `gp2`
- The creation & lifetimes of the Deployments

There is also no monitoring to ensure the pods start/function as intended.
