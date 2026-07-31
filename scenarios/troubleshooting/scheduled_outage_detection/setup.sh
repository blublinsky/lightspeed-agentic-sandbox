#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-scheduled-outage"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: outage-log
data:
  events.log: |
    2026-07-28T03:00:12Z API connection refused - scheduled maintenance window
    2026-07-28T03:15:44Z API connection refused - scheduled maintenance window
    2026-07-28T03:30:01Z API connection restored
    2026-07-27T03:00:08Z API connection refused - scheduled maintenance window
    2026-07-27T03:14:55Z API connection refused - scheduled maintenance window
    2026-07-27T03:29:59Z API connection restored
    2026-07-26T03:00:05Z API connection refused - scheduled maintenance window
    2026-07-26T03:16:22Z API connection refused - scheduled maintenance window
    2026-07-26T03:30:03Z API connection restored
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-monitor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api-monitor
  template:
    metadata:
      labels:
        app: api-monitor
    spec:
      containers:
        - name: monitor
          image: busybox:1.36
          command: ["sh", "-c", "echo 'Detected outage window at 03:00 UTC daily' >&2; sleep 3600"]
          volumeMounts:
            - name: outage-log
              mountPath: /var/log/outage
      volumes:
        - name: outage-log
          configMap:
            name: outage-log
EOF

oc rollout status deployment/api-monitor -n "$NAMESPACE" --timeout=120s
