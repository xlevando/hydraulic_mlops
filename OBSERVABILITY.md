# Наблюдаемость конвейера обработки задач

Стек наблюдаемости для конвейера (API => RabbitMQ => FastStream Worker => PostgreSQL), собирающий логи, трейсы и метрики.

## 1. Архитектура и обоснование

- **Логи:** Grafana Alloy (агент) => Loki.
  *Почему:* Loki индексирует только метаданные (лейблы), а не полный текст, что снижает потребление RAM и диска по сравнению с ELK. Alloy легковесен и нативно интегрирован с Grafana.
- **Трейсы:** OpenTelemetry SDK => OTel Collector => Jaeger.
  *Почему:* Jaeger - решение с удобным UI, легко разворачивается в одном контейнере и поддерживает OTLP "из коробки".
- **Метрики:** Prometheus.
  *Почему:* Для стенда (< 10 000 активных серий, retention 3 дня) возможностей Prometheus достаточно. VictoriaMetrics выигрывает на больших объёмах, но здесь избыточна. RabbitMQ уже отдаёт метрики в формате Prometheus.

## 2. Запуск

Только приложение
```bash
docker compose up -d
```
Поднимает `api`, `worker`, `postgres`, `rabbitmq`. Логи идут в `stdout`.

Полный стек наблюдаемости
```bash
docker compose --profile observability up -d
```
Поднимает всё (Grafana, Loki, Jaeger, Prometheus, Alloy, OTel Collector).


## 3. Логирование

- **Формат:** JSON (библиотека `structlog`).
- **Поля:** `timestamp`, `level`, `event`, `task_id`, `trace_id`, `span_id`, `request_id`.
- **Сбор:** Grafana Alloy читает `docker.sock` и отправляет логи в Loki.
- **Лейблы:** `job="hydraulic-logs"`, `container_name="hydraulic-app|hydraulic-worker"`.


## 4. Трассировка

- **Инструментация:** OTel SDK + `RabbitTelemetryMiddleware` (FastStream).
- **Экспорт:** OTLP => Collector => Jaeger.
- **Семплирование:** `ParentBasedTraceIdRatio` с коэффициентом `1.0` для стенда. Для продакшена с источником на сотни задач в секунду выбран бы `0.1` (10%), чтобы не перегружать хранилище.
- **Сквозной трейс:** `POST /api/v1/tasks` => `publish` => `process` (воркер) => `inference` => `save_to_db`.

## 5. Метрики и бюджет памяти

- **API:** Prometheus скрейпит `hydraulic-app:8000/metrics`.
- **Воркер:** Prometheus скрейпит `hydraulic-worker:8002/metrics`.
- **RabbitMQ:** Prometheus скрейпит `hydraulic-rabbitmq:15692/metrics`.

### Оценка кардинальности
Метрики имеют низкую кардинальность (лейблы `method`, `path`, `status_code`):
- `api_requests_total`: 3 × 5 × 5 = ~75 серий.
- `api_request_duration_seconds`: 3 × 5 = 15 серий (по 10 бакетов).
- `worker_tasks_processed_total`: 2 статуса = 2 серии.
- `rabbitmq_queue_messages`: 2 очереди × 1 инстанс = 2 серии.
- **Итого:** < 1000 активных временных рядов.


### Бюджет памяти (подтверждён `docker stats` под нагрузкой)

| Сервис | Лимит памяти | Фактическое потребление |
|---|---|---|
| Loki | 256 MB | (не был запущен в момент замера)* |
| Grafana | 256 MB | 58.28 MB |
| Prometheus | 256 MB | 27.48 MB |
| Jaeger | 256 MB | 27.87 MB |
| OTel Collector | 256 MB | 42.84 MB |
| Alloy | 256 MB | 55.59 MB |
| **Итого (наблюдаемость)** | **~1.5 GB** | **~212 MB** |

*(Замер сделан во время нагрузочного теста `MODE=load N_REQUESTS=500`. Loki не участвовал в замере, но его лимит 256 MB заложен в compose. Суммарное потребление стека наблюдаемости ~212 MB, что в 7 раз меньше заявленного бюджета 1.5 GB).*

## 6. Grafana

- **Provisioning:** Data sources, дашборды и алерты лежат в `observability/grafana/provisioning/`.
- **Дашборд:** `Hydraulic Pipeline Dashboard` (UID: `pipeline-dashboard`).
- **Корреляция:** В логах Loki есть поле `trace_id` с Derived Field, которое ведёт в Jaeger.
- **Алерты:**
  1. `Очередь заполнена более чем на 90%` (порог 90, `for: 1m`).
  2. `Сообщения в Dead Letter Queue` (порог > 0, `for: 0s`).


## Проверка выводов эксперимента (PromQL)

Для подтверждения выводов можно выполнить следующие запросы в Prometheus:

1. **Глубина очереди упирается в лимит (100):**
   ```promql
   rabbitmq_queue_messages{queue="tasks"}
   ```
   *На графике виден пик до 100 во время нагрузки.*

2. **Скорость источника падает (backpressure):**
   ```promql
   sum(rate(api_requests_total[1m]))
   ```
   *Во время нагрузки падает, так как API получает 503 и замедляется.*

3. **Пропускная способность воркера:**
   ```promql
   sum(rate(worker_tasks_processed_total[1m]))
   ```
   *Держится на уровне ~3-4 req/s (для 1 воркера).*

4. **Оценка числа рядов в Prometheus:**
   ```promql
   count({__name__=~".+"})
   ```
   *Показывает общее число активных временных рядов.*
