# Izlanish — Startup Finder

Веб-сайт для поиска реальных проектов и решаемых ими проблем. Охват Узбекистана сохраняется; по новому разрешению пользователя начато отдельное ежедневное обнаружение международных проектов. Stage 1 ещё не принят, а публикация требует подтверждённых проекта, проблемы, аудитории и решения.

Публичный интерфейс на узбекском: главная страница, простой каталог, архив, группы источников и подробная страница проекта с фактами. Техническое состояние доступно владельцу в `/admin`. Приложение не создаёт вымышленных карточек ради заполнения ленты.

## Что реализовано

- React + TypeScript + Vite; FastAPI + Pydantic; SQLAlchemy + SQLite.
- Реестр источников с частотами и состоянием, RSS Spot на узбекском и русском, страницы UzHunt, IT Park и ICT Week; необязательный Brave Search API для более широкого поиска, включая сайты университетов, мероприятий, компаний и другие направления.
- Проверка даты: обычный запуск — последние 30 дней, архивный — начиная с 01.01.2022. Дата публикации не подменяется датой обновления или обнаружения. Неизвестные и будущие даты отклоняются.
- Приоритет: последний час → сегодня → вчера → 7 дней → 30 дней. Публичные «Сегодня» и «Новые» определяются по дате публикации, не по `first_seen`; время отображается в Asia/Tashkent.
- Каждый час в `HH:00` проверяются только источники, которым подошёл срок; блокировка параллельного запуска через lease в БД. Ручной запуск через CLI.
- AI-анализ и перевод через совместимый с OpenAI Chat Completions API адаптер; валидация JSON, цитат, ссылок и имён.
- Раздельные факты и AI-выводы; формальные рейтинги полезности и доверия с сохранением компонентов.
- Дедупликация URL, названий, автора/организации, псевдонимов и сходства описаний. Добавление источника не меняет `first_seen`.
- Настоящие изображения из метаданных исходной страницы с указанием источника либо placeholder. Изображения не генерируются.
- Владелец видит состояние, источники, очередь, причины отклонения и эффективность источников в `/admin` после ввода `ADMIN_API_KEY`.

## Режим без платных API

AI не обязателен для публикации. Fallback извлекает названия в кавычках и явные
названия продуктов без кавычек, автора/команду/организацию и цитируемое доказательство
создания, запуска или прототипа. Обязательные gates (Узбекистан, дата, автор,
существование, источник, Tasdiqlanganlik ≥ заданного порога) сохраняются. Обычные
новости, рубрики интервью и экосистемные инициативы не становятся проектами.

`rating_method=deterministic_fallback` хранится в content и возвращается API;
для AI-извлечения используется `ai`. Число в обоих случаях считает код по прежней
шестикомпонентной шкале. Без AI учитываются только извлечённые из цитат признаки;
неизвестные критерии дают ноль. Это не экспертная оценка. Публичная карточка появляется
только после подтверждения решаемой проблемы, аудитории и механизма решения.
Проблема и аудитория извлекаются из узбекских фраз; неизвестные поля не выдумываются.
Для RU/EN допустимы только узкие структурированные узбекские шаблоны с оригинальными
именами и цитатами, без заявления о полноценном переводе.

Pending получает причину `ambiguous_project`, `missing_creator`,
`insufficient_evidence` или `needs_translation`. `/admin/status` показывает число
опубликованных без AI, методы рейтинга, языки, причины ожидания и происхождение.
Новая версия fallback повторно проверяет старые кандидаты и может исправить название
карточки, сохранив её ID, first_seen, дату и исходные цитаты. Новые источники
объединяются с существующим проектом. Старые записи не удаляются.

Проверка без ключей (также очистите альтернативный `OPENAI_API_KEY`):

```bash
AI_API_KEY= OPENAI_API_KEY= SEARCH_API_KEY= MAX_CANDIDATES=200 ARCHIVE_PAGES=12 \
  .venv/bin/python -m backend.app.cli --backfill --from-date 2022-01-01 --to-date 2026-09-30 --report /tmp/archive.json
AI_API_KEY= OPENAI_API_KEY= SEARCH_API_KEY= .venv/bin/python -m backend.app.cli --report /tmp/fresh.json
AI_API_KEY= OPENAI_API_KEY= SEARCH_API_KEY= .venv/bin/python -m backend.app.cli --force-sources --report /tmp/forced.json
```

В доверенной Codex-среде дополнительно задаётся `TRUSTED_EGRESS_PROXY=true`.
Backfill ограничен числом архивных страниц и бюджетом обработки; это не полный
обход каждого материала за пять лет. Оставшаяся очередь сохраняется, её можно
продолжить командой `--drain --archive`. Медленные университетские сайты соблюдают
robots/crawl-delay; работа может занимать заметное время. Не запускайте параллельные
discovery ради ускорения.

Brave-профили в новых seeds выключены по умолчанию; при желании их можно включить
CLI после настройки ключа. Seed-импорт при старте не меняет настройки существующих
источников. Для явного применения обновлённых адаптеров используйте
`.venv/bin/python -m backend.app.cli --update-sources` (он применяет и enabled из seeds).
Без Search API события обходятся по релевантным ссылкам/подписям на официальной странице (либо странице исходной публикации)
в пределах её домена и одному дополнительному уровню страниц участников/победителей.
Одна статья по-прежнему описывает одну карточку; списки нескольких проектов без
индивидуальных страниц не гарантируют полное извлечение всех участников.

Проверенные дополнения: Qarshi DU (HTML, даты статей), восстановившийся Gazeta RSS;
для UzHunt исправлены основной блок текста и полная дата, исключены рекомендации.
Публикация на UzHunt сама по себе не доказывает происхождение проекта из Узбекистана.
Непроверенные университетские адаптеры остаются disabled с notes.

Результаты живой проверки: [docs/KEYLESS_VALIDATION.md](docs/KEYLESS_VALIDATION.md).

## Требования и установка

Python 3.12+, Node.js 24, npm и uv 0.12.19. Для браузерных тестов нужен Chromium или браузер Playwright. Команды ниже выполняются из корня репозитория.

