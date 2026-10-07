# Project status

## Current stage
**Stage 1 — Uzbekistan. Реализация и расширение Startup Radar подготовлены к проверке; пользователь ещё не принял этап.** Global и отдельный GitHub / Yangi dasturlar не начинались.

**Последняя доработка (07.10.2026):** исправление старых архивных настроек в Source Registry и года queued-кандидатов; [актуальный отчёт Codespace](docs/CODESPACE_ARCHIVE_REPAIR.md). Ранее добавлены диагностика воспроизводимости и узбекское отображение дат. Точный сценарий Codespace проверен на отдельной пустой базе; он не равен годовому backfill. Подробности и результаты — [ARCHIVE_REPRODUCIBILITY.md](docs/ARCHIVE_REPRODUCIBILITY.md). Прежние 3 карточки Cloud и историческая статистика описаны в [KEYLESS_VALIDATION.md](docs/KEYLESS_VALIDATION.md); они не являются результатом одиночного запуска на чистой базе.

## Completed
- Узбекский React/TypeScript сайт: лента, поиск, фильтры, карточки, факты и отдельный AI-анализ, подробный read-only `/status`.
- Source Registry в SQL, 23 seed-записи `config/sources.json`, CLI импорта/обновления/включения источников. Индивидуальная частота, приоритет, надёжность и история ошибок.
- RSS, HTML-списки, Brave Search; региональные профили и университетские seeds. Ежечасный scheduler выбирает только источники с наступившим сроком; сохраняются lease и ограничения сети.
- Events и последующий поиск проектов/победителей/участников на трёх языках. Происхождение проекта связано с мероприятием; экосистемные новости хранятся отдельно от ленты.
- Типизированные цитируемые доказательства, объяснимые сигналы детектора, Tasdiqlanganlik 0–10 с компонентами. Обязательный stop filter: источник, существование и подтверждённый автор, порог качества, даты, идеи/спам/будущие планы.
- Несколько секторов, основной сектор, кликабельная статистика видимых проектов за 30 дней. AI-поля серьёзности/частоты проблемы и «Nega bu loyiha hozir muhim?»; прежний Foydalilik сохранён.
- Миграция схемы 2: старая SQLite-база обновлена с резервной копией, ID и first_seen сохранены. Старые статьи перенесены в project_sources, карточки переоценены.
- 86 backend-тестов и 6 browser-тестов desktop/mobile; Ruff, TypeScript/Vite build, Docker build/smoke и запуск HTTP-сервиса.
- Документация, CI, Docker/Compose, скрипты setup/start/check; тестовые базы изолированы от живой.

## Live evidence — 2026-10-06
- Проверены Spot UZ/RU (20 ссылок каждая), UzHunt (5), IT Park (12), ICT Week (3). Это результаты получения кандидатов, не число подтверждённых проектов.
- Первый radar-запуск: 9 источников, 28 обработанных кандидатов, 16 отклонённых, 11 ожидающих анализа, 1 мероприятие, 0 новых проектов. Частичный статус вызван четырьмя отсутствующими Search API bindings.
- Следующий запуск: 0 источников к повторной проверке, 11 ожидающих кандидатов; мероприятие требует Search API для продолжения.
- Реальная ранее сохранённая карточка @Hudud_gaz_taminot_bot осталась в БД с прежними ID/датами, но скрыта из основной ленты: creator_unknown. Публичная лента сейчас пуста; тестовых карточек туда не добавляли.

## User approved
Ни один этап не принят. Разрешение касается только Stage 1 и его улучшений.

## Pending
- Проверка и принятие Stage 1 пользователем.
- По желанию: добавить AI_API_KEY и SEARCH_API_KEY через защищённые настройки среды, перезапустить и проверить реальные платные API. Ключи не передавать в чат.
- Просмотреть/сохранить облачную конфигурацию и опубликовать окружение. Сохранённый черновик не означает публикацию; восстановление в новой задаче не проверено.

## Known limitations
- AI/Brave проверены mock-тестами, живых ключей нет. Без AI работает только консервативное узбекское извлечение; неполные кандидаты ждут анализа. Нет гарантии полного покрытия регионов.
- Gazeta — 403, TUIT robots — 503, SamDU — 409: отключены. Другие региональные университеты — выключенные непроверенные seeds. Универсального browser/API-адаптера нет, такие методы требуют настройки.
- HTML-страницы без доказуемой даты не публикуются. Поиск проектов мероприятия без Brave ограничен доступными ссылками официальной страницы; даты/организатор без явного подтверждения остаются неизвестными.
- Детектор и локальная дедупликация эвристические; независимость издателей не гарантирована. Один материал обрабатывается как один проект, списки требуют дополнительного разбиения. Процент доверия не является статистической вероятностью.
- PostgreSQL deployment/миграция, GitHub Actions и публичное размещение не проверены. Есть предупреждение стороннего Starlette/httpx; тесты проходят.

