#!/usr/bin/env bash
set -euo pipefail

oc delete namespace troubleshoot-wrong-netpol --ignore-not-found --wait=false
