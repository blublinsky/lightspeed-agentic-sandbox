#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-oom"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-hog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: memory-hog
  template:
    metadata:
      labels:
        app: memory-hog
    spec:
      containers:
        - name: hog
          image: busybox:1.36
          command: ["sh", "-c", "while true; do dd if=/dev/urandom bs=1M count=10 >> /dev/shm/oom 2>/dev/null; done"]
          resources:
            limits:
              memory: "64Mi"
            requests:
              memory: "64Mi"
EOF

deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  reason="$(oc get pods -n "$NAMESPACE" -l app=memory-hog \
    -o jsonpath='{.items[0].status.containerStatuses[0].lastState.terminated.reason}' \
    2>/dev/null || true)"
  [[ "$reason" == "OOMKilled" ]] && exit 0
  sleep 2
done

echo "memory-hog did not reach OOMKilled" >&2
exit 1
