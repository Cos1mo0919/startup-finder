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
| Новый bounded discovery | ручной Actions; закомментирован daily 09:00 UTC = 14:00 Ташкент | `DATABASE_URL`, опционально Gemini/Groq | До 45 минут работы, Actions timeout 48 минут |
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
| `DAILY_MAX_RUN_SECONDS` | 2700 | отдельный `TRIAL_MAX_RUN_SECONDS`: по умолчанию300, явно до600 |
| `DAILY_PAGES_PER_RUN` / `DAILY_PAGES_PER_DAY` | 60 / 80 | отдельные `TRIAL_PAGES_PER_RUN` / `TRIAL_PAGES_PER_DAY`: 40 / 40 |
| `DAILY_GEMINI_REQUESTS_PER_RUN` / `_PER_DAY` | 10 / 250 | не больше 5 / 5 |
| `DAILY_GROQ_REQUESTS_PER_RUN` / `_PER_DAY` | 10 / 500 | не больше 5 / 5 |
| `DAILY_SEARCH_REQUESTS_PER_RUN` / `_PER_DAY` (Brave) | 0 / 0 | 0 / 0 |
| `DAILY_GITHUB_REQUESTS_PER_RUN` / `_PER_DAY` | 2 / 2 | не больше 1 / 1 |
| `DAILY_CANDIDATES_PER_RUN` / `_PER_DAY` | 80 / 120 | не больше 20 / 20 |
| `DAILY_CANDIDATES_PER_SOURCE` | 3 (за запуск, по очереди между источниками) | 3 |
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
моделей. Bounded free_daily без разрешённого настроенного LLM теперь завершается
с no_llm_provider ДО выбора кандидатов. В общем catalog pipeline (вне bounded job)
без LLM generic RSS остаётся на рассмотрении. Публиковать детерминированно
может только существующий разрешённый adapter+page_type из
`config/trusted_catalog_pages.json`.
Не добавляйте доверие источникам ради количества. В текущей конфигурации может
не быть ни одного включённого trusted-профиля: keyless публикаций тогда будет 0.

Учёт сохраняется до сетевого запроса. Страницы имеют отдельные дневные записи
`free_pages:trial:YYYY-MM-DD` и `free_pages:daily:YYYY-MM-DD`; сутки —
00:00–24:00 Asia/Tashkent. Кандидаты имеют отдельные free_candidates:trial/daily ledger;
остальные общие счётчики остаются в `free_daily:YYYY-MM-DD`. Страницы failed/interrupted запусков возвращаются в
локальный бюджет страниц; реальные попытки и история сохраняются. Расход LLM,
токенов, поиска, кандидатов и публикаций автоматически не возвращается
(для missing_key кандидатов есть отдельная ручная recovery ниже). Завершённый bounded
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
Зашифрованный dump ≤20 MiB плюс небольшая служебная надбавка, retention7 дней:
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
   При confirmation=false или отсутствии обоих ключей trial завершится с
   no_llm_provider и0 попыток: это проверка preflight, не оценка классификатора.
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
приватный `.gpg` artifact на7 дней. В репозиторий/образ dump не входит.

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
запрос не выполняется. Groq и Gemini используют заданный output cap (по умолчанию2048),
сохраняя общий лимит input+output. Старый принудительный Groq cap1024 удалён. Превышение модели,
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


## Run125: тайминги и диагностика trial (2026-10-16)

Боевой run125 и источники из Supabase в этой среде не читались. По предоставленному
отчёту известно: 4 попытки, 2 article_body_missing, 1 review llm_unavailable,
1 budget_stopped/max_run_seconds, по одному запросу Gemini/Groq. Названия,
домены, HTTP-ответы и длительность отдельных этапов в предоставленных данных
отсутствуют. Нельзя объявить эти два случая JS/403/paywall или приписать Groq
reasoning truncation без сохранённого ответа/диагностики. 331 секунду нельзя
разложить на этапы задним числом. Расход запроса/токенов означает резерв/попытку,
а не валидный ответ классификатора.

Оператор может выполнить **только чтение**, после получения кода ветки:

```bash
.venv/bin/python -m backend.app.free_daily --inspect-run 125
```

Команда дополняет старые candidate_runs названием источника, доменом и типом
страницы, когда удаётся связать Candidate/дочерний Run. Показывает сохранённые
provider_metrics (накопительные метрики сервиса, не HTTP-лог отдельной попытки). Для старых записей без instrumentation: timings_available=false;
это не нулевая длительность. Если связь не сохранилась, источник остаётся
неизвестным. Новые fetch_failed тоже сохраняют last_run_id для этой связи.

