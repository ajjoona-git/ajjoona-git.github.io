---
title: "[SAN] 비동기 작업 재시도: HTTP 레벨과 잡 레벨 이중 방어"
date: 2026-05-20 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, SpringRetry, AOP, AsyncJob, RestClient, Recover, Scheduler, Architecture]
toc: true
comments: true
description: "비동기 작업 재시도를 두 계층으로 나눠 구현합니다. HTTP 레벨은 @Retryable로 즉각 대응하고, 잡 레벨은 배치 스케줄러로 FAILED 상태 잡을 주기적으로 복구합니다."
---

비동기 작업(`async_jobs`)의 재시도 전략을 두 계층으로 분리했습니다.

- **HTTP 레벨**: `@Retryable`로 외부 HTTP 호출 직후 즉각 재시도 — 일시적 네트워크 오류 대응
- **잡 레벨**: 배치 스케줄러로 `FAILED` 상태 잡을 주기적으로 재enqueue — HTTP 재시도를 소진한 잡 복구

기존에는 HTTP 재시도 3회 소진 시 잡이 `FAILED`로 굳어버리고 명시적인 복구 경로가 없었습니다.

---

## HTTP 레벨 재시도 — Spring Retry

### 왜 Spring Retry인가

재시도 로직을 직접 작성하면 각 클라이언트 메서드마다 반복 코드가 생기고, 백오프·복구 로직이 비즈니스 코드에 섞입니다. Spring Retry의 `@Retryable`은 AOP로 분리하므로 클라이언트 코드는 본래 역할(HTTP 호출)만 유지합니다.

### 재시도 파라미터 결정

| 항목 | 값 | 근거 |
|---|---|---|
| 최대 시도 횟수 | 3 | 일시 장애 기준. 그 이상은 잡 레벨에서 담당 |
| 백오프 초기 대기 | 2s | 과부하 방지. 너무 짧으면 장애 서버에 부하 가중 |
| 백오프 배수 | 2.0 (지수) | 2s → 4s. 선형보다 장애 서버 회복 시간 확보에 유리 |
| 재시도 대상 | `RestClientException` | HTTP/네트워크 계층 오류 포괄. `IOException`은 이미 하위 포함 |
| 재시도 제외 | `BusinessException`, `HttpClientErrorException` | 응답 검증 실패·4xx는 재시도로 해결 안 됨 |

### @Retryable 적용 위치

Processor 내부가 아니라 **외부 클라이언트 빈의 퍼블릭 메서드**에 붙였습니다. 두 가지 이유입니다.

첫째, `@Retryable`은 AOP 프록시 기반이라 같은 빈 내부 `this.method()` 호출에는 동작하지 않습니다. 별도 빈으로 분리해야 프록시를 통해 재시도가 적용됩니다.

둘째, 외부 호출 실패는 Processor의 상태 전이 로직과 관심사가 다릅니다. 클라이언트 빈에 재시도를 두면 Processor(`handle`, `process`)는 변경 없이 재사용됩니다.

```
handle(JobCreatedEvent)
  └── process(jobId, targetId)        ← 상태 전이 담당 (변경 없음)
       └── ExternalClient.call()      ← @Retryable 적용 위치
```

### @Recover 처리 방식

재시도 소진 후 `@Recover`가 호출됩니다. 여기서 두 경우를 구분합니다.

- `BusinessException`: 응답 검증 실패 등 재시도로 해결되지 않는 오류 → 그대로 re-throw
- 그 외 네트워크 오류: 도메인 예외(`BusinessException`)로 변환 → 상위 `process()`의 catch → `markFailed()`

`@Recover`를 생략하면 Spring Retry가 마지막 예외를 그대로 던져 상위로 전파됩니다. 명시적으로 구현해 네트워크 오류를 도메인 예외로 변환하고 로그를 남깁니다.

### GitHub PUT 멱등성

AI 서버 호출(`/ai/analyze`, `/ai/til`)은 무상태 생성 요청이라 재시도해도 안전합니다.

GitHub `/repos/.../contents` PUT은 동일 경로 재요청 시 409 Conflict가 발생할 수 있습니다. `noRetryFor = {HttpClientErrorException.class}`로 4xx 전체를 재시도에서 제외해 반복 실패를 막았습니다.

---

## 잡 레벨 재시도 — FAILED 잡 배치 복구

### 두 계층을 나눈 이유

HTTP 레벨 재시도는 호출 직후 빠르게 처리하지만, 장애가 길게 지속되면 3회 모두 소진됩니다. 이때 잡이 영구 `FAILED`로 남으면 사용자 데이터 처리가 누락됩니다.

잡 레벨 재시도는 주기가 길고(2시간) 외부 서비스가 회복된 후 재처리합니다. 두 계층의 역할이 다릅니다.

- HTTP 레벨: 일시적 순간 오류 즉각 흡수
- 잡 레벨: 장시간 장애 후 복구

### 기존 GhostJobRecoveryService와의 구분

기존 `GhostJobRecoveryService`는 PENDING/PROCESSING 상태로 멈춘 잡(워커 사망 등)을 FAILED 처리 후 새 잡을 enqueue합니다. 이번 `FailedJobRecoveryService`는 이미 FAILED로 전환된 잡을 대상으로 합니다. 복구 대상 상태가 다릅니다.

### 재시도 파라미터 결정

| 항목 | 값 | 근거 |
|---|---|---|
| 최대 재시도 횟수 | 3회 | HTTP 레벨과 동일 기준. 그 이상은 요청 자체 문제로 판단 |
| 스케줄 주기 | 2시간 | 기존 `runRecovery()` 주기에 맞춤. 별도 주기 관리 부담 없음 |

### FAILED 잡 처리 방식

기존 FAILED 잡을 수정하지 않고, 동일 `(jobType, targetId)`로 **새 잡을 enqueue**합니다. 원인 추적을 위해 기존 FAILED 잡 이력은 유지합니다.

동일 `(targetId, jobType)`의 FAILED 잡 개수가 `MAX_RETRY_COUNT` 이상이면 skip합니다. 이 카운트가 재시도 횟수 판단의 기준입니다.

### RecallQuiz 자동 생성을 함께 추가한 이유

TIL 자동 생성 배치(`runTilAutoGeneration`)가 실행되는 시점에 퀴즈 생성도 함께 트리거하는 것이 자연스럽습니다. 별도 스케줄을 추가하는 대신 기존 배치 흐름에 연결했습니다.

퀴즈가 이미 있는 사용자는 skip하므로 중복 생성되지 않습니다(`enqueueIfAbsent` 패턴).

### TIL_GITHUB_COMMIT 멱등성 재고

HTTP 레벨에서는 4xx를 `noRetryFor`로 차단했지만, 잡 레벨 재시도에서는 새 잡이 실행될 때 GitHub PUT이 다시 409를 낼 수 있습니다. 409 → `BusinessException` → FAILED 재전환이 반복될 수 있습니다.

`MAX_RETRY_COUNT` 초과 시 재시도를 중단하는 것으로 억제합니다. GitHub 커밋이 이미 성공한 케이스라면 FAILED가 아닌 COMPLETED 상태일 것이므로, 실질적으로 반복에 걸리는 케이스는 제한적입니다.
