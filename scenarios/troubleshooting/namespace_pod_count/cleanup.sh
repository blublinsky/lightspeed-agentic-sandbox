#!/usr/bin/env bash
set -euo pipefail

oc delete namespace fleet-alpha --ignore-not-found --wait=false