### Новые поля отчёта и /admin

Каждый candidate_runs содержит source {name,domain,page_type}, timings_ms:
robots, page_read, extraction, llm, pauses, lock_wait, total, other.
Измерения вложенных этапов исключают двойной учёт. total охватывает дочерний
pipeline, other — не размеченные операции/DB/запись результата; время внешнего
discovery, финального отчёта и закрытия соединений не входит в candidate total.
lock_wait — elapsed обращения к lease/его продления, включая выполнение SQL;
это не серверная статистика PostgreSQL pg_locks. Секреты, query strings,
заголовки, prompts и текст ответа LLM не сохраняются в telemetry.

fetch содержит домен, HTTP-статус, тип robots/page, безопасный код ошибки.
extraction содержит способ, число слов, selector_missing, encoding_replacements.
Наличие script/paywall даёт диагностическую гипотезу js_shell/paywall_detected,
а не доказательство блокировки. HTTP403/404/429 и page_timeout имеют собственные
коды и не маскируются как article_body_missing. Редиректы видны по HTTP3xx
и последующим доменам; доступа в обход robots/paywall/403 нет.

provider_attempts содержит provider/model, request_sent, http_status (null если
ответа не было), outcome, exception_class при ошибке, finish_reason, elapsed_ms.
Причины: timeout, rate_limited, quota_exceeded, provider_error, invalid_json,
empty_response, output_truncated, schema_validation_failed,
business_validation_failed, missing_key, circuit_open, local_block/local_budget.
Локальная причина содержит тип квоты/лимита без ключа. provider_waits показывает
минутные ожидания и пропуск ожидания, которое не помещается в deadline кандидата.
HTTP200 с invalid_json/schema_validation_failed всё равно заканчивается fallback;
если все провайдеры не дали валидного анализа, итоговый reason остаётся
llm_unavailable, а конкретная причина теперь доступна рядом.

Groq GPT-OSS получает reasoning_effort=low. Общий приблизительный предел запроса
5500 токенов сохраняется: увеличение доступного output до2048 сокращает input,
а не увеличивает общий резерв. JSON берётся только из content, не из reasoning;
finish_reason=length / Gemini MAX_TOKENS дают output_truncated, повреждённый JSON
не «чинится» выдуманными полями. Gemini объединяет все не-thought text parts.
На invalid JSON, schema failure, 403/404 нет бессмысленных повторов. Управляемые
повторы429 остаются ограниченными и пропускаются, если пауза не помещается.
Реальная эффективность этих настроек на run125 не измерена.

### Скорость и выбор кандидатов

В bounded профиле connect <=3s, read <=8s, LLM <=15s на провайдера; значения
уменьшаются до оставшегося времени кандидата/запуска. Отдельный
DAILY_CANDIDATE_TIMEOUT_SECONDS=45 (настраивается) ограничивает кооперативную
работу кандидата. Истечение даёт candidate_timeout, не обрывает остальные
кандидаты. Trial остаётся <=300 секунд работы; завершение транзакций/cleanup,
DNS и системные задержки могут выйти за предел. Это не жёсткое прерывание
psycopg/SIGALRM. После deadline новые кандидаты не стартуют.

Пять кандидатов по45s оставляют примерно75s из300s на discovery и накладные
расходы; это расчёт, не обещание пяти успешных LLM-анализов. Кэш robots сохраняется.
Убран лишний llm_batch_delay в bounded job: минутные/суточные квоты и обязательные
provider-паузы действуют независимо. Безнадёжные HTTP403/404 не повторяются.

Очередь сначала понижает источники с >=3 fetch_failed за7 дней (body missing,
403/404, timeout), затем предпочитает сохранённый текст >=200 символов,
project-first источники, project hints, приоритет и возраст. Источники не
блокируются/удаляются, провалы не превращаются в публикации. Исторические записи
сохраняются; штраф исчезает после окна7 дней. Группировка ошибок одним SQL
подзапросом избегает сканирования всей истории для каждого кандидата.

