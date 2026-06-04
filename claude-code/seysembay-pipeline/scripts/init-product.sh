#!/bin/bash
# init-product.sh
# Инициализирует структуру для нового продукта по пайплайну Сейсембая
#
# Использование:
#   ./init-product.sh <product-slug>
# Например:
#   ./init-product.sh partner-portal
#
# Создаёт:
#   <product-slug>/
#   ├── README.md (краткое описание + ссылка на _pipeline-status.md)
#   ├── _pipeline-status.md (заглушка из шаблона)
#   └── adr/
#       └── README.md (индекс ADR)

set -e

if [ -z "$1" ]; then
    echo "Ошибка: укажи product-slug"
    echo "Пример: $0 partner-portal"
    exit 1
fi

SLUG="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="$SKILL_DIR/templates"

if [ -d "$SLUG" ]; then
    echo "Ошибка: папка $SLUG уже существует"
    exit 1
fi

echo "Создаю структуру для продукта: $SLUG"

mkdir -p "$SLUG/adr"

# README.md для рабочей папки
cat > "$SLUG/README.md" <<EOF
# $SLUG — Seysembay Pipeline

Рабочая папка для проработки продукта по методике Маргулана Сейсембая.

## Навигация

- **Текущий прогресс:** [_pipeline-status.md](_pipeline-status.md)
- **ADR (принятые решения):** [adr/README.md](adr/README.md)

## Как пользоваться

Каждый шаг пайплайна создаёт свой .md файл с префиксом 01-, 02-, ..., 11-.

Файлы заполняются по ходу диалога со скиллом seysembay-pipeline.

## Когда пайплайн завершён

Создаётся отдельная папка \`${SLUG}-repo/\` со структурой для разработки.
Эта папка (\`$SLUG/\`) остаётся как **история размышлений**.

См. подробности в \`_pipeline-status.md\`.
EOF

# Копируем шаблон pipeline-status
if [ -f "$TEMPLATES_DIR/_pipeline-status.md" ]; then
    cp "$TEMPLATES_DIR/_pipeline-status.md" "$SLUG/_pipeline-status.md"
    # Подставим дату начала
    TODAY=$(date +%Y-%m-%d)
    sed -i.bak "s/YYYY-MM-DD/$TODAY/" "$SLUG/_pipeline-status.md" && rm "$SLUG/_pipeline-status.md.bak"
    # Подставим имя продукта
    sed -i.bak "s/<product-name>/$SLUG/" "$SLUG/_pipeline-status.md" && rm "$SLUG/_pipeline-status.md.bak"
else
    echo "Предупреждение: шаблон _pipeline-status.md не найден, создаю минимальный"
    cat > "$SLUG/_pipeline-status.md" <<EOF
# Pipeline Status: $SLUG

**Начат:** $(date +%Y-%m-%d)
**Текущий шаг:** 1/11

См. полный шаблон в templates/_pipeline-status.md
EOF
fi

# README для adr/
cat > "$SLUG/adr/README.md" <<EOF
# Architecture Decision Records — $SLUG

## Продуктовые

_Пока пусто. ADR будут появляться на шаге 6 пайплайна._

## Технические

_Пока пусто. ADR будут появляться на шаге 8 пайплайна._

## Статусы

- **Принято** — действует сейчас
- **Заменено на ADR-XXX** — устарело, см. указанный ADR
- **Пересмотрено YYYY-MM-DD** — было пересмотрено, но осталось

## Шаблон

См. \`templates/adr.md\` в скилле.
EOF

echo "✅ Готово!"
echo ""
echo "Структура создана:"
echo "  $SLUG/"
echo "  ├── README.md"
echo "  ├── _pipeline-status.md"
echo "  └── adr/"
echo "      └── README.md"
echo ""
echo "Следующий шаг: скилл seysembay-pipeline начнёт диалог по шагу 1 (Northern Star)"
