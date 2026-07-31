#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-scheduled-outage --ignore-not-found --wait=false