Readability-подобный fallback использует плотный prose-блок, затем доступные
JSON-LD/og:description/meta description; выбирается наиболее содержательный
реальный фрагмент с >=8 словами. Даты и доказательства не выдумываются.
Сломанный body_selector больше не отвергает страницу, если fallback нашёл текст.
Любой извлечённый фрагмент проходит прежнюю классификацию/quality gate;
Show HN с <50 словами по-прежнему требует дополнительного извлечения.
Очевидные assets/login endpoints отбрасываются до robots/страницы/LLM.
Неоднозначные product/landing/короткие страницы по URL не отбрасываются.

Параллельное чтение пока не включено. Без отдельной синхронизации оно создаёт
риски для атомарного page budget, последовательных provider quotas и crawl-delay.
Если новые измерения покажут, что узкое место именно чтение, следующий шаг —
небольшой prefetch pool с общим throttler и последовательным LLM, а не несколько
независимых pipeline workers. До измерений не обещаем ускорение на боевых URL.

### Как оценить следующий trial

status=completed и worker_failed=0 означают отсутствие аварии, но сами по себе
не доказывают качество trial. Смотрите:

- counts.reached_llm: кандидаты, для которых действительно начат provider attempt;
- counts.llm_validated: кандидаты с успешной валидацией хотя бы одного ответа;
- counts.before_llm и before_llm_reasons: отсев/остановки до запроса;
- published/rejected/review_required: итоговые решения, не число запросов;
- candidate_runs[].provider_attempts[].outcome=success: успешный анализ;
- fetch_failed/budget_stopped/worker_failed, llm_unavailable и output_truncated:
  причины неполной оценки.

Цель проверки пяти кандидатов: reached_llm>=5 и llm_validated>=5, worker_failed=0,
нет llm_unavailable для этих пяти. published может быть0: пять корректных
NOT_PROJECT — технически успешная оценка, а не повод ослабить quality gate.
max_run_seconds при меньшем числе анализов — частичный, не успешный прогон.
В /admin → Bepul kunlik ish раскрывайте каждого кандидата: источник, тип,
тайминги, extraction и provider HTTP/outcome; сверяйте counts и net40/40 budget.
Старые Run без таймингов не получают выдуманные значения.

Cron discovery **закомментирован**: 09:00 UTC =14:00 Asia/Tashkent, после Gemini
Pacific midnight и летом (07:00 UTC), и зимой (08:00 UTC). Weekly cron тоже
закомментирован. Encrypted backup artifact хранится7 дней, исходный dump <=20MiB;
скачивайте его в своё защищённое хранилище, Actions не заменяет долговременный backup.

Тесты не используют production DATABASE_URL: HTTP/provider ответы подменены,
SQLite временный; два новых варианта проверяют сохранение диагностики на
одноразовой PostgreSQL16 через postgres-regression workflow. Без локального
IZLANISH_TEST_PG_PORT они явно skipped, не считаются успешно выполненными.


## Keyless fail-fast, отдельные кандидаты и восстановление run148 (2026-10-17)

В free_daily (trial **и** daily) обязательны LLM_ENABLED=true,
FREE_PROVIDER_QUOTAS_CONFIRMED=true и хотя бы один настроенный Gemini/Groq ключ
с разрешённой моделью и положительным бюджетом. Иначе stop_reason=no_llm_provider,
attempted=0, usage={}, candidate_runs=[]; сохраняется только Run аудита. Очередь,
raw discoveries, исходные статусы, счётчики кандидатов/страниц не меняются; pipeline
даже не создаётся. Наличие ключа не доказывает его действительность: HTTP401 и
другие провайдерские ошибки остаются отдельной диагностикой. Ключи/флаги должны
быть в той среде, где запущена команда (Codespace не получает Cloud secrets сам).

Кандидаты теперь имеют отдельные ledger:
free_candidates:trial:YYYY-MM-DD и free_candidates:daily:YYYY-MM-DD,
сутки Asia/Tashkent. Стандартные пределы trial20/20, daily80/120 не повышены;
меняется разделение расхода. Первое создание восстанавливает **весь** прошлый
расход своего режима из Run. Failed-кандидаты автоматически не возвращаются;
адресный возврат missing_key выполняется только ручной командой ниже. Старая
общая запись остаётся историей и больше не определяет candidate gate нового кода.
Обновите все запускающие daily CLI экземпляры, не смешивайте старые и новые writers.
JSON содержит candidate_budget.mode/attempted_this_run/charged_today/daily_limit;
/admin показывает оба бюджета кандидатов, а24h — физические попытки, не net возврат.
LLM/token quotas и публикации не разделяются и не сбрасываются этим изменением.

