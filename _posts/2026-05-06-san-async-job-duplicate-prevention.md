---
title: "[SAN] async_jobs 중복 방지 설계"
date: 2026-05-06 09:00:00 +0900
categories: [Project, SAN]
tags: [Spring, AsyncJob, RaceCondition, PostgreSQL, UniqueIndex, Concurrency, Design]
toc: true
comments: true
description: "READ COMMITTED 환경에서 비동기 작업 중복 등록을 막기 위해 daily_summaries row lock을 사용했던 방식의 한계를 분석하고, async_jobs 테이블 자체의 부분 유니크 인덱스로 전환한 과정을 정리합니다."
---

TIL 생성 요청이 빠르게 중복으로 들어왔을 때, 비동기 작업이 두 번 등록되는 경합 조건이 있었습니다. 원인을 파악하고 두 가지 해결책을 검토한 끝에, 중복 방지 책임을 `async_jobs` 테이블 자체에 두는 방식으로 정착한 과정을 정리합니다.

## 서비스 구조

```
TilService                      ← 진입점 (API 레이어와 직접 대화)
  ├──▶ DailySummaryService      ← DailySummary 행 생명주기 관리
  └──▶ AsyncJobManager.enqueue()
            │ (트랜잭션 커밋 후 이벤트 발행)
            ▼
TilGenerationJobProcessor       ← 비동기 작업 처리기 (@Async + @TransactionalEventListener)
  ├──▶ DailySummaryService.getSummary()
  └──▶ TilGenerationService.generate()
            └──▶ TilSourceService.getSource()
```

| 서비스 | 역할 |
|---|---|
| `TilService` | HTTP 요청 진입점, 작업 등록 + 조회 |
| `DailySummaryService` | `daily_summaries` 행 생명주기 (생성/조회/결과 저장) |
| `TilGenerationJobProcessor` | 비동기 이벤트 수신 → 작업 실행 조율 |
| `TilGenerationService` | AI 서버 호출 오케스트레이션 |
| `TilSourceService` | AI 입력용 지식 원본 구성 |

---

## 경합 조건 발생 원인

PostgreSQL 기본 격리 수준(READ COMMITTED)에서는 커밋되지 않은 행이 다른 트랜잭션에 보이지 않습니다.

```
[요청 A 트랜잭션]                    [요청 B 트랜잭션]
getOrCreateSummary()
enqueue() → 중복 체크 (없음)
  save(PENDING) ─────────────────▶ enqueue() → 중복 체크
                                         READ COMMITTED이므로
                                         A의 미커밋 PENDING 안 보임
                                         → 중복 등록 (버그)
commit
```

`existsByTargetIdAndJobTypeAndStatusIn`은 커밋된 행만 읽으므로, A가 커밋하기 전에 B가 체크하면 PENDING 잡이 보이지 않아 중복 등록됩니다.

---

## 해결: daily_summaries FOR UPDATE

`enqueue()` 직전에 `getSummaryForUpdate()`를 호출해 `daily_summaries` 행에 `SELECT ... FOR UPDATE`를 걸어 동시 요청을 직렬화했습니다.

```
[요청 A]                              [요청 B]
getSummaryForUpdate()  ← 잠금 획득
enqueue() → 체크(없음) → PENDING 저장
                    ┌──────────────▶ getSummaryForUpdate() → 블로킹
commit → 잠금 해제   │
                    └──────────────▶ 잠금 획득
                                     enqueue() → 체크
                                     A의 PENDING 보임 → 409
```

B가 잠금을 얻는 시점은 A가 커밋한 직후이므로, B의 중복 체크는 항상 A의 커밋 결과를 봅니다. 의도대로 동작하지만 구조적인 문제가 있었습니다.

### 이 방식의 한계

중복 방지 책임이 두 테이블에 분산됩니다.

```
daily_summaries 행 잠금    ← 직렬화 담당
  + existsByTargetId 체크  ← 실제 중복 판단
```

"비동기 작업 중복 방지"인데 `async_jobs`가 스스로 막지 못하고 다른 테이블의 잠금을 빌리는 구조입니다. 같은 `summaryId`를 대상으로 하는 다른 JobType이 추가되면, 서로 무관한 작업끼리도 블로킹이 발생합니다.

---

## 개선: async_jobs 부분 유니크 인덱스

