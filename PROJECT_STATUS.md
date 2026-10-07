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