Trial выбирает максимум3 кандидата на один source_id за запуск, включая ошибки
и остановленные попытки. Для кандидатов без source_id используется домен.
Достигнув трёх, продолжает выбирать другие источники; оставшиеся записи первого
не меняют статус и не теряются. Source quality/project-first ordering сохраняется.
Daily этого ограничения3 не имеет. JSON source_attempts показывает распределение.

### Ручная recovery: только просмотр, затем явный apply

Эти команды **оператор запускает сам** в обновлённом checkout из корня репозитория.
Они предназначены именно для root run148 и дочерних149–167. Боевой запуск здесь
не выполнялся. Ожидается19 кандидатов review_required и20 резервирований root;
двадцатый кандидат, остановленный до обработки, уже queued и не переписывается.

```bash
# Только просмотр, без изменения БД и без захвата writer lease:
.venv/bin/python -m backend.app.free_daily --recover-no-llm-run 148 --child-from 149 --child-to 167
# После проверки вывода заменить HASH на его expected_state:
.venv/bin/python -m backend.app.free_daily --recover-no-llm-run 148 --child-from 149 --child-to 167 --apply --expect-state HASH
```

В preview: requeue_count=19, refund_candidates=20, budget_day, today,
refund_today, candidates_before/after, candidate_ids и expected_state. Отчёт не
печатает URLs, source text или ключи. Если исходный день уже прошёл, refund_today=0:
20 возвращаются в ИСХОДНЫЙ trial-день, сегодняшняя квота не увеличивается.

Проверяются completed trial родителя, нулевой LLM/token расход, точная принадлежность
дочерних записей родителю, missing_key обоих провайдеров без request_sent,
актуальный review_required + llm_unavailable и отсутствие проектов/ручных решений.
Неизвестные, изменённые, опубликованные или вручную рассмотренные записи не
перезаписываются; recovery_error объясняет отказ. Нельзя менять ID/range ради обхода.

Apply захватывает общий writer lease и выполняет всё одной транзакцией. Хеш
включает текущую ташкентскую дату, ledger, Run/child/Candidate/RawDiscovery значения;
изменение после preview отменяет операцию. Candidate становится queued,
RawDiscovery — pending, истории статусов дополняются, attempts/evidence и старые
Run остаются. Проверяется фактическое число обновлённых кандидатов и net-счётчик;
ошибка откатывает изменения. Refund привязан к root148, не вычитает20 из чужих
запусков. Повторный apply — already_applied без повторного возврата. Pages,
LLM/tokens, daily candidate budget, публикации и backup не затрагиваются.

После восстановления сначала задайте ключи и confirmation в Codespace, иначе
trial снова остановится с no_llm_provider (уже без расхода). Проверка успеха
предыдущего раздела остаётся: completed сам по себе не означает валидные анализы.

Тесты preflight не используют ключи/сеть. Компонентные тесты с injected offline
классификаторами явно подменяют только credential preflight через fixture;
реальные условия отсутствующих ключей/confirmation проверяются отдельно без неё.
Recovery проверяется на временном SQLite и в CI на disposable PostgreSQL16;
также проверяются stale hash/day, ручные решения, rollback, идемпотентность,
разделение ledger и разнообразие trial источников.


## Run169: разложение latency и сохранение результата

По предоставленным данным кандидаты заняли ~166s, LLM HTTP всего ~12.7s,
а total был ограничен300s. Это не измерение RTT Supabase: боевые SQL/ответы
здесь не читались. Старый other включал SQL SELECT/UPDATE, commit/rollback,
checkout ping+rollback, учёт provider health, quota reserve/reconcile и DB-работу
с источниками. Между короткими Session происходили отдельные round-trip.
Смена расположения runner/БД может усиливать это, но фактический регион runner
и точная разбивка старых42–46s без прежней instrumentation неизвестны.

### Новые измерения

candidate_runs[].timings_ms теперь дополнительно содержит db_sql, db_transaction,
db_checkout, db_connect, quota_before_http, quota_after_http, validation,
provider_window_wait, validated_checkpoint, decision_write, lease. Timings —
**exclusive**, вложенные этапы не складываются дважды. Собственно сон остаётся
pauses. other — оставшиеся неразмеченные Python/ORM/системные накладные расходы.

