---
title: "[둥지] 문서 발급 상태 동기화 문제: localStorage 타이머에서 서버 기반 폴링으로"
date: 2026-04-13 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Celery, Redis, Frontend, React, Architecture, Troubleshooting, AsyncTask, Backend]
toc: true
comments: true
image: /assets/img/posts/2026-04-13-doongzi-issuance-status-sync/4.png
description: "비동기 문서 발급 완료 상태를 프론트에 동기화하지 못해 무한 스피너가 발생한 문제를 분석하고, localStorage 타이머 우회책의 한계를 짚은 뒤 폴링·pending_since·celery beat 세 방안을 단계적으로 적용한 과정을 정리합니다."
---

둥지 서비스는 등기부등본·건축물대장 같은 문서를 외부 정부 사이트에서 자동 발급합니다. 발급 요청을 받으면 Celery Worker가 브라우저 자동화로 문서를 취득하고, S3에 업로드한 뒤 DB 상태를 갱신합니다.

비동기 작업이라 결과가 즉시 나오지 않습니다. 문제는 여기서 시작됩니다.

***"워커가 발급을 완료했다는 사실을 프론트엔드는 어떻게 알 수 있는가?"***

이 질문에 제대로 답하지 못한 결과는 무한 스피너였습니다.

---

## 무한 로딩의 구조적 원인

![문서 발급 무한 로딩 중](/assets/img/posts/2026-04-13-doongzi-issuance-status-sync/4.png)
*문서 발급 무한 로딩 중*

표면적인 원인은 issuance-worker가 실행 중이지 않은 것이었습니다. issuance-worker는 Windows 노트북에서 실행되는 브라우저 자동화 워커입니다. 노트북이 꺼져 있거나 절전 모드에 들어가면 `issuance` 큐를 소비할 주체가 없어 태스크가 `PENDING`에 고착됩니다.

```
requestIssuance() 호출
  → IssuanceTask 생성 (status=PENDING)
  → Redis issuance 큐에 적재
  → issuance-worker 미실행 → 태스크 영원히 실행 안 됨
  → DB 상태 PENDING 지속
  → 프론트 무한 스피너
```

### issuance-worker가 Windows 네이티브인 이유

`SimpleIrosBot`, `BuildingLedgerBot`은 Selenium 계열로 외부 정부 사이트를 조작하는데, 해당 사이트가 Windows 환경을 요구합니다. 컨테이너(Linux)에서는 동작하지 않아 개인 노트북을 상시 가동 서버로 사용하고, Tailscale VPN을 통해 클라우드 Redis(ElastiCache)와 통신합니다.

```
[사용자] → [EC2: FastAPI] → [Redis: issuance 큐 적재]
                                    ↓ (Tailscale VPN)
                          [Windows 노트북: issuance-worker]
                              ↓ (브라우저 자동화)
                          [외부 정부 사이트]
                              ↓
                          [S3 업로드 + DB 상태 갱신]
```

### 워커가 정상이어도 무한 스피너가 발생한다

더 본질적인 문제가 있었습니다. 워커가 정상 동작해 `SUCCESS`로 완료되더라도, **프론트엔드가 이 변화를 감지할 방법이 없었습니다.**

`handleIssue` 흐름을 보면 명확합니다.

```
1. requestIssuance()    → 발급 요청 (PENDING 생성)
2. nestsAPI.get(nestId) → nest 상태 1회만 조회
3. setNest(updated)     → UI 업데이트 후 종료
```

발급 직후 바로 조회하므로 당연히 `PENDING`이 반환됩니다. 이후 워커가 `SUCCESS`로 바꿔도 프론트는 알 수 없습니다. 폴링도, SSE도 없습니다.

두 가지 실패 경로는 서로 독립적입니다.

| 경로 | 원인 | 증상 |
|---|---|---|
| 워커 오프라인 | issuance-worker 미실행 → 태스크 PENDING 고착 | DB가 PENDING 그대로, 재발급 버튼도 안 뜸 |
| 워커 정상 | 프론트 폴링 없음 → 완료됐어도 프론트가 모름 | SUCCESS 됐어도 스피너 계속 표시 |

설계는 되어 있으나 미구현인 항목도 문제를 키웠습니다. celery beat 주기적 stale 정리 태스크가 없어서 워커 오프라인 시 고착된 `PENDING`/`PROCESSING`이 자동으로 `FAILED`로 정리되지 않았고, 재발급 버튼 자체가 뜨지 않는 상태였습니다.

---

## 기존 우회책과 그 한계 — localStorage 타이머

이 상황을 임시로 해결하려 localStorage 기반 타이머를 도입했습니다. 발급 요청 시각을 localStorage에 기록해두고, 2분이 지나면 재발급 버튼을 표시하는 방식입니다.

