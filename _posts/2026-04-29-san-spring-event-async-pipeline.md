---
title: "[SAN] 이벤트 기반 비동기 파이프라인: Spring Event"
date: 2026-04-29 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, Async, EventDriven, SpringEvent, Architecture, ThreadPool, Transactional, Polling, Backend]
toc: true
comments: true
description: "MVP 단계에서 Kafka 없이 Spring Event로 비동기 파이프라인을 구현한 이유를 정리합니다. 이벤트 기반 구조의 결합도 분리, @TransactionalEventListener AFTER_COMMIT 타이밍 문제, 스레드 풀 분리, Short Polling 선택까지 의사결정 과정을 기록합니다."
---

AI 요약과 벡터 임베딩 생성은 수 초가 걸리는 작업이라 동기 응답으로 처리할 수 없습니다. 비동기 파이프라인이 필요했고, 트리거 메커니즘으로 무엇을 선택할지 결정해야 했습니다.

---

## 외부 메시지 큐 대신 Spring Event

Kafka, RabbitMQ 같은 외부 메시지 큐는 장애 복구와 멀티 서버 분산 처리에 강점이 있지만, 별도 인프라 구성과 운영 비용이 따릅니다. MVP 단계에서 당장 필요한 것은 단일 서버 안에서 작업을 비동기로 위임하는 구조입니다.

| 방식 | 장점 | 단점 |
|---|---|---|
| Spring Event | 추가 의존성 없음, 발행자/수신자 분리 | 메모리 기반, 서버 재시작 시 소멸 |
| @Async 직접 호출 | 단순한 흐름 | Manager가 모든 Processor를 알아야 함 |
| DB 폴링 (Scheduler) | 장애 복구 가능 | 폴링 주기만큼 지연 |

Spring Event를 선택한 이유는 두 가지입니다. 

첫째, Kafka 없이도 발행자(`AsyncJobManager`)와 수신자(`Processor`) 결합도를 낮출 수 있습니다. 

둘째, JVM 내부에서 동작하므로 외부 인프라 의존성이 없습니다.

Python의 Redis + Celery와 개념적으로 동일한 구조이며, 차이는 큐가 외부(Redis)냐 JVM 내부 메모리냐의 차이입니다.

| Celery 개념 | Spring Event 대응 |
|---|---|
| `task.delay()` 호출 | `asyncJobManager.enqueue()` 호출 |
| Redis Queue (외부 저장소) | Spring 내부 이벤트 버스 (JVM 메모리) |
| 큐에 쌓인 태스크 메시지 | `JobCreatedEvent` 객체 |
| Celery Worker | `@EventListener` + `@Async` Processor |

---

## 발행자와 수신자를 분리하다

비동기 작업을 `@Async`로 직접 호출하면 `AsyncJobManager`가 모든 `Processor`를 알아야 합니다. 새로운 `JobType`이 생길 때마다 `AsyncJobManager` 코드를 직접 수정해야 합니다.

```
// 직접 호출 구조 (채택 안 함)
AsyncJobManager → CardAnalysisProcessor 직접 호출
AsyncJobManager → RecallProcessor 직접 호출
AsyncJobManager → TilProcessor 직접 호출
```

이벤트 기반 구조에서는 `AsyncJobManager`가 이벤트만 던지고 끝납니다. 누가 처리하는지 모릅니다.

```
// 이벤트 기반 구조 (채택)
AsyncJobManager → "JobCreatedEvent 발행" (나 몰라라)

CardAnalysisProcessor → "JobCreatedEvent 들을게요" (@EventListener)
RecallProcessor       → "JobCreatedEvent 들을게요" (@EventListener)
TilProcessor          → "JobCreatedEvent 들을게요" (@EventListener)
```

새로운 `JobType`이 생기면 새 `Processor`만 추가하면 되고, `AsyncJobManager`는 건드릴 필요가 없습니다.

---

## 파이프라인 실행 흐름

지식 카드 생성(`CARD_ANALYSIS`)을 기준으로 세 단계로 진행됩니다.

**1단계: 동기 응답 (메인 스레드)**

사용자가 스크랩을 요청하면 메인 스레드는 원본 데이터를 `scraps` 테이블에 저장하고, `async_jobs`에 `PENDING` 상태로 작업을 생성합니다. 즉시 `200 OK`와 `job_id`를 반환해 사용자 대기를 풀고, 내부적으로 `JobCreatedEvent`를 발행합니다.

