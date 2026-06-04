# seysembay-pipeline

> **EN (short):** A Claude skill implementing Margulan Seysembay's product-launch methodology — 11 steps from a raw idea to a ready-to-build `BACKLOG`. Core principle: *don't touch code until it's clear what and why you're building*. Work flows through three zones — **Meaning → Bridge → Implementation**. Ships in two flavors: a full **Claude Code** skill (with references, scripts, templates) and an inline **claude.ai** Project Skill. Russian docs below.

---

**seysembay-pipeline** — скилл, реализующий методику Маргулана Сейсембая для запуска новых продуктов. Главная мысль одной фразой: **не лезь в код, пока не понятно что и зачем строим**. Если идея сырая — Claude Code пишет наугад, переделывает, копит технический долг. Если идея проработана — кодинг становится почти механическим.

Скилл ведёт через **11 шагов**, разбитых на три зоны:

| Зона | Шаги | На какой вопрос отвечает | Где работаешь | Доля времени |
|------|------|--------------------------|----------------|--------------|
| 🧠 Смысл | 1–7 | Что и зачем мы делаем? | Чат с Claude / claude.ai | 40–50% |
| 🌉 Bridge | 8–10 | Как это технически устроено? | Чат с Claude / claude.ai | 30–40% |
| ⚙️ Реализация | 11 | Пишем код | Claude Code на VPS | 10–20% |

Главная ловушка — прыгнуть сразу в третью зону. Один день на первые две зоны экономит неделю в третьей.

## Что на выходе

После прохождения пайплайна в рабочей папке появляется структурированный набор артефактов — от Northern Star до готового бэклога и ADR-решений, которые можно передать в разработку:

```
<product-slug>/
├── 01-northern-star.md          # одно предложение про успех
├── 02-vision-story.md
├── 03-vision-contract-draft.md
├── 04-research-brief.md … 07-story-sync-check.md
├── 08-architecture.md / 08-tech-spec.md
├── 09-CLAUDE.md / 09-README-for-repo.md
├── 10-BACKLOG.md                # готовые задачи для Claude Code
├── _pipeline-status.md          # прогресс по 11 шагам
└── adr/                         # архитектурные решения
```

И отдельная папка `<product-slug>-repo/` — каркас репозитория для разработки.

## Две версии скилла

| | Claude Code (VPS) | claude.ai (Project Skill) |
|---|---|---|
| Все 11 шагов | ✅ | ✅ |
| Создание файлов в проекте | ✅ автоматически | ⚠️ копированием из чата |
| `init-product.sh` (быстрый старт) | ✅ | ❌ |
| Прогрессивное чтение референсов | ✅ читает только нужный шаг | ⚠️ весь файл сразу |
| Доступ с телефона | ✅ через Termius | ✅ |

**Когда какую:** Claude Code — для серьёзной работы с автоматизацией (скрипт init, файлы в проекте). claude.ai — для размышлений в чате, когда ещё не хочешь даже папку создавать, или с телефона.

## Установка

### Версия 1 — Claude Code

```bash
# из этого репозитория
git clone https://github.com/bronxtc52/seysembay-pipeline.git
mkdir -p ~/.claude/skills
cp -R seysembay-pipeline/claude-code/seysembay-pipeline ~/.claude/skills/
chmod +x ~/.claude/skills/seysembay-pipeline/scripts/init-product.sh

# проверка
ls ~/.claude/skills/seysembay-pipeline/   # SKILL.md  references/  scripts/  templates/
```

Готовые архивы для загрузки на VPS лежат в [`dist/`](dist/) (`.tar.gz` и `.zip`).

### Версия 2 — claude.ai

1. Открой нужный проект в claude.ai
2. **Settings → Capabilities → Skills → + Skill**
3. Загрузи файл [`claude-ai/SKILL.md`](claude-ai/SKILL.md)
4. Название — «Seysembay Pipeline», описание возьми из YAML frontmatter

Подробности и устранение проблем — в [INSTALL.md](INSTALL.md).

## Как пользоваться

В Claude Code (в папке будущего продукта) или в чате claude.ai:

```
Хочу запустить новый продукт. Помоги пройти все 11 шагов пайплайна Сейсембая.
```

Или просто:

```
Новая идея: партнёрский портал. С чего начнём?
```

Скилл срабатывает автоматически по триггерам в своём `description` и начинает диалог с вопросов про идею и Northern Star.

Есть и **Lite-версия** для маленьких задач (лендинги, одностраничники):

```
Хочу сделать одностраничник для записи на консультацию. Запусти пайплайн в Lite-версии.
```

## Документация

- **[guide.md](guide.md)** — рабочая инструкция «для человека, а не для программиста»: подробно по каждому из 11 шагов, с примерами хороших и плохих Northern Star.
- **[INSTALL.md](INSTALL.md)** — установка обеих версий, проверка, обновление, частые проблемы.

## Структура репозитория

```
seysembay-pipeline/
├── README.md
├── guide.md                       # человеческая инструкция по 11 шагам
├── INSTALL.md                     # установка обеих версий
├── claude-code/
│   └── seysembay-pipeline/        # полный скилл для Claude Code
│       ├── SKILL.md               # главный «мозг»
│       ├── references/            # инструкции по каждому шагу
│       ├── scripts/init-product.sh
│       └── templates/
├── claude-ai/
│   └── SKILL.md                   # inline-версия для claude.ai
└── dist/                          # готовые архивы для загрузки на VPS
    ├── seysembay-pipeline-claude-code.tar.gz
    └── seysembay-pipeline-claude-code.zip
```

## Лицензия

[MIT](LICENSE)
