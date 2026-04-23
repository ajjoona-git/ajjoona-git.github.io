---
title: "[둥지] 독소조항 분석 파이프라인 개선: 폴링에서 Celery Chain으로"
date: 2026-04-19 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Celery, CeleryChain, SQLAlchemy, Redis, Architecture, Backend, Troubleshooting, AsyncTask]
toc: true
comments: true
description: "독소조항 분석 워커가 Celery result backend 폴링에 의존하던 구조의 문제점을 분석하고, Celery chain을 도입해 폴링을 제거하기까지의 과정을 기록합니다. 세 가지 아키텍처 방안과 에러코드 체계 설계를 중심으로 의사결정 근거를 정리합니다."
---

[이전 글]({% post_url 2026-04-16-doongzi-celery-beat %})에서 Celery Beat로 stale 태스크를 자동 정리하는 구조를 issuance-worker와 ocr-worker에 도입했습니다. 그런데 Beat 로직을 작성하면서 **독소조항(clause) 워커는 다른 워커들과 구조가 근본적으로 다르다**는 점이 드러났습니다. `worker_id`를 기록하지 않고, 상태 전이도 워커가 아닌 백엔드가 담당하며, 2단계 파이프라인의 중간 상태가 불분명했습니다. 이 포스트에서는 그 구조적 문제를 분석하고 Celery chain으로 재설계한 과정을 기록합니다.

---

## 기존 아키텍처

### 폴링 기반 2단계 파이프라인

독소조항 분석은 두 단계로 구성됩니다.

1. **RAG 검색** (clause-worker): 문장 임베딩 생성 → FTS + pgvector 하이브리드 검색 → reranking
2. **LLM 분석** (backend): 1단계 결과를 받아 외부 LLM API 호출 → `ClauseAnalysis` 저장

두 단계가 독립된 주체에 의해 실행되기 때문에, 1단계가 끝났는지 백엔드가 알려면 주기적으로 확인해야 합니다. 이것이 폴링 구조가 도입된 이유입니다.

```
클라이언트 → POST /clause/analyze
                ↓
백엔드: ClauseTask(PENDING) 생성 (문장 1개당 1개)
        send_task("clause.search", args=[clause_text]) 발행
                ↓
clause-worker: 임베딩 → 하이브리드 검색 → reranking
               → 결과를 Celery result backend(Redis DB 1)에 저장
                ↓ (clause-worker 종료, DB 상태 변경 없음)
클라이언트 → GET /clause/{id} 반복 폴링
                ↓
백엔드 poll_and_process():
    AsyncResult(celery_task_id).ready() == False → ClauseTask.status = PROCESSING
    AsyncResult(celery_task_id).ready() == True  → Redis에서 chunks 꺼냄
                                                    → LLM API 호출
                                                    → ClauseAnalysis INSERT
                                                    → ClauseTask.status = SUCCESS
```

### 특징

- **clause-worker는 ClauseTask ID를 모른다.** task 인자가 `clause_text: str` 하나뿐.
- **clause-worker는 백엔드 DB에 접근하지 않는다.** rag 스키마(pgvector) 전용 커넥션만 보유.
- **상태 전이의 주체가 백엔드**다. PENDING → PROCESSING → SUCCESS/FAILED가 모두 `poll_and_process()`에서 발생한다.

---

## 문제점

Beat를 도입하면서 clause-worker 구조의 문제점이 세 가지로 구체화됐습니다.

### 1. Beat가 WORKER_DEAD를 판정할 수 없다

issuance-worker와 ocr-worker는 태스크를 시작할 때 `ClauseTask.worker_id`에 자신의 ID를 기록합니다. Beat는 이 ID로 Redis heartbeat 키를 조회해 워커 생존 여부를 즉시 판단합니다.

clause-worker는 `ClauseTask ID` 자체를 모르기 때문에 DB에 아무것도 기록하지 않습니다. Beat는 어떤 워커가 어떤 태스크를 처리하는지 알 수 없고, 결국 타임아웃에만 의존해야 합니다.

### 2. PROCESSING 상태의 의미가 모호하다

`ClauseTask.status = PROCESSING`이 설정되는 시점은 "clause-worker가 작업을 시작했을 때"가 아닙니다. `poll_and_process()`가 호출됐을 때 `AsyncResult.ready() == False`이면 PROCESSING으로 바꿉니다.

ClauseTask가 의미하는 작업이 clause-worker의 작업만을 의미하는지, 독소조항 분석 응답을 생성하기까지의 모든 작업을 의미하는지 모호합니다. 즉 두 가지 의미가 뒤섞입니다.

- clause-worker가 RAG 작업 중인 상태
- clause-worker는 이미 끝났고 백엔드가 LLM을 호출 중인 상태

둘 다 "아직 완료되지 않았다"는 의미에서 PROCESSING이지만, 장애가 발생했을 때 어느 단계에서 막혔는지 구분할 수 없습니다.

