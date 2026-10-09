# Project status

## Current stage
**Stage 1 ещё не принят. По явному новому разрешению пользователя начат отдельный Global discovery; Узбекистан остаётся основным направлением.** Актуальное состояние см. в последнем разделе этого файла; старые разделы сохранены как история работ.

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
Историческое ограничение на Global заменено явным разрешением пользователя в октябре 2026 года; текущий объём работ описан в последнем разделе.

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

## 07.10.2026 — problem-first architecture (review pending)

Latest user instruction replaces the earlier product direction with a
problem/startup/opportunity intelligence system while keeping Uzbekistan primary.
The old standalone Global stage is not started or accepted. A concise migration
plan is in `docs/PROBLEM_FIRST_PLAN.md`.

Version 4 adds problem, problem-evidence, project/problem link, solution-idea,
checkpoint tables and structured project gate/opportunity fields without clearing
projects/candidates or changing historical IDs/dates/first_seen. The three formerly visible Cloud projects remain visible. KotibAI now links to a source-backed everyday transcription problem; DMED and Uzbekistan Airways remain `pending_problem_analysis`. None has an unsupported opportunity grade.
Source seeds now contain 64 concepts, 12 active and 52 disabled until adapters
are verified. Existing scheduler keeps hourly discovery and adds checkpointed
08:00/23:30 reconciliation and weekly/local and monthly/cross-country scan
attempts. One public Show HN RSS signal source is active internationally, but this
is only bounded signal sampling, not a deep global trend study. API and Uzbek dashboard expose problem, idea, signal, sector and
source views while keeping the project feed/archive.

The problem detector is intentionally narrow; exact and selected deterministic paraphrase dedup work, with original quotes retained. Bounded event pages can now yield two separately evidenced projects from one URL. Broad semantic dedup, general non-Uzbek problem translation and validated international problem adapters remain outstanding. No actual solution ideas have
been generated because evidence for a plausible mechanism/alternatives is
insufficient. This extension must be reviewed as incomplete until those gaps
and live discovery coverage are addressed.

Live keyless validation for this extension: a clean 11-source forced sample collected
146 links, processed 12 (budget 6 × 2), rejected 8 and left 4 pending; zero
projects/signals/problems passed. A neutral university sentence initially
misclassified as a problem; the detector was narrowed and the clean sample
repeated with zero false problem records. Separately, the public Show HN RSS
adapter checked one HN article and produced one low-confidence TECHNOLOGY signal,
no project. A historical, live-accessible Spot article about HUMO card outages
(11.04.2022) was reclassified from a stored candidate into one evidenced
UZBEKISTAN_LOCAL problem; original URL and source publication date are retained.
The three historical project cards and IDs remain unchanged. KotibAI now has a source-backed problem link; the other two await problem analysis.
No solution idea is published because current evidence does not support one.

Follow-up: schema version 5 migrated the citation table without losing its 12
rows. A two-project hackathon fixture now produces two visible, separately
cited project cards from one source URL. The existing KotibAI article explicitly
states that journalists spent three hours transcribing a one-hour interview;
this verbatim quote links KotibAI to a second real everyday problem. DMED and
Uzbekistan Airways remain pending problem evidence. No A/B opportunity grade
was inferred for any existing project. Backend restart retained all three
project UUIDs and the HUMO problem UUID.

## 08.10.2026 — intelligence extension validation

The problem-first backend and Uzbek frontend are integrated. The dashboard now
separates projects, problems, solution ideas and signals; the archive and status
include period filters and scoring diagnostics. Main project cards display
Muammo, Bozor, Dalil, Yechim and Imkoniyat, with unknown values left blank rather
than invented. Desktop/mobile browser tests passed (12). The API and all new
routes answered HTTP 200 in a local backend smoke check.

## 08.10.2026 — visual second pass and bounded keyless discovery

Stage 1 remains unaccepted. A graphite/teal token system, distinct dashboard
sections, problem-first cards and status health treatment now replace the prior
uniform feed-like overview. The project feed, archive, database and scheduler
architecture remain. Desktop/tablet/mobile layouts were visually checked with
no horizontal overflow. Scheduler-disabled status wording is explicit.

The existing Cloud SQLite file was backed up before discovery. Forced current
source checks (12 enabled sources) and bounded 2024–2025 backfill completed
partially; one queue drain left durable work. Two real Spot-backed project
rows became visible: Tahrirchi (2023) and Tilmoch (2025), both founded by
Muhammadsaid Mamasaidov and both `PENDING` for problem/opportunity analysis.
There are now 15 project rows / 7 visible, 3 problems, 3 signals, 0 ideas,
212 queued, 304 pending and 549 rejected candidates. No quality threshold
was lowered. BITO's incorrect PizzaPitch event association was repaired to
the cited CEVF report. Detailed counts, sources, citations and limits are in
[SECOND_PASS_VALIDATION.md](docs/SECOND_PASS_VALIDATION.md).

