---
title: "[둥지] 실시간 알림 아키텍처 결정기: 폴링, Redis Pub/Sub, PostgreSQL LISTEN/NOTIFY"
date: 2026-03-30 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Redis, SSE, Celery, PostgreSQL, Architecture, Backend, RealTime, PubSub, FCM]
toc: true
comments: true
image: /assets/img/posts/2026-03-30-doongzi-realtime-notification-architecture/1.png
description: "둥지 서비스의 비동기 알림 시스템을 설계하며 폴링, Redis Pub/Sub + SSE, PostgreSQL LISTEN/NOTIFY를 비교한 과정을 정리합니다. 최종적으로 Redis Pub/Sub + SSE를 선택한 이유와 Redis DB 번호 분리 전략까지 다룹니다."
---

둥지 서비스에는 등기부등본 자동 발급, OCR 분석처럼 수초에서 수십 초가 걸리는 비동기 작업들이 있습니다. Celery Worker가 이 작업을 처리하는 동안 프론트엔드는 결과를 어떻게 받아야 할까요?

***"작업이 끝났다는 사실을 백엔드가 프론트에게 어떻게 알려줄 것인가."***

이것이 이번 설계의 핵심 질문이었습니다.

## 가장 단순한 방법 — 폴링(Polling)

처음 떠오르는 방법은 프론트엔드가 주기적으로 상태를 조회하는 폴링입니다.

```
프론트엔드 → GET /notifications?unread=true (3초마다)
         ← 백엔드가 DB에서 조회 후 반환
```

구현이 간단하고 별도 인프라가 필요 없습니다. 하지만 치명적인 문제가 있습니다.

- **DB 부하:** 알림이 없어도 3초마다 `SELECT` 쿼리가 발생합니다. 100명이 동시에 접속하면 분당 2,000건의 무의미한 쿼리가 DB를 두드립니다.
- **실시간성의 한계:** 3초 간격이라면 최대 3초의 지연이 발생합니다. 간격을 줄이면 부하가 더 심해지는 딜레마가 생깁니다.

폴링은 규모가 커질수록 스스로를 무너뜨리는 구조입니다. 다른 방법을 찾아야 했습니다.

## 세 가지 대안 비교

### 1. Redis Pub/Sub + SSE

둥지 아키텍처에는 이미 Redis가 구축되어 있었습니다. Redis의 Pub/Sub(발행/구독) 기능을 SSE(Server-Sent Events)와 결합하면 폴링 없이 실시간 알림을 구현할 수 있습니다.

데이터 흐름은 이렇습니다.

1. **Publish (Celery Worker):** 워커가 작업을 완료하면 `Notification` 테이블에 `INSERT`하고, 동시에 Redis 채널(`channel:noti:{user_id}`)에 이벤트를 발행합니다.
2. **Subscribe (FastAPI):** 유저가 접속하면 FastAPI SSE 엔드포인트에 연결을 맺습니다. FastAPI는 DB를 조회하는 대신 Redis 채널만 구독한 채로 대기합니다.
3. **Push (FastAPI → Frontend):** 워커가 Redis에 이벤트를 발행하는 즉시, 대기 중이던 FastAPI가 감지하고 브라우저로 알림 데이터를 밀어줍니다.

```
Celery Worker
  ├─ DB: INSERT INTO notifications
  └─ Redis PUBLISH channel:noti:{user_id}
          ↓
      FastAPI (SUBSCRIBE 대기 중)
          ↓
      SSE Push → 브라우저
```

DB는 알림 생성 시 딱 한 번만 일하고, 이후 실시간 전달은 메모리 기반의 Redis가 전담합니다.

**장점:** 구현이 직관적이고, 이미 구축된 Redis 인프라를 활용합니다. 폴링 쿼리가 0건이 됩니다.

**단점:** SSE는 HTTP 연결을 장기간 유지하는 방식이라, 유저가 많아질수록 서버에 열려 있는 커넥션 수가 증가합니다.

### 2. PostgreSQL LISTEN / NOTIFY

Redis 없이 DB만으로 실시간 알림을 구현하는 방법도 있습니다. PostgreSQL에는 고유한 이벤트 시스템인 `LISTEN / NOTIFY`가 내장되어 있습니다.