```ts
// 발급 요청 후
await requestIssuance();
recordPendingStart();  // localStorage에 현재 시각 기록

// 모달 열 때
const remaining = getRemainingMs();  // 2분 - 경과시간
if (remaining <= 0) setTimedOut(true);
else setTimeout(() => setTimedOut(true), remaining);
```

방향성 자체는 맞았지만 구현에 네 가지 구조적 문제가 있었습니다.

| 문제 | 상세 |
|---|---|
| 타 기기 / 스토리지 초기화 | localStorage 키가 없으면 `remainingMs = 2분` 반환 → 이미 오래된 PENDING이어도 새 2분 타이머가 다시 시작됨 |
| RTT 지연 | `await requestIssuance()` 완료 후 기록 → 느린 서버에서 실제 요청 시각보다 RTT만큼 늦게 기록, 체감 대기 = RTT + 2분 |
| AUTO 발급 경로 누락 | 둥지 생성 시 자동 발급으로 이미 PENDING인 경우 localStorage 기록 자체가 없어 마찬가지로 새 2분 타이머 시작 |
| 완료 감지 불가 | 타이머가 만료되기 전에 발급이 완료돼도 프론트는 알 수 없음. SUCCESS가 됐어도 타이머가 끝날 때까지 스피너 |

localStorage는 클라이언트 로컬 상태입니다. 서버에서 발급이 언제 시작됐는지, 지금 어떤 상태인지를 알 수 없으므로 근본적인 해결이 아닙니다.


## 세 가지 해결 방안

### 방안 A. 프론트 폴링 + 타임아웃

이미 구현되어 있는 `pollIssuanceUntilSettled` 함수를 `handleIssue`에 연결합니다. `DocumentAnalysisModal`, `InsuranceCheckModal`에서는 이미 이 함수를 사용하고 있었는데, `NestDetailModal`에만 적용이 누락된 상태였습니다.

```ts
const data = await analysisAPI.requestIssuance(nestId!, docType);

const settled = await pollIssuanceUntilSettled(nestId!, docType, data.task_id, {
  intervalMs: 5_000,       // 5초 간격
  maxAttempts: 36,         // 최대 3분 (5s × 36)
  shouldContinue: () => isOpen,  // 모달 닫히면 폴링 중단
});

if (settled === null) {
  setTimedOut(true);  // 타임아웃 → 재발급 버튼 표시
} else {
  const updated = await nestsAPI.get(nestId!);
  setNest(updated);
}
```

localStorage 코드 전체를 제거할 수 있습니다. 모달을 닫았다 다시 열면 `nestsAPI.get`이 그 시점의 상태를 가져오므로 자연스럽게 연결됩니다.

**장점:** 프론트엔드만 수정하면 되며 즉시 적용 가능합니다.

**단점:** 모달을 닫았다 다시 열면 3분 타이머가 초기화됩니다. 이미 2분 30초가 지난 PENDING이어도 다시 3분을 기다려야 재발급 버튼이 뜹니다.


### 방안 B. BE `pending_since` 필드 추가

`nestsAPI.get` 응답에 PENDING/PROCESSING 태스크의 `created_at`을 추가합니다. 모달을 다시 열 때 서버 기준 경과 시간을 계산해 타이머를 정확히 이어받을 수 있습니다.

```python
# nest/schemas.py
latest_registry_pending_since: datetime | None = None
latest_ledger_pending_since: datetime | None = None
```

```ts
// 모달 오픈 시 이미 PENDING인 경우
const pendingSince = nest.latest_registry_pending_since;
if (pendingSince) {
  const elapsed = Date.now() - new Date(pendingSince).getTime();
  const remaining = TIMEOUT_MS - elapsed;
  if (remaining <= 0) setTimedOut(true);
  else setTimeout(() => setTimedOut(true), remaining);
}
```

**장점:** localStorage 없이도 타 기기·스토리지 초기화·AUTO 발급 누락 문제가 모두 해결됩니다. 시각의 출처가 서버이므로 정확합니다.

**단점:** BE에 필드 추가와 프론트 수정이 함께 필요합니다.


### 방안 C. celery beat — stale 태스크 자동 정리

설계는 되어 있으나 미구현인 항목입니다. 주기적으로 고착된 PENDING/PROCESSING 태스크를 FAILED로 정리합니다.

현재 `_is_stale_pending_task`는 PENDING만 체크하고 다음 재발급 요청이 들어올 때만 작동합니다. PROCESSING 고착은 처리하지 않습니다.

```python
PROCESSING_TASK_TIMEOUT = timedelta(minutes=10)

def _is_stale_processing_task(task: IssuanceTask, now: datetime) -> bool:
    if task.status != TaskStatusEnum.PROCESSING:
        return False
    updated_at = task.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return now - updated_at >= PROCESSING_TASK_TIMEOUT
```

celery beat 스케줄 태스크가 주기적으로 실행되어 PENDING(5분), PROCESSING(10분) 이상 고착된 태스크를 FAILED로 전환하면, 이후 프론트 폴링이 FAILED를 감지해 재발급 버튼을 표시합니다.

