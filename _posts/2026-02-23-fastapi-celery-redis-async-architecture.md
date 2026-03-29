---
title: "[둥지] FastAPI + Celery + Redis: 비동기 백엔드 아키텍처와 최종 의사결정"
date: 2026-02-23 21:30:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Python, Celery, Redis, Asynchronous, Architecture, Backend]
toc: true
comments: true
image: /assets/img/posts/2026-02-23-fastapi-celery-redis-async-architecture/1.png
description: "AI 연산 및 스크래핑과 같이 오래 걸리는 작업을 비동기적으로 처리하기 위해 Celery와 Redis를 도입한 과정을 공유합니다. 트랜잭션 주체 분리, Polling 방식 채택, 그리고 Custom Task 패턴을 활용한 우아한 예외 처리까지 아키텍처 설계의 모든 것을 알아봅니다."
---

AI 모델 추론이나 외부 API 스크래핑처럼 처리 시간이 긴 작업을 웹 서버가 직접 수행하면, 서버가 응답을 기다리며 멈춰버리는 병목 현상(Blocking)이 발생합니다. '둥지' 프로젝트에서는 권리분석 AI와 등기부등본 자동 발급 로직이 필수적이기에, 이러한 문제를 해결하고 사용자 경험을 향상시키기 위해 **Celery와 Redis를 도입한 비동기 처리 아키텍처**를 구축했습니다.

이번 포스트에서는 Celery의 핵심 개념부터 시스템 데이터 흐름, 코드 중복을 줄이는 Custom Task 패턴, 그리고 최종 아키텍처를 확정하기까지의 의사결정 과정을 상세히 공유합니다.

---

## 1. Celery 핵심 개념 및 구성 요소

Celery는 Python에서 널리 사용되는 분산 작업 대기열(Distributed Task Queue) 시스템입니다. 긴 처리 시간이 필요한 작업을 백그라운드 프로세스로 넘겨, 웹 애플리케이션의 성능과 응답성을 획기적으로 향상시킵니다.

Celery 아키텍처를 이루는 4가지 기본 구성 요소는 다음과 같습니다.

- **Task**: 실행할 작업. 함수 형태로 정의됩니다.
- **Worker**: Task를 실행하는 프로세스. 여러 대의 서버에서 동시에 실행될 수 있습니다.
- **Broker**: Task 메시지를 보관하는 중앙 메시지 서버. Celery는 RabbitMQ, Redis 등 다양한 메시지 브로커를 지원합니다.
- **Backend**: Task의 결과를 저장하는 곳. 결과 저장 및 조회를 위해 사용됩니다.

## 2. 시스템 데이터 흐름 (Data Flow)

우리 프로젝트에서는 인프라 복잡도를 낮추기 위해 **Broker와 Backend로 모두 Redis를 사용**하며, 역할 구분을 위해 논리적 데이터베이스 번호(`DB 0`, `DB 1`)를 나누었습니다.

1. **FastAPI (Client):** 유저가 API를 호출하면 FastAPI는 `analyze_task.delay(doc_id)`를 실행하고 클라이언트에게 즉시 202 응답을 반환합니다. 이때 작업 지시서(Task 메시지)는 **Redis Broker (DB 0)**의 큐(Queue)에 쌓입니다. 클라이언트에게 즉시 `202 Accepted` 응답과 `Task ID`를 반환합니다.
2. **Celery Worker:** 백그라운드에서 대기 중이던 Worker 프로세스들이 Broker를 계속 주시하다가, 새로운 지시서가 들어오면 가져와서(Pull) 작업을 시작합니다.
3. **Redis Backend:** Worker가 작업을 끝내거나 실패하면, 그 최종 결과와 상태(SUCCESS/FAILURE)를 **Redis Backend (DB 1)**에 기록합니다.

## 3. Celery 설정 및 우아한 예외 처리 패턴

### ① Celery 애플리케이션 설정 (`celery_app.py`)

```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "doongzi",
    broker=settings.redis_broker_url,
    backend=settings.redis_backend_url,
    # Worker 시작 시 자동으로 discover할 태스크 모듈 목록
    include=["app.domains.checklist.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    # 태스크 상태 추적 (PENDING → STARTED → SUCCESS/FAILURE)
    task_track_started=True,
    # 결과 만료 시간: 1시간
    result_expires=3600,
    # 재시도 설정: 최대 3회, 60초 간격
    task_max_retries=3,
    task_default_retry_delay=60,
)
```

### ② Custom Base Task 패턴 (`tasks.py`) ⭐

이 아키텍처에서 가장 공을 들인 부분 중 하나입니다. 수많은 비동기 태스크마다 `try-except` 블록을 씌워 DB 실패 처리를 하는 대신, **Celery의 Task 기본 클래스를 상속받아 `on_failure` 훅(Hook)을 오버라이딩**했습니다.

