#!/bin/sh
set -eu

PORT_VALUE="${PORT:-8000}"

python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT_VALUE" \
  --server.headless true