189 backend tests, 12 Playwright desktop/mobile tests, Ruff, TypeScript and
production frontend build passed. Exa/Vercel were unavailable and no deploy
was attempted. Archive backlog remains; user review and acceptance are still
pending. Global has not been started.

Before reprocessing, a SQLite backup was made through the backup API. All 12
existing project IDs, publication dates and first-seen timestamps remained
identical. Cited prescription-error text now links DMED to a local problem;
KotibAI remains linked to its sourced transcription problem. The historical
Uzbekistan Airways card remains visible with `PENDING` problem analysis.
Reprocessing stored, reachable Spot articles published BITO (06.04.2026,
Umidjon Po‘latov) and surfaced the existing Agroko‘makchi row (22.11.2023,
Qishloq xo‘jaligi vazirligi). The latter now correctly belongs to agritech.
These two cards have `PENDING` problem gates; neither is claimed as a strong
opportunity. The live database currently has 13 project rows, 5 visible
projects, 3 distinct problems, 3 signals and 0 solution ideas. Existing
provenance and candidate backlog were retained.

Validation: 185 backend tests, 12 desktop/mobile browser tests, Ruff and
TypeScript/Vite build passed; one existing Starlette/httpx deprecation warning
remains. A separate clean keyless 2022–2026-09 backfill and targeted processing
of two URLs discovered by it produced five visible real cards. Three were
published by the bounded yearly run; Agroko‘makchi and BITO were completed from
its durable candidate queue. Detailed counts, URL citations, yearly results
and limits are in [PROBLEM_FIRST_VALIDATION.md](docs/PROBLEM_FIRST_VALIDATION.md).
The monthly
cross-country scan still samples a single public HN signal feed and is not
comprehensive global intelligence. Strong opportunity scores are still pending
because 15 cited criteria cannot yet be established. No synthetic idea or
project has been inserted. Product review and acceptance remain with the user.

## 2026-10-09 — public catalog, publication gate and Global discovery

The user's later instruction explicitly authorized Global project discovery
while keeping Uzbekistan coverage. Stage 1 remains unaccepted. The public
site now has four navigation items: Bosh sahifa, Loyihalar, Arxiv, Manbalar.
Technical intelligence entities remain stored and available for owner/admin
work. Public cards show the cited problem, target user, solution and evidence;
unfinished score groups and the former top opportunities panel are hidden.
The detail page places confirmed facts before optional detailed scoring.

Schema v6 adds a conservative `PUBLISHED` gate, lifecycle and review metadata,
secondary problem references and article-vs-project URL provenance. Seven
old rows still pass the earlier project-existence evidence check, but only
DMED and KotibAI also have complete source-backed problem analysis. The other
five are retained for review; 2 of 15 stored project rows fail fatal gates.
All 15 prior IDs and first-seen/publication timestamps matched the pre-change
SQLite backup, with 15 source links and 56 evidence records unchanged.
Old candidate `published` labels are synchronized with the project gate so
public/admin counts agree. As of validation, 2 public projects, 11 project
rows requiring review, 2 rejected; 206 candidates queued, 271 pending, 5
in review, 609 rejected, 17 errors. The 6 ecosystem signals remain stored;
2 irrelevant education/tax items are marked ignored, not deleted.

The Show HN RSS adapter now retains the maker URL and HN discovery URL
separately. Keyless fallback preserves international origin and will not
invent a translation. A targeted real Show HN run found 29 links and
processed 20, with 10 rejected, 7 pending and 3 page errors; 0 new public
Global projects. A targeted Spot Startups run found 29 links and processed
6, with 3 rejected, 2 pending and 0 new public Uzbekistan projects. These
were bounded source samples, not full coverage. Quality gates stayed active.
Source-yield, rejection distribution, historical preservation and exact
source URLs are recorded in [PUBLIC_GLOBAL_VALIDATION.md](docs/PUBLIC_GLOBAL_VALIDATION.md).

`ADMIN_API_KEY` must be configured privately for the owner area. No API keys
were committed. No deployment was made. Checks: 200 backend tests, 10
desktop/mobile browser tests, Ruff and production TypeScript/Vite build passed.
The existing Starlette/httpx dependency warning remains. User acceptance is
still pending.
