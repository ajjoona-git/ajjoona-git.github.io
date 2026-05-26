---
title: "[SAN] 배치 스케줄러 설계: 유령 잡·고아 스크랩 복구와 TIL 자동 생성"
date: 2026-05-12 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, AsyncJob, Scheduler, Recovery, BatchJob, Architecture, Design]
toc: true
comments: true
description: "비동기 파이프라인에서 발생하는 유령 잡과 고아 스크랩을 복구하고, 전날 학습한 사용자에게 TIL을 자동 생성하는 배치 스케줄러 설계를 기록합니다."
---

비동기 파이프라인은 이벤트 유실, 워커 중단, AI 호출 실패 등으로 파편 데이터를 남깁니다. 이를 방치하면 사용자 데이터 처리가 누락됩니다. 배치 스케줄러를 두어 주기적으로 감지하고 복구합니다.

---

## 스케줄러 구성

| 스케줄러 | 주기 | 역할 |
|---|---|---|
| `GhostJobRecoveryService` | 2시간 | PENDING/PROCESSING 상태로 멈춘 잡 복구 |
| `OrphanScrapRecoveryService` | 2시간 | 지식카드가 생성되지 않은 스크랩 복구 |
| `OrphanScrapRefineRecoveryService` | 2시간 | AI 정제가 되지 않은 스크랩 복구 |
| `TilAutoGenerationScheduleService` | 매일 03:00 | 전날 학습 사용자 전원 TIL 자동 생성 |

복구 스케줄러 셋은 모두 `BatchScheduler.runRecovery()`에서, TIL 생성은 `runTilAutoGeneration()`에서 호출합니다. 진입점을 한 곳으로 모아 실행 순서와 주기를 한눈에 파악할 수 있게 합니다.

### 흐름 요약

```
매 2시간
├── GhostJobRecoveryService
│   └── PENDING > 30분 / PROCESSING > 1시간 → markFailed + enqueue 재등록
├── OrphanScrapRecoveryService
│   └── 지식카드 없음 + 활성 CARD_ANALYSIS 잡 없음 → enqueue(CARD_ANALYSIS)
└── OrphanScrapRefineRecoveryService
    └── refinedContent IS NULL + 활성 SCRAP_REFINE 잡 없음 → enqueue(SCRAP_REFINE)

매일 03:00
└── TilAutoGenerationScheduleService
    └── 전날 카드 보유 사용자 전원 → DailySummary 생성 + enqueue(TIL_GENERATION)
```


---

## 1. Ghost Job 복구

### 스테일 기준

- `PENDING` > 30분: 이벤트 발행 직후 워커가 즉시 잡는 구조이므로 30분 이상은 이벤트 유실로 판단합니다.
- `PROCESSING` > 1시간: AI 서버 호출 타임아웃 상한을 감안한 값입니다.

### 처리 방식

스테일 잡을 `FAILED`로 닫고, 동일 `(jobType, targetId)`로 새 잡을 `enqueue()`합니다. 스케줄러 스레드는 이벤트 발행만 하고 워커가 비동기로 처리하므로 블로킹이 없습니다.

복구 스케줄러는 낮에도 실행되므로 클라이언트가 jobId를 폴링하다 `FAILED`로 바뀌는 상황이 생길 수 있습니다. 현재 클라이언트는 COMPLETED/FAILED 시 폴링을 중단하는 구조라, 이후 새 잡을 통해 카드가 정상 생성되면 스크랩 조회 시 `cardId`로 확인할 수 있습니다.

## 2. 고아 스크랩 복구

### CARD_ANALYSIS — OrphanScrapRecoveryService

지식카드가 없고 활성 `CARD_ANALYSIS` 잡도 없는 스크랩이 대상입니다. 조건을 두 가지로 나눈 이유가 있습니다.

PENDING/PROCESSING 잡이 있는 스크랩은 Ghost Job 복구에서 이미 처리하므로 여기서 제외합니다. 두 복구 서비스가 같은 스크랩을 중복으로 처리하는 것을 막기 위한 경계입니다.

`knowledge_cards.embedding IS NULL` 케이스는 현재 파이프라인 흐름상 발생하지 않으므로 별도로 처리하지 않습니다.

### SCRAP_REFINE — OrphanScrapRefineRecoveryService

`feat/scrap/S14P31A309-267`에서 AI 정제(`SCRAP_REFINE`) 비동기 작업이 추가됐습니다. 원본 저장 성공 여부가 AI 정제 성공에 의존하지 않도록 비동기로 분리된 구조입니다.

추가 전 복구 커버리지를 점검했습니다.

| 케이스 | 담당 | 커버 |
|---|---|---|
| SCRAP_REFINE 잡이 PENDING/PROCESSING 상태로 지연 | `GhostJobRecoveryService` | O |
| 중복 스크랩 재요청 시 `refinedContent` 없으면 재등록 | `enqueueScrapRefineJobIfNeeded` | O |
| `refinedContent IS NULL` + 활성 SCRAP_REFINE 잡 없음 | 없음 | X |

마지막 케이스는 잡 자체가 소실된 상황입니다. 사용자가 동일 원본을 다시 보내지 않는 한 영구 방치됩니다. `OrphanScrapRefineRecoveryService`가 이 케이스를 담당합니다.

`OrphanScrapRecoveryService`와 `OrphanScrapRefineRecoveryService`를 하나로 합치지 않고 별도 클래스로 작성했습니다. 현재 주기가 동일하더라도 두 복구의 성격이 다르고, 향후 주기나 정책을 독립적으로 조정할 수 있어야 하기 때문입니다.

## 3. TIL 자동 생성

전날(`targetDate = 어제`) 지식카드가 생성된 사용자 전원에게 TIL을 자동 생성합니다.

- 전날 스크랩이 있는 distinct `userId` 목록 조회
- 각 사용자에 대해 `DailySummary` 생성 + `TIL_GENERATION` enqueue
- 이미 당일 TIL이 있어도 새로 생성 (다건 허용 구조)

03:00에 실행하는 이유는 자정 이후 사용자가 당일 스크랩을 추가할 가능성이 낮고, 서버 부하가 가장 적은 유휴 시간이기 때문입니다.

