# Render deployment preparation — 2026-10-14

Created render-deploy directly from origin/main fcba079, independently of the
migration-data branch. Transferred PostgreSQL configuration, schema models and
manual migration/merge tools without SQLite databases, backups, decisions or
data reports. Removed inherited reports from the branch tree; original files
remain available on their historical branches. Main history was not rewritten.

Docker now starts via scripts/start.sh on 0.0.0.0:$PORT; health check uses PORT.
Existing Node/Vite multi-stage build and FastAPI SPA/assets serving are retained.
Added idempotent PostgreSQL RLS security migration covering all 22 app tables,
revoking public/anon/authenticated table access without creating public policies.
Added explicit schema command and safe first-boot controls; Render Blueprint
keeps scheduler, automatic migrations and startup data audits disabled.

Validation on the actual GitHub main base: 339 backend tests, Ruff,
TypeScript/Vite production build and 20 Playwright desktop/mobile tests passed. All test databases are isolated
temporary SQLite; optional AI keys are explicitly empty in test settings.

No production database operation was run, no schema was applied and no service
was deployed. Docker build was attempted; elevated retry reached Docker Hub but
base-image lookup was denied with 403. Thus full image and actual PostgreSQL RLS
execution remain unverified. The startup contract, data-preserving disabled
startup, API/SPA/assets, CORS and security SQL are covered by isolated tests.

Historical product status below is retained; data report paths refer to earlier
branches and are not shipped by render-deploy.

# Project status

## 2026-10-12 — Boshqa, compact home, 2025 backfill

The Cloud database was backed up at `data/backups/izlanish-before-boshqa-backfill-20251012.sqlite3`
before schema changes. Baseline: 44 project records, 23 published, one published
2025 project. The existing project IDs and pre-2025 archive were preserved.

Public navigation is now Bosh sahifa / Loyihalar / Boshqa / Arxiv / Manbalar.
The home header has four compact clickable counters and one fresh-project block.
It selects projects by Asia/Tashkent publication day: today, otherwise yesterday,
otherwise the past three days, otherwise an archive link. The catalog has 2026/2025
year and Uzbekistan/Global/GitHub/Boshqa section filters with counts. Boshqa is for
a real published project with uncertain section, never a substitute for the archive;
admin can assign its section with a recorded reason. Arxiv selects older publications
by source publication date, not discovery time. Existing 2022–2024 records remain
available, but were not scanned in this task.

The first live 2025 backfill exposed a queue bug: archived URLs were processed from
unrelated backlog instead of their year. The queue now tags and prioritizes the
requested archive window. A repeated fetch checked 18 sources and found 2,533 URL
candidates under configured limits. The subsequent drains processed a bounded
sample; the 100-candidate drain stopped after 69 candidates because Gemini and
Groq opened temporary provider circuits. The report records the partial reason,
provider counts, source yield and remaining backlog. The source classifier prompt
was versioned to v3 after manual review exposed false positives for degree programs,
accelerators, planned infrastructure and future-only systems.

Final Cloud state after manual source review: 58 project records, 27 published
(22 from 2026, 5 from 2025). Four valid 2025 projects were added: Burgut ko‘z,
Boyqush, Organizm and Smartcast. Ten erroneous automatic cards were withdrawn to
review with exact reasons and source history preserved. The 2025 scoped queue has
2,465 candidates, including 2,235 still queued; this is **not** a complete audit of
2025 or a 100-project claim. Brave search was unavailable without SEARCH_API_KEY;
archive pagination was limited, especially Show HN. Full figures and URLs are in
`reports/backfill-2025-20261012.json`; the large live run files remain under ignored
`data/backfill-2025*.json`.

Cloud API smoke checks: `/api/health` 200, home 27 total and 5 in the three-day
fallback, catalog facets 27, 2025 catalog/archive both 5, Boshqa 0. The empty Boshqa
state and admin assignment were tested with an isolated database. All 44 baseline
project IDs and their publication timestamps remain unchanged. Final validation
after the classifier prompt revision: 303 backend tests, Ruff, TypeScript/Vite
production build and 20 desktop/mobile Playwright checks passed. A concurrent
build initially caused a Playwright request to hit a missing `dist`; running the
browser suite after the build passed all checks.

