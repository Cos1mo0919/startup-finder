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
| `DAILY_PAGES_PER_RUN` / `DAILY_PAGES_PER_DAY` | 60 / 80 | отдельные `TRIAL_PAGES_PER_RUN` / `TRIAL_PAGES_PER_DAY`: 40 / 40 |
| `DAILY_GEMINI_REQUESTS_PER_RUN` / `_PER_DAY` | 10 / 250 | не больше 5 / 5 |
| `DAILY_GROQ_REQUESTS_PER_RUN` / `_PER_DAY` | 10 / 500 | не больше 5 / 5 |
| `DAILY_SEARCH_REQUESTS_PER_RUN` / `_PER_DAY` (Brave) | 0 / 0 | 0 / 0 |
| `DAILY_GITHUB_REQUESTS_PER_RUN` / `_PER_DAY` | 2 / 2 | не больше 1 / 1 |
| `DAILY_CANDIDATES_PER_RUN` / `_PER_DAY` | 80 / 120 | не больше 20 / 20 |
| `DAILY_MAX_SOURCES` | 12 | не больше 6 |
| `DAILY_LLM_MIN_INTERVAL_SECONDS` | 6 | 6 |
| `DAILY_LLM_MAX_OUTPUT_TOKENS` | 2048 | 2048 |
| `DAILY_MAX_DATABASE_BYTES` | 250000000 | столько же |
| `DAILY_MAX_RSS_MB` | 384 | столько же |

Более низкие заданные значения сохраняются в trial, кроме страниц: их trial-лимиты независимы от DAILY_PAGES_*. Нулевой бюджет запрещает
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

Учёт сохраняется до сетевого запроса. Страницы имеют отдельные дневные записи
`free_pages:trial:YYYY-MM-DD` и `free_pages:daily:YYYY-MM-DD`; сутки —
00:00–24:00 Asia/Tashkent. Общие остальные счётчики остаются в
`free_daily:YYYY-MM-DD`. Страницы failed/interrupted запусков возвращаются в
локальный бюджет страниц; реальные попытки и история сохраняются. Расход LLM,
токенов, поиска, кандидатов и публикаций не возвращается. Завершённый bounded
запуск (включая daily_limit:pages) сохраняет расход. При первом использовании
нового ledger он восстанавливается из старых Run, исключая failed/interrupted;
прерванные процессы также сверяются при следующем запуске. Это не отменяет
фактические HTTP-запросы и ограничения внешних сервисов.

Robots.txt, редиректы и GitHub HTTP считаются страницами. Обычная оценка пяти
кандидатов требует примерно 10 запросов (robots + страница), с редиректами и
несколькими доменами — ориентировочно 10–30; trial 40 оставляет запас на discovery.
Доступность источников и качество не гарантируют пять решений или публикаций.

### Диагностика и ручной сброс trial

Следующие команды выполняет оператор с актуальным кодом и своим DATABASE_URL:

```bash
# Только чтение; старые дочерние Run связаны по времени, это явно помечено.
.venv/bin/python -m backend.app.free_daily --inspect-run 121
# Только чтение: показывает net pages_before и expected_state.
.venv/bin/python -m backend.app.free_daily --reset-trial-pages
# Только после проверки предыдущего вывода; заменить HASH на expected_state.
.venv/bin/python -m backend.app.free_daily --reset-trial-pages --apply --expect-state HASH
```

Сброс выполняется транзакционно под общим writer lease. Изменение счётчика или
ташкентской даты после preview отменяет сброс: повторите preview. Обычный
страничный бюджет, LLM/токены, кандидаты, публикации и Run не сбрасываются.
Старые события/attempts остаются для аудита. Не редактируйте JSON SQL-запросом.
Например, по предоставленным данным 107=5 failed, 113=9 failed, 121=6 completed:
физически 20, net trial 6 (если других записей нет), возврат 14.