candidate_runs[].database содержит sql_queries, commits, rollbacks,
checkout_probes, elapsed_ms и by_component. Там quota_before_http/quota_after_http
показывают SQL-число и inclusive DB-time соответствующей операции (а не только
чистые UPDATE). Не суммируйте database.elapsed_ms повторно с timings: это
дополнительный агрегат тех же DB-вызовов. SQL text/параметры/ключи не пишутся.
Lease SQL помечен компонентом lease: это время запроса и network/execution/lock
вместе, не отдельная серверная статистика pg_locks.

provider_waits[].reason различает rpm, tpm_reserved_tokens, minimum_interval;
requested_seconds/skipped показывают ожидание или отказ ждать из-за deadline.
Минутные окна Gemini/Groq и резерв до HTTP остаются обязательными. Пауза Retry429
также измеряется как pauses; elapsed_ms отдельной попытки может включать её
backoff, для чистого HTTP смотрите timings_ms.llm.

run_phases_ms: initialization, queue_selection, processing, discovery, report,
total. processing включает подготовку/запись результата в родительский Run,
поэтому может быть больше суммы candidate totals. discovery включает получение
источников/RSS и сохранение ссылок; вложенная обработка кандидатов исключена.
run_database — SQL/transaction totals всего job. setup_timings_ms.engine_setup
измеряет создание engine; физическое подключение учитывается в db_connect и
initialization. setup_timings_ms.install заполняется Actions из длительности
install step; локально null, если измерения нет. Checkout/setup-python самого
Actions виден отдельно в UI Actions и сюда не включён.

Run/admin хранят снимок в существующем финальном отчёте (без дополнительного
commit ради telemetry); итоговый JSON содержит также завершение записи и освобождение lease. Малая разница
ожидаема: невозможно записать время собственного последнего commit без ещё
одного commit. Installation/engine setup не входят в300s рабочего budget.
Сам budget создаётся после начальной записи Run, а не с начала Actions job.

### Сокращение DB round-trip

- Все checkpoint reads в budget.check объединены в один SELECT; дублирующий
  pre-read в reserve убран, SELECT FOR UPDATE с проверкой перед списанием остаётся.
- Quota+aggregate ledger читаются одним locking SELECT на две строки, затем
  обновляются/commit ДО HTTP. Это один ledger-read, а не обещание одного SQL всего.
- Provider success/error+request metrics буферизуются до конца попытки и
  сохраняются вместе с usage reconciliation одной транзакцией. Fallback history
  по-прежнему сохраняется отдельно. Неизвестный usage сохраняет полный резерв.
- Advisory readiness cache действует внутри одного writer-owned job; reserve
  ВСЕГДА заново блокирует и проверяет durable quotas. Cache не разрешает HTTP
  поверх лимита. DB-size guard проверяется раз в10s, память/time — постоянно.
- Lease продлевается максимум раз в10s при lease >=600s (для коротких lease
  интервал не больше TTL/3). Checkout повторяет
  SELECT1 probe не чаще10s для недавно проверенного IDLE connection. ACTIVE,
  UNKNOWN и грязные транзакции всё равно обрабатываются при КАЖДОМ checkout,
  autocommit не переключается. Неисправный connection может обнаружиться первым
  SQL вместо лишнего pre-ping; rollback/error reporting сохраняются.

### Groq: два небольших запроса вместо двух резервов5500

Hard cap5500 и TPM8000 не повышены. Catalog Groq получает компактную версию тех же
инструкций config/prompts/catalog_classifier_compact_v3.txt; серверные business
validators не ослаблены. Система исходного prompt занимала ~3781 оценочных токенов
без article/output, поэтому просто поставить cap3872 для старого prompt нельзя.
Компактный prompt занимает ~1540 по текущей оценке, оставляя место source и JSON.

Soft cap обычно3872 (=8000/2-128), output cap catalog Groq <=1536 с reasoning=low;
резерв считается input+output, source-копия обрезается, сохранённая статья — нет.
При учтённом actual usage предыдущего запроса soft cap может уменьшиться, чтобы
вписаться в оставшееся окно. Два нормальных резерва <=7744 не требуют TPM-паузы.
Если provider фактически использовал больше оценки или окно занято, lock/check
по-прежнему потребует паузу/fallback; отсутствие ожидания не гарантируется.
Для большого deep prompt, который не помещается в soft cap, правила не удаляются:
сохраняется hard cap и обычное ожидание окна. Новый prompt version отмечается
суффиксом _groq_compact_v1. Качество живого Groq с новым prompt/output не измерено;
output_truncated/validation failures остаются видимыми, JSON не дописывается.

### Дедлайны и continuation

