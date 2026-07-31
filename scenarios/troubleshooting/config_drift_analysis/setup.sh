#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-config-drift"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  DB_HOST: "db-service"
  DB_PORT: "5432"
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: database
spec:
  replicas: 1
  selector:
    matchLabels:
      app: database
  template:
    metadata:
      labels:
        app: database
    spec:
      containers:
        - name: db
          image: busybox:1.36
          command: ["sh", "-c", "nc -lk -p 3306 -e echo 'ok' 2>/dev/null || while true; do echo ok | nc -l -p 3306; done"]
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Service
metadata:
  name: db-service
spec:
  selector:
    app: database
  ports:
    - port: 3306
      targetPort: 3306
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend-api
  template:
    metadata:
      labels:
        app: backend-api
    spec:
      containers:
        - name: api
          image: busybox:1.36
          command: ["sh", "-c", "echo 'Connecting to db-service:5432...' && echo 'connection refused: db-service:5432' >&2 && sleep 3600"]
          envFrom:
            - configMapRef:
                name: app-config
EOF

oc rollout status deployment/database -n "$NAMESPACE" --timeout=120s
oc rollout status deployment/backend-api -n "$NAMESPACE" --timeout=120s