Celery 워커가 `INSERT` 시 트리거를 통해 `NOTIFY` 이벤트를 발생시킵니다. FastAPI는 `asyncpg` 라이브러리로 `LISTEN` 상태로 대기하다가, DB가 밀어주는 이벤트를 수신해 SSE로 전달합니다.

**장점:** 별도 인프라 추가 없이 폴링을 제거할 수 있습니다.

**단점:** DB 연결이 장기 유지 커넥션으로 사용됩니다. PostgreSQL의 연결 수는 제한적이므로, 동시 접속자가 늘수록 커넥션 풀 고갈 위험이 높아집니다. 또한 Redis보다 이벤트 처리 레이턴시가 높습니다.

### 3. 단순 폴링 (Polling)

앞서 설명한 방식입니다. 구현이 가장 단순하지만, DB 부하와 실시간성의 한계라는 구조적 문제를 안고 있습니다.

### 비교 요약

| 방식 | DB 부하 | 실시간성 | 추가 인프라 | 커넥션 관리 |
|---|---|---|---|---|
| 폴링 | 높음 (주기적 SELECT) | 간격만큼 지연 | 없음 | 단순 |
| Redis Pub/Sub + SSE | 낮음 (INSERT 1회) | 즉각 | Redis (기존 활용) | 장기 연결 분리 필요 |
| PostgreSQL LISTEN/NOTIFY | 낮음 | 즉각 | 없음 | DB 커넥션 압박 |

## 결정: Redis Pub/Sub + SSE

**Redis Pub/Sub + SSE**를 선택했습니다.

근거는 다음과 같습니다.

1. **인프라 추가 비용 없음:** 둥지는 이미 Celery 브로커로 Redis를 사용하고 있습니다. Pub/Sub은 Redis의 내장 기능이므로 별도 서비스를 추가할 필요가 없습니다.

2. **DB에서 알림 로직을 분리:** PostgreSQL `LISTEN/NOTIFY`는 DB 커넥션을 장기 유지 목적으로 사용하게 됩니다. DB 연결은 값비싼 자원입니다. 이벤트 스트리밍 역할은 그 목적에 맞게 설계된 Redis에 맡기는 것이 올바른 역할 분리입니다.

3. **폴링의 근본적 한계 회피:** 실시간 이벤트 전달을 Pull(프론트가 당김) 구조가 아닌 Push(서버가 밀어줌) 구조로 전환합니다. DB를 불필요하게 두드리지 않습니다.

---

## SSE만으로 충분한가 - FCM과의 역할 구분

Redis Pub/Sub + SSE 방식을 채택했지만, 한 가지 전제가 있습니다. SSE는 **유저가 둥지 화면을 열어두고 있을 때**만 작동합니다.

발급이나 분석 과정이 길어져 유저가 탭을 닫거나 앱을 이탈하면 SSE 연결이 끊어지고, 그 순간부터는 알림을 전달할 방법이 없습니다.

| 기술 | 동작 환경 | 둥지 적용 예시 |
|---|---|---|
| **SSE** | 유저가 둥지 화면을 **켜두고 있을 때** | 체크리스트 화면에서 "건축물대장 발급 완료!" 팝업 노출 |
| **FCM** | 유저가 둥지를 **닫고 다른 작업 중일 때** | 잠금화면에 "등기부등본 분석이 완료되었습니다." 알림 진동 |

등기부등본 발급과 OCR 분석이 10초 이내에 끝난다면 유저가 화면을 보고 있을 확률이 높으므로 SSE만으로도 충분합니다.

하지만 처리가 지연되어 5분을 넘어가는 상황이 생기면, 이탈한 유저에게 FCM(앱 푸시)이나 카카오 알림톡을 병행하는 **하이브리드 아키텍처**가 필요합니다. 이 시나리오는 향후 발급 성공률이 안정화된 뒤 도입을 검토할 예정입니다.

### 알림 권한 거부에 대한 방어 전략

FCM은 유저가 브라우저 알림 권한을 거부하면 전달되지 않습니다. 이 경우를 대비해 `Notification` 테이블이 인앱 알림 센터 역할을 합니다.

유저가 브라우저 알림을 놓쳤더라도, 둥지에 다시 접속했을 때 우측 상단 종 아이콘에 **읽지 않은 알림 뱃지**를 표시해 시스템 알림을 놓치지 않게 합니다. DB에 저장된 알림 기록이 최종 안전망 역할을 하는 구조입니다.

