#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-ingress-mismatch"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: busybox:1.36
          command: ["sh", "-c", "while true; do echo -e 'HTTP/1.1 200 OK\r\n\r\nok' | nc -l -p 8080; done"]
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Service
metadata:
  name: backend
spec:
  selector:
    app: backend
  ports:
    - port: 8080
      targetPort: 8080
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: busybox:1.36
          command: ["sh", "-c", "while true; do wget -q -O- --timeout=2 http://backend:8080/ 2>&1 || echo 'request to backend failed' >&2; sleep 5; done"]
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-allow-frontend
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend-v1
      ports:
        - protocol: TCP
          port: 8080
EOF

oc rollout status deployment/backend -n "$NAMESPACE" --timeout=120s
oc rollout status deployment/frontend -n "$NAMESPACE" --timeout=120s