## Next stage
Остановиться после отчёта. **Не начинать Global** до явного принятия текущего этапа и отдельного разрешения пользователя.

## 2026-10-07 — discovery repair, then deployment priority
User explicitly kept Stage 1 unaccepted and then changed the immediate priority to a public HTTPS preview. Existing discovery changes are preserved separately from deployment work; further discovery changes are paused.

Implemented bounded per-year backfill (2022–2026-09), durable candidate queue, targeted multilingual queries, broader deterministic extraction, early noise classification, explicit partial/rejection/origin diagnostics, university adapters and setup-time DB preparation. Schema version 3 preserves old records. 110 backend tests and 6 browser tests passed before the final URL-preservation adjustment; final verification is recorded in the subsequent deployment report.

A live bounded backfill completed with partial outcomes in all five windows (no AI/Search keys). It added 0/0/1/1/1 visible records for 2022/2023/2024/2025/2026, respectively. These are pipeline outputs awaiting quality review, not a claim of discovery acceptance. The prior full discovery acceptance task is unfinished: a fresh run, final quality review and complete per-year report remain. Full run artifacts are in /workspace/artifacts/discovery-repair/backfill.json. Database and backlog were not cleared. Three regional university adapters are configured; NamDU trailing-slash behavior was fixed after observed parser failures and needs a subsequent live retry.

## 2026-10-07 — temporary preview requested; public access blocked

User explicitly selected temporary preview only and has no ngrok account. No paid
hosting, permanent deployment, PostgreSQL migration or Global work was performed.
The preview changes preserve the existing UI and discovery behavior.

- Added `scripts/preview.sh` (Cloudflare Quick Tunnel; optional ngrok), read-only
  `scripts/verify_deployment.py` and a SQLite backup command with WAL coverage and
  overwrite protection. README documents lifecycle, environment settings, logs,
  update/restart, backups and scheduler checks.
- **No public HTTPS URL exists yet.** Official cloudflared 2026.10.0 was verified
  against its published SHA-256. Both direct launch and the helper failed to create
  a tunnel: `api.trycloudflare.com:443: connect: connection refused`. The quick-tunnel
  request did not use this environment's HTTP egress proxy. No protections or TLS
  verification were bypassed. ngrok supports a proxy but requires an account/token;
  it was not run. No native public port publishing tool is available here.
- Restarted the owned backend with scheduler enabled. `/api/health`, frontend/assets,
  Bugun, all three visible details, year filters, search and `/status` passed local
  checks. Next scheduled run was `2026-10-07T04:00:00Z`; this is schedule verification,
  not evidence that an hourly tick has executed. Scheduler stops with the machine.
- Before/after restart: 10 stored projects, 792 candidates, 10 project sources,
  30 evidence records and 18 runs preserved. All project IDs, publication dates and
  first_seen were identical. Three projects are visible; seven remain hidden by
  evidence gates. A consistent pre-restart backup is retained outside the checkout.
  Environment deletion is not protected by this local backup; no permanent disk
  service has been provisioned.
- Full checks: **115 backend tests, 6 desktop/mobile browser tests, Ruff and
  TypeScript/Vite build passed**. Existing Starlette/httpx deprecation warning remains.
  Actual-data mobile checks (390×844) passed home, 2024/2025/2026, KotibAI search/detail
  and status with no horizontal overflow or JavaScript exceptions. These were local
  Chromium checks, not a phone accessing an external URL.

Artifacts: `/workspace/artifacts/discovery-repair/preview-checks.log`,
`before-preview.json`, `after-preview.json`, `preview-final-tunnel.log` and
`mobile-status.png`. They stay outside Git along with database backups.

Remaining prerequisite for phone review: a machine/network supporting the official
anonymous tunnel, or an authenticated tunnel service with supported connectivity.
The user is not asked to create paid hosting. Public URL, external HTTPS checks and
phone acceptance remain unfinished. **Stage 1 is not accepted; discovery acceptance
work remains paused and Global must not begin.**

## 2026-10-07 — keyless Uzbekistan acceptance run

