#!/usr/bin/env bash
# Azure Monitor alert-правила для launch-11 (rg-launch11-prod). БЕЗ action group (silent),
# как у остальных проектных алёртов — единственный канал уведомлений это server-watchdog.
#
# Стек: один Telegram-бот ca-launch11-bot (aiogram long-polling, БЕЗ ingress, min=max=1).
# min=1 => no-replicas применим (для scale-to-zero аппов его брать НЕЛЬЗЯ — ложный critical).
#
# ⚠️ ЗАПУСКАТЬ ПОСЛЕ bot/ops/provision-prod.sh и из авторизованной сессии владельца:
# у managed identity mh-central нет write-прав на RG.
#   az login && bash bot/ops/alerts-launch11.sh
set -euo pipefail

SUB="c05debcb-f65a-4aee-9d1e-0f598536a024"
RG="rg-launch11-prod"
WS="/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.OperationalInsights/workspaces/log-launch11"
APP_BASE="/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.App/containerapps"
TAGS="project=launch11 env=prod owner=bronxtc52"

APP="ca-launch11-bot"; SCOPE="${APP_BASE}/${APP}"

# бот always-on (min=1): пропажа реплик = бот не отвечает вообще
az monitor metrics alert create -n "al-${APP}-no-replicas" -g "$RG" --scopes "$SCOPE" \
  --condition "min Replicas < 1" --window-size 5m --evaluation-frequency 1m --severity 1 \
  --description "[$APP] нет реплик ≥5м — бот молчит" --tags $TAGS

# RestartCount — кумулятивный per-replica счётчик: агрегация total суммирует его по семплам окна
# → ложно залипает в Fired навсегда. Берём max + auto-mitigate (новая реплика после деплоя = 0).
# Пороги cpu/mem — от лимитов аппа (0.5 vCPU = 5e8 nanocores, 1Gi): ~80% и ~80%.
for cond in "al-${APP}-restarts|max RestartCount > 3|15m|5m|2|перезапуски (крэш-луп?)" \
            "al-${APP}-cpu-high|avg UsageNanoCores > 400000000|10m|5m|3|cpu >80% лимита" \
            "al-${APP}-memory-high|avg WorkingSetBytes > 858993459|10m|5m|3|mem >80% лимита"; do
  IFS='|' read -r n c w e s d <<< "$cond"
  az monitor metrics alert create -n "$n" -g "$RG" --scopes "$SCOPE" --condition "$c" \
    --window-size "$w" --evaluation-frequency "$e" --severity "$s" \
    --description "[$APP] $d" --auto-mitigate true --tags $TAGS
done

az monitor scheduled-query create -n "al-launch11-aca-system-failures" -g "$RG" \
  --scopes "$WS" --severity 1 --window-size 5m --evaluation-frequency 1m --condition "count 'rows' > 0" \
  --condition-query rows="ContainerAppSystemLogs_CL | where TimeGenerated > ago(5m)
    | where ContainerAppName_s startswith 'ca-launch11'
    | where Reason_s in~ ('ProbeFailed','RevisionFailed','ContainerFailed','Failed')
       or Log_s has_any ('Probe failed','Revision failed','Container failed','failed startup probe')
    | summarize total=count(), hard=countif(Reason_s in~ ('RevisionFailed','ContainerFailed','Failed') or Log_s has_any ('Revision failed','Container failed'))
    | where hard > 0 or total >= 10" \
  --description "ACA system failures across launch-11" --tags $TAGS

# 409 getUpdates = второй поллер на том же токене (локальный docker + прод одновременно).
# Симптом коварный: бот отвечает через раз, а не падает.
az monitor scheduled-query create -n "al-launch11-console-critical-errors" -g "$RG" \
  --scopes "$WS" --severity 2 --window-size 15m --evaluation-frequency 5m --condition "count 'rows' > 0" \
  --condition-query rows="ContainerAppConsoleLogs_CL | where TimeGenerated > ago(15m)
    | where ContainerAppName_s startswith 'ca-launch11'
    | where Log_s has_any ('CRITICAL','Traceback','TelegramConflictError','terminated by other getUpdates','sentry')
    | summarize c=count() | where c >= 3" \
  --description "launch-11: критические ошибки/конфликт поллеров в консоли" --tags $TAGS

echo "✅ алёрты созданы (silent). Проверка: az monitor metrics alert list -g $RG -o table"
