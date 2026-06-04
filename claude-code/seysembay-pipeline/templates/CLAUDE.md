# <Product Name>

## Что это

<2-3 предложения. Возьми из Vision Story (шаг 2). Без воды, по делу.>

## Stack

- **Frontend:** <технология, версия>
- **Backend:** <технология, версия>
- **БД:** <технология, версия>
- **Хостинг:** <Azure App Service / VM / serverless / ...>
- **Auth:** <провайдер>

## Команды

```bash
npm run dev        # Запуск dev-сервера
npm run build      # Сборка production
npm run test       # Тесты
npm run lint       # Линтер
npm run db:migrate # Миграции БД
```

## Структура репозитория

```
/src
  /app          # Next.js App Router (если применимо)
  /components   # React-компоненты
  /lib          # Утилиты, API-клиенты
  /db           # Миграции, схема
  /styles       # Глобальные стили
/tests
/docs           # Документация (architecture, tech-spec, vision)
/adr            # Architecture Decision Records
```

## Главные правила

- Всегда TypeScript strict mode
- Тесты на бизнес-логику (services/), не на UI-компоненты
- Никогда не коммитить `.env` или секреты (см. `.gitignore`)
- Все API-вызовы через `src/lib/api.ts`, не fetch напрямую
- Стили через Tailwind classes, не CSS-modules
- Простейший работающий подход — без избыточной абстракции
- Перед PR — `npm run lint` и `npm run test`, должно быть зелёное

## Не трогать

- `/legacy/` — старый код, не переписываем
- `/generated/` — авто-генерируемый, не редактировать вручную
- `node_modules/`, `.next/`, `dist/` — артефакты сборки

## Документация

- [Архитектура](docs/architecture.md) — обзор системы и компонентов
- [Tech Spec](docs/tech-spec.md) — детальная спецификация
- [Vision](docs/vision.md) — продуктовое видение
- [FAQ](docs/faq.md) — частые вопросы
- [ADR](adr/README.md) — принятые решения

## Контекст продукта

- **Northern Star:** <одна фраза из шага 1>
- **Целевой пользователь:** <одна фраза из блока B Vision Contract>
- **НЕ делаем в v1:**
  - <пункт 1 из блока D>
  - <пункт 2>
  - <пункт 3>

## Локально специфичное

- **Регион Azure:** <North Europe / другой — см. ADR-XXX>
- **БД-сервер:** <existing/new — см. ADR-XXX>
- **Алиас на VPS:** `<slug>` (cd + claude)