The user resumed discovery work and explicitly requested useful publication without
AI/Search keys. This supersedes the earlier pause for preview. Stage 1 remains
unaccepted; Global and GitHub / Yangi dasturlar were not started.

- Fallback accepts explicitly attributed unquoted product names, company launches,
  prototypes and supported multilingual constructions. Creator attribution must
  refer to the product, not an unrelated person later in the article. Uzbek problem
  statements/audiences are extracted without invented facts. Foreign material gets
  only narrow structured templates or explicit pending reasons.
- Stored/API `rating_method` distinguishes deterministic_fallback from ai; existing
  evidence thresholds and scoring rubric remain. UI labels the missing AI analysis
  and rule-based rating. Status adds published-without-AI, rating methods, languages
  and pending reasons; obsolete rejection records do not inflate current statistics.
- Parser v4 reads the UzHunt product body/date instead of recommendations and falls
  back to h1 for broken title metadata. Official/source-page event links work without
  Search API with bounded same-domain navigation. Rejected recruitment news do not
  become events. `--drain` no longer initiates event discovery.
- Processing v5 can improve old fallback cards on the same UUID. DMED was corrected
  from Uzinfocom. Editorial series Ryukzakda nima bor? and the financing program
  Ko‘mak were hidden after manual review, with records preserved. No quotas were used
  to lower publication gates.
- Probed 20 free seeds: 18 responded, TUIT/TerSU returned HTTP 503. Working Qarshi DU
  article parsing and Gazeta RSS/article access enabled; unverified university
  adapters remain disabled with notes. Four optional Brave profiles now default to
  disabled. Ordinary startup continues to preserve operator settings.

Live acceptance used explicitly empty AI_API_KEY, OPENAI_API_KEY and SEARCH_API_KEY:
archive runs 24–28 covered 2022–2026-09, fresh run 29 completed, archival retry runs
30–34 applied improved rules, and forced run 35 completed. All were partial, not
claimed as exhaustive coverage. Retry run 30 still used the older in-process event
navigation before the drain fix and found 14 links; the final code's no-discovery
drain behavior is regression-tested.

Final forced run: 11 free source listings succeeded, 163 URLs found, 325 candidates
processed, 27 rejected, 286 pending, 11 parser/fetch errors; zero source/configuration
errors and zero AI calls. It added no new card because qualifying stored projects
had already been processed. Overall DB: 881 unique candidates (78 new this task),
563 rejected, 286 pending, 11 errors, 15 events, 3 ecosystem candidates, 3 published.
11 distinct candidates have fallback processing recorded; zero AI. Per-run duplicates
and source/origin breakdowns are in the linked report, with repeated attempts clearly
separated from unique counts.

Visible cards: Uzbekistan Airways app (19.07.2022; creator Uzbekistan Airways;
Foydalilik 3.85 / Tasdiqlanganlik 7.02), DMED (07.01.2025; Uzinfocom; 2.1 / 6.72),
KotibAI (10.03.2026; Hikmatilla Ubaydullaev; 4.85 / 6.72). All use
deterministic_fallback and have working Spot URLs, retained quotations and named
creators. Qualified 2023/2024 cards were not found in this bounded sample. Three
visible cards is a result of evidence review, not a guarantee of complete discovery.

All 10 pre-existing project IDs/publication dates/first_seen and all 803 original
candidate URLs were preserved. No projects or candidates were deleted. Two additional
stored project rows include one hidden false positive (Ko‘mak), retained for audit.

Validation: **146 backend tests, 6 desktop/mobile browser tests, Ruff and
TypeScript/Vite build passed**. Existing Starlette/httpx deprecation warning remains.
Actual-data mobile checks passed home, all 2022–2026 filters, DMED search, all three
details with the missing-AI label, and `/status`; no horizontal overflow/JS errors.
Health/assets/API checks and an owned backend restart passed: all three visible
IDs and dates persisted. Original source URLs were fetched again with
robots/TLS checks. Scheduler is enabled while this machine runs; next run observed
at 15:00 Asia/Tashkent, not claimed as an already completed hourly tick.

Full report: [docs/KEYLESS_VALIDATION.md](docs/KEYLESS_VALIDATION.md).
Local artifacts/backup: `/workspace/artifacts/keyless/` (not committed). Setup/start
instructions updated in the cloud configuration draft, not published automatically.
Public preview remains a separate unresolved network limitation; local validation
does not claim a public deployment. Stop for user review; **Stage 1 is not accepted**.

## 07.10.2026 — архивная воспроизводимость и узбекские даты

