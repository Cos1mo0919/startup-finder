# Project status

## Current stage
**Stage 1 — Uzbekistan. Реализация и расширение Startup Radar подготовлены к проверке; пользователь ещё не принял этап.** Global и отдельный GitHub / Yangi dasturlar не начинались.

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