```python
from celery import Task

class AnalysisTask(Task):
    """문서 분석 태스크의 기본 클래스 (공통 예외 처리 담당)"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # TODO: DB의 분석 상태 필드를 FAILED로 업데이트하는 로직
        # 예: db_session.query(Doc).filter_by(id=args[0]).update({"status": "FAILED"})
        pass
```

이 패턴을 사용하면 권리분석 AI, 등본 스크래핑 등 다양한 태스크를 생성할 때 `@celery_app.task(base=AnalysisTask)` 데코레이터 한 줄만 붙여주면 됩니다. 실패 시 DB 상태 변경 로직이 일괄적으로 적용되므로 코드 중복이 획기적으로 줄어들고 유지보수성이 극대화됩니다.

## 4. 최종 아키텍처 의사결정 및 시퀀스

프로젝트를 진행하며 가장 깊게 고민했던 세 가지 주요 아키텍처 설계 이슈와 최종 결론입니다.

### 1. 트랜잭션 및 상태 관리 주체 분리

처음에는 FastAPI가 작업 중간중간 상태를 체크하여 DB를 업데이트할지 고민했습니다. 하지만 API 서버의 부하를 최소화하기 위해 역할을 명확히 나누었습니다.

- **FastAPI**: 요청 접수 직후 DB에 레코드를 생성하고 상태를 `PENDING`으로 기록하는 **초기화**만 담당합니다.
- **Celery Worker**: 큐에서 작업을 꺼낸 시점(`STARTED`)부터 로직 수행 완료(`SUCCESS`), 혹은 에러 발생(`FAILED`)까지의 **모든 중간 상태 변경 로직을 전담**합니다.

### 2. 작업 상태 확인 방식 (Polling vs SSE)

비동기 작업의 결과를 클라이언트에게 어떻게 전달할 것인가에 대한 고민입니다.
실시간성이 뛰어난 SSE(Server-Sent Events)도 고려했으나, 서버의 연결 유지 리소스 부담과 아키텍처 복잡도를 낮추기 위해 **Polling(주기적 요청)** 방식을 채택했습니다. 클라이언트는 발급받은 `Task ID`로 FastAPI에 상태를 묻고, FastAPI는 `Redis Backend`의 Task 상태와 `PostgreSQL`의 상세 데이터를 조합해 응답합니다.

### 3. Worker 생존 모니터링 (Server-side Heartbeat)

백그라운드에서 조용히 도는 Worker가 죽었을 때 장애를 빠르게 감지하기 위한 안전장치를 마련했습니다.

- **Celery Beat**를 별도 컨테이너로 분리하여 1분마다 'Heartbeat 태스크'를 발행합니다.
- Worker가 이 태스크를 수행할 때마다 DB 시스템 테이블에 `last_heartbeat_at` 타임스탬프를 갱신합니다.
- 이를 통해 시스템이 Worker의 실시간 생존 여부를 완벽하게 파악할 수 있게 되었습니다.

### 최종 등기부등본 분석 시퀀스

위의 모든 의사결정이 반영된 최종 데이터 흐름입니다. 등기부등본 분석 요청 시 전체적인 비동기 작업 처리의 흐름은 다음과 같이 진행됩니다.

![등기부등본 분석 요청 시 데이터 흐름](/assets/img/posts/2026-02-23-fastapi-celery-redis-async-architecture/1.png)
*등기부등본 분석 요청 시 데이터 흐름*

1. **요청 및 접수:** 클라이언트가 FastAPI에 등기부등본 분석을 요청합니다.
2. **작업 발행:** FastAPI는 DB에 상태를 `PENDING`으로 기록한 뒤, Redis Broker에 태스크를 발행하고 클라이언트에게 즉시 Task ID를 반환합니다.
3. **작업 수행:** Celery Worker가 Broker에서 작업을 가져와 DB 상태를 `STARTED`로 업데이트합니다.
4. **외부 연동:** Worker가 외부 API(등본 스크래핑) 및 AI 모델을 순차적으로 호출하여 무거운 연산을 수행합니다.
5. **결과 기록:**
    - **성공 시:** 분석 결과를 DB에 매핑하고 상태를 `SUCCESS`로 업데이트합니다.
    - **실패 시:** `AnalysisTask.on_failure` 훅이 동작하여 DB에 실패 사유와 함께 상태를 `FAILED`로 기록합니다.
6. **최종 상태 저장:** Celery가 자동으로 Redis Backend에 최종 실행 결과를 저장합니다.
7. **클라이언트 폴링:** 클라이언트는 반환받은 Task ID를 이용해 FastAPI에 주기적으로 상태를 조회(Polling)하여 최종 결과를 받아봅니다.

---

### 레퍼런스

[박민규 장시간 비동기 작업, Kafka 대신 RDB 기반 Task Queue로 해결하기 - 우아한형제들 기술블로그](https://techblog.woowahan.com/23625/)

[날으는물고기 <º)))><:티스토리](https://blog.pages.kr/2890)
