---
title: "[둥지] IssuanceTask / OcrTask 설계 논의 정리: DB 선행 패턴과 Retry 정책"
date: 2026-03-26 10:00:00 +0900
categories: [Project, 둥지]
tags: [Celery, Task, Async, Design, Python, FastAPI, Redis, DB]
toc: true
comments: true
description: "둥지 프로젝트에서 등기부 발급 자동화와 OCR 처리를 담당하는 IssuanceTask / OcrTask의 비즈니스 로직 흐름을 정리합니다. DB 선행 vs Redis 선행 패턴의 의사결정 과정, 보상 로직 현황, 그리고 향후 Retry 정책 합의 내용을 다룹니다."
---

둥지 프로젝트에서 등기부 발급 자동화(IssuanceTask)와 OCR 처리(OcrTask)는 Celery로 비동기 처리됩니다. 두 태스크의 비즈니스 로직 흐름을 정리하고, OcrTask의 문제점과 개선 방향, 그리고 팀 내에서 합의한 Retry 정책을 기록합니다.

---

## 전체 흐름 개요

```
클라이언트
  │
  ├─ POST /nests/{nestId}/analysis/registry/issue
  │     → IssuanceTask(PENDING) 생성 → Celery 발행
  │     ← task_id, status 반환
  │
  ├─ GET /nests/{nestId}/analysis/registry/issue/{taskId}  (폴링)
  │     ← IssuanceTask.status 반환
  │     ← SUCCESS 시 file_url, ocr_task_id 포함  ※ ocr_task_id는 현재 미구현
  │
  │   [IssuanceTask → SUCCESS 확인 후]
  │
  ├─ GET /nests/{nestId}/analysis/registry/ocr/{taskId}  (폴링)
  │     ← OcrTask.status 반환
  │     ← FAILED 시 error_code 포함
  │
Celery Worker (issuance queue)
  ├─ IssuanceTask → PROCESSING
  ├─ 발급 bot 실행 → PDF 취득
  ├─ S3 업로드 → File 레코드 생성
  ├─ IssuanceTask → SUCCESS
  ├─ OCR 큐 발행 → OcrTask(PENDING) 생성
  └─ 실패 구간별 → IssuanceTask FAILED(error_code)

Celery Worker (ocr queue)  ← 별도 서비스
  ├─ OcrTask → PROCESSING
  ├─ OCR 수행 → File.ocr_text 저장
  └─ OcrTask → SUCCESS / FAILED
```

## IssuanceTask 비즈니스 로직 흐름

### API 레이어 (`request_issuance`)

#### **1단계 — 둥지 검증 (with_for_update)**

```
Nest 조회 (행 락)
  ├─ 없음              → NestNotFoundException(404)
  └─ 소유자 불일치     → NestPermissionException(403)
```

#### **2단계 — 활성 태스크 재사용 판단 (낙관적 조회, 락 없음)**

```
IssuanceTask 조회 (PROCESSING | PENDING, 최신순, limit 1)
  │
  ├─ PROCESSING 존재   → 재사용 반환 (즉시 종료)
  │
  ├─ PENDING 존재
  │   ├─ 생성 후 5분 미만 (stale 아님)  → 재사용 반환 (즉시 종료)
  │   └─ 5분 초과 의심 (stale)          → 3단계로
  │
  └─ 없음              → 4단계로
```

#### **3단계 — Stale PENDING 재확인 (with_for_update)**

```
같은 IssuanceTask 재조회 (행 락)
  │
  ├─ PROCESSING으로 변경됨
  │     → 재사용 반환 (즉시 종료)
  │     ※ 2단계와 3단계 사이에 워커가 처리를 시작한 경쟁 조건 처리
  │
  ├─ PENDING + 여전히 stale
  │     → FAILED(STALE_PENDING) 처리 → 4단계로
  │
  └─ PENDING + stale 아님
        → 재사용 반환 (즉시 종료)
        ※ 동시 요청 경쟁 조건에서 시각 차이로 인한 케이스
```

#### **4단계 — 신규 IssuanceTask 생성 및 Celery 발행 (DB 선행)**

```
IssuanceTask(PENDING) 생성 → DB 커밋   ← DB 먼저
  │
  ├─ Celery(Redis) 발행 실패
  │     → IssuanceTask FAILED(DISPATCH_FAILED) → DB 커밋
  │     → InternalServerErrorException(500) 반환
  │
  └─ Celery(Redis) 발행 성공
        → IssuanceTask.celery_task_id 저장 → DB 커밋
        → IssuanceTask 반환
```

### Celery 워커 레이어 (`_issue_registry_task_async`)

