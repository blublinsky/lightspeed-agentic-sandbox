#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-ingress-mismatch --ignore-not-found --wait=false
