#!/bin/sh
set -e

# Create the endpoint config on first run (persisted in the mounted volume).
if [ ! -d "$HOME/.globus_compute/$ENDPOINT_NAME" ]; then
  globus-compute-endpoint configure "$ENDPOINT_NAME"
fi

# Runs in the foreground; the first start prints the endpoint UUID.
exec globus-compute-endpoint start "$ENDPOINT_NAME"
