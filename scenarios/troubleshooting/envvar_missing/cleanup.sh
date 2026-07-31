#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-envvar-missing --ignore-not-found --wait=false