```
_set_task_processing()  ← IssuanceTask → PROCESSING (행 락)
  │
  ├─ Bot 초기화 실패        → FAILED(AUTOMATION_FAILED)
  │
  ├─ 발급 자동화 실패       → FAILED(AUTOMATION_FAILED)
  ├─ 중복 결제 감지         → FAILED(DUPLICATE_PAYMENT)
  ├─ PDF 경로 비어있음      → FAILED(AUTOMATION_FAILED)
  │
  ├─ S3 업로드 실패         → FAILED(UPLOAD_FAILED)
  │     ※ 이미 업로드된 S3 오브젝트 정리 없음 (고아 오브젝트 발생 가능)
  │
  ├─ DB 저장 실패           → FAILED(SAVE_FAILED)
  │     ※ S3 업로드 성공 상태이므로 S3 고아 오브젝트 발생
  │
  └─ 성공
        → IssuanceTask SUCCESS
        → OCR 큐 발행 → OcrTask 생성  ← 현재 Redis 선행 (문제)
        → 예외 발생 시 로깅만 (보상 없음)  ← 현재 문제
```

### 안전망 — `AnalysisTask.on_failure()`

Celery 내부에서 예상치 못한 예외가 발생했을 때 `IssuanceTask → FAILED(UNKNOWN)`을 보장하는 Celery 베이스 클래스 훅입니다. 내부 로직에서 `_mark_failure()`로 처리하지 못한 케이스를 커버합니다.


## OcrTask 비즈니스 로직 흐름

### 현재 구현 — Redis 선행 방식

```
[IssuanceTask SUCCESS 처리 후]
  │
  celery_app.send_task("ocr.process_registry_document")  ← Redis 먼저
    │
    ├─ 발행 성공
    │     → _create_ocr_task() → OcrTask(PENDING) DB 저장
    │     → 이후 OCR 워커가 PROCESSING → SUCCESS/FAILED 처리
    │
    └─ 발행 실패 (예외)
          → logger.exception() 로깅만
          → OcrTask 레코드 미생성
          → 클라이언트 추적 불가
```

### 문제점

1. **추적 단절**: 발행 실패 시 OcrTask 레코드 자체가 없어 클라이언트가 실패 여부를 알 수 없습니다.
2. **ocr_task_id 전달 불가**: IssuanceStatusData에 `ocr_task_id` 필드가 없어 클라이언트가 OcrTask ID를 받을 방법이 없습니다. (별도 이슈)
3. **패턴 불일치**: IssuanceTask는 DB 선행, OcrTask는 Redis 선행으로 일관성이 없습니다.

## OcrTask 개선 방향 — DB 선행 방식으로 통일

### 의사결정 과정

| 방식 | 설명 | 장점 | 단점 |
|------|------|------|------|
| Redis 선행 (현재) | 큐 발행 후 DB 저장 | 구현 단순 | 발행 실패 시 레코드 없음, 추적 불가 |
| DB 선행 (개선) | DB 저장 후 큐 발행 | 항상 추적 가능, IssuanceTask와 패턴 통일 | 큰 단점 없음 |

DB 선행 방식으로 통일하기로 결정했습니다. 이유는 다음과 같습니다.

- IssuanceTask가 이미 DB 선행 방식으로 안정적으로 동작 중입니다.
- OcrTask 생성 시점에 `nest_id`, `file_id`가 이미 확정된 상태이므로 DB 선행에 제약이 없습니다.
- Redis 선행 방식은 발행 성공 + DB 저장 실패 케이스에서 워커가 실행되는데 추적 레코드가 없는 더 위험한 시나리오도 존재합니다.

### 개선된 흐름

```
[IssuanceTask SUCCESS 처리 후]
  │
  OcrTask(PENDING, celery_task_id=None) 생성 → DB 커밋  ← DB 먼저
    │
    ├─ celery_app.send_task(...) 실패
    │     → OcrTask FAILED(DISPATCH_FAILED) → DB 커밋
    │     ※ IssuanceTask는 SUCCESS 유지
    │       (발급 자체는 성공했으므로 OCR 실패가 발급을 되돌리지 않음)
    │
    └─ celery_app.send_task(...) 성공
          → OcrTask.celery_task_id 저장 → DB 커밋
          → OCR 워커가 PROCESSING → SUCCESS/FAILED 처리
```


## 보상 로직 현황 비교

| 실패 구간 | IssuanceTask | OcrTask (현재) | OcrTask (개선 후) |
|-----------|-------------|----------------|-------------------|
| Celery 발행 실패 | DISPATCH_FAILED 기록 | 로깅만 (보상 없음) | DISPATCH_FAILED 기록 |
| 워커 처리 실패 | 구간별 error_code 기록 | OCR 워커가 처리 (별도 서비스) | 동일 |
| 예상치 못한 예외 | `on_failure()` 안전망 | 없음 | — |
| S3 고아 오브젝트 | 정리 로직 없음 | 해당 없음 | 해당 없음 |