```bash
python -m pip install uv==0.12.19
cp .env.example .env   # только если .env ещё не существует
./scripts/setup.sh
```

`setup.sh` устанавливает Python-зависимости из `uv.lock`, npm-зависимости из `frontend/package-lock.json`, собирает frontend, создаёт/мигрирует БД и импортирует отсутствующие источники. После fresh clone достаточно `./scripts/setup.sh`, затем `./scripts/start.sh`; отдельные `npm ci` и `npm run build` не нужны. `start.sh` сообщает понятную ошибку, если setup ещё не выполнен. Пакеты и контрольные суммы проверяются штатными средствами; проверки TLS не отключаются. Папки кеша можно изменить через `UV_CACHE_DIR` и `npm_config_cache`. Для обычной машины без `/workspace` задайте доступные пути кеша перед запуском скрипта.

## Запуск сайта

```bash
./scripts/start.sh
```

Один процесс обслуживает frontend и API на порту **8000**. Публичные проверки: `GET /api/health`, `GET /api/projects`; техническое состояние: `GET /api/admin/status` с заголовком `X-Admin-Key`. Веб-страницы: `/`, `/loyihalar`, `/arxiv`, `/manbalar`, `/loyiha/{id}`; `/admin` доступен владельцу. Сервис должен быть доступен через порт вашего окружения или настроенный reverse proxy; облачный onboarding не создаёт публичный URL автоматически.

Для frontend-разработки используйте два терминала:

```bash
.venv/bin/uvicorn backend.app.main:create_app --factory --reload --port 8000
```

```bash
cd frontend
npm run dev
```

Vite работает на порту 5173 и проксирует `/api` в backend. Для процесса разработки с частыми перезапусками можно задать `SCHEDULER_ENABLED=false` и запускать поиск вручную.

## Конфигурация

Все настройки читаются из переменных окружения и `.env`. Переменные окружения имеют приоритет. **Не коммитьте `.env` и реальные ключи.** Значения для облака вводятся в защищённых настройках среды, не в чате.

| Переменная | Назначение |
| --- | --- |
| `AI_API_KEY` | Необязательный ключ AI API. Для локального запуска также поддержан `OPENAI_API_KEY`. В облаке используйте `AI_API_KEY`: префикс `OPENAI_` зарезервирован платформой. |
| `AI_BASE_URL` | По умолчанию `https://api.openai.com/v1`; совместимый endpoint без перенаправлений. |
| `AI_MODEL` | По умолчанию `gpt-4.1-mini`; модель с JSON object mode. |
| `SEARCH_API_KEY` | Необязательный ключ Brave Search API. |
| `ADMIN_API_KEY` | Обязателен для `/admin` и `/api/admin/*`; задаётся только в защищённой конфигурации среды. |
| `DATABASE_URL` | По умолчанию абсолютный путь к `data/finder.sqlite3`. PostgreSQL: `postgresql+psycopg://...`. |
| `SOURCES_FILE` | Путь к `config/sources.json`. |
| `EVIDENCE_MIN_SCORE` | Минимальный Tasdiqlanganlik для ленты: 5 из 10. Автор и существование обязательны независимо от балла. |
| `MAX_EVENT_FOLLOWUPS` | До 3 мероприятий для дополнительных поисков за запуск. |
| `SCHEDULER_ENABLED` | `true` по умолчанию. |
| `ARCHIVE_PAGES` | Лимит страниц архива на источник/год, по умолчанию 20. |
| `SEARCH_QUERIES_PER_SOURCE` | Число целевых запросов в обычном цикле, по умолчанию 3. |
| `MAX_CANDIDATES` | По умолчанию 30; общий лимит обработки — до `2 × MAX_CANDIDATES` кандидатов за запуск (новые и повторы вместе). |
| `FETCH_TIMEOUT` | Таймаут одного HTTP-запроса, по умолчанию 15 секунд. |
| `MAX_PAGE_BYTES` | Лимит распакованной страницы: 2 МБ. |
| `USER_AGENT` | Честный идентификатор сборщика; для своего deployment укажите контакт. |
| `TRUSTED_EGRESS_PROXY` | По умолчанию `false`. Включать только за управляемым HTTPS-прокси, который ограничивает назначения и блокирует приватные адреса. |

### Что работает без ключей

Сайт, БД, расписание, публичные RSS/HTML/архивы, дедупликация и детерминированные оценки работают без платных ключей. Fallback распознаёт именованные проекты, прототипы, запуски и явное указание автора на узбекском, русском и английском. Он сохраняет исходную цитату; узбекский текст извлекается из источника, а для иностранного текста используется ограниченный узбекский шаблон с именем и атрибуцией. Это **не полноценный перевод или AI-анализ**. Неизвестные проблема, аудитория и преимущества не выдумываются.

AI_API_KEY включает полный адаптер перевода/анализа. Pending/error-кандидаты и extractive-карточки проходят повторную обработку с сохранением ID, first_seen и доказательств. Архивные кандидаты сохраняют свой период и не становятся «слишком старыми» при последующем обычном запуске. Ошибка AI/перевода оставляет запись для повтора. Без достаточного доказательства автора/существования карточка скрыта независимо от языка.

### Сеть в облаке

Проверены RSS Spot и публичные страницы UzHunt, IT Park (`www.it-park.uz`) и ICT Week (`www.ictweek.uz`). Это подтверждает получение страниц, но не гарантирует наличие пригодных проектов. Gazeta.uz ранее вернула 403, TUIT и TerSU — 503. SamDU теперь отвечает, но корректное извлечение статьи и её даты не подтверждено; источник остаётся отключённым. Бухарский, Андижанский и Наманганский университеты проверены с адаптерами текста/даты и включены. Остальные региональные университеты проверены на доступность и оставлены выключенными, если не подтверждён подходящий адаптер; включайте их после проверки доступности и адаптации ссылок. Защиты не обходятся.