## 2026-10-11 — daily processing, GitHub section, source verification

The Cloud SQLite database was backed up before migration at
`/tmp/izlanish-before-daily-cycle-20261011.sqlite3`. The pre-change state was
42 project records, 21 canonically published projects and 34,409 pending raw
discoveries. The user's site showed 15 cards, but the separate site/Codespace
database is unavailable here; its exact count and identity are unverified.
`--db-stats` and admin status now expose a persistent database UUID so the two
instances can be compared without printing secrets.

Publication transitions now reserve a `daily_stats` slot, limited to 100 per
Asia/Tashkent day. Local candidates are processed before international sources;
30 places are reserved while actionable local items remain. Global and GitHub
share the remaining 70, and may fill unused places once the local queue is
empty. A new daily 09:00 processing job complements hourly discovery and the
15-minute queue worker. Last stop reason, processed/published/remaining counts,
daily/weekly/monthly totals and three section counts appear in admin diagnostics.
Legacy publication dates and project IDs were not changed. Existing publication
history populated the new counters once; old `first_seen` was used only where
the legacy record lacked a publication transition timestamp.

GitHub is now a separate public catalog section. Source-provenance routing is
exclusive and preserves the factual country field. The Cloud API smoke check
after routing gave 21 public projects: 14 Uzbekistan-source, 1 Global-source,
6 GitHub-source. This changes section membership, not the public project total.

Source check: BetaList, Product Hunt, Indie Hackers, Uneed, GitHub Trending and
GitHub Search were reachable and yielded project URLs; existing IT Park,
UzHunt, ICT Week and Spot were reachable and yielded 12, 7, 3 and 20+20 links,
respectively. Stanbase returned 503. StartupBase,
startup.ilmiy.uz, loyiha.ilmiy.uz, Debocha and YC Directory currently lack
server-rendered project links; Microlaunch exceeds the configured page limit.
These remain disabled. Active source checks and limitations are in
`reports/source-probe-2026-10-11.json`. Previously dormant verified sources
were activated explicitly in the Cloud DB without resetting blocked sources.

The Codespace/site database has not been copied or synchronized. No claim of
100 actual publications, source quality yield over time, or site-side count
reconciliation is made until those runs and the second DB can be observed.
One bounded live BetaList run checked 54 directory links, saved 54 raw rows and
processed two. Both became real project cards (Pixfy and Clerk.AI) after LLM
classification. Their official homepages were independently fetched and linked
with verbatim metadata; BetaList `/visit` redirects are no longer stored as an
official site. The run ended at its two-candidate batch budget, with 35,026
candidates remaining. Cloud public catalog now totals 23: 14 Uzbekistan-source,
3 Global-source and 6 GitHub-source. This small sample does not establish source
precision or imply that the whole backlog was processed.

## 2026-10-10 — catalog publication consistency

The current checkout had 12 candidate URLs marked published but 11 canonical
`PUBLISHED` projects. Ten of those candidates retained `entity_type=IGNORE`
from older processing. A backed-up local reconciliation verified each against
an exact canonical project source URL, preserved prior types in classification
history and corrected those ten to `PROJECT`. The canonical public count stayed
11 before and after; `/api/projects` and `/api/catalog/home` both returned 11.
No candidate was promoted solely from its candidate status. The Codespace
database cited by the user (10 published candidates, 2 public projects) is a
different SQLite file and has not been inspected or changed by this local repair.

Catalog writes now synchronize current classification and project publication,
known URL dedup requires an already published project, admin actions update
linked state, and a newer high-confidence NOT_PROJECT can withdraw a single-source
automatic card to review. Card excerpt length is limited only in React; detail
text and stored evidence are unchanged. Local suspicious-source audit: All Things
Banana, Piet in Piet and Tumar Innovation Hub remain review/hidden; Woodpecker
remains rejected under old rules pending reliable classifier review; Turan Security
is absent from this DB. A live Gemini recheck timed out, so no new LLM verdict is
claimed. Full browser and backend checks are recorded in the final task report.

