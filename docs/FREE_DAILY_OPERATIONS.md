# Бесплатная ежедневная работа: подготовка, не активация

Ветка `free-daily-operations` от `render-deploy`. Боевые подключения, discovery,
дампы и workflow здесь не запускались. Render остаётся веб-сервисом Free с
`SCHEDULER_ENABLED=false`, `DATABASE_AUTO_MIGRATE=false`,
`STARTUP_DATA_UPDATES_ENABLED=false`. Спящий Render не отвечает за сбор.
Никаких keep-alive запросов и дополнительных платных workers.

## Что запускается

| Задача | Существующий встроенный график | Сервисы / ключи | В бесплатной конфигурации |
|---|---|---|---|
| Получение источников | каждый час | RSS/HTML, GitHub public API; Brave `SEARCH_API_KEY` опционально | Только внутри внешнего bounded job; 12 источников, 60 HTTP/запуск, 80/сутки |
| Очередь raw/catalog | каждые 15 минут; отдельная ежедневная обработка 09:00 | Gemini/Groq; остальные провайдеры существуют в общем pipeline | Внешний job: до 80 кандидатов/запуск, 120/сутки |
| Сверка пропусков | watchdog каждые 15 минут; 08:00 и 23:30 Ташкент | те же источники/LLM | Встроенный watchdog выключен |
| Переанализ catalog | каждые 6 часов | настроенный LLM | Встроенная задача выключена; отдельного безлимитного enrichment нет |
| Глубокий анализ | каждые 4 часа | настроенный LLM | Выключен; не расходует бюджет ежедневного job |
| Локальные проблемы / мировые тренды | еженедельно / ежемесячно через watchdog | поиск, LLM | Выключены |
| Telegram ingestion | каждые 15 минут | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` | Выключен; ключи в workflow не передаются |
| Уведомления админу | каждые 30 минут | `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_CHAT_ID` | Выключены; наблюдение через `/admin` |
| Startup-аудиты / registry / синхронизация | при старте, если явно разрешено | PostgreSQL; чтение и исправления данных | `STARTUP_DATA_UPDATES_ENABLED=false`; CLI не запускает startup-аудиты |
| Схема / RLS | при старте, если разрешено | PostgreSQL | `DATABASE_AUTO_MIGRATE=false`; только отдельная ручная maintenance-команда |
| Новый bounded discovery | ручной Actions; закомментирован daily 03:00 UTC = 08:00 Ташкент | `DATABASE_URL`, опционально Gemini/Groq | До 45 минут работы, Actions timeout 48 минут |
| pg_dump | ручной Actions; закомментирован Sunday 02:00 UTC | `DATABASE_URL`, `BACKUP_ENCRYPTION_PASSPHRASE` | До 180 секунд дампа / 20 MiB, job timeout 10 минут |

При включении старого встроенного scheduler его задачи НЕ становятся автоматически
ограниченными новым дневным бюджетом. Для этого режима scheduler должен оставаться
выключенным на всех веб-экземплярах. Ручные старые CLI-команды тоже не получают
новые расходы/лимиты автоматически: используйте только `backend.app.free_daily`.

## Команда и ограничения

```bash
.venv/bin/python -m backend.app.free_daily --trial
# После проверки владельцем:
.venv/bin/python -m backend.app.free_daily
```

Работает с уже подготовленной схемой PostgreSQL через `DATABASE_URL`.
Не создаёт/мигрирует схему перед получением lease. Ошибка настройки не включает
SQLite fallback. Обе команды записывают данные: не запускайте их для простой
проверки подключения. Цель — новые первые публикации за календарные сутки
**Asia/Tashkent**; восстановление старой скрытой карточки не увеличивает счётчик.

| Переменная | Обычный запуск | Trial |
|---|---:|---:|
| `DAILY_PROJECT_TARGET` | 20 | не больше 5 |
| `DAILY_MAX_RUN_SECONDS` | 2700 | не больше 300 |
| `DAILY_PAGES_PER_RUN` / `DAILY_PAGES_PER_DAY` | 60 / 80 | не больше 20 / 20 |
| `DAILY_GEMINI_REQUESTS_PER_RUN` / `_PER_DAY` | 10 / 10 | не больше 5 / 5 |
| `DAILY_GROQ_REQUESTS_PER_RUN` / `_PER_DAY` | 10 / 10 | не больше 5 / 5 |
| `DAILY_SEARCH_REQUESTS_PER_RUN` / `_PER_DAY` (Brave) | 0 / 0 | 0 / 0 |
| `DAILY_GITHUB_REQUESTS_PER_RUN` / `_PER_DAY` | 2 / 2 | не больше 1 / 1 |
| `DAILY_CANDIDATES_PER_RUN` / `_PER_DAY` | 80 / 120 | не больше 20 / 20 |
| `DAILY_MAX_SOURCES` | 12 | не больше 6 |
| `DAILY_LLM_MIN_INTERVAL_SECONDS` | 60 | 60 |
| `DAILY_LLM_MAX_OUTPUT_TOKENS` | 2048 | 2048 |
| `DAILY_MAX_DATABASE_BYTES` | 250000000 | столько же |
| `DAILY_MAX_RSS_MB` | 384 | столько же |

Более низкие заданные значения сохраняются в trial. Нулевой бюджет запрещает
соответствующий ресурс. OpenAI/OpenRouter/совместимый AI отключены в этом CLI,
даже если их ключи случайно присутствуют. Workflow вообще не передаёт их.
Brave тоже не передаётся. Профиль CLI допускает Brave только при отдельном
`FREE_SEARCH_QUOTA_CONFIRMED=true` и положительных лимитах; в поставляемом
workflow он всегда отключён. Основной путь бесплатного поиска — публичные
страницы/RSS и ограниченный GitHub API без токена.

По умолчанию `FREE_PROVIDER_QUOTAS_CONFIRMED=false`: Gemini/Groq не вызываются,
даже если ключи заданы. Включать `true` можно только после проверки аккаунтов и
моделей. Без LLM generic RSS уходит на рассмотрение. Публиковать детерминированно
может только существующий разрешённый adapter+page_type из
`config/trusted_catalog_pages.json`.
Не добавляйте доверие источникам ради количества. В текущей конфигурации может
не быть ни одного включённого trusted-профиля: keyless публикаций тогда будет 0.

Учёт в `scheduler_checkpoints` (`free_daily:YYYY-MM-DD`) сохраняется ДО сетевого
запроса: авария может завысить расход, но не обнулит его. Считаются попытки,
включая неудачные, robots.txt и редиректы. GitHub HTTP учитывается и как поиск,
и как страница. Дневные счётчики общие для повторных trial/daily запусков;
trial намеренно может остановиться раньше, если расход за день уже больше его
лимита. Входящие запросы посетителей, старые CLI и чужие приложения с тем же
API-ключом сюда не входят.

При достижении любого положительного run/day лимита работа завершается; остаток
очереди сохранён. Поэтому 10 успешных запросов к основному LLM могут остановить
job раньше цели 20. MULTI может дать несколько проектов за запрос; оставшиеся
валидированные записи сохраняются до следующего дня без повторного LLM.
429/quota блокирует только этот сервис до конца дня и переключает на другой.
Остальные ошибки имеют существующий circuit breaker и ноль повторов в bounded
профиле. При смене суток job завершается; новый запуск использует новый ledger.

Lease `pipeline` общий для job, обычного pipeline, CLI-писателей, админских
правок и вспомогательных workers. Вложенные операции не снимают внешний lease.
Конкурирующий запуск возвращает busy, админская запись — HTTP 409. После аварии
lease истекает (с запасом к runtime), зависший Run при следующем захвате отмечается
interrupted. Maintenance/schema/import требуют отдельно остановить писателей.
Старый запущенный код без этой защиты нужно остановить перед первым запуском.

Сначала идёт существующая очередь: project-first источники/Show HN, проектные
подсказки в заголовке, приоритет источника, возраст. Это сортировка, не обход
quality gate. Затем проверяются due-источники по приоритету. Гарантии ротации всех
низкоприоритетных источников за один короткий запуск нет. HIDE/REJECT владельца
сохраняются и проверяются до AI и при повторной записи; новая ссылка не снимает
админское решение с уже известного канонического проекта.

## Реалистичная стоимость и результат

Актуальные бесплатные квоты этих аккаунтов неизвестны. Лимиты выше — локальные
предохранители, а не утверждение о праве на бесплатное использование. Не
включайте платный billing/автопополнение. При нулевых доступных квотах оставьте
провайдеры выключенными. Нельзя гарантировать отсутствие списаний только наличием
API-ключа и счётчиком запросов: провайдеры считают также токены/модели/другие jobs.

| Сервис | Что проверить самостоятельно до включения |
|---|---|
| Gemini | Есть ли free tier для выбранной модели/страны/проекта без карты; RPM, TPM, RPD, billing и расход другими клиентами |
| Groq | Бесплатная доступность выбранной модели; RPM/TPM/RPD/TPD, условия аккаунта и лимиты панели |
| OpenAI | Общий API не считать бесплатным; подписка ChatGPT не является API-кредитами. Здесь отключён |
| OpenRouter | Не считать баланс или `:free` гарантией; здесь полностью отключён |
| Brave | Наличие free allowance, карта/тариф/автопополнение; здесь отключён |
| GitHub public API | Лимит анонимного IP/shared runner и search rate limit; 403/429 останавливает поиск на день |
| GitHub Actions | Остаток Linux minutes и artifact storage аккаунта, другие репозитории, spending limit = 0 |
| Supabase / Render | Фактический Free plan, размер/egress/паузы; не включены платные cron/worker/disk |

Верхние пределы суток: 80 HTTP, 10 Gemini + 10 Groq попыток (если разрешены),
2 GitHub searches, 0 платных LLM/Brave; реальный запуск останавливается раньше
при первом достигнутом лимите. 60 секунд между запросами к каждому LLM —
консервативная настройка, не подтверждённая квота аккаунта. Выход не более 2048
токенов/запрос. Промпт классификатора около 9.2 тыс. символов плюс до 3.8 тыс.
символов статьи и служебная обёртка; точное число input/thinking/billed tokens
зависит от модели, его нужно измерить на пробном запуске в панели провайдера.

Историческая **офлайн** выборка из ранее закоммиченного SQLite snapshot:
98 runs, 37593 raw; catalog-подвыборка 32 runs, 806 обработок, 43 перехода в
публикацию. Provider health накопленно: Gemini 240 запросов / 139 успешных;
Groq 31 / 6, в том числе 9 rate-limit ошибок. Это разные популяции и повторные
обработки: 806/43 ≈ 18.7 обработок/публикацию и 271/43 ≈ 6.3 LLM-попытки —
только грубый ориентир, НЕ измеренная стоимость одного нового проекта.
Исторический pages counter отсутствует; среднее страниц честно вычислить нельзя.
При такой грубой экстраполяции 20 публикаций потребовали бы ~375 обработок и
~126 LLM-попыток — больше новых defaults. Начните с цели 3–5, затем измерьте
yield; default 20 сохраняет желаемый потолок, не обещает выдачу. Фильтры не ослаблены.

Один daily job максимум 48 Actions-минут, 31 запуск = 1488 минут/месяц.
5 weekly backups по 10 минут = ещё 50; вместе ≤1538, плюс CI/ручные повторы и
прочие репозитории. Trial job обычно ≤5 минут обработки плюс install; общий
Actions timeout остаётся48 минут. CI timeout15 минут на запуск, артефакты ошибок
1 день. Не считать это автоматически доступным лимитом аккаунта.
Зашифрованный dump ≤20 MiB плюс небольшая служебная надбавка, retention1 день:
это НЕ долгосрочное хранение — скачивайте его в своё защищённое хранилище.

Память: HTTP body ≤500000 bytes; ответы LLM ограничены; диагностика не загружает
десятки тысяч article JSON, dedup читает проекты пакетами50. Job проверяет
peak RSS перед единицами работы и останавливается при384MiB. Это предохранитель,
не OS-cgroup лимит и не доказательство fit всей реальной БД в512MiB. Фактический
peak сохраняется в Run.details; проверяйте trial. Офлайн чтение диагностики
исторического snapshot с37889 кандидатами дало peak76MiB в отдельном процессе;
это не замер HTTP/LLM или полного production-сервиса. Веб-сервис не запускает сбор.

## Настройка владельцем и первый trial

1. Review/merge код из `free-daily-operations` в default branch, чтобы GitHub
   показывал `workflow_dispatch`. Если Render отслеживает `render-deploy`,
   обновляйте его отдельно и осознанно; push дочерней ветки не включает сервисы.
2. GitHub → Settings → Secrets and variables → Actions → Secrets:
   обязательный **`DATABASE_URL`** (та же подготовленная Supabase Session pooler
   база, что на Render). Не добавлять строку в Variables/логи/команды чата.
   Опциональные **`GEMINI_API_KEY`**, **`GROQ_API_KEY`** — только после проверки
   бесплатных квот. `ADMIN_API_KEY` нужен на Render для `/admin`, не для job.
   Для backup отдельно **`BACKUP_ENCRYPTION_PASSPHRASE`** — сильная фраза,
   хранить вне GitHub тоже. Платные API/Search/Telegram secrets job не нужны.
3. Variables: `FREE_PROVIDER_QUOTAS_CONFIRMED=true` только после проверки выше;
   `GEMINI_MODEL` / `GROQ_MODEL` — модели с подтверждёнными free-квотами.
   При необходимости лимиты из таблицы (можно снижать, не повышать вслепую).
   Отсутствующие variables имеют defaults. `DAILY_PROJECT_TARGET=20` опционален.
   Для абсолютно keyless trial оставить confirmation=false, ожидая review/0 публикаций.
4. Render Environment: оставить все три safety flags=false; тот же
   `DATABASE_URL`, свой `ADMIN_API_KEY`. Для нового admin budget блока нужен
   проверенный deployment этой версии. Не включать встроенный scheduler.
   Остановить старые Codespace скрипты/scheduler; новый lease не защитит от старого кода.
5. GitHub Actions → **Bounded free daily discovery** → Run workflow → выбрать
   ветку с этим кодом и mode **trial**. Это уже боевой write, выполните сами
   после резервной копии. Повторный запуск в тот же день НЕ обнуляет бюджеты.
6. Проверить JSON stop_reason/counts/usage в Actions и `/admin` → «Bepul kunlik ish»:
   день Ташкент, найденные raw за24ч, новые публикации, запросы по сервисам,
   страницы, enabled/blocked, предупреждения80%. Данные API `/api/admin/status`
   доступны только с admin key; ключи не возвращаются. «Найдено» означает новые
   raw-кандидаты, не гарантированно реальные проекты.
7. Если trial безопасен, вручную mode daily. Лишь затем раскомментировать daily
   schedule в `.github/workflows/daily-discovery.yml` на default branch.
   GitHub может задерживать cron; дневной ledger исключает сброс расхода при повторах.
   Для weekly backup аналогично сначала ручная проверка, затем отдельное включение
   закомментированного schedule. Автоматически ничего не включено.

## Резервная копия и восстановление

```bash
# На доверенной машине с pg_dump соответствующей версии; URL только в env:
.venv/bin/python scripts/backup_postgres.py
# Либо клиент postgres:18 через Docker, как в workflow:
.venv/bin/python scripts/backup_postgres.py --docker-client
```

`pg_dump --format=custom --schema=public --no-owner --no-acl`, уникальное UTC-имя
в `data/backups/`, mode0600, streaming; credentials в env дочернего процесса,
не в argv. Лимиты `BACKUP_MAX_BYTES=20971520`, `BACKUP_MAX_SECONDS=180`.
Ошибка/превышение удаляет неполный файл. Это копия application public schema,
НЕ всей Supabase платформы auth/storage/ролей. Workflow выполняется только в
private repository, шифрует AES256 через GPG, удаляет plaintext и сохраняет
приватный `.gpg` artifact на1 день. В репозиторий/образ dump не входит.

Скачайте artifact, расшифруйте интерактивно (не передавать фразу в аргументе):

```bash
gpg --output restored.dump --decrypt izlanish-YYYYMMDDTHHMMSSZ-unique.dump.gpg
# Только отдельная ПУСТАЯ тестовая БД, никогда не боевой DATABASE_URL:
pg_restore --dbname="$RESTORE_TEST_DATABASE_URL" --no-owner --no-acl restored.dump
```

Для реального аварийного восстановления нужен отдельный review/остановка
писателей, проверка ролей/RLS и содержимого. Автоматического destructive restore нет.

## Что проверено и что ещё нет

Офлайн тесты: расход до запроса, restart/day boundary, цели/остаток MULTI,
quota fallback, блокировка до конца дня, запрет paid providers, один писатель,
HIDE/REJECT,80% status, источник с ошибкой, ограничение HTTP/GitHub, безопасный
streaming dump с подставным процессом. Backend/Ruff/build/browser результаты
смотрите в финальном отчёте коммита. Базы тестов временные SQLite; production
DATABASE_URL не используется и не очищается. Новых таблиц/миграций не требуется.

**Не проверены:** live Supabase и его роли/размер/egress, настоящий pg_dump/restore,
Docker pull postgres:18, реальные LLM модели/квоты/токены, текущая точность/yield,
Actions secrets/права/расписание, реальный512MiB peak и Render deploy. Никаких
боевых discovery/backup/записей или внешнего включения расписания не выполнено.

## Изменённые и добавленные файлы

- `.dockerignore`
- `.env.example`
- `.github/workflows/ci.yml`
- `.github/workflows/daily-discovery.yml`
- `.github/workflows/weekly-backup.yml`
- `.gitignore`
- `ARCHITECTURE.md`
- `PROJECT_STATUS.md`
- `README.md`
- `backend/app/admin_alerts.py`
- `backend/app/catalog.py`
- `backend/app/catalog_admin.py`
- `backend/app/catalog_pipeline.py`
- `backend/app/catalog_store.py`
- `backend/app/cli.py`
- `backend/app/collectors/sources.py`
- `backend/app/config.py`
- `backend/app/daily.py`
- `backend/app/deep_analysis.py`
- `backend/app/diagnostics.py`
- `backend/app/free_budget.py`
- `backend/app/free_daily.py`
- `backend/app/llm_service.py`
- `backend/app/main.py`
- `backend/app/network.py`
- `backend/app/pipeline.py`
- `backend/app/raw_discovery.py`
- `backend/app/registry.py`
- `backend/app/scheduler.py`
- `backend/app/telegram_ingest.py`
- `backend/app/writer.py`
- `docs/FREE_DAILY_OPERATIONS.md`
- `docs/RENDER_DEPLOY.md`
- `frontend/e2e/site.spec.ts`
- `frontend/src/StatusPage.tsx`
- `frontend/src/types.ts`
- `render.yaml`
- `scripts/backup_postgres.py`
- `tests/test_backup_postgres.py`
- `tests/test_daily_publication.py`
- `tests/test_free_daily.py`

Проверки: 360 backend tests, Ruff, TypeScript/production build и22 браузерных
теста прошли локально. После уточнения выборки last_run повторно прошли21
целевой budget/backup test. CI на GitHub не запускался как отдельное доказательство.
