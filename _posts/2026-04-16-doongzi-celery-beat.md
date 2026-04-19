---
title: "[둥지] Celery Beat 도입기: 워커 크래시로 고착된 태스크를 자동으로 정리하기"
date: 2026-04-16 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Celery, CeleryBeat, Redis, Architecture, AsyncTask, Backend, Worker]
toc: true
comments: true
description: "워커 크래시/오프라인으로 PENDING·PROCESSING에 고착된 Celery 태스크를 자동으로 FAILED로 정리하기 위해 Celery Beat를 도입한 과정을 정리합니다. 워커 생존 감지 방법(Redis TTL vs PostgreSQL)과 stale 판정 기준을 중심으로 의사결정 근거를 기록합니다."
---

[이전 글]({% post_url 2026-04-13-doongzi-issuance-status-sync %})에서 문서 발급 상태 동기화 문제를 세 단계로 나눠 해결하기로 했습니다. Phase 2(프론트 폴링)와 Phase 3(`pending_since` 필드)로 워커가 정상일 때의 무한 스피너는 해결됐습니다. 남은 것은 Phase 4 — **워커가 오프라인이거나 크래시했을 때 고착된 태스크를 자동으로 FAILED로 정리하는 것**입니다.

---

## 워커가 죽으면 태스크가 영원히 고착된다

issuance-worker는 Windows 노트북에서 돌아가는 브라우저 자동화 워커입니다. 노트북이 꺼지거나 프로세스가 죽으면 `issuance` 큐를 소비할 주체가 없어 태스크는 `PENDING`이나 `PROCESSING`에 그대로 남습니다.

```
워커가 PROCESSING 중 크래시
  → IssuanceTask: status=PROCESSING 고착
  → 프론트 폴링: PROCESSING 계속 반환 → 스피너 무한 표시
  → 재발급 버튼 없음
```

Phase 2의 폴링 타임아웃(3분)은 "모달이 열려 있는 동안 응답이 없으면 재발급 버튼을 표시"하는 클라이언트 측 방어막입니다. 모달을 닫으면 타이머가 초기화되고, 모달을 다시 열기 전까지는 FAILED로 전환되지 않습니다. Phase 3의 `pending_since`로 서버 경과 시간을 가져와도 DB 상태가 `PROCESSING`이면 재발급 버튼 조건 자체가 충족되지 않습니다.

서버에서 고착 태스크를 직접 `FAILED`로 바꿔줘야 합니다. 그 역할을 **Celery Beat**에 맡기기로 했습니다.

---

## 1. Beat는 어느 서비스에 두는가

Celery Beat를 어느 서비스에서 실행할지부터 결정해야 했습니다.

| 후보 | 장점 | 단점 |
|------|------|------|
| backend | 항상 EC2에서 실행 중, DB 직접 접근 가능 | 없음 |
| issuance-worker | 태스크와 같은 프로세스 | Windows 노트북 → 항상 가동 보장 불가 |
| ocr-worker | — | 마찬가지로 로컬 노트북 |

Beat는 **항상 켜져 있어야** stale 정리 효과가 있습니다. issuance-worker나 ocr-worker는 바로 그 워커가 죽었을 때를 처리해야 하는데, 같은 프로세스에 Beat가 있으면 워커가 죽는 순간 Beat도 함께 죽습니다.

**결정: Beat는 backend 서비스에서만 구현한다.** issuance-worker와 ocr-worker는 태스크 실행 전용으로 유지한다.

---

## 2. stale 판정 기준을 어떻게 잡는가

### PENDING 타임아웃

기존 코드에 `_is_stale_pending_task`가 이미 있었습니다. 이 함수는 다음 발급 요청이 들어올 때 호출되어 직전 PENDING 태스크를 정리하는 용도였는데, Beat 없이 트리거 조건이 "발급 재요청"에만 의존하는 게 문제였습니다.

기준값(5분)은 그대로 유지했습니다. 태스크가 큐에 적재된 뒤 5분 안에 워커가 소비하지 못한다면 워커가 없다고 보는 것이 합리적입니다.

### PROCESSING 타임아웃

PROCESSING이 얼마나 걸리는지를 먼저 측정했습니다.

issuance-worker의 `issue_registry_task`는 내부적으로 IROS 메인페이지 로드 실패 시 최대 3회 재시도합니다. 회당 소요 시간(자동화 + 대기)이 최대 약 5–6분이므로, 최악의 경우 15–18분입니다. 여기에 여유를 더해 **20분**을 기준으로 잡았습니다.

10분으로 잡으면 정상 진행 중인 태스크를 잘못 FAILED로 처리할 수 있습니다.

| 상태 | 타임아웃 | 근거 |
|------|---------|------|
| `PENDING` | 5분 | 기존 기준 유지 |
| `PROCESSING` | 20분 | IROS 재시도 3회 포함 최대 소요 시간 고려 |

---

## 3. 워커 생존 여부를 어떻게 감지하는가

