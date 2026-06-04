# Установка скилла seysembay-pipeline

Две версии. Поставь обе — будешь использовать в зависимости от того, где работаешь.

---

## Версия 1: Claude Code на VPS

**Файл:** `seysembay-pipeline-claude-code.tar.gz` (или `.zip` — на выбор)

### Установка

```bash
# 1. Скачать архив на VPS (или загрузить через scp)
scp seysembay-pipeline-claude-code.tar.gz user@vps:~/

# 2. На VPS — распаковать в папку скиллов Claude Code
ssh user@vps
mkdir -p ~/.claude/skills
cd ~/.claude/skills
tar -xzf ~/seysembay-pipeline-claude-code.tar.gz

# Проверить
ls ~/.claude/skills/seysembay-pipeline/
# Должно показать: SKILL.md  references/  scripts/  templates/

# 3. (Опционально) Сделать init-скрипт исполняемым, если не был
chmod +x ~/.claude/skills/seysembay-pipeline/scripts/init-product.sh
```

### Как использовать

```bash
# В любой папке, где хочешь начать продукт
cd ~/projects/
claude

# Внутри Claude Code:
> Хочу запустить новый продукт по пайплайну Сейсембая
# Или:
> Запускаю партнёрский портал, помоги пройти все 11 шагов

# Claude Code автоматически подхватит скилл и начнёт диалог
```

### Альтернатива — глобальная установка

Если хочешь, чтобы скилл был доступен всем пользователям VPS:

```bash
sudo mkdir -p /etc/claude/skills
sudo tar -xzf seysembay-pipeline-claude-code.tar.gz -C /etc/claude/skills/
```

---

## Версия 2: claude.ai как Project Skill

**Файл:** `seysembay-pipeline-claudeai-SKILL.md`

### Установка

1. Открой проект в claude.ai (тот, где обычно работаешь с продуктовыми задачами — например, отдельный проект "Запуск продуктов")
2. **Settings → Capabilities → Skills** (или ищи кнопку "+ Skill" в UI проекта)
3. Загрузи файл `seysembay-pipeline-claudeai-SKILL.md`
4. Если попросит — название "Seysembay Pipeline", описание возьми из YAML frontmatter
5. Сохрани

### Как использовать

В новом чате внутри проекта:

```
Хочу запустить новый продукт. Помоги пройти все 11 шагов пайплайна Сейсембая.
```

Или просто:

```
Новая идея: партнёрский портал. С чего начнём?
```

Скилл должен сработать автоматически (триггеры в его description).

---

## Как проверить что скилл работает

### В Claude Code

```bash
cd /tmp
mkdir test-product
cd test-product
claude

> Запусти пайплайн Сейсембая для теста — идея: внутренний бот для отслеживания задач команды
```

Должен начаться диалог с вопросов про идею, обсуждение Northern Star.

### В claude.ai

В чате проекта:

```
Тестовая идея — запуск пайплайна для проработки нового MVP. С чего начнём?
```

---

## Структура артефактов (для понимания)

После запуска скилла в любой версии в текущей папке появится:

```
<product-slug>/                    # рабочая папка
├── README.md
├── _pipeline-status.md            # прогресс по 11 шагам
├── 01-northern-star.md
├── 02-vision-story.md
├── 03-vision-contract-draft.md
├── 04-research-brief.md
├── 05-research-results.md
├── 06-vision-contract-final.md
├── 06-faq.md
├── 07-story-sync-check.md
├── 08-architecture.md
├── 08-tech-spec.md
├── 09-CLAUDE.md
├── 09-README-for-repo.md
├── 10-BACKLOG.md
└── adr/
    ├── README.md
    └── 001-*.md, 002-*.md, ...

<product-slug>-repo/               # после шага 11 — для разработки
├── README.md
├── CLAUDE.md
├── BACKLOG.md
├── docs/
└── adr/
```

---

## Обновление скилла

Если захочешь поменять содержимое (например, добавить шаги или поменять контекст):

**Claude Code версия:**
```bash
# Редактировать напрямую
nano ~/.claude/skills/seysembay-pipeline/SKILL.md
# Или конкретный шаг
nano ~/.claude/skills/seysembay-pipeline/references/step-03-contract-draft.md
```

**claude.ai версия:** Удалить старый Project Skill, загрузить обновлённый файл.

---

## Структура внутри Claude Code версии

Если интересно, что внутри архива:

```
seysembay-pipeline/
├── SKILL.md                              # главный мозг скилла
├── references/                           # инструкции по каждому шагу
│   ├── step-01-northern-star.md
│   ├── step-02-vision-story.md
│   ├── step-03-contract-draft.md
│   ├── step-04-research-brief.md
│   ├── step-05-research.md
│   ├── step-06-final-contract.md
│   ├── step-07-sync-check.md
│   ├── step-08-architecture.md           # с особым вниманием к Azure
│   ├── step-09-documentation.md
│   ├── step-10-backlog.md
│   ├── step-11-handoff.md
│   └── spec-kit-bridge.md                # гибрид с GitHub Spec Kit
├── scripts/
│   └── init-product.sh                   # создаёт структуру нового продукта
└── templates/
    ├── _pipeline-status.md
    ├── 01-northern-star.md
    ├── 03-vision-contract-draft.md
    ├── 10-BACKLOG.md
    ├── adr.md
    └── CLAUDE.md
```

В claude.ai версии всё то же самое, но **inline в одном .md файле** (Project Skills там не поддерживают подпапки).

---

## Что отличается между версиями

| Возможность | Claude Code | claude.ai |
|-------------|-------------|-----------|
| Все 11 шагов | ✅ | ✅ |
| Создание файлов в проекте | ✅ автоматически | ⚠️ через копирование из чата |
| `init-product.sh` (быстрый старт) | ✅ | ❌ |
| Прогрессивное чтение референсов | ✅ (читает только нужный шаг) | ⚠️ весь файл сразу |
| Учёт Azure-карты | ✅ | ✅ если карта в проекте |
| Доступ из мобильного (Termius) | ✅ | ✅ |

**Когда какую использовать:**

- **Claude Code на VPS** — для серьёзной работы, когда сразу пишешь и хочешь автоматизацию (скрипт init, файлы в проекте)
- **claude.ai** — для размышлений в чате, когда ещё не хочешь даже папку создавать. Или с телефона, когда лень открывать Termius. Артефакты потом скопируешь в VPS.

---

## Если что-то не работает

1. **Скилл не срабатывает в Claude Code:** проверь путь `~/.claude/skills/seysembay-pipeline/SKILL.md` существует. Проверь YAML frontmatter — там не должно быть синтаксических ошибок.

2. **Скилл не срабатывает в claude.ai:** убедись что Project Skills включены в настройках проекта. Перезайди в проект.

3. **Скилл срабатывает не там, где надо:** мне можно прислать пример диалога — поправлю триггеры в `description`.

4. **Хочу поменять Lite-версию (для лендингов):** редактируй `SKILL.md`, секция "Версии пайплайна".

---

## Что дальше

После установки — протестируй на маленькой задаче. Например:

> Хочу сделать одностраничник для записи на консультацию. Запусти пайплайн в Lite-версии.

Если что-то в диалоге будет неудобно — пиши, поправим.