---

## Redis Pub/Sub 구현 시 DB 번호 분리

Redis Pub/Sub + SSE 방식을 채택했지만, 구현 시 한 가지 더 결정해야 할 것이 있었습니다. 

***기존 캐시용 Redis와 같은 DB를 쓸 것인가, 별도 DB 번호를 할당할 것인가.***

### 역할별 DB 번호 구분

| DB | 역할 | 데이터 특성 |
|---|---|---|
| DB 2 | 상태 및 만료 관리 (캐시) | 이메일 인증 토큰, Rate Limit 카운터, API 응답 캐시. TTL이 있는 Key-Value |
| DB 3 | 실시간 이벤트 버스 (Pub/Sub) | 알림 메시지를 저장하지 않고 구독자에게 즉시 스트리밍. 상태 없음(Stateless) |

### DB 번호를 분리한 3가지 이유

**1. 커넥션 풀의 독립성 보장**

SSE용 Pub/Sub 커넥션은 클라이언트가 접속해 있는 동안 계속 열려 있는 **장기 연결(Long-lived connection)**입니다. DB 2 하나로 캐시와 SSE를 공용하면, 수백 명의 유저가 SSE 연결을 점유해 이메일 인증 토큰 조회 같은 단기 커넥션이 부족해지는 **풀 고갈(Pool Exhaustion)**이 발생할 수 있습니다.

DB 3으로 별도 커넥션 풀을 분리하면 두 기능이 서로의 성능에 영향을 주지 않습니다.

**2. 장애 격리 및 모니터링**

`redis-cli`로 디버깅할 때, DB 2의 순간적인 CRUD 트래픽과 DB 3의 지속적인 스트리밍 커넥션을 분리해서 관제할 수 있어 병목 지점을 찾기 훨씬 수월해집니다.

**3. 물리적 인프라 확장 대비**

서비스가 성장해 Redis 인스턴스 하나로 버티기 어려워지면, 캐시 전용 Redis와 메시지 브로커 전용 Redis를 물리적으로 분리해야 합니다. 지금처럼 `redis_pubsub_url`을 별도 프로퍼티로 분리해두면, 나중에 환경변수만 교체하여 무중단에 가깝게 인프라를 확장할 수 있습니다.

> **참고:** Redis 내부적으로 Pub/Sub 채널은 DB 번호의 경계를 무시하고 전역(Global) 공간에서 동작합니다. 즉, 물리적인 데이터 격리는 일어나지 않습니다. 하지만 애플리케이션 레벨의 **커넥션 관리와 아키텍처 분리** 측면에서 DB 번호를 나누는 것은 실무에서 권장하는 모범 사례입니다.

---

## 정리

| 결정 사항 | 선택 | 핵심 근거 |
|---|---|---|
| 실시간 알림 전달 방식 | Redis Pub/Sub + SSE | 기존 Redis 활용, DB 부하 제거, Push 구조 |
| 폴링 vs Pub/Sub | Pub/Sub | 무의미한 SELECT 쿼리 제거 |
| PostgreSQL LISTEN/NOTIFY | 미채택 | DB 커넥션을 장기 연결 목적으로 쓰는 것은 역할 혼용 |
| SSE + FCM 전략 | SSE 우선, FCM 향후 검토 | 10초 내 완료 시 SSE로 충분, 이탈 시나리오는 추후 도입 |
| Redis DB 번호 분리 | DB 2(캐시) / DB 3(Pub/Sub) | 커넥션 풀 독립성, 장애 격리, 확장성 |

폴링의 DB 부하 문제를 출발점으로, 이미 구축된 Redis 인프라를 Pub/Sub 이벤트 버스로 활용하는 방향으로 수렴했습니다. 알림 권한 거부나 유저 이탈 시나리오는 `Notification` DB와 향후 FCM 도입으로 단계적으로 보완할 예정입니다.

### 레퍼런스

- [Firebase Cloud Messaging(FCM)](https://firebase.google.com/docs/cloud-messaging?hl=ko)
- [Server-Sent Events 사용하기 - MDN](https://developer.mozilla.org/ko/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [LISTEN & NOTIFY 명령으로 구현하는 비동기식 작업](https://postgresql.kr/blog/pg_listen_notify.html)

