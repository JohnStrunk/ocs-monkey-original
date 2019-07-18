#! /bin/bash

MARKER_DIR=/status
MARKER_FILE="$MARKER_DIR/running"

echo "$(date) - Starting."

touch "$MARKER_FILE"

python3 /workload.py "$@"
rc=$?

rm -f "$MARKER_FILE"

if [[ $rc -ne 0 ]]; then
        echo "$(date) - Non-zero exit, sleeping."
        sleep infinity
fi
