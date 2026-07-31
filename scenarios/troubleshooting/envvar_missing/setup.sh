#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-envvar-missing"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: warehouse-ops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: warehouse-ops
  template:
    metadata:
      labels:
        app: warehouse-ops
    spec:
      containers:
        - name: warehouse-ops
          image: busybox:1.36
          command: ["sh", "-c", "if [ -z \"${DEPLOY_ENV:-}\" ]; then echo 'DEPLOY_ENV is not set' >&2; exit 1; fi; sleep 3600"]
EOF

oc rollout status deployment/warehouse-ops -n "$NAMESPACE" --timeout=30s 2>/dev/null || true

deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  waiting="$(oc get pods -n "$NAMESPACE" -l app=warehouse-ops \
    -o jsonpath='{.items[0].status.containerStatuses[0].state.waiting.reason}' \
    2>/dev/null || true)"
  [[ "$waiting" == "CrashLoopBackOff" ]] && exit 0
  sleep 3
done

echo "warehouse-ops did not reach CrashLoopBackOff" >&2
exit 1