Для текущей облачной машины установите `TRUSTED_EGRESS_PROXY=true`: публичный DNS здесь разрешается управляемым прокси. Только точные имена включённых источников реестра (начальный seed — `config/sources.json`) могут использовать proxy DNS при недоступном локальном DNS; произвольные новые хосты блокируются. URL всё равно должен быть HTTPS, без паролей, приватных IP и нестандартных портов. Для AI разрешается только явно настроенный хост провайдера. На обычной машине оставьте настройку `false`.

Для расширения web search в ограниченной среде новые домены нужно добавить в сетевые настройки и зарегистрировать как разрешённые источники. В обычной среде с публичным DNS действует проверка публичных адресов и robots.txt для каждого назначения. Приложение не заменяет сетевой firewall: для production также ограничьте приватные сети на уровне исходящего прокси.

## Ручной поиск и расписание

```bash
.venv/bin/python -m backend.app.cli
.venv/bin/python -m backend.app.cli --archive
# Для текущего облака:
TRUSTED_EGRESS_PROXY=true .venv/bin/python -m backend.app.cli
```

Обычный discovery берёт новые публикации за 30 дней. `--archive` оставлен для совместимости: разрешает более старые материалы, проверяет текущие списки и сохранённую очередь, но **не обходит годовые архивы**. `--force-sources` только игнорирует расписание включённых источников; он не превращает этот запуск в backfill. `--audit` переоценивает уже сохранённые карточки и не ищет отсутствующие URL. Для отдельного исторического поиска используйте:

```bash
TRUSTED_EGRESS_PROXY=true MAX_CANDIDATES=200 ARCHIVE_PAGES=12 \
  .venv/bin/python -m backend.app.cli --backfill \
  --from-date 2022-01-01 --to-date 2026-09-30 --report data/backfill-report.json
# Продолжить обработку сохранённой очереди без повторного обхода источников:
TRUSTED_EGRESS_PROXY=true .venv/bin/python -m backend.app.cli --drain --archive
# Обычный свежий поиск поверх постоянного архива:
TRUSTED_EGRESS_PROXY=true .venv/bin/python -m backend.app.cli --force-sources
```

Backfill создаёт отдельный run для каждого года. Верхняя календарная дата включительна по Asia/Tashkent. Старые Spot-материалы находятся через публичные sitemap, другие поддержанные архивы — через настроенную пагинацию; Brave при наличии ключа получает конкретный год и диапазон дат. `ARCHIVE_PAGES` ограничивает число архивных страниц/sitemap на источник и год (по умолчанию 20, диапазон 1–100). Sitemap выбираются равномерно по году; `lastmod` никогда не используется как дата публикации. Это ограниченный обход, а не гарантия полноты архива. Покрытие, выбранные sitemap и лимиты записываются в `run.details.coverage`, `run.details.limits` и JSON-отчёт. `discovery_mode` различает `current_listings`, `year_backfill` и `queue_only`. Изменение `ARCHIVE_PAGES` меняет выборку sitemap, а не только её размер; одинаковый код с другой очередью и лимитами не гарантирует одинаковый набор карточек.

Все найденные URL сохраняются до применения лимита обработки. `MAX_CANDIDATES` ограничивает работу за run; остаток не теряется и доступен через `--drain`. Повторное обнаружение URL не создаёт проект автоматически. Новая публикация о старом проекте добавляет доказательства через дедупликацию.

**База не очищается ни после backfill, ни в новый день.** Bugun/7/30 дней фильтруют по `first_seen`, годы — по исходной дате публикации. Проект из 2022 года, впервые найденный сегодня, виден и в Bugun, и в фильтре 2022. При новой статье first_seen не меняется. Выбор года в интерфейсе автоматически снимает фильтр текущего дня.

Планировщик работает в одном API-процессе, каждый час в `HH:00` по Ташкенту. Не запускайте несколько `uvicorn --workers` с активным расписанием. Lease защищает и от одновременного CLI-запуска; незавершённая блокировка истекает через 20 минут и продлевается в ходе обработки. Пропущенные во время длительного выключения часы не проигрываются пачкой. После восстановления облачного snapshot необходимо заново запустить процесс.

Для внешнего cron отключите встроенный scheduler и вызывайте CLI из корня проекта каждый час. API не содержит публичной команды запуска поиска. Код завершения CLI: 0 — выполнен/уже работает; 1 — частичная ошибка или сбой. Состояние и причины доступны в `/status`.

### Проверка отсутствующей карточки

```bash
.venv/bin/python -m backend.app.cli --inspect-url https://www.spot.uz/oz/2025/01/07/dmed
```

Команда не запускает discovery и показывает точный URL, статус, причину, попытки обработки, архивный период и видимость связанного проекта. `not_discovered` означает отсутствие URL в очереди кандидатов (поле `project` отдельно показывает сохранённый источник, если он есть), `queued` — ещё не обработан, `pending` — ожидает достаточных данных/анализа, `rejected` — отклонён. Узбекская и русская статьи о DMED — разные URL с отдельными статусами. Результаты проверки на чистых базах: [ARCHIVE_REPRODUCIBILITY.md](docs/ARCHIVE_REPRODUCIBILITY.md).

Для списка **всех** ожидающих кандидатов и точных причин:

```bash
.venv/bin/python -m backend.app.cli --list-candidates --candidate-status pending
.venv/bin/python -m backend.app.cli --inspect-candidate 'https://www.spot.uz/oz/2025/01/07/dmed'
# Вместо URL можно передать полный id вида sha256:... из списка.
.venv/bin/python -m backend.app.cli --debug-report --report /tmp/finder-debug.json
```

`--inspect-url` сохранён как совместимый вариант. ID вычисляется из канонического URL, стабилен между запусками и не требует миграции БД; это не UUID проекта. `pending_reason` содержит сохранённую причину, не новую оценку модели. `--candidate-status all` показывает все состояния. Диагностические команды не запускают discovery, не переоценивают кандидатов и не изменяют настройки источников.

Debug-отчёт содержит commit, наличие локальных изменений, путь SQLite, действующие лимиты, только **наличие** API-ключей, счётчики очереди, pending-список, включённость источников, наличие архивного адаптера и его совпадение с seed, последние runs и последний run каждого архивного окна. Он не экспортирует ключи, URL подключения к PostgreSQL, proxy credentials или полные тексты статей. `archive_matches_seed=false` — основание проверить сохранённую конфигурацию, а не автоматически перезаписать настройки оператора. Выключенные источники остаются выключенными. Отчёт нужно получать в том Codespace, где наблюдается проблема: Cloud-база не является его копией.

