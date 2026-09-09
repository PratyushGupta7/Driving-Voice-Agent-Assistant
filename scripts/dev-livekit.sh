#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# --dev only raises log verbosity / pprof. Keys come from livekit.yaml.
exec livekit-server --config livekit.yaml --dev