더 심각한 문제는 **아무도 폴링하지 않으면 ClauseTask가 PENDING에서 영원히 벗어나지 못한다**는 점입니다. clause-worker가 RAG를 마쳤더라도 클라이언트가 폴링을 호출하지 않으면 상태는 `PENDING` 그대로입니다.

### 3. 에러 원인을 구분할 수 없다

RAG 실패와 LLM 실패가 모두 `FAILED`로 기록됩니다. 재시도 전략이나 사용자 안내 문구가 두 실패 원인에 따라 다를 수 있는데, 현재는 구분이 불가능합니다.

---

## 개선 방안

세 가지 방향을 검토했습니다.

### 방안 A: ClauseTask 범위를 RAG로만 축소

`ClauseTask.SUCCESS`를 "RAG 완료"로 정의하고, LLM 실패는 예외로 처리해 500 응답으로 올립니다.

```
clause-worker: RAG 완료 → ClauseTask.status = SUCCESS
백엔드 poll_and_process(): SUCCESS 감지 → LLM 호출
LLM 실패 → 500 응답
```

**문제:** `ClauseTask.status = SUCCESS`인데 `ClauseAnalysis`가 없는 상태가 만들어집니다. 클라이언트가 재폴링하면 "완료됐는데 결과가 없다"는 모순적인 응답을 받게 됩니다. ClauseTask가 나타내는 "분석 완료"의 의미가 희석됩니다.

### 방안 B: 상태 기록 주체만 분리

ClauseTask의 의미는 유지하되, 기록 주체를 정리합니다.

- clause-worker: PENDING → PROCESSING + worker_id 기록
- 백엔드: LLM 완료 후 SUCCESS, 실패 시 FAILED

**문제:** PROCESSING 상태에서 "RAG가 끝났는지 안 끝났는지"를 알기 위해 Redis(Celery result backend)를 계속 폴링해야 합니다. 백엔드와 워커 간 결합 구조가 그대로 남아 근본적인 문제가 해결되지 않습니다.

### 방안 C: Celery chain (채택)

```python
chain(
    clause_search.s(clause_task_id, clause_text),   # clause-worker (RAG)
    process_llm.s(clause_task_id),                  # backend worker (LLM)
)
```

두 태스크를 Celery가 직접 연결합니다. `clause_search`가 완료되면 Celery가 `process_llm`을 자동으로 트리거합니다. 백엔드가 결과를 폴링할 필요가 없습니다.

Celery chain에서 앞 태스크의 반환값은 뒤 태스크의 첫 번째 인자로 전달됩니다. `clause_search`가 `chunks`를 반환하면 `process_llm(chunks, clause_task_id)`로 자동 호출됩니다.


## 왜 Chain인가?

방안 A와 B를 채택하지 않은 핵심 이유는 **폴링 구조가 남는다**는 점입니다.

현재 구조의 문제는 두 단계 파이프라인의 "단계 간 결합"이 폴링으로 이루어진다는 데 있습니다. 방안 B는 기록 주체를 정리하지만, 백엔드가 여전히 Redis에서 RAG 완료를 확인해야 합니다. 방안 A는 폴링 자체를 없애지만 ClauseTask의 의미가 왜곡됩니다.

Chain은 파이프라인의 단계 연결을 Celery 브로커에 위임합니다. 브로커가 `clause_search` 완료를 감지하고 `process_llm`을 발행하므로 백엔드가 주기적으로 확인할 이유가 없습니다. `poll_and_process()` 자체가 삭제됩니다.

또한 chain은 앞 태스크가 실패하면 뒤 태스크를 자동으로 중단합니다. RAG가 실패하면 LLM 호출이 발생하지 않습니다. 별도의 분기 처리 없이 파이프라인이 안전하게 중단됩니다.

---

## 새로운 아키텍처

### 전체 흐름

```
클라이언트 → POST /clause/analyze
                ↓
백엔드: ClauseTask(PENDING) 생성
        chain(clause_search.s(clause_task_id, clause_text), process_llm.s(clause_task_id)).apply_async()
                ↓
clause-worker (clause_search):
    ClauseTask.status = PROCESSING, worker_id = self.request.id
    임베딩 → 하이브리드 검색 → reranking
    실패 시 → ClauseTask.status = FAILED, error_code = ANALYSIS_FAILED (chain 자동 중단)
    성공 시 → chunks 반환 → Celery가 process_llm 자동 트리거
                ↓
backend worker (process_llm):
    chunks와 clause_task_id를 받아 LLM API 호출
    ClauseAnalysis INSERT
    ClauseTask.status = SUCCESS
    실패 시 → ClauseTask.status = FAILED, error_code = LLM_FAILED

클라이언트 → GET /clause/{id} 폴링
    → ClauseTask 조회 (AsyncResult 폴링 없음)
```

