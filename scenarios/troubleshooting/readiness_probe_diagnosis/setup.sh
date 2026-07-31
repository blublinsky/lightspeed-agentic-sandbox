#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-readiness-probe"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web-frontend
  template:
    metadata:
      labels:
        app: web-frontend
    spec:
      containers:
        - name: frontend
          image: busybox:1.36
          command: ["sleep", "3600"]
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 2
            periodSeconds: 5
            failureThreshold: 3
EOF

deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  phase="$(oc get pods -n "$NAMESPACE" -l app=web-frontend \
    -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)"
  ready="$(oc get pods -n "$NAMESPACE" -l app=web-frontend \
    -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null || true)"
  [[ "$phase" == "Running" && "$ready" == "false" ]] && exit 0
  sleep 3
done
echo "Expected Running/NotReady but got phase=${phase:-missing} ready=${ready:-missing}" >&2
exit 1
