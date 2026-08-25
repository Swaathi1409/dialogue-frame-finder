#!/bin/sh
# docker-entrypoint.sh
#
# Decides whether to run the CLI or the Flask web server based on the
# first argument passed to the container.
#
# CLI usage:
#   docker run dialogue-frame-finder URL "dialogue line" [--verbose] [--json]
#
# Web UI usage:
#   docker run -p 5000:5000 dialogue-frame-finder web

set -e

if [ "$1" = "web" ]; then
    # Start the Flask web server on all interfaces so it is reachable
    # outside the container. Debug mode is off; this is not a dev server.
    echo "Starting web UI on http://0.0.0.0:5000 ..."
    export FLASK_HOST=0.0.0.0
    exec python app.py
else
    # Pass all arguments through to the CLI module.
    exec python -m dialogue_finder "$@"
fi