The user supplied a separate Codespace listing: 10 published candidates, six
with legacy `IGNORE`, and 2 public cards. That listing omits canonical
`publication_status`, so the exact number of old-gate withdrawals is not yet
measured there. Startup repair now prevents the old problem migration from
withdrawing catalog publications and conservatively restores records withdrawn
only by that old gate when original validation survives. Manual exact-URL review
keeps the All Things Banana portal and Tumar webinar out of the public catalog.
The fetched Turan Security article describes concrete cybersecurity services
and a Threat Intelligence product beyond its competition headline.

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
work. Former public intelligence links now redirect to `/admin`; protected
owner routes retain the problem, idea, signal and sector views. Their APIs
require `ADMIN_API_KEY`. Public cards show the cited problem, target user, solution and evidence;
unfinished score groups and the former top opportunities panel are hidden.
The detail page places confirmed facts before optional detailed scoring.

Schema v6 adds a conservative `PUBLISHED` gate, lifecycle and review metadata,
secondary problem references and article-vs-project URL provenance. Seven
old rows still pass the earlier project-existence evidence check, but only
DMED and KotibAI also have complete source-backed problem analysis. The other
five are retained for review; 2 of 15 stored project rows fail fatal gates.
All 15 prior IDs and first-seen/publication timestamps matched the pre-change
SQLite backup. The 15 source links stayed intact; evidence increased from 56
to 57 after the verified KotibAI product page title was added.
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
After the narrow official-link resolver was added, a stored KotibAI article
was rechecked without source discovery: `https://kotib.ai/` was verified
against its page and saved as the official URL with a separate verbatim-title
evidence record. Runs 65–66 reported one existing-project match each, zero
new cards and zero errors; ID and historical dates stayed the same.
International paid-search corroboration now uses an international
query instead of an Uzbekistan-only query.

`ADMIN_API_KEY` must be configured privately for the owner area. No API keys
were committed. No deployment was made. Checks: 204 backend tests, 10
desktop/mobile browser tests, Ruff and production TypeScript/Vite build passed.
The existing Starlette/httpx dependency warning remains. User acceptance is
still pending.

## 2026-10-09 — v3.1 catalog pipeline in progress (feature branch)

The user supplied `docs/PROJECT_CATALOG_PIPELINE_V3_1.md` and explicitly
replaced the problem gate for catalog publication. Baseline commit `2132813`
records 15 projects: 2 published, 11 in review, 2 rejected. A verified SQLite
backup and exact restore command are recorded in `reports/pipeline-restore.md`.
Stage A adds schema v7, a versioned classifier prompt, validated catalog
scoring and status decisions, deterministic trust-pair checks, source excerpt
preservation, deduplication and histories. The 15 historical project IDs,
first-seen/publication dates and source links were unchanged by migration.
Stage B and Stage C remain in progress on the feature branch; main is unchanged.

## 2026-10-09 — v3.1 Stage B/C validation

Stage B committed as `27cf234`: the public site keeps four navigation items,
shows project-first cards and an archive based on publication date, with no
fake score for unevaluated items. Stage C connects the new catalog pipeline to
hourly discovery, CLI and yearly backfill. Generic keyless pages stay in owner
review with `llm_unavailable`. A production trusted-page positive allowlist
has **not** been added without page-level validation. The admin catalog offers
Publish, Hide, Reject and Merge; histories and source/evidence records persist.

Live keyless Spot and Show HN runs found no new publishable projects. Spot:
21 section links, 3 already-known candidates reviewed, 0 new rows. Show HN:
20 new URLs, 26 review-required processing decisions and 4 isolated page
errors, 0 published. The local database remains 15 projects, including 2
published legacy cards (DMED, KotibAI), 11 review-required and 2 rejected.
No real LLM classifier precision was measured because AI_API_KEY is absent.
Detailed run IDs, source yield and audit samples: `reports/stage-c.md`.
The immutable baseline and database restore instructions are in `reports/`.

## 2026-10-10 — autonomous discovery engine (feature branch)

