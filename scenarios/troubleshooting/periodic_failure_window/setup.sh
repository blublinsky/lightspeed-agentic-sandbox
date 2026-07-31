#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-periodic-failure"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-sync
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      backoffLimit: 0
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: sync
              image: busybox:1.36
              command: ["sh", "-c", "echo 'sync failure: upstream unreachable at 03:00' >&2; exit 1"]
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: failure-log
data:
  history.log: |
    2026-07-28T03:00:45Z nightly-sync FAILED: upstream unreachable
    2026-07-27T03:00:33Z nightly-sync FAILED: upstream unreachable
    2026-07-26T03:00:51Z nightly-sync FAILED: upstream unreachable
    2026-07-25T03:00:28Z nightly-sync FAILED: upstream unreachable
    2026-07-24T09:00:12Z nightly-sync SUCCESS
EOF
