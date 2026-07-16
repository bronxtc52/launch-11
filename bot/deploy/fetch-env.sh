#!/usr/bin/env bash
# Build a local .env from Key Vault kv-bronxtc-dev.
# Phase 1 policy (council finding S1): local dev pulls ONLY from the launch11--dev--* namespace.
# Production secrets are NEVER written to a local .env; prod runs on ACA with keyvaultref (later phase).
set -euo pipefail

VAULT="kv-bronxtc-dev"
ENVNS="${1:-dev}"        # dev | production ; production requires explicit break-glass
OUT="${2:-.env}"

if [[ "$ENVNS" == "production" && "${BREAK_GLASS_APPROVED:-}" != "true" ]]; then
  echo "REFUSED: refusing to fetch launch11--production--* into a local .env." >&2
  echo "Set BREAK_GLASS_APPROVED=true only if you truly intend to (you almost never do)." >&2
  exit 1
fi

get() { az keyvault secret show --vault-name "$VAULT" --name "launch11--${ENVNS}--$1" --query value -o tsv; }

{
  echo "LAUNCH11_BOT_TOKEN=$(get BOT-TOKEN)"
  echo "ANTHROPIC_API_KEY=$(get ANTHROPIC-API-KEY)"
  # Phase-3 rollout kill-switch: keep populated during smoke, clear for public launch
  echo "BETA_ALLOWLIST_IDS=$(get BETA-ALLOWLIST-IDS)"
  # owners: unlimited runs, never billed, never beta-gated
  echo "OWNER_IDS=$(get OWNER-IDS)"
  echo "DATABASE_URL=${DATABASE_URL:-postgresql://launch11:launch11@localhost:5432/launch11}"
  echo "LAUNCH11_MODEL=${LAUNCH11_MODEL:-claude-sonnet-5}"
  echo "FREE_RUNS=${FREE_RUNS:-1}"
  echo "STARS_PRICE=${STARS_PRICE:-100}"
} > "$OUT"

chmod 600 "$OUT"
echo "Wrote $OUT from $VAULT (namespace launch11--${ENVNS}--*)"