**장점:** 워커가 오프라인이거나 크래시한 상황에서도 고착 태스크가 자동 정리됩니다. 방안 A의 타임아웃과 연동하면 워커 오프라인 → FAILED 자동 전환 → 재발급 버튼 표시 흐름이 완성됩니다.

**단점:** 세 방안 중 구현 범위가 가장 넓습니다. 방안 A·B가 없으면 FAILED로 전환됐어도 프론트가 이를 감지할 수 없으므로 단독으로는 의미가 없습니다.


### 세 방안의 관계

방안 A, B, C는 독립적이지 않습니다. 서로 다른 실패 경로를 막는 방어막이고, 셋이 모두 갖춰져야 정상 동작합니다.

| 실패 시나리오 | A만 있을 때 | A+B | A+B+C |
|---|---|---|---|
| 워커 정상, 폴링 없음 | 해결 | 해결 | 해결 |
| 모달 재오픈 시 타이머 초기화 | 미해결 | 해결 | 해결 |
| 워커 오프라인, stale 고착 | 3분 후 타임아웃 표시 (부정확) | 서버 경과 시간 기준 표시 | FAILED 자동 전환 → 정확한 재발급 유도 |
| AUTO 발급 누락 | 미해결 | 해결 | 해결 |

---

## 결정: 단계적 적용

세 방안을 한 번에 적용하는 것보다 실질적인 해결부터 순서대로 적용하기로 결정했습니다.

| 단계 | 내용 | 범위 | 효과 |
|---|---|---|---|
| Phase 1 | issuance-worker 기동 확인 | 운영 | 기본 흐름 복구 |
| Phase 2 | 방안 A: 폴링 + 3분 타임아웃, localStorage 제거 | 프론트만 | TD-271의 실질적 해결 |
| Phase 3 | 방안 B: BE `pending_since` 필드 추가 | BE 1필드 + 프론트 | 모달 재오픈 시 타이머 정확도 |
| Phase 4 | 방안 C: celery beat + PROCESSING stale 처리 | BE | 워커 오프라인 자동 복구 |

**Phase 2가 핵심 해결입니다.** localStorage 방식의 타이머를 서버 폴링으로 교체하면 워커가 정상일 때의 무한 스피너 문제가 사라집니다.

Phase 3, 4는 안정성 강화입니다. 특히 방안 C가 없어도 방안 A의 타임아웃이 폴백으로 작동하지만, 워커 오프라인이 장시간 지속되는 상황에서는 고착 태스크를 자동으로 정리하는 celery beat이 최후 방어막이 됩니다.

### 발급 UI 위치는 유지

논의 중 "발급 기능을 둥지 상세 모달에 두는 것이 적절한가"라는 질문도 나왔습니다. 결론은 **현재 위치를 유지**하는 것입니다.

유저가 "이 둥지의 문서 상태가 어떻게 됐지?"를 확인하는 가장 직접적인 경로가 둥지 카드 클릭이기 때문에, 발급 상태 확인, 다운로드를 모달에서 끝내는 것이 자연스럽습니다. 업로드와 분석은 체크리스트의 `DocumentAnalysisModal`에 이미 구현되어 있고, 사용자 의도(서버 자동 취득 vs 사용자 직접 첨부)가 다르므로 분리를 유지합니다.

| 기능 | 위치 |
|---|---|
| 문서 발급 상태 확인 / 다운로드 | 둥지 상세 모달 |
| 문서 자동 발급 + 직접 업로드 + 분석 | 체크리스트 → DocumentAnalysisModal |
| 발급 문서 기반 위험 항목 검토 | 체크리스트 |

| 미발급 | 발급 요청 시 | 발급 실패 시 (모달 오픈 후 3분 경과)|
|--|--|--|
|발급하러 가기 -> 체크리스트 페이지에서 발급 모달 오픈 | 체크리스트에서 상태 확인 -> 모달 닫히고 체크리스트 페이지로 이동 | 모달 열린 채로 3분간 PENDING이면 재발급 버튼 활성화|
| ![미발급 상태](/assets/img/posts/2026-04-13-doongzi-issuance-status-sync/3.png) | ![발급 요청 시](/assets/img/posts/2026-04-13-doongzi-issuance-status-sync/2.png) | ![발급 실패 시](/assets/img/posts/2026-04-13-doongzi-issuance-status-sync/1.png) |

---

## 마치며

무한 스피너의 근본 원인은 비동기 태스크 완료를 프론트가 인지할 방법이 없었다는 것입니다. localStorage 타이머는 이 문제를 클라이언트 로컬에서 흉내 냈을 뿐이었고, 서버 상태와의 동기화를 처음부터 포기한 구조였습니다. 폴링, pending_since, celery beat 세 방안은 각각 다른 실패 경로를 막는 방어막으로, 단계적으로 적용해 안정성을 확보합니다.