Если debug показывает `archive_configured=false`, `seed_archive_configured=true` и пустое `coverage` годовых runs, сохранённый реестр не получил архивный адаптер после обновления кода. Точечное восстановление:

```bash
.venv/bin/python -m backend.app.cli --repair-archive-config
# Затем повторите backfill с явными лимитами из примера выше.
```

Команда добавляет только отсутствующий `options.archive` для совпадающих ID/URL/метода, сохраняет enabled, расписание, доверие, health и остальные options. Существующий archive и изменённые endpoints пропускаются; возможен `--source-id spot-uz`. Без восстановления годовой запуск сообщает `archive_configuration_missing` / `NEEDS_CONFIG`, вместо молчаливого чтения текущего RSS. Полный `--update-sources` для этого не требуется. [Разбор конкретных 8 pending и причины расхождения Codespace](docs/CODESPACE_ARCHIVE_REPAIR.md).

Пользовательские даты отображаются как `10 mart 2026` и `7 oktabr 2026, 14:48`. Общий frontend-форматтер использует явные узбекские названия месяцев, чтобы не зависеть от полноты ICU браузера; часовой пояс остаётся Asia/Tashkent. Значения в БД и ISO-даты API не меняются.

## Реестр источников и управление

`config/sources.json` содержит 24 начальные записи. При запуске добавляются только отсутствующие записи; изменения оператора в БД сохраняются. `sources` — реестр, `project_sources` — цитируемые статьи, `project_evidence` — доказательства с типами и цитатами. Автоматически обнаруженные издатели могут добавляться в реестр как выключенные записи для атрибуции.

```bash
.venv/bin/python -m backend.app.cli --seed-sources
.venv/bin/python -m backend.app.cli --list-sources
# Применить изменения config/sources.json, сохранив историю проверок:
.venv/bin/python -m backend.app.cli --update-sources
.venv/bin/python -m backend.app.cli --source-id SOURCE_ID --enable-source
.venv/bin/python -m backend.app.cli --source-id SOURCE_ID --disable-source
# Проверить все включённые источники независимо от срока:
TRUSTED_EGRESS_PROXY=true .venv/bin/python -m backend.app.cli --force-sources
# Повторно оценить доказательства и видимость сохранённых карточек:
.venv/bin/python -m backend.app.cli --audit
```

Частота задаётся в минутах: приоритет 5 → 60, 4 → 180, 3 → 480, 2 → 1440, 1 → 10080. Можно явно задать `check_frequency`. `--force-sources` не включает отключённые источники. Source health показывает последний сбор списка кандидатов, а не подтверждает качество каждого проекта. `candidates_found` относится к последней проверке, `new_projects` — накопленный счётчик. Приоритет 5 у специализированных источников (UzHunt, IT Park, ICT Week, Spot Startaplar); проверенные университеты имеют приоритет 4, общие RSS — 3.

Пример записи (замените демонстрационный домен реальным):

```json
{"id":"university-demo","name":"Universitet","url":"https://university.example/news","source_type":"university","kind":"university","region":"Regional Uzbekistan","priority":3,"check_frequency":480,"reliability_score":9,"enabled":false,"collection_method":"direct_page","options":{"link_pattern":"/news/[^/]+$"},"notes":"Avval ochiq kirish va havolalarni tekshiring."}
```

RSS/Atom, HTML-списки (`direct_page`, `options.link_pattern`) и Brave (`search`, `options.query` с планом целевых запросов) реализованы. Для одиночной статьи используйте `options.single_article=true`. API/browser/manual_config зарезервированы в модели и показывают необходимость настройки; универсального адаптера для произвольного API/браузера нет. При добавлении источника проверьте условия использования, robots.txt, точный HTTPS-домен, даты и цитаты. Для ограниченной среды добавьте домен в сетевые настройки. Тип доверия задаёт оператор, не AI.

Четыре поисковых профиля охватывают регионы, IT Park, хакатоны и государственные инициативы; нужен Brave API. К ним добавляется план запросов на трёх языках: конкретный проект, студент, разработка, запуск, прототип, победитель хакатона, Demo Day. Обычный запуск чередует запросы и регионы (`SEARCH_QUERIES_PER_SOURCE`, по умолчанию 3); архивный выполняет целевой набор с годом. Региональные запросы чередуются, чтобы не обходить все регионы при каждом запуске. Наличие профиля не означает проверенное покрытие каждого региона.

Мероприятия сохраняются отдельно. На следующих запусках (не чаще 6 часов) система ищет участников, победителей и проекты на трёх языках. Без ключа возможен ограниченный обход релевантных ссылок официальной страницы. Неточная/неизвестная дата или организатор остаются неизвестными. Новость о фонде, программе или акселераторе хранится как `ECOSYSTEM_SIGNAL` вне ленты.

`/status` показывает реестр, ошибки, мероприятия, отклонения и причины детектора. Это публичный read-only технический экран: секретов и управляющих команд в нём нет. API: `/api/sources`, `/api/sectors/stats`. Дополнительно видны pending AI, очередь, AI/fallback, ошибки перевода, причины отклонений и происхождение кандидатов. Run сохраняет этап и источник каждой ошибки, границы архива и причины partial. Ошибки настройки и pending не маскируются как полный успех. Секторная статистика за 30 дней считает только видимые проекты по `first_seen`; один проект может входить в несколько секторов. На карточке AI-раздел объясняет проблему и актуальность; оценка серьёзности проблемы не меняет Foydalilik.

## Рейтинги и достоверность

Полезность — сумма шести компонентов: практическая польза (2.5), решение проблемы (2), аудитория (1.5), инновационность (1.5), возможность использования (1.5), качество источника (1). Число не генерируется AI: модель выбирает категориальные признаки и указывает индекс факта; код проверяет наличие цитаты и рассчитывает значение по фиксированной таблице. На странице показаны компоненты и причины. Извлечение смысла факта моделью всё ещё может ошибаться.