Кандидат по умолчанию45s (DAILY_CANDIDATE_TIMEOUT_SECONDS), включая ожидания/DB.
Run по умолчанию300s. Для ОДНОГО ручного диагностического запуска оператор может
явно задать TRIAL_MAX_RUN_SECONDS=600 (строго максимум600; default300). В Actions
это Repository Variable того же имени; после диагностики удалить/вернуть300.
Квоты,3/source и candidate45 от этого не меняются. Таймауты кооперативные:
текущий SQL ограничен statement_timeout30s, HTTP — своим timeout, финальный
rollback/report не обрывается SIGALRM. Поэтому wall time может превысить deadline.

```bash
# Только оператор, только после обновления ветки; это боевой discovery write:
TRIAL_MAX_RUN_SECONDS=600 .venv/bin/python -m backend.app.free_daily --trial
```

candidate_timeout теперь stage=timeout, counts.timeouts, Candidate.pending;
не fetch_failed. Устаревшие Run не переписываются. После валидного LLM-ответа
сохраняется отдельный _validated_catalog_result checkpoint. Истечение45s не
препятствует безопасному commit решения, но общий Run deadline/day/publication
limits сохраняются. Если общий deadline уже истёк, checkpoint остаётся queued:
следующий job валидирует и использует его без нового LLM/HTTP. canonical dedup
и все publication/evidence gates остаются. Факт reuse виден в continuation.
Потерянный ответ Groq из старого run169 этим кодом задним числом не восстановить.

### Почему Gemini STOP не означает валидный результат

В старой версии business_validation_failed выставлялся для invalid_score*;
штатная группа — invalid_score_evidence. Для ДВУХ случаев run169 конкретная
ветка не сохранена, назвать её для каждого нельзя. HTTP200/STOP подтверждает
транспорт/завершение генерации, а не достоверность оценок.

Теперь provider_attempts[].rule_code различает: scores_or_evidence_missing,
neutral_fallback_mismatch, score_reason_keys, score_reason_length,
real_product_usage_unsupported; также unsupported_project_name,
unsupported_official_url, invalid_description, invalid_json_schema и другие
allowlisted правила. Исходный текст ответа/исключения с данными не выводится.
При business failure следующий provider анализирует тот же source, самостоятельно
проходит все validators; если никто не прошёл, review_required/llm_unavailable.
request_sent=false с candidate_timeout_before_http означает резерв без отправки;
консервативный счётчик llm_requests сохраняется. llm_http_attempts отличает число
начатых provider вызовов от числа резервов (DNS failure может не дать HTTP).

### Один итоговый признак проверки

trial_evaluation=passed: минимум5 llm_validated и5 processed, без timeouts и
worker failures. Публикаций может быть0 при валидных NOT_PROJECT. partial —
обработка начата, но проверка пяти не завершена; failed — авария; not_started —
ничего не обработано. completed сам по себе не означает passed. Нормальное
достижение time budget после пяти валидных решений не отменяет passed.
Проверьте в /admin → Bepul kunlik ish фазы всего job, SQL-count/DB-time по
кандидатам и quota-компонентам, provider_waits и rule_code.

Боевой run169/база/живые провайдеры здесь не запускались. Offline тесты проверяют
реальное commit-before-HTTP, сохранение результата после обоих дедлайнов и
продолжение без повторного LLM, timeout stage, два TPM-reserve без ожидания,
коды business rules, SQL timing, checkout ACTIVE safety и trial600 cap.
PostgreSQL-варианты запускаются postgres-regression на disposable service16;
без локального сервиса они skipped, CI outcome отдельно не подтверждён.

### Publication rollback and bounded continuation

A validated LLM response is committed in `Candidate.article._validated_catalog_result`
**before** the publication transaction. This deliberately changes an old
`review_required / llm_unavailable` candidate to `queued`; a later INSERT failure
rolls back the project, not the checkpoint. Continuation validates that saved
result again and does not call the LLM again.

Publication failures retain that checkpoint and append status history. Existing
JSON metadata `_publication_retry` records failures and the next UTC attempt.
The first and second failures wait 5 and 10 minutes respectively. The third sets
`review_required / publication_retry_exhausted` for operator investigation.
Neither the daily selector nor explicit pipeline URL processing selects deferred
or exhausted retries; skipped candidates consume no candidate budget. Each actual
retry remains charged normally. A failed transaction is rolled back and pipeline
leases are released, including when retry bookkeeping itself fails.

