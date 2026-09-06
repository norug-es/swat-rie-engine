#!/usr/bin/env bash
set -Eeuo pipefail

BYTES="${BYTES:-32}"
WRITE_ENV="${WRITE_ENV:-false}"
ENV_FILE="${ENV_FILE:-.env}"

if command -v openssl >/dev/null 2>&1; then
  API_KEY="$(openssl rand -hex "$BYTES")"
  EVIDENCE_SIGNING_SECRET="$(openssl rand -hex "$BYTES")"
elif command -v python3 >/dev/null 2>&1; then
  API_KEY="$(python3 - <<PY
import secrets
print(secrets.token_hex($BYTES))
PY
)"
  EVIDENCE_SIGNING_SECRET="$(python3 - <<PY
import secrets
print(secrets.token_hex($BYTES))
PY
)"
else
  echo "[FAIL] Neither openssl nor python3 is available." >&2
  exit 2
fi

echo "Generated secure secrets:"
echo
echo "RIE_API_KEY=$API_KEY"
echo "EVIDENCE_SIGNING_SECRET=$EVIDENCE_SIGNING_SECRET"

if [[ "${WRITE_ENV,,}" =~ ^(1|true|yes|on)$ ]]; then
  touch "$ENV_FILE"

  upsert_env() {
    local key="$1"
    local value="$2"
    local file="$3"

    if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$file"; then
      if sed --version >/dev/null 2>&1; then
        sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${value}|" "$file"
      else
        sed -i '' -E "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${value}|" "$file"
      fi
    else
      printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
  }

  upsert_env "RIE_API_KEY" "$API_KEY" "$ENV_FILE"
  upsert_env "EVIDENCE_SIGNING_SECRET" "$EVIDENCE_SIGNING_SECRET" "$ENV_FILE"

  echo
  echo "[OK] Secrets written to $ENV_FILE"
  echo "[INFO] Recreate dependent containers so they load the new values."
fi
