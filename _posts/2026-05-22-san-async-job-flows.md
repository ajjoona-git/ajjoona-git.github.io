---
title: "[SAN] 비동기 작업 흐름 전체 정리"
date: 2026-05-22 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, AsyncJob, Async, Architecture, pgvector, GitHub]
toc: true
comments: true
description: "CARD_ANALYSIS, SCRAP_REFINE, TIL_GENERATION, TIL_GITHUB_COMMIT, RECALL_QUIZ_GENERATION, GITHUB_STAR_RECOMMENDATION 6개 JobType의 등록부터 처리까지 전체 흐름을 정리합니다."
---

현재 구현된 `JobType` 6종의 전체 흐름을 정리합니다. 공통 인프라를 먼저 설명하고, 각 잡 타입의 등록과 처리 흐름을 순서대로 기술합니다.

---

## 공통 인프라

### async_jobs 테이블

| 컬럼 | 설명 |
|---|---|
| `job_id` | UUID (PK) |
| `job_type` | 6종 JobType 중 하나 |
| `target_id` | 작업 대상 엔티티 ID (job_type에 따라 의미가 다름, FK 없음) |
| `status` | `PENDING` → `PROCESSING` → `COMPLETED` / `FAILED` |
| `error_message` | 실패 시 cause chain 기록 |

### 중복 방지 — 유니크 부분 인덱스

앱 기동 시 `ApplicationRunner`가 아래 인덱스를 생성합니다. 동일 `(target_id, job_type)` 조합의 활성 잡이 두 개 이상 등록되는 것을 DB 레벨에서 막습니다. 충돌 시 `DataIntegrityViolationException`이 발생하고, `AsyncJobManager`가 `DUPLICATE_RESOURCE` 예외로 변환합니다.

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uk_async_jobs_active_target_job_type
    ON async_jobs (target_id, job_type)
    WHERE status IN ('PENDING', 'PROCESSING')
```

### 상태 전이 공통 패턴

```
[등록]
  → AsyncJobManager.enqueue()           -- REQUIRES_NEW (기본)
    또는 enqueueInCurrentTransaction()  -- MANDATORY (TilService만 사용)
  → async_jobs INSERT (PENDING) + 이벤트 발행
  ← 202 반환 (jobId, targetId 포함)

[비동기 처리]
  @TransactionalEventListener(AFTER_COMMIT) + @Async(전용 Executor)
  → PROCESSING 전환
  → 실제 작업 수행
  → COMPLETED 또는 FAILED 전환 (실패 시 cause chain 기록)

[클라이언트 폴링]
  GET /async-jobs/{jobId}
  ← { jobId, jobType, status, errorMessage }
