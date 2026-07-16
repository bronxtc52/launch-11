#!/usr/bin/env bash
# One-time production provisioning for launch-11.
#
# RUN THIS FROM YOUR OWN AUTHORIZED SESSION (your laptop / MacBook Air), NOT from mh-central:
#   * mh-central's managed identity is read-only on project RGs by design, so it physically
#     cannot create these resources;
#   * ~/.claude/rules/deploy-via-ci.md forbids a personal `az login` on shared VMs.
#
# After this runs once, every deploy goes through GitHub Actions + OIDC
# (.github/workflows/deploy.yml). You never run `az containerapp update` by hand again.
#
#   az login
#   az account set --subscription c05debcb-f65a-4aee-9d1e-0f598536a024
#   bash bot/ops/provision-prod.sh
#
set -euo pipefail

SUB=c05debcb-f65a-4aee-9d1e-0f598536a024
RG=rg-launch11-prod
LOC=northeurope
ACR=acrlaunch11prod
PG=psql-launch11-prod
PGDB=launch11
PGADMIN=launch11admin
ENVIRONMENT=cae-launch11-prod
LAW=log-launch11
UAMI_APP=id-launch11              # the app: reads secrets from Key Vault, pulls from ACR
UAMI_CI=uami-launch11-deploy      # GitHub Actions: pushes images, updates the app
KV=kv-bronxtc-dev
REPO=bronxtc52/launch-11
TAGS="project=launch11 env=prod owner=bronxtc52"

say() { echo -e "\n\033[1;36m▶ $*\033[0m"; }

say "0. Sanity"
az account set --subscription "$SUB"
az account show --query "{sub:name,user:user.name}" -o table

say "1. Resource group (tagged — cost attribution depends on it)"
az group create -n "$RG" -l "$LOC" --tags $TAGS -o none

say "2. ACR (Basic)"
az acr create -n "$ACR" -g "$RG" --sku Basic -l "$LOC" --tags $TAGS -o none

say "3. Postgres B1ms + database (password already waiting in Key Vault)"
PGPASS=$(az keyvault secret show --vault-name "$KV" --name launch11--production--PG-ADMIN-PASSWORD --query value -o tsv)
az postgres flexible-server create -n "$PG" -g "$RG" -l "$LOC" \
  --admin-user "$PGADMIN" --admin-password "$PGPASS" \
  --sku-name Standard_B1ms --tier Burstable --version 16 --storage-size 32 \
  --public-access 0.0.0.0 --yes --tags $TAGS -o none
az postgres flexible-server db create -g "$RG" -s "$PG" -d "$PGDB" -o none
# let Azure services (the Container App) reach it
az postgres flexible-server firewall-rule create -g "$RG" -n "$PG" \
  --rule-name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none

say "4. DATABASE_URL -> Key Vault (never printed, never in git)"
DBURL="postgresql://${PGADMIN}:${PGPASS}@${PG}.postgres.database.azure.com:5432/${PGDB}?sslmode=require"
az keyvault secret set --vault-name "$KV" --name launch11--production--DATABASE-URL --value "$DBURL" -o none

say "5. Log Analytics + 2GB daily cap (unbounded ingestion is how logs eat credits)"
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOC" --tags $TAGS -o none
az monitor log-analytics workspace update -g "$RG" -n "$LAW" --quota 2 -o none
LAW_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query customerId -o tsv)
LAW_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LAW" --query primarySharedKey -o tsv)

say "6. Container Apps environment"
az containerapp env create -n "$ENVIRONMENT" -g "$RG" -l "$LOC" \
  --logs-workspace-id "$LAW_ID" --logs-workspace-key "$LAW_KEY" --tags $TAGS -o none

say "7. App identity -> Key Vault Secrets User + AcrPull"
az identity create -n "$UAMI_APP" -g "$RG" -l "$LOC" --tags $TAGS -o none
APP_PRINCIPAL=$(az identity show -n "$UAMI_APP" -g "$RG" --query principalId -o tsv)
KV_ID=$(az keyvault show -n "$KV" --query id -o tsv)
ACR_ID=$(az acr show -n "$ACR" --query id -o tsv)
for i in $(seq 1 10); do  # identity propagation is eventually consistent
  az role assignment create --assignee-object-id "$APP_PRINCIPAL" --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" --scope "$KV_ID" -o none 2>/dev/null && break || sleep 6
done
az role assignment create --assignee-object-id "$APP_PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "AcrPull" --scope "$ACR_ID" -o none

say "8. CI identity (OIDC) -> AcrPush on ACR + Contributor on THIS RG only"
az identity create -n "$UAMI_CI" -g "$RG" -l "$LOC" --tags $TAGS -o none
CI_CLIENT=$(az identity show -n "$UAMI_CI" -g "$RG" --query clientId -o tsv)
CI_PRINCIPAL=$(az identity show -n "$UAMI_CI" -g "$RG" --query principalId -o tsv)
RG_ID=$(az group show -n "$RG" --query id -o tsv)
for i in $(seq 1 10); do
  az role assignment create --assignee-object-id "$CI_PRINCIPAL" --assignee-principal-type ServicePrincipal \
    --role "AcrPush" --scope "$ACR_ID" -o none 2>/dev/null && break || sleep 6
done
az role assignment create --assignee-object-id "$CI_PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "Contributor" --scope "$RG_ID" -o none
# the app's identity must be assignable by CI when it creates/updates the app
az role assignment create --assignee-object-id "$CI_PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "Managed Identity Operator" --scope "$(az identity show -n "$UAMI_APP" -g "$RG" --query id -o tsv)" -o none

say "9. Federated credential — GitHub Actions signs in with no stored secret"
az identity federated-credential create --name gh-main --identity-name "$UAMI_CI" -g "$RG" \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${REPO}:ref:refs/heads/main" \
  --audiences api://AzureADTokenExchange -o none
az identity federated-credential create --name gh-env-prod --identity-name "$UAMI_CI" -g "$RG" \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${REPO}:environment:production" \
  --audiences api://AzureADTokenExchange -o none

say "10. Repo secrets (ids, not passwords)"
TENANT=$(az account show --query tenantId -o tsv)
gh secret set AZURE_CLIENT_ID --repo "$REPO" --body "$CI_CLIENT"
gh secret set AZURE_TENANT_ID --repo "$REPO" --body "$TENANT"
gh secret set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$SUB"

cat <<EOF

✅ Инфраструктура готова.

Осталось (без этого бот не поднимется):
  1. Положить prod-ключ Anthropic:
       az keyvault secret set --vault-name $KV --name launch11--production--ANTHROPIC-API-KEY --value '<sk-ant-...>'
  2. Погасить локального бота на mh-central, иначе два поллера подерутся за getUpdates (409):
       cd ~/projects/launch-11/bot && docker compose down
  3. Запустить деплой:
       gh workflow run deploy.yml --repo $REPO
EOF
