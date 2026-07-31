#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-periodic-failure --ignore-not-found --wait=false