- Проверены текущая Cloud-база и точные команды пользователя на отдельной пустой SQLite-базе без AI/SEARCH ключей. `--archive --force-sources` нашёл 147 URL, обработал 60, не обнаружил Uzbekistan Airways/DMED и оставил KotibAI в queued. Audit и запуск API не заменяют backfill.
- На отдельной копии этой базы `--drain --archive` завершил очередь и опубликовал только KotibAI. Это подтверждает различие обнаружения ссылок и качества анализа.
- Прямое получение трёх оригинальных статей в ещё одной пустой диагностической базе подтвердило, что все три проходят существующие фильтры без прежних evidence. Прямой тест не выдаётся за discovery.
- CLI объясняет режим `--archive`, `--inspect-url` показывает конкретный статус/причину, run.details содержит режим и лимиты, coverage — выбранные sitemap. Детектор, fallback, пороги и выборка коллектора не изменены.
- Общий frontend-форматтер исправлен на явные узбекские месяцы, включая архивные диапазоны status. Формат проверен на реальных карточках при мобильной ширине. БД и timezone logic не менялись; редизайна нет.
- Проверки: Ruff, 152 backend-теста, TypeScript/Vite build, 10 desktop/mobile browser-тестов. Есть прежнее предупреждение зависимости FastAPI/Starlette о httpx; ошибок проверок нет. Backend после точного сценария отвечал 200 на главной, status, health и API проектов.
- Итоговые live-результаты годового backfill и команды повторения — [ARCHIVE_REPRODUCIBILITY.md](docs/ARCHIVE_REPRODUCIBILITY.md). Ни Stage 1, ни последующие этапы не объявлены принятыми.

Чистый годовой backfill завершён: 791 уникальный кандидат, 3 published, 498 rejected, 272 pending, 12 event, 3 ecosystem, 3 error, queued=0. Все три целевых проекта воспроизведены автоматически без API: Uzbekistan Airways (2022), DMED (2025), KotibAI (2026); оценки и исходные даты совпали с Cloud. Для 2023/2024 подтверждённых карточек в выборке нет. Проверено 11 уникальных источников; все пять run имеют объяснённый partial (pending без AI, в первом окне также 3 ошибки страниц). Полные счётчики — в связанном отчёте.

## 07.10.2026 — повторное расхождение Codespace, диагностика продолжается

Пользователь сообщил 1 published / 8 pending / 22 rejected после backfill и drain в своём Codespace. Его база и ошибки запусков пока недоступны этой Cloud-среде; предыдущие 791 кандидат и 3 проекта не описывают этот Codespace. Корневая причина нового расхождения пока не установлена, исправленной она не объявляется.

Добавлены полный CLI-список pending, точные pending_reason, стабильные ID для инспекции и debug-отчёт с настройками/архивными ошибками, включая годовые runs, предшествовавшие drain. Фильтры, collector и настройки источников не изменены. Для диагноза нужен отчёт из проблемного Codespace. Stage 1 не принят; Global не начинался.

Причина повторного расхождения подтверждена присланным пользователем debug: в его БД у Spot UZ/RU и IT Park отсутствует archive, хотя в seed он есть; coverage всех пяти годовых runs пустой. Прислан полный список 8 pending, ни Uzbekistan Airways, ни DMED среди них нет. Добавлено узкое восстановление `--repair-archive-config` и явная ошибка конфигурации вместо скрытого RSS fallback. 157 backend-тестов, 10 browser-тестов, Ruff и build прошли. Операторские настройки и quality gates сохранены. Подробности и результаты новых live-проверок — [CODESPACE_ARCHIVE_REPAIR.md](docs/CODESPACE_ARCHIVE_REPAIR.md).

Финальная проверка: в пустой базе со старым seed после точечного repair и backfill 200/12 воспроизведены все 3 проекта (2022/2025/2026), всего 603 кандидата, queued=0. В отдельном чистом контроле выявлена и исправлена ошибочная привязка unprocessed queued URL к первому году: теперь повторно найденный dated URL маршрутизируется в свой год, но настоящая дата статьи по-прежнему проверяется. После поправки чистые defaults 30/20 + один drain дают DMED и KotibAI, queued=1089; Airways отсутствует в выборке 20 sitemap (это не quality rejection). Покрытие при 12/20 различается; алгоритм выборки не менялся. 160 backend-тестов, 10 browser-тестов, Ruff/build и startup/API smoke прошли; ID/даты 3 карточек сохранены. Требуется применить опубликованный repair в рабочем Codespace и проверить результат там; доступ к его БД остаётся у пользователя.