Tasdiqlanganlik — отдельная детерминированная сумма: надёжность лучшего источника существования × 0.35 (до 3.5), существование (2), автор (1.5), дополнительные издатели с разными цитатами (до 1.5), разнообразие ролей доказательств (до 1.5). Компоненты, цитаты и ссылки доступны на карточке. Одинаковые перепечатанные цитаты не повышают независимость; разные домены и цитаты всё равно не гарантируют реальную независимость. Процент Real project confidence равен баллу × 10 и не является статистической вероятностью.

Обязательный фильтр скрывает проект при балле ниже порога, отсутствии источника, подтверждённого автора или существования, недопустимой дате, списке идей, спаме или только будущих планах. Скрытые записи доступны для диагностики и могут вернуться после добавления доказательств. Рейтинг полезности сохраняет прежние шесть критериев; бизнес/инвестиционного рейтинга нет.

## Проверки

```bash
.venv/bin/ruff check backend tests
.venv/bin/pytest -q
npm run build --prefix frontend
# Если Chromium отсутствует:
cd frontend && npx playwright install --with-deps chromium
# Из корня репозитория:
npm run test:e2e --prefix frontend
# Или все проверки:
./scripts/check.sh
```

Playwright использует системный `/usr/bin/chromium`, если он существует, иначе свой установленный браузер. Путь можно переопределить через `CHROMIUM_PATH`. Browser-тесты запускают отдельный API на порту 8011 с временной SQLite-базой; тестовые проекты не попадают в `data/`. Покрыты frontend-поиск, год, фильтры, детали с фактами, статус и отсутствие горизонтального переполнения на desktop/mobile. Скриншоты находятся в игнорируемой `frontend/test-results/`.

Backend-тесты покрывают рейтинги, дедупликацию, независимость `first_seen`, даты и границу 2022, detector, перевод, парсеры, SSRF/robots/лимиты, БД, API, scheduler, lease, повторные запуски и обновление анализа после добавления AI. Внешние API замоканы. CI описан в `.github/workflows/ci.yml`; наличие файла не означает, что GitHub Actions уже выполнился.

## Docker

```bash
cp .env.example .env  # не перезаписывайте имеющийся файл
docker compose up --build -d
docker compose logs -f web
```

Образ собирает frontend, запускает backend от непривилегированного пользователя и хранит SQLite в томе `finder-data`. Healthcheck проверяет API. Контейнерные процессы и ключи не входят в Git. Для production настройте HTTPS reverse proxy и резервное копирование тома; `docker compose down -v` удаляет данные.

За корпоративным прокси передавайте штатные build-args `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`. Для доверенного CA предусмотрен необязательный BuildKit secret `build_ca`; сертификат используется только во время установки и не сохраняется в образе. Не отключайте проверку TLS. Облачная сеть контейнеров может требовать отдельной маршрутизации к управляемому прокси.

## Временный HTTPS preview (без постоянного хостинга)