**2단계: 비동기 처리 (워커 스레드)**

`@TransactionalEventListener`가 커밋 후 이벤트를 감지하면 `@Async` 스레드 풀에서 워커 스레드가 실행됩니다. 작업을 집어 들 때 상태를 `PROCESSING`으로 변경한 뒤, AI 서버(FastAPI)에 원문을 보내 요약·태그·벡터 임베딩을 요청합니다. 응답을 받아 `knowledge_cards`에 적재하면 `COMPLETED`로 전환하고 종료합니다. 예외가 발생하면 `FAILED`로 기록합니다.

**3단계: 상태 확인 (클라이언트 폴링)**

프론트엔드는 받은 `job_id`로 `GET /api/jobs/{jobId}`를 1~2초 주기로 호출해 완료 여부를 확인합니다.

### 상태 변경은 누가 담당하지?

상태 변경 주체를 정리하면 다음과 같습니다.

| 상태 | 변경 주체 | 시점 |
|------|----------|------|
| `PENDING` | 메인 스레드 | 작업 생성 시 (기본값) |
| `PROCESSING` | 비동기 워커 스레드 | AI 요청 직전 |
| `COMPLETED` | 비동기 워커 스레드 | DB 적재 완료 후 |
| `FAILED` | 비동기 워커 스레드 | 예외 발생 시 |

```java
// [메인 스레드] ScrapService.java
@Transactional
public ScrapResponse createScrap(ScrapRequest request) {
    Scrap scrap = scrapRepository.save(new Scrap(request));

    AsyncJob job = AsyncJob.builder()
            .jobType(JobType.CARD_ANALYSIS)
            .targetId(scrap.getId())
            .build(); // 기본값 PENDING
    asyncJobRepository.save(job);

    eventPublisher.publishEvent(new JobCreatedEvent(job.getId()));
    return new ScrapResponse(scrap.getId(), job.getId());
}

// [비동기 워커 스레드] CardAnalysisProcessor.java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void handleCardAnalysis(JobCreatedEvent event) {
    AsyncJob job = asyncJobRepository.findById(event.getJobId()).orElseThrow();

    try {
        job.markAsProcessing();
        asyncJobRepository.saveAndFlush(job);

        aiClient.analyze(job.getTargetId());

        job.markAsCompleted();
    } catch (Exception e) {
        String message = e.getMessage();
        if (message != null && message.length() > 1000) {
            message = message.substring(0, 1000) + "...";
        }
        job.markAsFailed(message);
        log.error("[AsyncJob Failed] JobId: {}, Reason: {}", job.getId(), e.getMessage(), e);
    } finally {
        asyncJobRepository.save(job);
    }
}
```

---

## 이벤트 발행

### @TransactionalEventListener AFTER_COMMIT: 타이밍 문제

`@EventListener`를 사용하면 이벤트가 즉시 발행됩니다. 이때 `AsyncJobManager.enqueue()`의 트랜잭션이 아직 커밋되기 전이라면, `Processor`가 이벤트를 받아 `asyncJobRepository.findById(jobId)`를 조회했을 때 DB에서 해당 잡을 찾지 못하는 경우가 생길 수 있습니다.

`@TransactionalEventListener(phase = AFTER_COMMIT)`을 사용하면 트랜잭션 커밋이 완전히 끝난 뒤에 이벤트가 전달됩니다.

워커 트랜잭션에 `Propagation.REQUIRES_NEW`를 사용하는 이유도 같은 맥락입니다. 같은 트랜잭션 안에서 실행되면 `PROCESSING` 상태 변경이 메인 커밋 전까지 DB에 반영되지 않아 폴링 시 정합성 문제가 생깁니다.

### enqueue()에 @Transactional이 필요한 이유

`AsyncJobManager.enqueue()`에서 `@Transactional`이 없으면, `save()`가 성공했는데 `publishEvent()`에서 예외가 발생할 경우 DB에 `PENDING` 잡이 남아있지만 이벤트는 발행되지 않은 상태가 됩니다. 아무도 처리하지 않는 유령 잡이 생성됩니다.

