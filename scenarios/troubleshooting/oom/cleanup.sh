#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-oom --ignore-not-found --wait=false
