#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-readiness-probe --ignore-not-found --wait=false
