#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="fleet-alpha"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fleet-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fleet-worker
  template:
    metadata:
      labels:
        app: fleet-worker
    spec:
      containers:
        - name: worker
          image: busybox:1.36
          command: ["sleep", "3600"]
EOF

oc rollout status deployment/fleet-worker -n "$NAMESPACE" --timeout=120s
