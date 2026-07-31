#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-storage-binding --ignore-not-found --wait=false