### 상태 전이표

| 상태 | 기록 주체 | 시점 |
|------|----------|------|
| `PENDING` | 백엔드 | 분석 요청 시 생성 |
| `PROCESSING` | clause-worker | RAG 작업 시작 시 (worker_id 포함) |
| `FAILED` | clause-worker | RAG 실패 (chain 자동 중단) |
| `SUCCESS` | backend worker | LLM 완료 + ClauseAnalysis 저장 |
| `FAILED` | backend worker | LLM 실패 |
| `FAILED` | beat | PENDING/PROCESSING 고착 |

`ClauseTask.SUCCESS`는 "RAG + LLM 모두 완료된 최종 상태"입니다. 중간 단계(RAG만 완료)에 SUCCESS가 붙는 상황이 없습니다.

### 에러코드 체계

폴링 구조에서는 RAG 실패와 LLM 실패가 모두 `FAILED`로 뭉뚱그려졌습니다. Chain으로 전환하면서 실패 지점이 명확해졌으므로 에러코드도 함께 정리했습니다.

| 에러코드 | 기록 주체 | 발생 시점 |
|---|---|---|
| `DISPATCH_FAILED` | 백엔드 | `chain.apply_async()` 자체 예외 (Redis 연결 불가 등) |
| `ANALYSIS_FAILED` | clause-worker | embed/search 실패가 max_retries 초과 |
| `LLM_FAILED` | backend worker | LLM API 호출 실패 (rate limit, API 오류 등) |
| `STALE_PENDING` | beat | PENDING 상태로 5분 초과 |
| `WORKER_DEAD` | beat | PROCESSING 중 clause-worker heartbeat TTL 만료 |
| `STALE_PROCESSING` | beat | PROCESSING 상태로 10분 초과 |

### 전체 분기 흐름

```
analyze_clauses()
  └─ chain dispatch 실패              → DISPATCH_FAILED (즉시)

clause.search (clause-worker)
  └─ embed/search 실패 & 재시도 소진  → ANALYSIS_FAILED (chain 중단)
  └─ 정상 완료                        → batch_process_llm으로 자동 연결

batch_process_llm (backend worker)
  └─ LLM 호출 실패                    → LLM_FAILED

beat (5분 주기)
  └─ PENDING 5분 초과                 → STALE_PENDING
  └─ heartbeat 키 만료                → WORKER_DEAD
  └─ PROCESSING 10분 초과             → STALE_PROCESSING
```

`PROCESSING` 타임아웃 기준(10분)은 RAG 작업만을 대상으로 잡았습니다. 기존 폴링 구조에서는 PROCESSING이 LLM 호출 시간도 포함했지만, chain으로 전환하면 PROCESSING은 clause-worker가 RAG를 수행하는 시간만 의미합니다. 임베딩 생성과 pgvector 검색의 최대 소요 시간을 기준으로 10분으로 설정했습니다.

---

## issuance/ocr worker와의 비교

Chain 도입 이후 clause-worker의 구조가 다른 워커들과 동일한 패턴이 됩니다.

| 항목 | issuance/ocr-worker | clause-worker (이전) | clause-worker (이후) |
|------|---------------------|---------------------|---------------------|
| 상태 기록 주체 | 워커가 직접 | 백엔드가 폴링 후 | 워커가 직접 |
| PROCESSING 전환 시점 | 워커 작업 시작 즉시 | 백엔드가 폴링했을 때 | 워커 작업 시작 즉시 |
| worker_id 기록 | 가능 | 불가 | 가능 |
| beat WORKER_DEAD 판정 | 가능 | 불가 | 가능 |
| 결과 저장 방식 | DB에 직접 | Redis 경유 | DB에 직접 |
| 파이프라인 단계 | 단일 | 2단계 (폴링 연결) | 2단계 (chain 연결) |


---

## 마치며

이번 개선에서 핵심 판단은 **"폴링을 최소화할 수 있는가"** 였습니다. 방안 B처럼 기록 주체만 분리해도 문제의 일부는 해결되지만, 두 단계를 잇는 연결 방식이 여전히 폴링이라면 PROCESSING 상태의 의미 모호성과 아무도 폴링하지 않으면 상태가 전이되지 않는 문제가 남습니다.

Celery chain은 **파이프라인의 연결을 브로커에 위임함으로써 폴링 자체를 구조에서 제거**합니다. 이로써 클라이언트 폴링(`GET /clause/{id}`)은 "결과를 확인하는" 역할만 남고, 상태 전이를 유도하는 역할을 더 이상 맡지 않습니다.

추가로 `worker_id` 기록이 가능해지면서 Beat의 `WORKER_DEAD` 판정이 clause-worker에도 적용됩니다. issuance/ocr-worker에 이미 동작하는 패턴을 clause-worker도 그대로 따르게 되어 아키텍처 일관성도 확보됩니다.