`@Transactional`이 있으면 `save()`와 `publishEvent()`가 하나의 트랜잭션으로 묶여, `publishEvent()`에서 예외가 터지면 `save()`도 함께 롤백됩니다.

단, DB 자체가 다운된 경우는 `@Transactional`이 해결하는 문제가 아닙니다. 이는 인프라 레벨(헬스체크, 재시작 정책)에서 대응합니다.

### 중복 요청 방지는 enqueue() 내부에서

버튼 연타 등 동일 작업이 중복 실행되는 것을 막아야 합니다. 도메인 서비스마다 체크 코드를 작성하면 하나라도 빠뜨리면 버그가 됩니다. 중복 방지는 "비동기 잡 생성 규칙"이므로 `enqueue()` 내부에서 처리해 어디서 호출하든 보장합니다.

```
enqueue(CARD_ANALYSIS, cardId) 호출
→ targetId + jobType 조합으로 PENDING/PROCESSING 잡 조회
→ 있으면 409 DUPLICATE_RESOURCE 예외
→ 없으면 새 잡 생성
```

---

## 스레드 풀 분리: Tomcat과 asyncJobExecutor

Spring은 기본적으로 HTTP 요청 하나당 Tomcat 스레드 하나를 배정합니다. AI 분석 작업을 Tomcat 스레드에서 직접 처리하면, 동시 요청이 몰릴 때 새 요청 자체를 받지 못하게 됩니다.

```
// 분리 안 했을 때
사용자 1000명 동시 요청
→ Tomcat 스레드 200개가 전부 AI 분석 중 (10초씩)
→ 새 요청 자체를 못 받음 → 서버 다운

// 분리 했을 때
사용자 1000명 동시 요청
→ Tomcat 스레드 200개가 요청 받고 "접수됐습니다" 즉시 응답 후 반납
→ AI 분석은 asyncJobExecutor 10개가 순서대로 백그라운드 처리
→ Tomcat 스레드는 계속 새 요청을 받을 수 있음
```

AI 분석이 오래 걸리는 건 변하지 않습니다. 핵심은 사용자가 HTTP 연결을 붙잡고 기다리느냐, 끊고 나중에 결과를 확인하러 오느냐의 차이입니다.

스레드 풀은 `@Bean`으로 등록해 애플리케이션 전체에서 하나만 생성합니다. 각 서비스에서 `new`로 생성하면 풀이 여러 개가 되어 `core=2, max=10` 설정값이 의미 없어집니다.

---

## 상태 조회: Short Polling

완료 여부를 클라이언트에 전달하는 방법으로 Short Polling, SSE, WebSocket을 검토했습니다.

| 방식 | 장점 | 단점 |
|---|---|---|
| Short Polling | 구현 단순, 무상태 | 불필요한 요청 발생 |
| SSE | 실시간, 단방향으로 충분 | 연결 유지 비용, 스케일아웃 시 복잡 |
| WebSocket | 완전 실시간 | 구현 복잡, 단방향에 과함 |

데이터 전처리 작업이 3초 내외 소요됩니다. 3초짜리 작업에 연결 유지 비용을 쓰는 건 과하므로 Polling으로 충분합니다.

```
클라이언트: enqueue 요청 → jobId 받음
클라이언트: GET /api/async-jobs/{jobId} 1~2초마다 폴링
서버:       { jobId, jobType, status, errorMessage } 반환
클라이언트: status == COMPLETED 이면 폴링 중단
```

---

## 향후 Redis 확장 경로

현재는 JVM 내부 이벤트 버스를 사용합니다. 서버 재시작 시 처리 중인 잡이 소멸하고, 멀티 서버 환경에서는 다른 인스턴스에 이벤트를 전달할 수 없습니다.

비동기 파이프라인이 확장되면 Redis Stream/List 기반 외부 메시지 큐로 교체할 수 있습니다.

```
[현재]
AsyncJobManager → [JVM 메모리 이벤트 버스] → Processor

[확장 후]
AsyncJobManager → [Redis List/Stream] → Processor (Consumer)
```

교체 시 `AsyncJobManager`의 enqueue 방식, `Processor`의 이벤트 수신 방식이 변경되지만, `AsyncJobProcessor` 인터페이스 규격은 유지할 수 있어 변경 범위를 최소화할 수 있습니다.
