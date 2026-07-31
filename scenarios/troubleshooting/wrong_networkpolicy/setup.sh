#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-wrong-netpol"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web-app
  template:
    metadata:
      labels:
        app: web-app
    spec:
      containers:
        - name: web
          image: busybox:1.36
          command: ["sh", "-c", "while true; do echo -e 'HTTP/1.1 200 OK\r\n\r\nok' | nc -l -p 8080; done"]
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: Service
metadata:
  name: web-app
spec:
  selector:
    app: web-app
  ports:
    - port: 80
      targetPort: 8080
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: client
  template:
    metadata:
      labels:
        app: client
    spec:
      containers:
        - name: client
          image: busybox:1.36
          command: ["sh", "-c", "while true; do wget -q -O- --timeout=2 http://web-app/ 2>&1 || echo 'request to web-app failed' >&2; sleep 5; done"]
EOF

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
spec:
  podSelector: {}
  policyTypes:
    - Ingress
EOF

oc rollout status deployment/web-app -n "$NAMESPACE" --timeout=120s
oc rollout status deployment/client -n "$NAMESPACE" --timeout=120s

deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
  logs="$(oc logs -n "$NAMESPACE" -l app=client --tail=20 2>/dev/null || true)"
  if echo "$logs" | grep -q "request to web-app failed"; then
    echo "Client cannot reach web-app (NetworkPolicy confirmed)"
    exit 0
  fi
  sleep 3
done
echo "Client never logged 'request to web-app failed' — NetworkPolicy may not be enforced" >&2
exit 1