`recover-no-llm-run` remains restricted to its original missing-key evidence and
state hash; it does not reset publication failures or checkpoint retry limits.
No production recovery or data operation is part of this code fix.

### LLM run exhaustion, reviews and database latency (2026-10-17)

Before selecting/reserving the next candidate, the worker checks configured
Gemini/Groq per-run counters. When no configured provider has requests left it
stops with `llm_run_budget_reached`. Remaining candidate status/history/budget
are untouched. Durable quota reservation still locks and commits the ledger
before **each** HTTP attempt. Temporary provider/daily blocks use
`llm_provider_budget_reached`, not the per-run exhaustion label.

Historical `review_required / llm_unavailable` rows are eligible when providers
are configured, ordinarily after six hours; old deterministic/keyless reviews
can be retried immediately when keys appear. Due reviews receive a queue boost
within their source-priority tier (the trial three-per-source cap still applies).
Following actual failed LLM analysis, `_llm_retry` preserves a failure counter
and UTC due date: retry after six hours, then twelve hours. Three failures leave
`review_required / llm_retry_exhausted` for manual investigation. Exhausted or
not-yet-due rows are filtered before candidate charging. Existing history remains;
no old run is edited or automatically refunded. Guarded `recover-no-llm-run`
continues to apply only to its verified missing-key case.

Database checkout checks connection transaction state on every borrow; unfinished
ACTIVE/UNKNOWN sockets are still discarded. The SELECT probe now runs at most
once per physical connection per 120 seconds (previously ten). PostgreSQL idle
rollbacks are skipped. Advisory size/target/counter reads are cached for ten
seconds under the shared writer lease and invalidated after publication. Actual
reservations always lock/recheck the authoritative resource ledger, and publication
still uses its atomic conditional UPDATE. Candidate reservation and its run audit
share one transaction. Network/LLM calls never hold the publication transaction.
The validated-result checkpoint remains a separate durable transaction.

Publication changes are flushed together in one transaction; new IDs are assigned
before writing, dedup also checks pending projects in MULTI responses, and sources /
evidence are not eagerly loaded for every project in the dedup scan. Explicit-URL
processing no longer ranks/reloads the whole queue or materializes unrelated raw
rows. Queue selection and outcome reporting reuse joined source metadata.
A disposable SQLite/PostgreSQL regression limits the simple publication fixture's
`decision_write` component to 16 SQL statements and checks evidence/relationships.
This is not a production latency benchmark.

Run JSON and /admin include `run_database.select_1_ms` (warm checkout, simple SQL
round trip), `query_elapsed_ms`, and `average_query_ms` (SQL execution only;
`elapsed_ms` also includes transaction/connect overhead). Initial connection / probe
cost remains in run timing. `source_yield` summarizes the last 20 daily/trial runs
within seven days: candidates, publications, rejections, reviews, llm_unavailable,
fetch failures. After ten candidates and zero publications a source is softly
ordered later. It remains enabled and can still run. Counters describe attempts,
not unique candidates. Legacy reports without source metadata cannot be attributed.

Gemini/Groq requests in this worker still time out at min(LLM_TIMEOUT_SECONDS,15s),
additionally bounded by candidate/run remaining time. A timeout gets at most one
retry, only if retry policy permits, a whole request plus one-second delay can fit,
and a per-run request remains. That retry reserves its own quota before HTTP.
429 retries retain their existing bounded backoff; quota and health gates apply.
Groq remains `openai/gpt-oss-20b` by default / GROQ_MODEL; no model or account quota
change is made. GPT-OSS already uses reasoning_effort=low and JSON-object mode.
The compact prompt now explicitly specifies array/nullable/score/enum types.
Schema failures expose `provider_attempts[].schema_issues` containing allowlisted
field paths and error types, never raw replies, input values or validation messages.
`unsupported_project_name` remains a business rejection; it is not auto-corrected
into an unsupported name. Strict provider JSON-schema mode is not enabled without
verifying model support and accounting for the schema's additional token overhead.
Old `invalid_json_schema` events cannot reveal their failed fields retroactively.

## Run191: счётчики публикаций, честный source_yield и чередование источников (2026-10-20)

**`published` считает проекты, а не кандидатов.** Это разница `DailyStats.published_count`
за день (Asia/Tashkent) до и после запуска. Одна статья может описывать несколько
проектов (`MULTI`). В run 191 одна статья Spot (кандидат 196) дала три проекта, поэтому
`counts.published=3` при одном `published` в `candidate_runs`. Публикации trial
расходуют ту же дневную цель: run 174 опубликовал 2, run 191 добавил 3, итого 5 = цель.
Новые поля отчёта:

