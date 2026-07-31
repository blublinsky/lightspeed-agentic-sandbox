#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-config-drift --ignore-not-found --wait=false
