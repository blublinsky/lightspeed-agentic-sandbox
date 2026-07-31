#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="troubleshoot-storage-binding"

oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

oc apply -n "$NAMESPACE" -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-volume
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: nonexistent-storage-class
  resources:
    requests:
      storage: 1Gi
EOF

deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
  phase="$(oc get pvc data-volume -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "$phase" == "Pending" ]] && exit 0
  sleep 2
done
echo "data-volume PVC did not stay Pending (got phase=${phase:-missing})" >&2
exit 1
