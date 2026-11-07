"""Эксперимент: сбор метрик backpressure."""

import asyncio
import csv
import logging
import os
import subprocess
import time
from pathlib import Path

import asyncpg
import httpx

log = logging.getLogger(__name__)

MODE = os.getenv("MODE", "load")
API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1/tasks")
N_REQUESTS = int(os.getenv("N_REQUESTS", "300"))
RABBITMQ_API = os.getenv("RABBITMQ_API", "http://localhost:15672/api")
RABBITMQ_AUTH = ("admin", "admin")
OUTPUT_DIR = Path("data/experiments")
WORKER_CONTAINER = os.getenv("WORKER_CONTAINER", "hydraulic-worker")
QUEUE_MAX_LENGTH = int(os.getenv("QUEUE_MAX_LENGTH", "100"))
SAMPLE_INTERVAL_SEC = float(os.getenv("SAMPLE_INTERVAL_SEC", "1.0"))
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/hydraulic_mlops",
)
SIGTERM_AT_SEC = float(os.getenv("SIGTERM_AT_SEC", "20.0"))
DRAIN_TIMEOUT_SEC = float(os.getenv("DRAIN_TIMEOUT_SEC", "180"))

SENSORS = [
    "PS1",
    "PS2",
    "PS3",
    "PS4",
    "PS5",
    "PS6",
    "EPS1",
    "FS1",
    "FS2",
    "TS1",
    "TS2",
    "TS3",
    "TS4",
    "VS1",
    "CE",
    "CP",
    "SE",
]
STATS = ["mean", "std", "rms", "min", "max", "median", "skew", "kurtosis", "delta", "slope"]
FEATURES = {f"{s}_{st}": 1.0 for s in SENSORS for st in STATS}


async def _rmq_get(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.get(f"{RABBITMQ_API}{path}", auth=RABBITMQ_AUTH, timeout=5.0)
    return r.json() if r.status_code == 200 else {}


async def get_queue_depth(client: httpx.AsyncClient, queue: str = "tasks") -> int:
    data = await _rmq_get(client, f"/queues/%2F/{queue}")
    # Считаем и готовые, и те, что уже в работе (unacked), чтобы понять,
    # остались ли еще задачи в системе.
    return int(data.get("messages", 0)) + int(data.get("messages_unacknowledged", 0))


async def get_dlq_depth(client: httpx.AsyncClient) -> int:
    data = await _rmq_get(client, "/queues/%2F/tasks.dlq")
    return int(data.get("messages", 0))


def get_container_memory(container: str) -> float:
    try:
        r = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
        s = r.stdout.strip()
        if not s or s.startswith("--"):
            return -1.0
        s = s.split("/")[0].strip()
        for unit, mult in (("GiB", 1024.0), ("MiB", 1.0), ("KiB", 1.0 / 1024.0)):
            if unit in s:
                return float(s.replace(unit, "").strip()) * mult
    except Exception as e:  # noqa: BLE001
        log.warning("mem %s: %s", container, e)
    return -1.0


async def publish_one(
    client: httpx.AsyncClient,
    idx: int,
    mode: str,
) -> dict:
    """Опубликовать одну задачу.
    load:            503 => возвращаем rejected, не ретраим (клиент увидел 503).
    backpressure /
    no_backpressure: 503 => уважаем Retry-After, ретраим (источник замедляется).
    sigterm:         503 => как backpressure.
    """
    t0 = time.monotonic()
    attempts = 0
    backoff = 0.1
    while True:
        attempts += 1
        try:
            r = await client.post(
                API_URL,
                json={"features": FEATURES},
                timeout=10.0,
            )
            if r.status_code == 202:
                body = r.json()
                return {
                    "idx": idx,
                    "status": 202,
                    "attempts": attempts,
                    "task_id": body.get("task_id"),
                    "t_publish": time.time(),
                    "latency_http": time.monotonic() - t0,
                }
            if r.status_code == 503:
                ra = r.headers.get("Retry-After")
                try:
                    retry_after = float(ra) if ra is not None else 1.0
                except TypeError, ValueError:
                    retry_after = 1.0
                if mode == "load":
                    return {
                        "idx": idx,
                        "status": 503,
                        "attempts": attempts,
                        "retry_after": retry_after,
                        "latency_http": time.monotonic() - t0,
                    }
                await asyncio.sleep(retry_after)
                continue
            return {
                "idx": idx,
                "status": r.status_code,
                "attempts": attempts,
                "latency_http": time.monotonic() - t0,
            }
        except Exception as e:  # noqa: BLE001
            if mode == "load":
                return {
                    "idx": idx,
                    "status": "err",
                    "attempts": attempts,
                    "error": str(e),
                    "latency_http": time.monotonic() - t0,
                }
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)


