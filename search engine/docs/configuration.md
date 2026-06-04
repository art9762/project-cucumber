# Конфигурация find-engine

## Вступление

Вся конфигурация find-engine читается из переменных окружения, либо из файла
`.env` в корне проекта. За загрузку отвечает класс `Settings`
(`find_engine/config.py`), построенный на [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

Ключевые принципы:

- **Секреты — только из окружения.** Токены и ключи (`GITHUB_TOKEN`,
  `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`) задаются исключительно через ENV /
  `.env` и никогда не хранятся в коде.
- **Файл `.env` опционален.** Если файла нет, берутся значения по умолчанию из
  `Settings` либо переменные текущего окружения. Кодировка файла — UTF-8.
- **Лишние переменные игнорируются.** Модель сконфигурирована с `extra="ignore"`,
  поэтому неизвестные переменные в окружении не вызывают ошибок.
- **Настройки кешируются.** `get_settings()` обёрнут в `lru_cache`, то есть
  объект `Settings` создаётся один раз за процесс.

Шаблон со всеми переменными лежит в `.env.example` — скопируйте его в `.env` и
заполните.

---

## Таблица переменных окружения

### Database

| ENV | Поле `Settings` | Тип | Дефолт | Описание |
|-----|-----------------|-----|--------|----------|
| `DB_URL` | `db_url` | `str` | `postgresql+asyncpg://findengine:findengine@localhost:5432/findengine` | DSN PostgreSQL для асинхронного драйвера `asyncpg`. |

### Секреты и учётные данные

| ENV | Поле `Settings` | Тип | Дефолт | Описание |
|-----|-----------------|-----|--------|----------|
| `GITHUB_TOKEN` | `github_token` | `str \| None` | `None` | Personal Access Token GitHub. Опционален, но снимает строгий anonymous rate-limit. |
| `REDDIT_CLIENT_ID` | `reddit_client_id` | `str \| None` | `None` | Client ID приложения Reddit. Опционален (публичный JSON работает без него). |
| `REDDIT_CLIENT_SECRET` | `reddit_client_secret` | `str \| None` | `None` | Client Secret приложения Reddit. Опционален. |
| `REDDIT_USER_AGENT` | `reddit_user_agent` | `str` | `find-engine/0.1` | Заголовок `User-Agent` для запросов к Reddit. Должен быть корректным и уникальным. |

### Поведение HTTP

| ENV | Поле `Settings` | Тип | Дефолт | Описание |
|-----|-----------------|-----|--------|----------|
| `HTTP_TIMEOUT` | `http_timeout` | `float` | `30.0` | Таймаут HTTP-запросов (секунды). Применяется во всех источниках при создании `httpx.AsyncClient`. |
| `HTTP_MAX_RETRIES` | `http_max_retries` | `int` | `3` | Максимум повторов запроса при сбоях (передаётся в `request_with_retry`). |

### Настройка источников

| ENV | Поле `Settings` | Тип | Дефолт | Описание |
|-----|-----------------|-----|--------|----------|
| `GITHUB_TOPICS` | `github_topics` | `str` (CSV) | `ai,llm,machine-learning,agents` | Список топиков GitHub через запятую. Доступен как список через `github_topic_list`. |
| `REDDIT_SUBREDDITS` | `reddit_subreddits` | `str` (CSV) | `MachineLearning,LocalLLaMA,artificial,singularity` | Список сабреддитов через запятую. Доступен как список через `reddit_subreddit_list`. |
| `ARXIV_CATEGORIES` | `arxiv_categories` | `str` (CSV) | `cs.AI,cs.LG,cs.CL` | Категории arXiv через запятую. Доступны как список через `arxiv_category_list`. |
| `HN_QUERY` | `hn_query` | `str` | `AI OR LLM OR "machine learning"` | Поисковый запрос для Hacker News (Algolia search-синтаксис). |
| `HN_MIN_POINTS` | `hn_min_points` | `int` | `10` | Минимальный порог очков (`points`) для отбора историй HN. |

### Расписание (cron)

| ENV | Поле `Settings` | Тип | Дефолт | Описание |
|-----|-----------------|-----|--------|----------|
| `CRON_ARXIV` | `cron_arxiv` | `str` | `""` | Cron-расписание для источника arxiv. Пустая строка = выключено. |
| `CRON_HACKERNEWS` | `cron_hackernews` | `str` | `""` | Cron-расписание для источника hackernews. Пустая строка = выключено. |
| `CRON_GITHUB` | `cron_github` | `str` | `""` | Cron-расписание для источника github. Пустая строка = выключено. |
| `CRON_REDDIT` | `cron_reddit` | `str` | `""` | Cron-расписание для источника reddit. Пустая строка = выключено. |

---

## База данных

`DB_URL` — это DSN в формате SQLAlchemy/async с драйвером **asyncpg**:

```
postgresql+asyncpg://<user>:<password>@<host>:<port>/<database>
```

Дефолтное значение соответствует контейнеру из `docker-compose.yml`:

| Часть DSN | Значение | Источник в docker-compose |
|-----------|----------|----------------------------|
| user | `findengine` | `POSTGRES_USER` |
| password | `findengine` | `POSTGRES_PASSWORD` |
| host / port | `localhost:5432` | проброс портов `5432:5432` |
| database | `findengine` | `POSTGRES_DB` |

То есть после `docker compose up postgres` дефолтный `DB_URL` работает без
изменений. Образ — `postgres:16`, данные хранятся в томе `pgdata`, есть
healthcheck через `pg_isready`.

---

## Секреты и rate limits

### GitHub (`GITHUB_TOKEN`)

Источник `GithubSource` (`find_engine/sources/github.py`) ищет репозитории через
GitHub REST Search API. Токен используется при формировании заголовков:

- если `github_token` задан — добавляется заголовок `Authorization: Bearer <token>`;
- если не задан — запросы идут анонимно.

Без токена действует строгий **anonymous rate-limit (~10 запросов/мин)** для
Search API, поэтому токен рекомендуется задавать, хотя он и опционален.

### Reddit (`REDDIT_*`)

Источник `RedditSource` (`find_engine/sources/reddit.py`) читает публичный JSON
(`/r/<subreddit>/new.json`). Особенности:

- **Публичный JSON работает без ключей** — поля `REDDIT_CLIENT_ID` и
  `REDDIT_CLIENT_SECRET` опциональны и в текущей реализации источника напрямую
  не используются (зарезервированы под OAuth).
- Reddit лимитирует анонимные запросы, поэтому обязателен корректный
  **`User-Agent`**: `reddit_user_agent` подставляется в заголовок `User-Agent`
  каждого запроса. Указывайте осмысленное значение, например
  `find-engine/0.1 (by u/yourname)`.

---

## Настройка источников

### Comma-separated списки

Три настройки задаются как строки со значениями через запятую и преобразуются в
списки через property-хелперы. Парсинг выполняет внутренняя функция `_split`,
которая разбивает по запятой, обрезает пробелы и отбрасывает пустые элементы:

| ENV | property | Используется в |
|-----|----------|----------------|
| `GITHUB_TOPICS` | `github_topic_list` | строит запрос `topic:<t>` для каждого топика |
| `REDDIT_SUBREDDITS` | `reddit_subreddit_list` | перебирает сабреддиты, читая `/r/<sub>/new.json` |
| `ARXIV_CATEGORIES` | `arxiv_category_list` | строит запрос `cat:<c>` через `OR` |

Пример: `GITHUB_TOPICS=ai, llm , machine-learning` → `["ai", "llm", "machine-learning"]`.

### Hacker News (`HN_QUERY`, `HN_MIN_POINTS`)

Источник `HackerNewsSource` (`find_engine/sources/hackernews.py`) использует
Algolia HN Search API:

- **`HN_QUERY`** — текст поискового запроса (параметр `query`). Поддерживает
  синтаксис Algolia, в том числе булевы операторы, например
  `AI OR LLM OR "machine learning"`.
- **`HN_MIN_POINTS`** — порог очков: подставляется в `numericFilters` как
  `points>=<N>`, отсекая истории с числом очков ниже порога.

---

## Расписание (cron)

Каждый источник может запускаться по своему расписанию. Формат — стандартный
**5-полевой cron**:

```
┌───── минута (0-59)
│ ┌───── час (0-23)
│ │ ┌───── день месяца (1-31)
│ │ │ ┌───── месяц (1-12)
│ │ │ │ ┌───── день недели (0-6)
│ │ │ │ │
* * * * *
```

- **Пустая строка = расписание выключено** (источник не планируется к запуску).
- Получить расписание конкретного источника можно методом
  `Settings.cron_for(source)`, который сопоставляет имя источника с нужным полем:

| `source` | Поле | ENV |
|----------|------|-----|
| `arxiv` | `cron_arxiv` | `CRON_ARXIV` |
| `hackernews` | `cron_hackernews` | `CRON_HACKERNEWS` |
| `github` | `cron_github` | `CRON_GITHUB` |
| `reddit` | `cron_reddit` | `CRON_REDDIT` |

Для неизвестного имени источника `cron_for` возвращает пустую строку (то есть
расписание считается выключенным).

Пример из `.env.example`:

```env
CRON_ARXIV=0 */6 * * *       # каждые 6 часов
CRON_HACKERNEWS=0 */3 * * *  # каждые 3 часа
CRON_GITHUB=0 */6 * * *      # каждые 6 часов
CRON_REDDIT=0 */6 * * *      # каждые 6 часов
```

---

## Пример минимального `.env`

Для локального запуска с PostgreSQL из `docker-compose.yml` достаточно дефолтов —
явно задавать `DB_URL` не обязательно. Минимальный осмысленный файл:

```env
# БД из docker-compose (можно опустить — совпадает с дефолтом)
DB_URL=postgresql+asyncpg://findengine:findengine@localhost:5432/findengine

# Рекомендуется, чтобы не упереться в anonymous rate-limit GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Корректный User-Agent для Reddit
REDDIT_USER_AGENT=find-engine/0.1 (by u/yourname)

# Включить хотя бы один источник по расписанию
CRON_HACKERNEWS=0 */3 * * *
```

Всё остальное (топики, сабреддиты, категории, HTTP-таймауты, HN-запрос)
подхватится из значений по умолчанию `Settings`.
