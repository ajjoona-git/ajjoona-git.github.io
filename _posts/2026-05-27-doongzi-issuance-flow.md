---
title: "[둥지] 건축물대장과 등기부등본 발급 흐름 정리"
date: 2026-05-27 10:00:00 +0900
categories: [Project, 둥지]
tags: [Celery, Task, Async, Python, FastAPI, Issuance, Selenium, Automation]
toc: true
comments: true
description: "둥지 프로젝트의 건축물대장·등기부등본 발급 흐름을 정리합니다. triggered_by / visible_to_user_at 두 필드의 역할, AUTO·MANUAL·MANUAL_UPLOAD 경로별 동작, 워커 처리 완료 후 분기, PENDING/PROCESSING 재사용 정책을 다룹니다."
---

둥지 프로젝트에서 건축물대장(LEDGER)과 등기부등본(REGISTRY) 발급은 `IssuanceTask`로 관리됩니다. 두 문서 모두 공식 API가 없는 정부 포털을 Selenium으로 자동화해 PDF를 내려받고, Celery worker가 이 작업을 비동기로 처리합니다. 발급 요청 경로(AUTO/MANUAL/MANUAL_UPLOAD)와 사용자 노출 시점을 분리하는 두 필드를 중심으로 전체 흐름을 정리합니다.

---

## Selenium 기반 브라우저 자동화

공식 API가 없는 정부 포털을 실 사용자처럼 조작해 PDF를 내려받는 방식입니다. 두 문서 모두 **Chrome headless + Selenium**을 사용하며, Celery worker 안에서 실행됩니다.

headless 환경에서는 Chrome의 다운로드 설정이 무시되기 때문에 CDP(`Page.setDownloadBehavior`)로 다운로드 경로를 강제 지정합니다. 다운로드 완료는 임시 파일 소멸과 `.pdf` 출현을 폴링해 감지합니다. 포털 간 쿠키·세션 재사용을 위해 영속 Chrome 프로필을 공유하며, 장애 추적을 위해 단계별 스크린샷과 HTML 소스를 저장합니다.

### 등기부등본

대상은 `iros.go.kr`(인터넷등기소)입니다. WebSquare(전자정부 UI 프레임워크) 기반 SPA로, 결제 단계에서 보안 프로그램·세션 쿠키 게이트가 발동해 영속 Chrome 프로필 공유가 필수입니다.

자동화는 세 단계로 나뉩니다.

```
[1. 부동산 검색 및 발급 옵션 선택]
  - 주소 전처리 후 검색 (괄호 제거, 다가구 주택 호수 토큰 제거 재시도)
  - 검색 결과 다건이면 자동 선택 중단 (오발급 방지)
  - 집합건물 여부에 따라 발급 옵션 UI 분기 처리
  - 열람 매수 초과 팝업 처리 (20매·100매 기준)

[2. 결제]
  - 비회원 로그인 → 선불전자지급수단 결제
  - 중복결제 팝업 감지 → DUPLICATE_PAYMENT 마감
  - 잔액 부족 감지 → Discord 크리티컬 알림 후 INSUFFICIENT_BALANCE 마감

[3. 열람 및 PDF 저장]
  - 미열람 항목 선택 → 열람 팝업에서 저장
  - CDP 다운로드 경로 지정 후 PDF 수신 대기
```

발급 완료 후 바로 알림을 보내지 않습니다. OCR 큐에 후속 태스크를 dispatch하고, OCR 완료 후 알림이 발송됩니다.

### 건축물대장

대상은 `eais.go.kr`(세움터)입니다. Nuxt.js SPA(Vue.js 기반)로, 메인 메뉴 버튼을 headless에서 직접 클릭할 수 없어 인증·발급 페이지를 URL로 직접 이동합니다. ag-grid 기반 건물 목록 선택, ClipReport 뷰어에서 JavaScript를 직접 호출해 PDF를 추출합니다.

```
[1. 로그인]
  - 인증 페이지 URL 직접 이동 (Nuxt SPA headless 조작 불가 우회)
  - Vue.js v-model 반응성을 트리거하기 위해 JS 이벤트 dispatch 필요
    (일반 send_keys만으로는 Vue 상태가 갱신되지 않아 로그인 실패)

[2. 건물 선택 및 발급 신청]
  - 이전 봇 실행에서 남은 cart 항목 자동 삭제 (오발급 방지)
  - 주소에서 도로명 + 번지만 추출해 검색
  - ag-grid 클릭 시 ActionChains 필요 (mousedown→mouseup→click 시퀀스)
  - 건수가 있는 첫 번째 탭 자동 선택

[3. PDF 추출]
  - 신청내역에서 최신 발급 건 선택 → ClipReport 뷰어 새 창 전환
  - canvas 렌더링 완료 대기 후 JS 함수 호출로 PDF 다운로드
```

발급 완료 후 PDF에서 위반건축물 여부를 감지해 `Nest.is_violation_building`을 갱신합니다. 등기부등본과 달리 OCR 연계가 없어 발급 완료 즉시 알림이 발송됩니다.

