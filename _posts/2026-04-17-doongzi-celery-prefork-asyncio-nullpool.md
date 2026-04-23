---
title: "[둥지] Celery prefork + async SQLAlchemy: NullPool을 선택한 이유"
date: 2026-04-17 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Celery, CeleryBeat, SQLAlchemy, AsyncIO, NullPool, Python, Troubleshooting, Backend]
toc: true
comments: true
description: "Celery Beat 태스크 안에서 asyncio.run()으로 async SQLAlchemy를 호출할 때 발생하는 'Future attached to a different loop' 에러의 원인을 분석하고, NullPool·스레드 격리·전용 동기 세션 세 가지 대안 중 NullPool을 선택한 의사결정 근거를 기록합니다."
---

[이전 글]({% post_url 2026-04-16-doongzi-celery-beat %})에서 Celery Beat로 stale 태스크를 자동 정리하는 구조를 도입했습니다. Beat 태스크 구현을 마치고 실제로 실행하자 곧바로 런타임 에러에 맞닥뜨렸습니다.

```
RuntimeError: Task got Future <Future pending> attached to a different loop
```

---

## Celery prefork와 asyncio의 충돌 구조

### Celery prefork 모델

Celery의 기본 실행 모델은 **prefork**입니다. 부모 프로세스가 워커 프로세스 N개를 미리 `fork()`해두고, 브로커에서 태스크 메시지가 도착하면 유휴 자식 프로세스 하나에 배분합니다. 자식 프로세스는 태스크를 처리한 뒤 **종료되지 않고 재사용**됩니다.

```
[부모 프로세스]
     │
     ├── [Worker-1] ← 태스크 A 처리 → 대기 → 태스크 D 처리 → ...
     ├── [Worker-2] ← 태스크 B 처리 → 대기 → ...
     └── [Worker-3] ← 태스크 C 처리 → 대기 → ...
```

프로세스를 재사용하기 때문에 새 프로세스를 `fork()`하는 비용 없이 빠르게 태스크를 처리할 수 있습니다.

### asyncio.run()의 이벤트 루프 생성 방식

`asyncio.run(coro)`는 호출될 때마다 **새 이벤트 루프를 생성하고 종료**합니다.

```python
asyncio.run(my_coro())  # loop-A 생성 → 실행 → loop-A 종료
asyncio.run(my_coro())  # loop-B 생성 → 실행 → loop-B 종료
```

동기 함수 안에서 async 코드를 실행하는 가장 간단한 방법이며, FastAPI 외부(CLI, Celery 태스크 등)에서 흔히 사용됩니다.

---

## 커넥션 풀과 이벤트 루프의 불일치 문제

### SQLAlchemy 커넥션 풀의 동작 원리

SQLAlchemy의 기본 풀은 **QueuePool**입니다. DB 커넥션을 미리 생성해 두고 재사용함으로써 매 쿼리마다 TCP 핸드셰이크와 DB 인증 비용을 절감합니다.

async 드라이버(asyncpg, aiomysql 등)로 생성된 커넥션은 생성 시점의 **이벤트 루프에 바인딩**됩니다. asyncio의 소켓 I/O는 루프 단위로 관리되는 `Transport` 객체를 통해 동작하기 때문입니다.

### 에러 발생 시나리오

Celery prefork 워커가 프로세스를 재사용하면서 다음 상황이 만들어집니다.

```
1회차 태스크 실행
  asyncio.run() → loop-A 생성
  engine.connect() → asyncpg 커넥션 C1 생성 → loop-A에 바인딩
  asyncio.run() 종료 → loop-A 파괴
  C1은 QueuePool에 반환되어 캐싱됨 (loop-A 참조 유지)

2회차 태스크 실행 (같은 워커 프로세스 재사용)
  asyncio.run() → loop-B 생성
  engine.connect() → QueuePool에서 C1 재사용 시도
  C1은 이미 파괴된 loop-A에 바인딩 → 충돌
  RuntimeError: Task got Future attached to a different loop
```