비동기 작업 중복이라는 문제를 `async_jobs` 테이블이 직접 소유하도록 방향을 바꿨습니다. `DailySummaryService`가 `daily_summaries` unique constraint 위반을 잡아 처리하는 패턴과 동일하게 적용했습니다.

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uk_async_jobs_active_target_job_type
    ON async_jobs (target_id, job_type)
    WHERE status IN ('PENDING', 'PROCESSING');
```

active 상태인 동일 작업은 하나만 존재할 수 있다는 불변 조건을 DB가 직접 강제합니다. 애플리케이션 코드의 체크 시점과 무관하게, 어떤 경합 조건에서도 하나만 살아남습니다. `WHERE` 절 덕분에 COMPLETED/FAILED 상태에는 제약이 걸리지 않아 동일 target에 대한 재등록이 가능합니다.

### 변경 후 흐름

```
TilService.requestGeneration()  [@Transactional]
  → getOrCreateSummary()        ← daily_summaries unique constraint 방어
  → asyncJobManager.enqueue()   ← REQUIRES_NEW INSERT → constraint 위반 시 catch → 409
```

`enqueue()`에서 `REQUIRES_NEW` 트랜잭션으로 INSERT를 시도하고, `DataIntegrityViolationException`이 발생하면 409로 변환합니다. 외부 트랜잭션(`TilService`)이 constraint 위반으로 오염되지 않기 위해 `REQUIRES_NEW`가 필요합니다.

> Spring self-invocation 문제로 `@Transactional(propagation = REQUIRES_NEW)` 직접 호출은 프록시가 우회됩니다. `DailySummaryService.createSummaryInNewTransaction()`과 동일하게 `TransactionTemplate` 방식이 안전합니다.

### 방식 비교

| | 1차 해결 (FOR UPDATE) | 개선 (부분 유니크 인덱스) |
|---|---|---|
| 중복 방지 주체 | `daily_summaries` 잠금 + 앱 코드 체크 | `async_jobs` DB 제약 |
| 다른 JobType 간 블로킹 | 발생 | 없음 |
| 패턴 일관성 | `daily_summaries`와 다름 | unique constraint 처리와 동일 |

---

## 인덱스 생성 방법 결정

부분 유니크 인덱스(`WHERE` 절 포함)를 어떻게 생성할지도 결정해야 했습니다.

### 검토한 방법들

**JPA 어노테이션** (`@Table(indexes = ...)`) — 불가. Hibernate는 `WHERE` 절이 있는 부분 인덱스를 지원하지 않습니다. 일반 유니크 제약은 가능하지만, 그러면 COMPLETED/FAILED 행까지 포함되어 재등록이 불가능해집니다.

**`docker/db/init/` init 스크립트** — 불가. init 스크립트는 컨테이너 최초 생성 시 한 번만 실행되는데, 그 시점에 `async_jobs` 테이블이 아직 존재하지 않습니다. JPA `ddl-auto: update`가 테이블을 생성하는 건 앱 시작 시이기 때문입니다. 실제로 시도했을 때 `ERROR: relation "async_jobs" does not exist`가 발생했습니다.

**Flyway** — 가능하지만 과도한 도입 비용. 6주 제한 프로젝트에서 단일 인덱스를 위해 마이그레이션 툴을 도입하는 것은 과했습니다.

**`spring.sql.init` (schema.sql)** — PostgreSQL에서는 기본 비활성화이므로 `spring.sql.init.mode=always` 설정이 필요하고, `ddl-auto: update`와 실행 순서 충돌 가능성이 있었습니다.

### 채택: ApplicationRunner + JdbcTemplate

앱 시작 시 JPA가 테이블을 생성한 직후 실행되므로 순서가 보장됩니다. `IF NOT EXISTS`로 멱등성을 확보해 매 시작마다 실행되어도 안전하고, 의존성 추가 없이 코드로 팀 전체에 공유할 수 있습니다.

```java
@Component
@RequiredArgsConstructor
public class SchemaIndexInitializer implements ApplicationRunner {

    private final JdbcTemplate jdbcTemplate;

    @Override
    public void run(ApplicationArguments args) {
        jdbcTemplate.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uk_async_jobs_active_target_job_type
                ON async_jobs (target_id, job_type)
                WHERE status IN ('PENDING', 'PROCESSING')
            """);
    }
}
```