---

## 두 필드가 하는 일

| 필드 | 역할 |
|---|---|
| `triggered_by` | 파일이 **어떤 경로**로 들어왔는지 (AUTO / MANUAL / MANUAL_UPLOAD) |
| `visible_to_user_at` | 사용자가 **이 태스크를 인지한 시점** — NULL이면 UI·알림에서 숨김 |

두 필드는 독립적입니다. AUTO로 발급된 태스크도 나중에 사용자가 명시적으로 요청하면 `visible_to_user_at`만 기록되고, `triggered_by`는 AUTO 그대로 유지됩니다.


## 1. triggered_by (발급 경로)

### AUTO: 둥지 등록 시 자동 발급

- 둥지 등록 시 건축물대장(LEDGER)만 자동 발급
- `visible_to_user_at = NULL` → UI에 노출 안 됨
- 사용자가 나중에 MANUAL 요청을 하면 이 태스크를 재사용하고 `visible_to_user_at`을 기록

### MANUAL: 사용자가 직접 요청

- `request_issuance(triggered_by=MANUAL)` 진입
- **건축물대장(LEDGER)**: 기존 SUCCESS 태스크가 있으면 재사용 → `visible_to_user_at = now`
  - 없으면 새 PENDING 태스크 생성 (`visible_to_user_at = now`, Celery dispatch)
- **등기부등본(REGISTRY)**: 재사용 없이 항상 새 PENDING 태스크 생성
- `force=True`이면 건축물대장도 재사용 건너뛰고 새 발급 (사용자가 확인 모달 통과한 경우)

### MANUAL_UPLOAD: PDF를 직접 올리는 경우

- Celery 없이 즉시 SUCCESS 태스크 생성
- `visible_to_user_at = now`, `celery_task_id = NULL`, `error_code = NULL`


## 2. visible_to_user_at (사용자 인지 시점)

`visible_to_user_at`은 두 곳에서 게이트 역할을 합니다.

| 위치 | 역할 |
|---|---|
| `nest/service.py` — 둥지 목록 발급 상태 조회 | `visible_to_user_at IS NOT NULL` 필터로 AUTO 태스크 제외 |
| `checklist/routers/analysis_router.py` | SUCCESS 태스크의 파일 URL 제공 시 동일 필터 적용 |
| `notification.py:80` — 알림 발송 | NULL이면 알림 skip (AUTO 완료 시 사용자에게 알리지 않음) |

둥지 목록/상세 API는 이 필터 덕분에 사용자가 직접 요청하기 전에 백그라운드 자동 발급 파일이 화면에 뜨는 것을 막습니다.

---

## 전체 흐름

```
[둥지 등록]
    └─▶ 건축물대장 AUTO 발급
         IssuanceTask { triggered_by: AUTO, visible_to_user_at: NULL }
         └─▶ Celery dispatch → issuance-worker
              ├─▶ SUCCESS: File 저장, Nest.is_violation_building 갱신
              │    └─▶ visible_to_user_at = NULL → 알림 발송 안 함
              └─▶ FAILED: IssuanceTask.error_code 기록, 알림 발송 안 함

[사용자가 건축물대장 발급 버튼 클릭]
    └─▶ request_issuance(triggered_by=MANUAL, doc_type=LEDGER)
         ├─▶ 기존 AUTO SUCCESS 태스크 있음
         │    └─▶ visible_to_user_at = now 업데이트 (triggered_by는 AUTO 유지)
         │         → UI에 노출됨
         └─▶ 기존 SUCCESS 태스크 없음
              └─▶ 새 IssuanceTask { triggered_by: MANUAL, visible_to_user_at: now }
                   └─▶ Celery dispatch → issuance-worker
                        ├─▶ SUCCESS: File 저장, 알림 발송
                        └─▶ FAILED: error_code 기록, 알림 발송

[사용자가 등기부등본 발급 버튼 클릭]
    └─▶ request_issuance(triggered_by=MANUAL, doc_type=REGISTRY)
         └─▶ 항상 새 IssuanceTask { triggered_by: MANUAL, visible_to_user_at: now }
              └─▶ Celery dispatch → issuance-worker
                   ├─▶ SUCCESS: File 저장, 알림 발송
                   └─▶ FAILED: error_code 기록, 알림 발송

[사용자가 PDF 직접 업로드]
    └─▶ IssuanceTask { triggered_by: MANUAL_UPLOAD, visible_to_user_at: now, status: SUCCESS }
         → 즉시 UI에 노출됨, 알림 발송
```

### 이미 진행 중인 태스크가 있을 때

- **PROCESSING** 태스크가 있으면 중복 dispatch 방지를 위해 재사용 (triggered_by 무관)
- **PENDING** 태스크가 있으면 stale 여부 확인 (생성 후 5분 초과 = stale)
  - stale이 아니면 재사용
  - stale이면 FAILED로 마감 후 새 태스크 생성
- PENDING/PROCESSING 재사용 시 MANUAL 요청이면 `visible_to_user_at` 기록