PROCESSING 타임아웃만으로도 고착 태스크를 처리할 수 있지만, 워커가 죽었다는 것을 **즉시** 감지할 수 있다면 20분을 기다리지 않아도 됩니다.

두 가지 방법을 검토했습니다.

### 방안 A: PostgreSQL worker_status 테이블

```sql
CREATE TABLE worker_status (
    worker_id     VARCHAR PRIMARY KEY,
    last_heartbeat_at TIMESTAMP,
    current_task_id   UUID,
    status        VARCHAR  -- 'busy' | 'idle'
);
```

워커가 주기적으로 이 테이블에 자신의 상태를 upsert합니다. Beat는 `last_heartbeat_at`이 N분 초과한 워커를 죽은 것으로 판정하고, 그 워커의 `current_task_id`를 FAILED 처리합니다.

**단점:**
- heartbeat마다 DB write 발생
- TTL이 없어서 Beat의 stale 판정 로직이 여전히 필요
- 테이블 추가, 마이그레이션 필요
- 히스토리가 쌓이면 별도 정리 필요

### 방안 B: Redis TTL 기반 키 (채택)

```
SETEX worker:{worker_id} 90 {json}
```

워커가 30초마다 이 키를 갱신합니다. TTL(90초 = 주기 × 3)이 만료되면 키가 자동으로 소멸합니다. Beat는 키 존재 여부만 확인하면 됩니다.

```
키 없음 → 워커 사망
키 있음 → 워커 생존
```

**장점:**
- 워커가 죽으면 cleanup 없이 TTL 만료로 자동 감지
- heartbeat write가 DB 대신 Redis (훨씬 경량)
- 히스토리 불필요 → 별도 정리 로직 없음
- 기존 ElastiCache(DB 2) 재사용 → 인프라 추가 없음

### 두 가지 방안 비교

| 항목 | Redis TTL | PostgreSQL 테이블 |
|------|-----------|------------------|
| 워커 사망 감지 | TTL 만료로 자동 | beat가 직접 stale 판정 필요 |
| 히스토리 | 없음 | 가능 |
| heartbeat 부하 | Redis write (경량) | DB write |
| 인프라 추가 | 없음 | 테이블 + 마이그레이션 |

**결정: Redis TTL 방식 채택.** 
생존/사망의 이분 판단에 히스토리가 필요 없고, 기존 Redis 인프라를 그대로 활용할 수 있습니다.

### Redis 키 구조

```
worker:{worker_id}
TTL: 90초 (heartbeat 주기 30초 × 3)

값(JSON):
{
  "worker_id": "issuance-worker-laptop-01",
  "last_heartbeat_at": "2026-04-15T10:00:00Z",
  "current_task_id": "uuid-...",   // 없으면 null
  "status": "busy" | "idle"
}
```

`worker_id`는 환경변수(`WORKER_ID`)로 주입합니다. 같은 노트북에서 워커를 여러 개 띄우는 경우가 없으므로 hostname 기반으로도 무방합니다.

---

## 4. Redis TTL과 타임아웃을 함께 쓰는 이유

Redis heartbeat로 워커 사망을 감지할 수 있다면, 타임아웃(PENDING 5분, PROCESSING 20분)이 왜 여전히 필요한지 의문이 생깁니다.

커버하는 장애 시나리오가 다릅니다.

| 상황 | Redis TTL | 타임아웃 |
|------|-----------|---------|
| 워커가 죽음 | 키 만료로 감지 가능 | 함께 커버됨 |
| 워커 생존 + 큐 적체 (PENDING 고착) | 키 존재 → 감지 불가 | PENDING 5분 초과 → FAILED |
| 워커 생존 + 태스크 내부 hang (Selenium 무한 대기 등) | 키 존재 → 감지 불가 | PROCESSING 20분 초과 → FAILED |

워커가 살아있어도 태스크가 고착될 수 있습니다. 큐 적체나 Selenium hang은 Redis TTL로는 감지할 수 없습니다. 두 메커니즘은 서로 다른 장애를 막는 방어막이므로 병존합니다.

---

## 5. IssuanceTask에 worker_id 컬럼이 필요한 이유

Beat가 PROCESSING 태스크를 발견했을 때 Redis에서 워커 생존 여부를 확인하려면 "이 태스크를 처리하는 워커가 누구인가"를 알아야 합니다.

현재 IssuanceTask에는 워커 ID가 없습니다. 따라서 Beat는 태스크별로 워커를 특정할 수 없어 Redis 확인을 건너뛰고 타임아웃만으로 판정할 수밖에 없습니다.

`worker_id` 컬럼을 IssuanceTask에 추가하고, issuance-worker가 태스크를 `PROCESSING`으로 전환할 때 자신의 ID를 기록하면 Beat가 정확히 해당 워커의 Redis 키를 조회할 수 있습니다.

```python
# IssuanceTask 모델
worker_id: Mapped[str | None] = mapped_column(String, nullable=True)
```