loop-A가 파괴된 뒤에도 QueuePool이 C1을 보유하고 있다는 점이 문제입니다. 풀은 루프의 생명주기를 알지 못하므로 C1이 유효한 커넥션이라고 판단합니다.

---

## 어떻게 해결하는가

### 대안 1: NullPool 사용 (채택)

`NullPool`은 커넥션을 **캐싱하지 않습니다**. `engine.connect()`가 호출될 때마다 새 커넥션을 생성하고, 컨텍스트 매니저가 종료되면 즉시 닫습니다. 따라서 루프 경계 문제 자체가 발생하지 않습니다.

Beat 태스크 안에서 엔진을 태스크 호출마다 새로 생성하여 루프와 엔진의 생명주기를 일치시킵니다.

```python
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

@celery_app.task(name="beat.cleanup_stale_tasks")
def cleanup_stale_tasks() -> dict:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession,
        autoflush=False, autocommit=False, expire_on_commit=False
    )
    try:
        return asyncio.run(_cleanup_stale_tasks_async(session_factory))
    finally:
        asyncio.run(engine.dispose())
```

**장점**
- 구현이 단순하고 변경 범위가 태스크 파일 하나로 한정됩니다.
- 루프 불일치 원인을 근본적으로 차단합니다.
- Beat 태스크는 수십 초~수 분 간격으로 실행되므로 커넥션 생성 오버헤드가 무시할 수준입니다.

**단점**
- 매 호출마다 TCP 핸드셰이크와 DB 인증이 발생합니다. 초당 수백 번 호출되는 hot path에는 적합하지 않습니다.

### 대안 2: 스레드 풀(run_in_executor) 격리

`loop.run_in_executor()`로 async 작업을 별도 스레드에서 실행하면 각 실행마다 독립된 이벤트 루프를 사용할 수 있습니다.

```python
import concurrent.futures

@celery_app.task(name="beat.cleanup_stale_tasks")
def cleanup_stale_tasks() -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _cleanup_stale_tasks_async(global_session_factory))
        return future.result()
```

**단점**
- 스레드와 이벤트 루프의 생명주기 관리가 복잡해집니다.
- 스레드 간 세션 공유 시 thread-safety 문제가 생길 수 있습니다.
- 보일러플레이트가 늘어나 가독성이 떨어집니다.

### 대안 3: 전용 동기(sync) 세션 사용

Beat 태스크에서만 psycopg2 기반 동기 SQLAlchemy 엔진을 별도로 구성합니다. asyncio를 아예 사용하지 않으므로 루프 문제 자체가 없습니다.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sync_engine = create_engine(str(settings.sync_database_url))
SyncSession = sessionmaker(bind=sync_engine)

@celery_app.task(name="beat.cleanup_stale_tasks")
def cleanup_stale_tasks() -> dict:
    with SyncSession() as session:
        return _cleanup_stale_tasks_sync(session)
```

**단점**
- `_cleanup_stale_tasks_async`를 동기 버전으로 재작성해야 합니다.
- 비즈니스 로직을 두 가지 버전으로 관리하게 되어 유지보수 부담이 증가합니다.
- DB URL과 드라이버 설정도 이중화됩니다.

---

## 최종 선택: NullPool

| 항목 | NullPool | 스레드 격리 | 동기 세션 |
|---|---|---|---|
| 구현 복잡도 | 낮음 | 높음 | 중간 |
| 변경 범위 | 태스크 파일만 | 태스크 파일 + 실행 래퍼 | 태스크 + DB 설정 + 비즈니스 로직 |
| 커넥션 오버헤드 | 매 호출 | 없음 | 없음 |
| 적용 범위 | 저빈도 Beat 태스크에 적합 | 고빈도 태스크 가능 | 동기 전용 태스크 |

Beat 태스크(`cleanup_stale_tasks`)는 수 분 간격으로 실행됩니다. 커넥션 생성 비용이 전체 실행 시간에서 차지하는 비율이 미미하고, 비즈니스 로직을 async 그대로 유지하면서 변경 범위를 최소화할 수 있어 NullPool을 선택했습니다.