Раньше processed означал число вернувшихся вызовов pipeline, даже без решения.
Теперь итоговый JSON содержит attempted, pipeline_calls_returned, processed
(записанное решение), fetch_failed, budget_stopped, no_decision, worker_failed;
rejected включает pre_filtered. Поле candidate_runs содержит SHA кандидата,
дочерний run_id, status/stage, reason, stop_reason, error_codes. Дополнительно
выводятся llm_requests и page_budget (mode, attempted_this_run, refunded,
charged_today, daily_limit). Три старых processed нельзя без дочерних Run
объявить тремя классификациями: возможны ошибки fetch, остановка бюджета,
отсутствие работы или ранее не учтённый pre_filtered. --inspect-run показывает
доступные старые дочерние отчёты, но не выдумывает отсутствующие stage.

При достижении общих лимитов (страницы/кандидаты/цель/время) работа завершается;
остаток очереди сохранён. Лимиты LLM обрабатываются отдельно: исчерпавший свой
бюджет провайдер пропускается, следующий может продолжить работу. Ограничение
10 запросов на один запуск сохраняется независимо от больших суточных бюджетов;
trial — максимум5. MULTI может дать несколько проектов за запрос; оставшиеся
валидированные записи сохраняются без повторного LLM. 429 получает до2 повторов
с паузами15/30 секунд, с учётом Retry-After и минутного окна. После неудачных
повторов сервис блокируется до конца его окна; остальные ошибки не повторяются.
При смене суток Ташкента job завершается, но API-бюджет НЕ обнуляется.

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

Владелец сообщил квоты Gemini/Groq (см. ниже); доступность моделей и расходы
других клиентов здесь не проверялись. Лимиты выше — локальные
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

Верхние пределы: 80 HTTP за сутки Ташкента; Gemini250 запросов за Pacific-день;
Groq500 запросов и100000 токенов за скользящие24 часа; 2 GitHub searches,
0 платных LLM/Brave. На ОДИН запуск остаётся не больше10 запросов каждому LLM.
Сутки разных сервисов не складываются в один счётчик. Фактические расходы могут
быть значительно ниже из-за цели20, ограничений страниц/очереди/времени.
Подробности резервирования токенов и окон — в следующем разделе.

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
   `GROQ_MODEL` — модель с подтверждёнными free-квотами. Gemini в bounded job
   закреплён на `gemini-3.1-flash-lite`.
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

## Дополнение 2026-10-15: токены и реальные окна API

| Настройка | Default | Окно |
|---|---:|---|
| `DAILY_GROQ_REQUESTS_PER_DAY` | 500 | Скользящие24 часа, агрегировано для всех Groq-моделей |
| `DAILY_GROQ_TOKENS_PER_DAY` | 100000 | То же окно, input+output |
| `GROQ_REQUESTS_PER_MINUTE` | 30 | Скользящие60 секунд |
| `GROQ_TOKENS_PER_MINUTE` | 8000 | Скользящие60 секунд, безопасный резерв |
| `GROQ_TOKENS_PER_REQUEST` | 5500 | Оценка input+максимальный output+128 framing |
| `DAILY_GEMINI_REQUESTS_PER_DAY` | 250 | Полночь America/Los_Angeles, DST учитывается |
| `GEMINI_REQUESTS_PER_MINUTE` | 10 | Скользящие60 секунд |
| `GEMINI_TOKENS_PER_MINUTE` | 200000 | Локальный запас ниже сообщённых250000 TPM |
| `DAILY_GEMINI_TOKENS_PER_DAY` | 1000000 | Дополнительный наш safety cap; НЕ заявленная квота Google |
| `LLM_RATE_LIMIT_RETRIES` | 2 | Дополнительные попытки только при429 |
| `LLM_RATE_LIMIT_BACKOFF_SECONDS` | 15 | Базовая пауза; затем30 секунд |

Сообщённые владельцем Groq-квоты:30 RPM,1000 RPD,8000 TPM,200000 TPD для
его gpt-oss-120b/gpt-oss-20b/qwen3.8-27b. Приложение считает Groq совокупно,
не умножает allowance при смене модели. Default `GROQ_MODEL=openai/gpt-oss-20b`;
меняется GitHub Variable/переменной окружения `GROQ_MODEL`. ID другой модели
копируйте из панели Groq: доступность и точное написание здесь не проверялись.