async def fetch_created_at(task_ids: list[str]) -> dict[str, float]:
    if not task_ids:
        return {}
    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch(
            "SELECT task_id, created_at FROM task_results WHERE task_id = ANY($1::varchar[])",
            task_ids,
        )
        return {r["task_id"]: r["created_at"].timestamp() for r in rows}
    finally:
        await conn.close()


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{MODE}_{int(time.time())}"
    ts_path = OUTPUT_DIR / f"metrics_{tag}.csv"
    summary_path = OUTPUT_DIR / f"summary_{tag}.csv"
    log.info(
        "MODE=%s N=%d QUEUE_MAX_LENGTH=%d WORKER=%s tag=%s",
        MODE,
        N_REQUESTS,
        QUEUE_MAX_LENGTH,
        WORKER_CONTAINER,
        tag,
    )

    async with httpx.AsyncClient() as c:
        q0 = await get_queue_depth(c)
        d0 = await get_dlq_depth(c)
    log.info("start: queue=%d dlq=%d", q0, d0)

    start = time.time()
    results: list[dict] = []
    sigterm_sent = False
    sigterm_at: float | None = None

    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(publish_one(client, i, MODE)) for i in range(N_REQUESTS)]

        with open(ts_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "ts",
                    "elapsed_s",
                    "queue_depth",
                    "dlq_depth",
                    "worker_mem_mb",
                    "publish_rate_1s",
                    "accepted",
                    "rejected_503",
                    "in_flight",
                ]
            )

            last_accepted = 0
            last_ts = time.monotonic()

            while not all(t.done() for t in tasks):
                elapsed = time.time() - start
                if MODE == "sigterm" and not sigterm_sent and elapsed >= SIGTERM_AT_SEC:
                    log.warning("SIGTERM → %s", WORKER_CONTAINER)
                    sigterm_at = time.time()
                    subprocess.run(
                        ["docker", "kill", "--signal=SIGTERM", WORKER_CONTAINER],
                        check=False,
                    )
                    sigterm_sent = True

                depth = await get_queue_depth(client)
                dlq = await get_dlq_depth(client)
                mem = get_container_memory(WORKER_CONTAINER)

                done = [t for t in tasks if t.done()]
                accepted_now = sum(1 for t in done if t.result().get("status") == 202)
                rejected_now = sum(1 for t in done if t.result().get("status") == 503)

                now = time.monotonic()
                dt = max(now - last_ts, 1e-6)
                rate = (accepted_now - last_accepted) / dt
                last_accepted = accepted_now
                last_ts = now

                w.writerow(
                    [
                        time.strftime("%H:%M:%S"),
                        round(elapsed, 2),
                        depth,
                        dlq,
                        round(mem, 1),
                        round(rate, 2),
                        accepted_now,
                        rejected_now,
                        len(tasks) - len(done),
                    ]
                )
                f.flush()

                log.info(
                    "t=%.1fs q=%d dlq=%d mem=%.0fMB rate=%.2f/s acc=%d rej=%d",
                    elapsed,
                    depth,
                    dlq,
                    mem,
                    rate,
                    accepted_now,
                    rejected_now,
                )
                await asyncio.sleep(SAMPLE_INTERVAL_SEC)

            results = await asyncio.gather(*tasks)

    elapsed_http = time.time() - start

    ok = [r for r in results if r.get("status") == 202]
    rej = [r for r in results if r.get("status") == 503]
    err = [r for r in results if r.get("status") == "err"]

    ok_ids = [r["task_id"] for r in ok if r.get("task_id")]

    # drain: ждём, пока воркеры РЕАЛЬНО не разберут принятые задачи из БД
    log.info("drain: ждём %d задач в БД (timeout=%.0fs)", len(ok_ids), DRAIN_TIMEOUT_SEC)
    deadline = time.time() + DRAIN_TIMEOUT_SEC
    while time.time() < deadline:
        created_db = await fetch_created_at(ok_ids)
        if len(created_db) >= len(ok_ids):
            log.info("drain ok: все %d задач записаны в БД", len(ok_ids))
            break
        log.info("drain: в БД %d/%d задач", len(created_db), len(ok_ids))
        await asyncio.sleep(2.0)

    elapsed_total = time.time() - start

    # Финальный пересчёт метрик (уже после drain)
    created = await fetch_created_at(ok_ids)
    id_to_pub = {r["task_id"]: r["t_publish"] for r in ok if r.get("task_id")}
    latencies = [created[tid] - id_to_pub[tid] for tid in id_to_pub if tid in created]

    async with httpx.AsyncClient() as c:
        q_final = await get_queue_depth(c)
        dlq_final = await get_dlq_depth(c)

    retry_after_vals = [r["retry_after"] for r in rej if "retry_after" in r]
    summary = {
        "mode": MODE,
        "tag": tag,
        "n_requests": N_REQUESTS,
        "queue_max_length": QUEUE_MAX_LENGTH,
        "worker_container": WORKER_CONTAINER,
        "elapsed_http_s": round(elapsed_http, 2),
        "elapsed_total_s": round(elapsed_total, 2),
        "accepted": len(ok),
        "rejected_503": len(rej),
        "errors": len(err),
        "completed_in_db": len(latencies),
        "lost": len(ok) - len(latencies),
        "dlq_final": dlq_final,
        "queue_final": q_final,
        "throughput_acc_per_s": round(len(ok) / elapsed_total, 3) if elapsed_total else 0,
        "latency_p50_s": round(percentile(latencies, 0.5), 3) if latencies else None,
        "latency_p95_s": round(percentile(latencies, 0.95), 3) if latencies else None,
        "latency_max_s": round(max(latencies), 3) if latencies else None,
        "retry_after_median": percentile(retry_after_vals, 0.5) if retry_after_vals else None,
        "retry_after_p95": percentile(retry_after_vals, 0.95) if retry_after_vals else None,
        "sigterm_at_s": round(sigterm_at - start, 2) if sigterm_at else None,
    }

    with open(summary_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        w.writeheader()
        w.writerow(summary)

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"timeseries: {ts_path}")
    print(f"summary:    {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
