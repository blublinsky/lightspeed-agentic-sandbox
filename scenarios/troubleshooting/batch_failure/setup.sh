#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-batch-failure"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: data-import
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: importer
          image: busybox:1.36
          command: ["sh", "-c", "echo 'Import failed: connection timeout' >&2; exit 1"]
EOF

if ! oc wait --for=condition=failed job/data-import -n "$NAMESPACE" --timeout=60s; then
  echo "data-import job did not reach Failed condition" >&2
  exit 1
fi
