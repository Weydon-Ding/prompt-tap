#!/bin/sh
set -eu

if [ -z "${NEW_API_BASE_URL:-}" ]; then
  cat >&2 <<'EOF'
NEW_API_BASE_URL is required.
Copy prompt-tap/.env.example to prompt-tap/.env, then set NEW_API_BASE_URL to your New API HTTP base URL.
Example: NEW_API_BASE_URL=http://host.docker.internal:3000
EOF
  exit 1
fi

exec mitmdump \
  --mode "reverse:${NEW_API_BASE_URL}" \
  --listen-host "0.0.0.0" \
  --listen-port "8080" \
  -s /scripts/log_prompts.py