- `counts.published_candidates` — сколько кандидатов (статей) стали `published`;
- `counts.published_projects_from_candidates` — сумма проектов от этих кандидатов;
- `candidate_runs[].projects_published` — проектов от конкретного кандидата;
- `published_today_before_run`, `source_cap` в details запуска.

Если `published` больше `published_projects_from_candidates`, разницу во время запуска
добавил кто-то ещё (например, публикация в /admin).

**`daily_project_target` и `daily_publish_limit_reached` — один и тот же лимит,
`DAILY_PROJECT_TARGET`, на двух уровнях.** В free_daily `daily_publish_limit` приравнивается
к цели. `daily_publish_limit_reached` — стоп внутри обработки кандидата, когда
резервирование публикации достигло лимита; оставшиеся проекты статьи откладываются
(`daily_goal_deferred_entries`) и публикуются в следующем запуске, где есть место в цели,
без нового вызова LLM.
`daily_project_target` — стоп всего запуска перед следующим кандидатом.

**`source_yield` больше не штрафует источник за наши собственные ограничения.**
Источник понижается в очереди, только если у него ≥10 *оценённых* кандидатов
(`counts.evaluated`) и 0 публикаций. Не считаются оценёнными: причины
`llm_unavailable`, `llm_retry_exhausted` и стадии `budget_stopped`, `timeout`,
`worker_failed`, `no_decision`. Реальная ошибка чтения (`fetch_failed`) по-прежнему
считается. В /admin добавлена колонка «Baholangan». Из-за прежнего правила Gazeta.uz
(12 кандидатов, все `llm_unavailable`) и namdu.uz (11 из 14) были понижены
несправедливо; после обновления они вернутся в обычный порядок.

**Лимит на источник и чередование действуют и в daily.** Раньше «не больше 3 с
одного источника» работало только в trial; daily брал все кандидаты подряд из
одного источника (run 191: 5 из 5 — Spot). Теперь `DAILY_CANDIDATES_PER_SOURCE`
(по умолчанию 3) ограничивает кандидатов одного источника за запуск, а выбор
идёт по кругу: следующим берётся наименее использованный в этом запуске источник.
Незарегистрированные URL группируются по домену. Если все источники с очередью
исчерпали лимит, запуск переходит к discovery и заканчивается обычным образом.

**Повтор `llm_unavailable`.** На 2026-10-20 в базе 349 таких кандидатов (288
`deterministic`, 61 `llm_failed`), у всех 0 неудачных повторов и срок наступил. Они
выбираются раньше новых кандидатов (через `_llm_retry`, максимум 3 повтора с
задержкой 6/12 ч), поэтому возвращаются в работу без ручных действий.

## Run197: `unsupported_official_url` и скрытая админка (2026-10-20)

В run 197 правило `unsupported_official_url` отклонило 5 из 12 ответов LLM (Gemini и
Groq). Правило требовало, чтобы `official_url` буквально, символ в символ, встречался в
тексте статьи, и при несовпадении отбрасывало весь анализ. Модели же приводят ссылку к
обычной форме (`https://pulse.ciphera.net` при `https://pulse.ciphera.net/demo` в тексте,
`https://turistx.ai` при `Turistx.ai`). После трёх неудач подряд срабатывал circuit
breaker Gemini, и остальные кандидаты шли только через Groq.

Теперь `supported_official_url()` сравнивает без учёта регистра, `http(s)://`, `www.` и
завершающего `/`, с границами слова (`x.ai` не совпадает внутри `turistx.ai`):

- ссылка с путём (`github.com/owner/repo`) принимается, только если она есть в тексте;
- ссылка без пути принимается, если в тексте есть её домен, и сохраняется как корень сайта;
- неподтверждённая, небезопасная или локальная ссылка **удаляется** (`official_url=null`),
  а остальной анализ сохраняется. Выдуманный URL по-прежнему никогда не попадает в базу.

Адрес самой статьи не считается официальным сайтом: для агрегаторов это был бы адрес
агрегатора. Он и так сохраняется как источник проекта.

OpenRouter не нужен: проблема была в проверке, а не в квоте. Бесплатный профиль
по-прежнему принудительно отключает OpenAI/OpenRouter (`llm:openrouter = 0/0`).