nullable로 정의한 이유는 구버전 태스크나 컬럼 추가 이전 기록에 대한 하위 호환입니다. `worker_id`가 없으면 Redis 확인을 건너뛰고 타임아웃만 적용합니다.

---

## 전체 동작 흐름

```
[issuance-worker 자체 백그라운드 스레드]
  └─ 30초마다 SETEX worker:{worker_id} 90 {json}

[backend celery-beat — 5분 주기]
  └─ DB: PENDING/PROCESSING 태스크 목록 조회
  └─ PENDING 5분 초과 → FAILED (error_code=TIMEOUT)
  └─ PROCESSING 태스크:
       └─ worker_id로 Redis 키 조회
            └─ 키 없음 (TTL 만료, 워커 사망) → 즉시 FAILED
            └─ 키 있음, 20분 초과 → FAILED (hang)
            └─ 키 있음, 20분 미만 → 정상 진행 중, 대기
  └─ DB 상태 FAILED로 변경

[프론트 폴링 — 5초 간격]
  └─ FAILED 감지 → 재발급 버튼 표시
```

---

## 구현 내용

### ① `_is_stale_processing_task`

```python
PROCESSING_TASK_TIMEOUT = timedelta(minutes=20)

def _is_stale_processing_task(
    task: IssuanceTask,
    now: datetime,
    redis_client: SyncRedis,
) -> bool:
    if task.status != TaskStatusEnum.PROCESSING:
        return False

    if task.worker_id:
        worker_alive = redis_client.exists(f"worker:{task.worker_id}")
        if not worker_alive:
            return True  # 워커 사망 → 즉시 stale

    updated_at = task.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return now - updated_at >= PROCESSING_TASK_TIMEOUT
```

워커 사망이 확인되면 20분을 기다리지 않고 즉시 stale로 판정합니다. `worker_id`가 없는 경우(구버전 태스크)에는 타임아웃만 적용합니다.

### ② `cleanup_stale_tasks` Celery 태스크

backend는 비동기 SQLAlchemy(`asyncpg`)를 사용합니다. Celery 태스크는 동기 컨텍스트에서 실행되므로 `asyncio.run()`으로 비동기 함수를 호출합니다.

```python
@celery_app.task(name="issuance.cleanup_stale_tasks")
def cleanup_stale_tasks():
    redis_client = get_cache_sync_client()  # cache DB 2
    return asyncio.run(_cleanup_stale_tasks_async(redis_client))

async def _cleanup_stale_tasks_async(redis_client: SyncRedis):
    now = datetime.now(timezone.utc)
    stale = []

    async with get_async_session() as session:
        result = await session.execute(
            select(IssuanceTask).where(
                IssuanceTask.status.in_([
                    TaskStatusEnum.PENDING,
                    TaskStatusEnum.PROCESSING,
                ])
            )
        )
        candidates = result.scalars().all()

        for task in candidates:
            if _is_stale_pending_task(task, now) or \
               _is_stale_processing_task(task, now, redis_client):
                task.status = TaskStatusEnum.FAILED
                task.error_code = IssuanceErrorCodeEnum.TIMEOUT
                stale.append(str(task.id))

        await session.commit()

    return {"cleaned": stale}
```

### ③ beat_schedule 등록

```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "cleanup-stale-issuance-tasks": {
        "task": "issuance.cleanup_stale_tasks",
        "schedule": crontab(minute="*/5"),
    },
}
```

### ④ beat 프로세스 분리

```yaml
celery-beat:
  build: ./backend
  command: celery -A app.core.celery_app beat --loglevel=info
  env_file: ./backend/.env
  depends_on:
    - redis
  restart: unless-stopped
```

worker와 beat는 **별도 컨테이너**로 분리합니다. 동일 프로세스에서 `--beat` 플래그를 함께 쓰는 방식은 프로덕션 환경에서 권장되지 않습니다. 스케줄 엔트리가 중복 실행될 수 있고, 워커가 죽으면 Beat도 같이 죽어 스케줄 자체가 멈춥니다.

---

## 마치며

Celery Beat 도입에서 가장 많이 고민한 지점은 두 가지였습니다.

첫째, **워커 생존 감지 방법**. PostgreSQL 테이블도 충분히 동작하지만, "워커가 살았는가 죽었는가"라는 이분 판단에 히스토리가 필요하지 않습니다. Redis TTL은 만료 자체가 사망 신호라는 점에서 의미상으로도 정확하고, 추가 정리 로직이 필요 없어 구현이 단순합니다.

둘째, **Redis TTL과 타임아웃 병존**. 워커가 살아있어도 태스크가 고착될 수 있는 시나리오(큐 적체, 내부 hang)가 있어서 타임아웃을 제거할 수 없었습니다. 두 메커니즘은 커버하는 장애가 달라서 중복이 아니라 보완 관계입니다.

Phase 2·3으로 워커가 정상일 때 폴링이 작동하고, Phase 4로 워커가 죽었을 때도 자동 복구 경로가 생겼습니다. 세 방어막이 갖춰지면 무한 스피너는 더 이상 발생하지 않습니다.