Frontend и FastAPI обслуживаются одним процессом. Туннель публикует этот процесс,
а SQLite остаётся в `data/finder.sqlite3` на текущей машине. Платформа постоянного
размещения не создаётся. Установите официальный
[cloudflared](https://developers.cloudflare.com/tunnel/downloads/), затем:

```bash
./scripts/setup.sh
SCHEDULER_ENABLED=true ./scripts/start.sh
# В другом терминале, пока backend работает:
./scripts/preview.sh cloudflare
```

Клиент печатает случайный HTTPS URL `trycloudflare.com`. Перед передачей ссылки
проверьте её (замените URL фактическим адресом из вывода):

```bash
.venv/bin/python scripts/verify_deployment.py "$PREVIEW_URL" --save /tmp/preview-before.json
```

Скрипт проверяет frontend/assets, health, status, Bugun, все видимые карточки,
поиск и годы. Для внутренней проверки можно использовать `--local` с loopback URL;
это не ссылка для телефона. Проверка API не заменяет просмотр мобильного интерфейса.

**Состояние на 07.10.2026:** публичный URL в текущей Codex-среде не получен.
cloudflared завершился с `connect: connection refused` при обращении к
`api.trycloudflare.com:443`: его quick-tunnel запрос не использовал управляемый
HTTP-прокси. Локальный сайт проверен, но проверка внешнего HTTPS не выполнена.
Не отключайте TLS и не обходите сетевую политику. Альтернатива
`./scripts/preview.sh ngrok` требует установленного официального ngrok и аккаунта;
ngrok поддерживает `http_proxy`. Его подключение в этой среде не проверено,
поскольку у пользователя нет аккаунта. Дополнительные ключи сейчас не требуются.

Настройки приложения: `PORT` (по умолчанию 8000), `DATABASE_URL` (по умолчанию
локальная SQLite), `SCHEDULER_ENABLED=true`. `AI_API_KEY` и `SEARCH_API_KEY`
необязательны для просмотра; они нужны для соответствующих discovery API.
Для ngrok используется защищённая настройка `NGROK_AUTHTOKEN` или штатный локальный
config вне Git. Ни один секрет не передавайте в командной строке или чате.
`TRUSTED_EGRESS_PROXY=true` используется только в доверенной управляемой среде,
как описано выше. `RENDER_API_KEY` для временного preview не нужен.

Обновление: остановите свой backend через Ctrl+C, получите новый commit,
выполните `./scripts/setup.sh` и снова `./scripts/start.sh`. Туннель можно оставить
работать во время короткого restart backend; если перезапустить сам Cloudflare
туннель, URL изменится. Логи API/scheduler и туннеля выводятся в их терминалы.
`/status` показывает `scheduler_enabled`, ближайший запуск и результаты discovery;
наличие ближайшего времени подтверждает расписание, а завершённый run — выполнение.
Один worker запускает hourly discovery в HH:00 Asia/Tashkent **только пока машина
и backend работают**. После остановки среды нет постоянно работающего cron/worker.

Перезапуск backend не очищает SQLite. Перед обновлением можно сделать согласованную
резервную копию, включая WAL, без остановки API:

```bash
.venv/bin/python -m backend.app.db_transfer --output /tmp/finder-backup.sqlite3
# После restart, с тем же URL и той же базой:
.venv/bin/python scripts/verify_deployment.py "$PREVIEW_URL" --compare /tmp/preview-before.json
```

Экспорт не перезаписывает существующие файлы; сохраните резервную копию вне временной
машины для защиты от её удаления. На текущей машине сохранение всех записей, ID,
publication date и first_seen после restart проверено. Удаление среды/диска не
равнозначно restart: постоянное хранение за пределами этой машины не обеспечено.

Cloudflare Quick Tunnel бесплатный, без SLA, с лимитом 200 одновременных запросов
и без SSE; ссылка публична и действует только пока жив туннель. Эти ограничения
описаны в [официальной документации](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
На телефоне после получения проверенной ссылки нужно открыть Bugun, годы 2024–2026,
карточку KotibAI, поиск и `/status`. Карточки после backfill ещё требуют проверки
качества; Stage 1 не принят. Постоянный Render/Railway deploy остаётся вне текущего
запроса пользователя.

## Хранение и ограничения Stage 1

- SQLite подходит для первой версии. ORM и драйвер готовы к PostgreSQL, но реальный PostgreSQL deployment в этом этапе не проверялся. Версия схемы 3 применяется автоматически; добавлены происхождение, версия обработки, архивный период и анализ кандидата, структурированные детали запуска. Перед переносом старой SQLite-схемы создаётся `data/finder.sqlite3.pre-radar-backup`; старые цитаты переносятся в `project_sources`, ID и даты сохраняются. Не удаляйте рабочую базу ради обновления. Перед ручным восстановлением остановите сервис и сохраните текущую базу вместе с WAL/SHM; используйте SQLite backup API. PostgreSQL-миграция не проверялась.
- Нет гарантии найти все проекты: RSS ограничен текущими публикациями, web search зависит от тарифа/квоты, неизвестные даты и слабые доказательства отбрасываются. Нет публичного административного редактирования карточек.
- Дедупликация консервативная: URL, имя/псевдонимы, автор/организация и локальная векторная близость текста. Это не мультиязычная embedding-модель. Переименованные проекты и отсутствующие сведения об авторах могут требовать дополнительного подтверждения; разные продукты одного автора не объединяются только по автору.
- AI-запросы ограничены по объёму; инструкция в чужой статье не считается командой. Цитаты проверяются на наличие в источнике, но это не независимый фактчекинг истины утверждения.
- robots.txt, таймауты и HTTP-ошибки соблюдаются. CAPTCHA, авторизация, 403 и код чужих репозиториев не обходятся и не исполняются.
- Исходные тексты кандидатов хранятся ограниченными по размеру для повторной обработки; интерфейс показывает краткие описания, цитаты и ссылки. Проверяйте условия источника перед публичным распространением.
- Реальные ключи AI/Search в текущую среду не добавлены; ограниченный fallback и публичные архивы не заменяют их возможности. Живые RSS и HTML-источники проверены отдельно; оплачиваемые API подтверждены только mock-тестами.

Подробности — в [ARCHITECTURE.md](ARCHITECTURE.md), состояние этапа — в [PROJECT_STATUS.md](PROJECT_STATUS.md), результаты проверок — в [docs/VALIDATION.md](docs/VALIDATION.md).

## Muammo → yechim → imkoniyat (Stage 1 kengaytmasi)

Bosh sahifa `/` endi loyihalar, muammolar va signallar uchun o‘zbekcha
intelligence panelidir. Oldingi loyiha lentasi, qidiruv va arxiv
`/loyihalar` va `/arxiv?period=all` da saqlangan. Alohida sahifalar:
`/muammolar`, `/goyalar`, `/signallar`, `/sektorlar`, `/manbalar`, `/status`.
API: `/api/intelligence/dashboard`, `/api/problems`, `/api/problems/{id}`,
`/api/ideas`, `/api/ideas/{id}`, `/api/signals`, `/api/sectors/intelligence`.
Barcha yozuvlar haqiqiy manbalardan; bo‘sh sahifa sun’iy kartochka bilan
«to‘ldirilmaydi».

**Muammo darvozasi.** Loyiha haqidagi dalil alohida tekshiriladi. Aniq muammo,
zarar ko‘rayotgan foydalanuvchi va loyiha bilan bog‘liq manba iqtibosi topilsa
`PASS`; yetarli dalil bo‘lmasa `PENDING/pending_problem_analysis`; faqat
kichik interfeys o‘zgarishi bo‘lsa `REJECT/minor_feature`. Avvalgi tasdiqlangan
kartochkalar o‘chirilmaydi, ammo muammo isbotlanmaguncha ularga kuchli
«imkoniyat» bahosi berilmaydi. Faktlar iqtibos va URL bilan, tizim
xulosalari alohida ko‘rsatiladi. `SOLUTION_IDEA` mavjud mahsulot emas, gipoteza;
bitta maqoladan avtomatik g‘oya yasalmaydi.

**Baholash.** Ichki 15 mezon muammo (og‘riq, takrorlanish, majburiylik,
xarajat), bozor (mijozlar, to‘lov istagi, kengayish), biznes modeli
(takroriy tushum, mijozga yetish, kapital, huquqiy xavf), amalga oshirish
(MVP tezligi, raqobat, bajarish imkoniyati, O‘zbekistonga moslik) bo‘yicha
1–5 ball oladi. Har bir bahoga sabab va dalil URL kerak. Hammasi dalillanmasa
raqam va A/B darajasi ko‘rsatilmaydi. To‘liq bahoda to‘rtta guruhning 0–10
ballari o‘rtachasi ×10, keyin dalil darajasi koeffitsiyenti (1→0,45;
2→0,60; 3→0,75; 4→0,90; 5→1,00) qo‘llanadi. A ≥80, B ≥65,
C ≥50, qolganlari D; fatal stop-filtr `REJECTED`. AI yoki skraper to‘lov,
pilot, mijoz suhbatini dalilsiz tasdiqlay olmaydi. Eski Foydalilik va
Tasdiqlanganlik baholari mustaqil qoladi.

**Jadval.** Soatlik loyiha qidiruvi manbaning o‘z chastotasiga bo‘ysunadi.
Har 15 daqiqadagi nazoratchi 08:00 va 23:30 Toshkent vaqti moslashtirishini,
haftalik O‘zbekiston muammolari va oylik xalqaro muammo/signallar skanini
tekshiradi. Server o‘chiq bo‘lgan vaqtdagi slot keyingi ishga tushishda
qoplanadi; holat SQL `scheduler_checkpoints` da saqlanadi. Faqat API jarayoni
yoqilganida scheduler ishlaydi. Xalqaro qidiruvning hozirgi faol qismi
Show HN ochiq RSS orqali past ishonchli texnologiya signallarini oladi;
bu hali dunyo muammolari va tendensiyalarining to‘liq tahlili emas.

```bash
.venv/bin/python -m backend.app.cli --local-problems
.venv/bin/python -m backend.app.cli --global-trends
.venv/bin/python -m backend.app.cli --list-sources
.venv/bin/python -m backend.app.cli --list-candidates --candidate-status problem
.venv/bin/python -m backend.app.cli --inspect-url 'https://manba.example/maqola'
```

`config/sources.json` da 64 ta boshlang‘ich manba konsepti mavjud. 11 ta avval
ishlagan integratsiya va 1 ta Show HN signal manbasi yoqilgan; yangi konseptlar endpoint, robots.txt va parser
tekshiruvigacha o‘chirilgan. Boshlang‘ich import mavjud manbalarning faqat bo‘sh
meta maydonlarini boyitadi; operator o‘chirgan manbani yoqmaydi. AI_API_KEY va
SEARCH_API_KEY ixtiyoriy. Haqiqiy kalitlar `.env` yoki hosting env vars ichida,
Gitda emas. Mavjud SQLite migratsiya vaqtida o‘chirilmaydi; ishlab chiqarishda
barqaror disk yoki sozlangan PostgreSQL kerak. Arxivning 2022-01-01 —
2026-09-30 oraliqdagi eski buyruqlari va yozuvlari saqlangan.

Tarixiy muammo uchun yil filtri birinchi dalilning asl nashr sanasini ishlatadi;
`first_seen_at` esa tizim topgan vaqt bo‘lib qoladi. Muayyan saqlangan
nomzodni yangi qoidalar bilan qayta tekshirish:

```bash
.venv/bin/python -m backend.app.cli --reclassify-url 'https://www.spot.uz/oz/2022/04/11/humo-app'
.venv/bin/python -m backend.app.cli --reanalyze-problems
.venv/bin/python -m backend.app.cli --reclassify-candidates
.venv/bin/python -m backend.app.cli --drain --archive
```

`--reclassify-url` tarmoqdan yangi material qidirmaydi; saqlangan maqolani
manba/iqtibos qoidalari bilan qayta baholaydi. `--reclassify-candidates` eski
rad etilgan yozuvlarning cheklangan partiyasini navbatga qaytaradi. Yangi
real muammo misoli: [Spot HUMO uzilishlari](https://www.spot.uz/oz/2022/04/11/humo-app),
11 aprel 2022; bu maqola asosida mahsulot yoki yechim g‘oyasi to‘qib
chiqarilmagan. Show HN orqali kelgan signallar tasdiqlangan loyiha deb
ko‘rsatilmaydi.

Bitta tadbir maqolasida har bir nomlangan loyiha uchun alohida muallif/yaratish
iqtibosi bo‘lsa, bir maqola URL manbasi bir necha PROJECT kartasiga bog‘lanishi
mumkin. `project_sources` ning yangi `(project_id, url)` cheklovi bilan
migratsiya eski manba ID va URLlarini saqlaydi; SQLite uchun migratsiyadan
oldin `.pre-multisource-backup` nusxasi olinadi. Oddiy maqola URL bo‘yicha
dedup avvalgidek qat’iy qoladi.

KotibAI maqolasidagi jurnalistlarning bir soatlik suhbatni matnga ko‘chirishga
uch soat sarflagani haqidagi asl iqtibos unga `EVERYDAY` muammo havolasini
beradi. DMED maqolasidagi retsept xatolarini bartaraf etish haqidagi iqtibos
`UZBEKISTAN_LOCAL` muammoga bog‘lanadi. Uzbekistan Airways, Agroko‘makchi va
BITO uchun mustaqil muammo dalili yetarli emas: mavjud loyiha kartalari
saqlanadi, ammo ularning imkoniyat bahosi `PENDING` bo‘lib qoladi. To‘liq 15
mezon bo‘lmagani uchun KotibAI va DMED ham A/B bahosini olmaydi.

2026-10-08 dagi manba bilan tekshirilgan qayta ishlash CEVF tadbir maqolasidan
BITO (asoschisi Umidjon Po‘latov) va oldin saqlangan Spot maqolasidan
Agroko‘makchi (Qishloq xo‘jaligi vazirligi) kartalarini ko‘rsatdi. Ikkala
manba sahifasi HTTP 200 qaytardi. Bu kartalar mavjud mahsulot daliliga ega,
lekin kuchli biznes imkoniyati deb tasdiqlanmagan. Birinchi marta ko‘rinadigan
oldingi yashirin loyiha endi run hisobotida yangi e’lon deb hisoblanadi.
Yillik arxivda cheklangan qayta ishlash byudjeti avval shu yilga mos URL/feed
sanasiga ega loyiha sarlavhalariga sarflanadi. Bu faqat navbat tartibi:
maqolaning haqiqiy nashr sanasi yuklangach yana tekshiriladi, sanasi noma’lum
materiallar esa navbatdan yo‘qotilmaydi.

2026-10-08 dagi yangi, API kalitsiz va bo‘sh bazadan boshlagan arxiv tekshiruvi
hamda manbalari bilan beshta karta haqidagi batafsil natija:
[PROBLEM_FIRST_VALIDATION.md](docs/PROBLEM_FIRST_VALIDATION.md). Baza Gitga
qo‘shilmaydi; boshqa muhit shu natijani olish uchun backfill/navbat buyruqlarini
o‘z SQLite bazasida ishlatishi kerak. Cheklangan birinchi pass 2023 yoki 2024
arxivini to‘liq qamrab olgani deb talqin qilinmaydi.

## Stage 1: ikkinchi vizual va discovery pass (08.10.2026)

Bosh sahifa endi to‘q grafit/teal intelligence panelidir: loyihalar, muammolar,
dalilga asoslangan g‘oyalar va signallar alohida ko‘rsatiladi. To‘liq loyiha
lentasi va eski filtrlar `/loyihalar` da saqlangan. Karta avval muammo va
foydalanuvchini ko‘rsatadi; yetarli dalil bo‘lmasa imkoniyat balli berilmaydi.
`/status` scheduler o‘chirilgan bo‘lsa buni ochiq ko‘rsatadi.

Ro‘yxatdan o‘tgan **yoqilgan** manbadagi bitta aniq maqolani oddiy pipeline
orqali tekshirish:

```bash
AI_API_KEY= SEARCH_API_KEY= TRUSTED_EGRESS_PROXY=true \
  .venv/bin/python -m backend.app.cli \
  --process-url 'https://www.spot.uz/oz/2025/09/12/tilmoch/' \
  --report /tmp/tilmoch-run.json
```

Buyruq HTTPS/robots, sana, loyiha mavjudligi, muallif, dedup va stop-filtrni
chetlab o‘tmaydi. Mavjud yozuv qayta tekshiriladi; nomzod manbasi o‘chirilgan
bo‘lsa qayta yoqilmaydi. `--backfill` va `--drain` kengroq tarixiy qidiruvni
cheklangan byudjet bilan davom ettiradi. Baza va navbat o‘chirilmaydi.

Ikkinchi pass ikki yangi manbali kartani ko‘rsatdi: Tahrirchi (2023) va
Tilmoch (2025). Ikkisining mavjudligi va asoschisi tasdiqlangan; muammo
dalili yetarli emasligi sabab imkoniyat darajasi `PENDING`. Joriy muhitdagi
sanalar, manbalar, rad etish/queue holati va testlar
[SECOND_PASS_VALIDATION.md](docs/SECOND_PASS_VALIDATION.md) da. Bu natija
boshqa Codespace bazasiga avtomatik ko‘chmaydi.

## Joriy ochiq mahsulot va Global discovery — 09.10.2026

Ochiq menyu: `Bosh sahifa`, `Loyihalar`, `Arxiv`, `Manbalar`. Bosh sahifa
faqat nashr sanasiga ko‘ra oxirgi 30 kundagi tayyor loyihalarni ko‘rsatadi.
`Loyihalar` oddiy katalog, nom bo‘yicha qidiruv va `Barchasi / O‘zbekiston /
Global` tanloviga ega. `Arxiv`da Bugun, 7 kun, 30 kun, yil va nom qidiruvi
bor. `Manbalar` manbalar guruhlarini tushuntiradi; texnik xatolarni ko‘rsatmaydi.
Imkoniyatlar reytingi, muammolar, signallar va g‘oyalar ochiq bosh menyudan
olingan, ammo ularning SQL modellari va tahlil ma’lumotlari saqlangan.

Ommaviy `/api/projects` faqat `publication_status=PUBLISHED` qaytaradi.
Loyiha nomi/muallifi va mavjudligi tasdiqlansa-yu, aniq muammo, foydalanuvchi
yoki yechim yetishmasa, yozuv `REVIEW_REQUIRED` bo‘lib saqlanadi. Loyiha
`DISCOVERED → VERIFIED_PROJECT → ANALYZED → PUBLISHED` sifat bosqichlaridan
o‘tadi; rad va dubllar alohida qayd etiladi. Adminning `ACCEPT` amali faqat
oddiy qayta tekshirish navbatiga qo‘yadi; dalil chegarasini chetlab o‘tmaydi.
`first_seen` va eski dalillar o‘chirilmaydi. Eski maqola bugun topilsa ham
`Yangi` hisoblanmaydi.

`/admin`, `/admin/review` va `/admin/sources` egasiga navbat, holat va manbalar
samarasini ko‘rsatadi. `ADMIN_API_KEY` ni `.env` yoki hostingning himoyalangan
environment sozlamasida uzoq tasodifiy qiymatga o‘rnating. U Gitga kiritilmaydi.
Admin API so‘rovlarida `X-Admin-Key` yuboriladi. Kalit bo‘lmasa admin API 503,
noto‘g‘ri bo‘lsa 401 qaytaradi. Ochiq sahifa kalitga muhtoj emas.

Global loyihalar uchun bepul Show HN RSS bevosita loyiha saytlari havolalarini
topadi; HN submission havolasi alohida discovery provenance sifatida saqlanadi.
Sayt yoki loyiha nomining mavjudligi o‘zi yetarli emas: sanasi, yaratuvchisi,
muammosi, foydalanuvchisi va manbaga tayangan tavsifi kerak. Noma’lum inglizcha
tavsifni AI kalitisiz to‘qib tarjima qilish o‘rniga nomzod navbatda qoladi.
Manba va navbat bo‘yicha alohida tekshirish:

```bash
.venv/bin/python -m backend.app.cli --only-source show-hn-rss --force-sources --report /tmp/show-hn.json
.venv/bin/python -m backend.app.cli --only-source show-hn-rss --drain --report /tmp/show-hn-drain.json
```

`--only-source` manbaning yangi havolalari va shu manbaga tegishli saqlangan
navbatni cheklaydi. Lokal Uzbekistan manbalari va hourly scheduler ishlashda
davom etadi. `AI_API_KEY` va `SEARCH_API_KEY` ixtiyoriy; birortasi ham oddiy
manba tekshiruvi uchun talab qilinmaydi. Mavjud `--backfill` tarixiy oynalari
o‘zgarmadi. Natijalarni to‘liq statistikasi va cheklovlari
[PUBLIC_GLOBAL_VALIDATION.md](docs/PUBLIC_GLOBAL_VALIDATION.md) da.