The immutable pre-change inventory is `reports/pipeline-baseline.json`:
15 projects (2 published, 11 review, 2 rejected), zero raw discoveries.
The consistent SQLite backup is at `/tmp/izlanish-autonomous-2026-10-10.sqlite3`;
`reports/autonomous-pipeline-restore.md` has the exact restore command. Existing
project IDs, first-seen/publication dates and source links were preserved.

Stages A–C add the durable `raw_discoveries` queue, provider-independent
Gemini/OpenRouter/Groq/OpenAI fallback, conservative prefilter, project-first
processing priority, separate queue/reanalysis jobs, optional Telethon channel
ingestion, exception-only Telegram admin alerts, source block history and
post-publication 15-criterion deep analysis. The public project gate remains
identity + meaningful description + valid source + dedup, independent of deep
score. Generic RSS without an LLM remains in owner review. No positive
deterministic trust pair was added without validation. Deep Excel weights were
not found in validated form, so final weighted score remains unset.

Real keyless run (run 69) checked 12 sources, found and stored 177 raw links,
processed 30 candidates (29 review, one robots-disallowed fetch error) and
published zero new projects. Bounded drains and cached review reprocessing
continued; 201 legacy pending/review candidates were re-evaluated. Final
read-only audit after a fresh recovery pass: 15 projects unchanged (2 published),
598 raw observations including legacy candidates, 473 review, 71 rejected,
21 processed, 23 failed and 10 raw pending; 111 candidates remain queued.
The recovery pass returned 19 recently published October items from a prior
archive-window-only rejection to normal keyless review. The large review backlog
reflects absent LLM keys and no approved structured trust pair. Neither
Uzbekistan nor Global gained a verified new public card in this keyless run.
Review samples include potentially relevant project articles mixed with broad
news; reject samples mainly show unrelated university updates, dates outside
archive windows and explicit noise. Two obvious Nobel news rows were moved
from review to rejected after a narrow title-filter correction. One source
failure does not stop other sources; parser/robots failures remain visible.

No LLM provider, Telegram user session or admin bot credential was configured
in this environment. The fixed saved-page live benchmark reports
`llm_quality_measured=false`; live precision/recall and bot delivery therefore
remain unmeasured. The production Telegram target channel list is empty pending
operator configuration. Detailed source yield and samples are in
`reports/autonomous-audit.json`, with first-run and drain reports alongside it.
Public navigation remains Bosh sahifa / Loyihalar / Arxiv / Manbalar.
## 2026-10-10 — live Gemini activation and bounded backlog recovery

The cloud worker now sees `GEMINI_API_KEY` (value never printed). The previous
default `gemini-2.5-flash` returned HTTP 404 for this key; `gemini-3.8-flash`
timed out here. `gemini-3.1-flash-lite` passed the live JSON/schema smoke test
using `catalog_classifier_v2`. The three-case human-labeled end-to-end live
benchmark passed 3/3 (precision/recall 1.0), including one deterministic
scholarship prefilter and two Gemini responses. This sample is too small to
establish general accuracy; a raw Gemini-only trial did misclassify that
scholarship. The production prefilter now recognizes inflected `stipendiyalari`.

Backlog reprocessing uses a bounded, project-first `--reprocess-review` batch
for current-version `llm_unavailable` records, with configurable delay and
six-hour retry for attempted provider failures. The circuit breaker leaves
unattempted rows untouched. An optional live smoke command reports provider,
model and schema result without secrets. Missing score evidence is capped at
the documented neutral value; MULTI pages cannot claim entry-level customer
usage from page-wide text. Exact-name/creator conflicts go to duplicate review.

Pre-run backup: `/tmp/izlanish-before-gemini-2026-10-10.sqlite3` (SQLite backup
API). The preserved baseline remains 15 projects / 2 published / 473 raw review.
After bounded live processing and manual source audit: 28 project rows,
11 published, 14 review, 2 rejected, 1 duplicate; 598 raw observations with
455 review, 79 rejected, 31 processed, 10 pending and 23 failed. The candidate
queue still has 111 queued. Nine net new public projects came from previously
stored sources: five UzHunt profiles and four Show HN product pages. Three
vaguely described Next Rise entries were hidden for review, and the duplicate
DMED from that article was merged into the existing 2025 record while retaining
the new source. A fresh Spot Startups check found 20 known links; Show HN's
fresh feed returned HTTP 502, but its saved queue continued processing.
No deterministic published project currently awaits Gemini enrichment. Deep
Excel weights remain unvalidated and deep analysis stays optional.