```

### 배치 복구 (2시간마다)

| 서비스 | 역할 |
|---|---|
| `GhostJobRecoveryService` | PENDING 30분·PROCESSING 1시간 초과 잡 → FAILED 후 재등록 |
| `FailedJobRecoveryService` | FAILED 잡 최대 3회까지 재등록 |
| `OrphanScrapRecoveryService` | 지식카드 없는 스크랩 → CARD_ANALYSIS 재등록 |
| `OrphanScrapRefineRecoveryService` | 정제되지 않은 스크랩 → SCRAP_REFINE 재등록 |

---

## 1. CARD_ANALYSIS — 지식카드 AI 분석

스크랩 저장 시 자동으로 등록됩니다. `target_id`는 `scrap_id`입니다.

### 등록

`POST /scraps` 요청이 들어오면 원본 내용을 정규화(CRLF→LF, trim)하고 SHA-256 해시로 중복을 판별합니다.

- **기존 스크랩**: 지식카드 유무를 확인해 없으면 활성 잡이 있는지 조회하고, 없을 때만 새 잡을 등록합니다.
- **신규 스크랩**: `scraps` INSERT 후 CARD_ANALYSIS와 SCRAP_REFINE을 동시에 등록합니다.

두 경우 모두 202와 함께 `scrapId`, `analysisJobId`, `refineJobId`를 반환합니다.

### 처리 (`aiJobExecutor`)

스크랩 원문을 AI 서버에 전달해 `title`, `summary`, `tags`, `category`, `embedding(1536차원)`을 받습니다. 카테고리와 태그를 조회 또는 생성한 뒤 `knowledge_cards`에 저장합니다.

### 완료 후 조회

- `GET /cards/{scrapId}` — 생성된 카드 ID 조회
- `GET /cards/{cardId}/similar-cards` — 코사인 거리 기반 유사 카드 조회 (threshold 0.5, 결과 없으면 fallback으로 가장 가까운 K개 반환)

---

## 2. SCRAP_REFINE — 스크랩 원본 정제

CARD_ANALYSIS와 함께 스크랩 저장 시 자동으로 등록됩니다. `target_id`는 `scrap_id`입니다.

### 처리 (`aiJobExecutor`)

스크랩 원본을 AI 서버에 전달해 정제된 내용(`refinedContent`)을 생성하고 `scraps`를 업데이트합니다. 원본 저장 성공 여부가 AI 정제 성공에 의존하지 않도록 CARD_ANALYSIS와 별개의 잡으로 분리되어 있습니다.

---

## 3. TIL_GENERATION — TIL 문서 생성

사용자가 특정 날짜의 TIL 생성을 요청할 때 등록됩니다. `target_id`는 `summary_id`입니다.

### 등록

`POST /til { targetDate }` 요청 시 두 가지 중복 방지를 거칩니다.

1. `daily_summaries` 행에 SELECT FOR UPDATE를 걸어 동시 생성 요청을 직렬화합니다.
2. 동일 사용자의 활성 TIL 생성 잡이 있으면 409를 반환합니다.

통과하면 `daily_summaries`를 INSERT하고 같은 트랜잭션 안에서 잡을 등록합니다(`enqueueInCurrentTransaction` — MANDATORY). 6개 JobType 중 유일하게 부모 트랜잭션에 참여하는 방식으로, `daily_summaries` 생성과 잡 등록의 원자성을 보장합니다.

### 처리 (`aiJobExecutor`)

해당 날짜의 지식카드 원문을 모아 AI 서버에 전달하면 `title`, `tilMarkdown`, `embedding(1536차원)`을 받습니다. `daily_summaries`를 업데이트해 TIL을 완성합니다.

### 완료 후 조회

- `GET /til?date=YYYY-MM-DD` — TIL 목록 조회
- `GET /til/{summaryId}/recall-cards` — TIL 임베딩 기반 리콜 카드 조회 (threshold 0.5, 원본 카드 제외, fallback 포함)

---

## 4. TIL_GITHUB_COMMIT — TIL GitHub 커밋

사용자가 생성된 TIL을 GitHub에 푸시를 요청할 때 등록됩니다. `target_id`는 `til_github_commit_id`입니다. `async_jobs`와 별개로 `til_github_commits` 테이블이 자체 상태(`PENDING` → `PROCESSING` → `COMPLETED`/`FAILED`)를 관리합니다.

### 등록

`POST /til/{summaryId}/github-commits` 요청 시 아래 순서로 검증합니다.

1. TIL 생성 완료 여부 확인 (미완료면 400)
2. GitHub 계정 연동 여부 확인
3. 연결된 레포지토리 정확히 1개인지 확인
4. `contentHash` 기준 중복 커밋 확인 (PENDING/PROCESSING/COMPLETED이면 409)
5. GitHub API로 파일명 충돌 회피 후 `filePath` 결정
6. `til_github_commits` INSERT + `async_jobs` 등록

### 처리 (`githubJobExecutor`)

`async_jobs`와 `til_github_commits` 양쪽을 PROCESSING으로 전환한 뒤, 암호화된 GitHub 액세스 토큰을 복호화해 `PUT /repos/{owner}/{repo}/contents/{filePath}` 요청을 보냅니다. 성공하면 커밋 SHA와 URL을 기록하고 양쪽 테이블을 COMPLETED로 전환합니다.

GitHub PUT은 동일 경로 재요청 시 409 Conflict가 발생할 수 있으므로 `aiJobExecutor`와 별도 풀(`githubJobExecutor`)로 분리했습니다. 비동기 컨텍스트에서 `til_github_commits` 상태 업데이트는 `TransactionTemplate`으로 독립 트랜잭션을 사용합니다.

---

## 5. RECALL_QUIZ_GENERATION — 리콜 퀴즈 생성

사용자의 리콜 퀴즈 생성 요청 또는 TIL 자동 생성 배치에서 등록됩니다. `target_id`는 `generation_id`입니다.

### 처리 (`aiJobExecutor`)

`recall_quiz_generations`에서 대상 날짜와 퀴즈 타입(`OX`, `SHORT_ANSWER`)을 읽어 AI 서버에 퀴즈 생성을 요청하고 결과를 저장합니다.

---

## 6. GITHUB_STAR_RECOMMENDATION — GitHub Star 추천 분석

사용자의 GitHub Star 추천 요청 시 등록됩니다. `target_id`는 `user_id`입니다.

### 처리 (`aiJobExecutor`)

사용자의 GitHub Star 목록을 분석해 학습에 유용한 레포지토리를 추천합니다. 결과는 별도 테이블에 저장됩니다.

---

## 흐름 비교

| | CARD_ANALYSIS | SCRAP_REFINE | TIL_GENERATION | TIL_GITHUB_COMMIT | RECALL_QUIZ_GENERATION | GITHUB_STAR_RECOMMENDATION |
|---|---|---|---|---|---|---|
| 진입점 | `POST /scraps` (자동) | `POST /scraps` (자동) | `POST /til` | `POST /til/{id}/github-commits` | 별도 API | 별도 API |
| target_id | scrap_id | scrap_id | summary_id | til_github_commit_id | generation_id | user_id |
| 외부 호출 | AI (분석+임베딩) | AI (정제) | AI (TIL+임베딩) | GitHub API | AI (퀴즈) | AI (추천) |
| 스레드 풀 | aiJobExecutor | aiJobExecutor | aiJobExecutor | **githubJobExecutor** | aiJobExecutor | aiJobExecutor |
| 추가 상태 테이블 | — | — | — | til_github_commits | — | — |
| enqueue 방식 | REQUIRES_NEW | REQUIRES_NEW | **MANDATORY** | REQUIRES_NEW | REQUIRES_NEW | REQUIRES_NEW |
| 중복 방지 | content_hash + 유니크 인덱스 | 유니크 인덱스 | SELECT FOR UPDATE + 활성 잡 조회 | content_hash 조회 | 유니크 인덱스 | 유니크 인덱스 |
