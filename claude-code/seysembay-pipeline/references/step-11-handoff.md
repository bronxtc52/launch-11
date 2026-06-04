# Шаг 11: Coding (передача в Claude Code)

## Цель шага

**Не писать код.** Скилл передаёт эстафету Claude Code. На этом шаге — финальная подготовка проекта и инструкции для запуска.

## Workflow шага

### 1. Переезд из рабочей папки в репозиторий

Объясни пользователю, что сейчас будет:
- В нашей рабочей папке `<product-slug>/` лежат все 11 шагов с префиксами для истории
- Для разработки нужна **отдельная папка** с правильной структурой репозитория

**Создай новую папку `<product-slug>-repo/`** со структурой:

```
<product-slug>-repo/
├── README.md              # из 09-README-for-repo.md
├── CLAUDE.md              # из 09-CLAUDE.md
├── BACKLOG.md             # из 10-BACKLOG.md
├── .gitignore             # стандартный для стека
├── .env.example           # шаблон переменных окружения
├── docs/
│   ├── vision.md          # из 06-vision-contract-final.md
│   ├── architecture.md    # из 08-architecture.md
│   ├── tech-spec.md       # из 08-tech-spec.md
│   └── faq.md             # из 06-faq.md
└── adr/                   # вся папка как есть
    ├── README.md
    ├── 001-*.md
    └── ...
```

Рабочая папка `<product-slug>/` **остаётся** — это твоя история размышлений (шаги 1-7 + промежуточные документы), к ней можно возвращаться.

### 2. Git инициализация (опционально)

Если пользователь готов:

```bash
cd <product-slug>-repo
git init
git add .
git commit -m "Initial: documentation, ADR, BACKLOG (from Seysembay pipeline)"

# Если есть remote (GitHub/GitLab)
git remote add origin <url>
git branch -M main
git push -u origin main
```

### 3. Алиас для Claude Code на VPS

Напомни пользователю про `claude-code-cheatsheet.md` — у него на VPS есть алиасы для проектов (mhaibot, marineweb, president, fc, miniapp, sw).

**Если этот проект новый** — нужно добавить новый алиас в `.zshrc` или `.bashrc` на VPS:

```bash
# В ~/.zshrc или ~/.bashrc
alias <slug>='cd ~/projects/<product-slug>-repo && claude'
```

Где `<slug>` — короткое имя для команды.

### 4. Инструкция запуска кодинга

Финальный артефакт — короткая памятка для пользователя:

```markdown
# Готово к разработке. Что дальше:

## 1. Закинь проект на VPS

```bash
# С локальной машины
scp -r <product-slug>-repo/ user@vps:~/projects/

# Или через git, если запушил
ssh user@vps
cd ~/projects
git clone <repo-url> <product-slug>-repo
```

## 2. Добавь алиас (один раз)

```bash
echo "alias <slug>='cd ~/projects/<product-slug>-repo && claude'" >> ~/.zshrc
source ~/.zshrc
```

## 3. Запусти tmux + Claude Code

```bash
# Из Termius на iPhone, например
ssh user@vps
tmux new -s <slug>     # создать сессию
<slug>                  # запустить алиас (cd + claude)
```

## 4. Скорми Claude Code первую задачу

Открой `BACKLOG.md`, скопируй **T-001** целиком и вставь в Claude Code.

Claude Code прочитает CLAUDE.md, поймёт контекст, и начнёт работу.

## 5. Используй Plan Mode

Перед каждой задачей: `Shift+Tab` дважды (включи Plan Mode).
Claude предложит план — поправь, потом `Shift+Tab` один раз → Auto-Accept.

## 6. Не забывай /clear между задачами

Свежий контекст лучше деградировавшего. После завершения T-NNN: `/clear`, потом T-NNN+1.

## 7. Настрой hooks (опционально, но рекомендую)

См. `claude-code-vibe-coding-guide.md` раздел 6.
Минимум: уведомления + авто-форматирование при Edit.

## Полезные ссылки в проекте

- BACKLOG.md — следующие задачи
- adr/README.md — почему мы делаем именно так
- docs/architecture.md — обзор системы
- docs/tech-spec.md — детальные спеки
```

### 5. Финальное обновление _pipeline-status.md

```markdown
# Pipeline Status: <product-name>

**Версия:** Full
**Начат:** YYYY-MM-DD
**Завершён:** YYYY-MM-DD
**Текущий шаг:** 11/11 ✅ Передано в Claude Code

## Прогресс

- [x] Шаг 1: Northern Star
- [x] Шаг 2: Vision Story
- [x] Шаг 3: Vision Contract Draft
- [x] Шаг 4: Research Brief
- [x] Шаг 5: Research
- [x] Шаг 6: Final Contract + ADR + FAQ
- [x] Шаг 7: Story Sync Check
- [x] Шаг 8: Architecture + Tech-spec
- [x] Шаг 9: CLAUDE.md + Documentation
- [x] Шаг 10: BACKLOG
- [x] Шаг 11: Handoff в Claude Code

## Принятые ADR

- ADR-001: ...
- ADR-002: ...
- ...
- (N штук)

## Файлы продукта

**Рабочая папка (история):** `<product-slug>/`
**Репозиторий разработки:** `<product-slug>-repo/`
**Алиас на VPS:** `<slug>`

## Дальше

Кодинг идёт в Claude Code на VPS. Этот пайплайн возвращается к жизни если:
- Появится крупный новый эпик (новая фича) → можно пройти от шага 3 для него
- Будет дрейф продукта → шаг 7 (Sync Check)
- Понадобится принять новое значимое решение → новый ADR
```

### 6. Что делать если задача всё-таки требует кода

Если пользователь спрашивает "помоги с задачей T-007" — **не пиши код**. Скажи:

> Кодинг — задача Claude Code на VPS. Скилл seysembay-pipeline отвечает за планирование. Если хочешь, могу:
> - Уточнить формулировку задачи в BACKLOG
> - Разбить задачу подробнее
> - Подготовить промпт для Claude Code

Если пользователь прямо настаивает "ну напиши код в этом чате" — окей, но напомни, что это вне зоны скилла, и предложи в следующий раз сразу в Claude Code.

## Антипаттерны

- **Начать писать код прямо тут.** Скилл не для этого. Передавай эстафету.
- **Забыть про переезд из рабочей папки.** Если пользователь начнёт писать код в `<product-slug>/01-northern-star.md` — будет каша.
- **Не обновить алиас.** Каждый раз вручную набирать `cd ~/projects/...` — раздражает.

## Когда пайплайн завершён

✅ Репозиторий создан с правильной структурой
✅ Инструкция запуска вручена пользователю
✅ `_pipeline-status.md` обновлён, шаг 11 закрыт
✅ Пользователь знает, что дальше делать в Claude Code

Скажи пользователю: "Пайплайн пройден. У тебя есть всё: понимание продукта (зона смысла), архитектура (Bridge), и готовый BACKLOG. Можно идти кодить. Удачи."