## 2026-10-11 — Global catalog routing and 2026 archive audit

The public Global tab had a real routing bug: `Project.country == ""` was excluded
by `/api/projects?country=global` and `/api/catalog/home`, even when the source
was Show HN. `project_scope` now uses explicit country first and source provenance
when country is unknown. Two manually checked international products mentioned
by Spot use their official product domain to avoid a false Uzbekistan assignment.
The API and homepage share the same scope rule; homepage counters use complete
section counts rather than the four-card previews. No country was invented for
unknown-country projects. A pre-run database copy verified the repair: 11
published records split into 7 Uzbekistan and 4 Global in both home and catalog
filters; `/api/health` returned 200.

Backup before discovery: `/tmp/izlanish-before-2026-archive-20261011T095229Z.sqlite3`.
Restore only after stopping all backend/worker processes: copy the backup to
`data/finder.sqlite3` and remove the old `data/finder.sqlite3-wal` and
`data/finder.sqlite3-shm` sidecars. The backup was created with SQLite's backup
API; the current database was not cleared.

The 2026-01-01 through 2026-10-10 (inclusive, Asia/Tashkent) Uzbekistan pass
checked 12 enabled sources, found 858 links and stored 691 new raw observations.
Spot's Uzbek/Russian sitemaps each had 40 maps; IT Park, ADU and NamDU archive
pages were also traversed. The separate Show HN Global archive scanned 283 daily
slices and 530 public API pages, examined 38,949 hits and found 33,993 distinct
external URLs; the API reported zero unscanned pages or capped daily slices.
These numbers describe accessible configured sources, not all websites. The
large raw archive is durable. It is ingested in 250-item transactions, and the
processing queue rotates across sources so Global volume does not starve local
coverage. The `--backfill --only-source` queue restriction now matches its fetch
restriction. Coverage and source yield are returned in CLI reports.

The Cloud baseline was 28 project records / 11 published / 598 raw discoveries.
After source-backed review: 42 project records / 21 published (12 Uzbekistan,
9 Global), 18 review, 2 rejected, 1 duplicate; 35,233 raw observations,
including 34,409 still pending, and 34,503 queued candidates. Twenty public
projects have a 2026 source publication date. The ten net new public cards are
Tezbor, Tezride, Robosell, Virtual Accelerate, Turan Security, PodcastDelay,
Cerberus, Scribe, xcrashlytics and MemoryKit. Four proposed cards were moved
to review after inspecting their source text: Reclip (insufficient project
description), Robotis O‘zbekistonda (factory announcement), Tashkent Medical
Smart City (planned infrastructure) and Kelajak texnologiyalari markazi
(planned center). Their evidence and review reasons remain stored. Tezbor's
incorrect Kyrgyzstan country label was corrected from the Spot text and its
official `.uz` URL, with the previous value in `attribute_history`.

Gemini analyzed live sources; Groq was added as a working fallback after its
old default model returned HTTP 404. `openai/gpt-oss-20b` passed a live JSON/schema
smoke. A three-case Groq benchmark was partial because of rate limiting; it
does not establish general precision. Both providers encountered validation or
rate-limit failures, so the archive runs were partial and most raw items remain
unclassified. The 15-minute scheduled drain can continue from the saved queue
while the service runs; this task does not claim that all 2026 links have been
analyzed or that the user's separate Codespace database was changed. The full
Cloud audit is `reports/2026-10-11-archive-audit.json`.

The audit with 9 published, 10 review and 10 rejected samples is
`reports/gemini-live-audit.json`. At the time of the 2026-10-10 audit, the
international country-filter tab showed only Screens (United States). The
2026-10-11 scope fix above now routes other validated Show HN products to
Global without inventing a country. Telegram
credentials remain unconfigured. Stage/user acceptance is not implied by this
technical validation.
