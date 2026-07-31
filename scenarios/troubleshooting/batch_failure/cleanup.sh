#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-batch-failure --ignore-not-found --wait=false