Gemini только `gemini-3.1-flash-lite`: другие Gemini-модели не считаются
configured; bounded профиль закрепляет эту модель даже при старом env override.
Владелец сообщил15 RPM/250000 TPM/500 RPD. Локально10 RPM/250 RPD.
Полночь Pacific —12:00 Ташкента при PDT и13:00 при PST; не00:00 Ташкента.
Публикации/страницы по-прежнему считаются по Ташкенту. Groq24h выбран
консервативно, потому что точное время сброса аккаунта неизвестно.

Долговечный ledger `scheduler_checkpoints:llm_quota:<provider>` хранит каждую
попытку ДО HTTP, резерв токенов, usage и timezone/reset. Новая схема/миграция
не требуется. При переходе с request-only версии старые попытки импортируются
с максимальным резервом, не обнуляются. Паузы и токены переживают restart;
смена модели/Ташкентская полночь не сбрасывают Groq. При Pacific rollover
минутное окно Gemini сохраняется (включая25-часовой день осеннего DST).

Оценка: Latin UTF-8 bytes/3 с запасом25%, не-ASCII — bytes с тем же запасом.
Это НЕ точный model-specific tokenizer;5500 — приблизительный предохранитель.
Служебные правила сохраняются, убираются лишние пробелы; обрезается только
копия source текста, отправляемая модели. Если одни правила не помещаются,
запрос не выполняется. Groq output ограничен1024 токенами (либо меньшим
заданным лимитом); Gemini сохраняет общий output cap. Превышение модели,
reasoning и особенности её tokenizer могут отличаться: usage API уточняет
расход. Usage отсутствует/timeout/429/крах — полный резерв остаётся списанным.
Минутный резерв после успешного ответа не уменьшается, чтобы не нарушить TPM.

`/admin` отдельно показывает provider requests/tokens/80%, подтверждённые токены,
неподтверждённые попытки, блокировку и окно/reset. Верхняя дневная таблица больше
не сравнивает запросы Gemini по Ташкенту с Pacific-лимитом. Возвращённые
`usage.total_tokens` (Groq) и `usageMetadata.totalTokenCount` (Gemini) учитывают
общее API usage; сторонние клиенты с теми же ключами в наши счётчики не входят.
Проверьте панель провайдера после trial. Существующие GitHub Variables со старым
значением10/сутки нужно обновить вручную — defaults не переписывают Variables.

Защита действует в `backend.app.free_daily`; старые произвольные CLI/включённый
встроенный scheduler не становятся автоматически free-budget jobs.

Изменения2026-10-15: новый `backend/app/llm_budget.py`, тесты
`tests/test_llm_token_budgets.py`; интеграция в `free_budget.py`, `free_daily.py`,
`llm_service.py`, `config.py`; workflow/env example, admin types/UI/browser test
и документация обновлены. Проверки:377 backend tests, Ruff, build и22 browser tests.
Trial ограничивает запросы за запуск до5, но не переписывает общий API-day cap
на5: иначе пробный запуск мог бы заблокировать обычный daily до конца окна.

### 2026-10-15: безопасный дедлайн и PostgreSQL pool

После ошибки run113 удалён SIGALRM, который мог прервать psycopg внутри SQL.
Дедлайн45 минут проверяется между операциями; один текущий ограниченный запрос
и cleanup могут завершиться позже. Daily CLI задаёт PostgreSQL statement_timeout
30 секунд на НОВОМ соединении, connect_timeout10 секунд; Actions hard timeout
остаётся48 минут. Runtime checkout не переключает autocommit: откатывает
незавершённые неактивные транзакции, заменяет ACTIVE-соединения, выполняет
SELECT1/rollback до передачи соединения приложению. SQLite не меняется.
Отдельная PostgreSQL CI-проверка: `.github/workflows/postgres-regression.yml`.
Подробности/непроверенные пункты — `docs/DAILY_POSTGRES_DEBUG.md`.