---

## Task Dispatch / Retry 정책

현재 retry 로직은 구현되어 있지 않으며, 전체적으로 IssuanceTask의 패턴을 따릅니다.

### `not_started`와 `pending`은 분리하지 않습니다

별도 `NOT_STARTED` 상태를 두지 않으며, 최초 상태는 `PENDING` 단일 상태로 처리합니다.

- queue dispatch 실패 케이스는 곧바로 `FAILED + DISPATCH_FAILED`로 정리되므로, "아직 queue에 못 들어간 상태"를 별도 enum으로 관리할 실익이 낮습니다.
- `PENDING`은 "아직 worker가 실제 처리를 시작하지 않은 상태"를 의미합니다.
- queue dispatch 성공 여부가 필요하면 `celery_task_id` 존재 여부로 보조 판단합니다.

### retry는 아직 없고, 추후 실패 원인별 auto-retry를 도입합니다

현재 retry 로직은 없으며, 추후 retry는 상태 기준이 아니라 실패 원인 기준으로 도입합니다.

- 일시적 외부 장애, 네트워크 오류 등은 retry 후보가 될 수 있습니다.
- `DUPLICATE_PAYMENT` 같은 비가역 오류는 retry 대상이 아닙니다.

### retry 정책은 task별로 정의합니다

retry 횟수, 지연 시간, 대상 예외는 task 종류별로 다를 수 있습니다. 따라서 retry 정책은 공통 base에 일괄 고정하지 않고 각 task에서 정의합니다.

### retry 시 기존 task row를 그대로 사용합니다

retry는 "같은 사용자 요청의 재시도"로 봅니다. retry 시 새 `issuance_task` row를 만들지 않으며, 최초 요청에서 생성된 같은 row를 계속 업데이트합니다.

- 같은 요청에 대해 `task_id`를 안정적으로 유지합니다.
- 상태 조회, 중복 제어, 운영 추적을 단일 row 기준으로 유지합니다.

### retry 중 별도 `RETRYING` enum은 두지 않습니다

retry 중이라고 해서 `RETRYING` 같은 별도 상태로 업데이트하지 않으며, 최초 시도와 동일한 상태 흐름을 유지합니다.

### 상태 의미 정리

| 상태 | 의미 |
|------|------|
| `PENDING` | task row는 생성되었지만 worker가 아직 실제 처리를 시작하지 않은 상태 (큐잉 이전과 큐잉 후 작업 시작 전의 상태를 포괄) |
| `PROCESSING` | worker가 처리를 시작했으며, retry가 있더라도 같은 요청의 활성 처리 상태 |
| `SUCCESS` | 최종 성공 |
| `FAILED` | 최종 실패 확정 |

`PENDING` 하나만으로 queue dispatch 전/후를 완전히 구분하지는 않으며, 필요한 경우 `celery_task_id`나 로그를 함께 확인합니다.

### 구현 시 주의사항

**retry 재진입 시 기존 `PROCESSING` row를 다시 사용할 수 있어야 합니다**

현재 구현은 worker 진입 시 `PENDING → PROCESSING` 전환을 전제로 하고 있어, 그대로 auto-retry만 붙이면 재시도 메시지가 와도 task가 바로 종료될 수 있습니다.

retry 도입 시 아래 중 하나를 반드시 보완해야 합니다.

- retry 컨텍스트에서는 이미 `PROCESSING`인 row도 재진입 허용
- 또는 retry 시점의 상태 전이/검증 로직을 별도로 분리

핵심은 "같은 row를 쓰되, 재시도 시에도 실제 로직이 다시 실행되도록" 만드는 것입니다.

**stale 정책은 `PENDING` 외에 `PROCESSING`도 재검토해야 합니다**

현재 재요청 로직은 오래된 `PENDING` task를 `STALE_PENDING`으로 마감하고 새 row를 만드는 구조입니다. retry 도입 후에는 아래 상황을 따로 판단해야 할 수 있습니다.

- 정말 멈춘 `PROCESSING`
- 정상적인 retry 대기 중인 `PROCESSING`

`RETRYING` 상태를 추가하지 않으므로, 필요 시 아래 메타데이터를 별도 필드로 관리하는 방안을 고려합니다.

- `retry_count`
- `last_error_code`
- `last_attempt_at`
- `next_retry_at`

---

## 마치며

이번 정책은 상태 enum을 과도하게 늘리지 않고, "하나의 사용자 요청은 하나의 task row로 추적한다"는 원칙을 유지하는 데 목적이 있습니다.

- dispatch 실패도 같은 row에서 관리
- retry도 같은 row에서 관리
- 상태는 단순하게 유지
