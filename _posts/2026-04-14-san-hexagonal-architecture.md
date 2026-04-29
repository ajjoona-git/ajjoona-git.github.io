---
title: "[SAN] 오픈소스 설계: 헥사고날 vs 레이어드 아키텍처, 그리고 엔진-서비스 분리"
date: 2026-04-14 10:00:00 +0900
categories: [Project, SAN]
tags: [Architecture, HexagonalArchitecture, LayeredArchitecture, OpenSource, Backend, API, DDD, Python]
toc: true
comments: true
description: "SAN 프로젝트의 리콜 엔진을 오픈소스로 설계하면서 헥사고날 아키텍처와 레이어드 아키텍처를 비교하고, 도메인 기반 레이어드 구조를 선택한 과정을 정리합니다."
---

**SAN(Scrap & Notify)**은 비정형 데이터를 저장하고, 현재 맥락과 연결해 다시 꺼내 쓸 수 있는 **리콜(Recall)** 기능을 핵심으로 하는 프로젝트입니다. 엔진을 독립 모듈로 분리하고 오픈소스로 공개하는 구조를 설계하면서, 내부 아키텍처로 헥사고날과 레이어드 중 무엇을 택할지 검토했습니다.

---

## 엔진-서비스 분리를 선택한 이유

초기 설계에서 두 가지 방향이 충돌했습니다.

> "크롬 확장프로그램 하나만 만들 것인가, 아니면 백엔드를 독립 엔진으로 분리할 것인가?"

서비스에 모든 기능을 묶으면 개발은 빠릅니다. 하지만 기능이 특정 UI에 종속되고, 다른 환경에서는 재사용이 불가능해집니다. SAN을 오픈소스로 가치 있게 만들려면 **핵심 로직이 서비스 바깥에서도 독립적으로 동작해야** 했습니다.

그래서 방향을 고정했습니다.

**핵심 기능은 엔진으로 분리하고, 서비스는 그 엔진을 REST API로 호출하는 구조.**

분리 방향은 정했고, 그 다음이 엔진 내부 아키텍처 선택이었습니다.

---

## 레이어드 아키텍처

레이어드(계층형) 아키텍처는 Controller → Service → Repository 순서로 계층이 나뉘고, 요청은 위에서 아래로 흐릅니다.

### 패키지 구조

```
domain/
  til/
    controller/   ← Presentation Layer
    dto/
    service/      ← Business Layer
    entity/
    repository/   ← Persistence Layer
  user/
  recall/
global/
  config/
  external/ai/
```

도메인별로 폴더를 묶었지만, 각 도메인 안은 전통적인 3계층을 그대로 따릅니다.

### 의존성 방향

```
Controller → Service → Repository(JPA) → DB
```

Service가 Repository를 직접 참조하고, `entity/`에 `@Entity`, `@Table` 등 JPA 어노테이션이 위치합니다.

### 장점

- 구조가 직관적이고 팀원 전체가 빠르게 이해 가능
- Spring Boot 표준 패턴과 일치해 러닝커브 낮음
- 소규모 프로젝트에서 불필요한 보일러플레이트 없음

### 한계

도메인이 커질수록 문제가 생깁니다.

- 도메인 계층이 DB에 의존하게 되어, DB 변화가 도메인 계층까지 전파됨
- Service 간 순환 참조, 코드 응집도 저하
- Spring, JPA가 비즈니스 로직 깊숙이 침투해 기술과 독립적인 테스트가 어려워짐
- 계층 스킵이 가능해 경계를 강제할 수 없고, 시간이 지날수록 의도하지 않은 의존성이 스며듦

---

## 헥사고날 아키텍처

헥사고날 아키텍처는 Alistair Cockburn이 제안한 **포트와 어댑터(Ports and Adapters)** 패턴입니다.

> **도메인 로직을 외부 세계로부터 완전히 격리한다.**

도메인은 Spring, JPA, HTTP 등 어떤 프레임워크도 알지 못합니다. 외부와의 소통은 오직 포트(인터페이스)를 통해서만 이루어지고, 그 구현은 어댑터가 담당합니다.

### 패키지 구조

```
domain/til/
  ├── domain/                        ← 순수 도메인 (프레임워크 의존 없음)
  │   ├── Til.java                   ← 도메인 객체 (not @Entity)
  │   └── TilStatus.java
  │
  ├── application/
  │   ├── port/
  │   │   ├── in/                    ← Inbound Port (인터페이스)
  │   │   │   ├── CreateTilUseCase.java
  │   │   │   └── GetTilUseCase.java
  │   │   └── out/                   ← Outbound Port (인터페이스)
  │   │       ├── SaveTilPort.java
  │   │       └── LoadTilPort.java
  │   └── service/
  │       └── TilService.java        ← UseCase 구현, Port만 사용
  │
  └── adapter/
      ├── in/
      │   └── web/                   ← Inbound Adapter
      │       ├── TilController.java
      │       └── dto/
      └── out/
          └── persistence/           ← Outbound Adapter
              ├── TilEntity.java     ← @Entity는 여기에만
              ├── TilRepository.java
              └── TilPersistenceAdapter.java  ← SaveTilPort 구현체
```

### 의존성 방향

```
Controller → UseCase(Port) ← Service → SaveTilPort ← PersistenceAdapter → JPA
```

- `TilService`는 `SaveTilPort` 인터페이스만 알고, JPA를 직접 모름
- `TilController`는 `CreateTilUseCase` 인터페이스만 알고, Service를 직접 참조 안 함
- `domain/` 패키지는 어떤 프레임워크도 import하지 않음

### 장점

- 도메인 로직을 프레임워크 없이 단독 테스트 가능
- DB, AI 모델 등 외부 시스템을 어댑터 교체만으로 변경 가능
- 의존성 방향이 항상 도메인을 향함 (의존성 역전)
- UseCase 단위로 비즈니스 시나리오가 명확하게 드러남

---

## 두 아키텍처 비교

| 항목 | 헥사고날 | 레이어드 (도메인 기반) |
|---|---|---|
| `@Entity` 위치 | `adapter/out/persistence/` | `domain/til/entity/` |
| Repository | Port 인터페이스 + Adapter 구현체 분리 | JPA 인터페이스를 도메인 안에 직접 |
| Service 의존 | Outbound Port 인터페이스만 참조 | Repository 직접 참조 |
| Controller 의존 | Inbound Port(UseCase) 인터페이스만 참조 | Service 직접 참조 |
| 도메인 순수성 | 프레임워크 의존 없음 | JPA, Spring 어노테이션 포함 |
| 테스트 격리 | 도메인 단독 테스트 용이 | Mock 필요 |
| 외부 시스템 교체 | 어댑터만 교체 | 코드 여러 곳 수정 필요 |
| 초기 복잡도 | 높음 (파일/인터페이스 많음) | 낮음 |

---

## SAN의 선택: 도메인 기반 레이어드

SAN은 **도메인 기반 레이어드 아키텍처**를 선택했습니다.

이유는 다음과 같습니다.

- 단기간 개발하는 팀 프로젝트에서 헥사고날의 보일러플레이트는 부담
- 외부 시스템(AI 모델, DB) 교체 가능성보다 기능 완성이 우선
- 도메인별 패키징으로 관심사 분리는 충분히 확보
- 팀원 전체가 구조를 직관적으로 이해하고 협업 가능

오픈소스 관점에서도 레이어드 구조는 **외부 기여자가 코드를 빠르게 파악하기 쉽다**는 장점이 있습니다. 헥사고날의 포트/어댑터 분리는 익숙하지 않은 개발자에게 진입장벽이 될 수 있습니다.

헥사고날이 필요해지는 시점은, 서비스 규모가 커지고 팀이 성장해 레이어드의 한계가 구조적 문제로 드러날 때입니다. 당근페이처럼 그 시점에 전환을 고려하면 됩니다.


### 전체 시스템 구조

엔진-서비스 분리와 내부 레이어드 구조를 합치면 다음과 같습니다.

```
[크롬 확장프로그램]  [사내 지식관리]  [외부 개발자 서비스]
        ↓                 ↓                  ↓
        └─────────────────┴──────────────────┘
                          ↓
               [ REST API (경계) ]
               POST /scrap / GET /search / POST /recall
                          ↓
               [ 리콜 엔진 서버 ]
               ┌─────────────────────┐
               │  Controller Layer   │
               │  Service Layer      │
               │  Repository Layer   │
               └─────────────────────┘
                          ↓
               [ DB / 임베딩 모델 ]
```

엔진 내부는 레이어드 구조지만, 외부 서비스 입장에서는 REST API라는 명확한 경계가 존재합니다. 이 경계가 헥사고날의 포트 역할을 시스템 레벨에서 담당합니다.

---

## 마치며

헥사고날 아키텍처는 외부 시스템 교체와 테스트 격리에 강하지만, 팀 규모와 개발 기간에 맞지 않으면 복잡도만 높아집니다. 당근페이도 레이어드로 시작해 문제를 직접 겪은 뒤 헥사고날로 전환했습니다. SAN은 도메인 기반 레이어드 구조로 관심사 분리를 확보하면서, REST API 경계로 엔진과 서비스를 분리해 오픈소스로서의 재사용 가능성을 만들었습니다.

### 레퍼런스

- [헥사고날 아키텍처 vs 레이어드 아키텍처](https://ivory-room.tistory.com/91)
- [당근페이 백엔드 아키텍처가 걸어온 여정](https://medium.com/daangn/%EB%8B%B9%EA%B7%BC%ED%8E%98%EC%9D%B4-%EB%B0%B1%EC%97%94%EB%93%9C-%EC%95%84%ED%82%A4%ED%85%8D%EC%B2%98%EA%B0%80-%EA%B1%B8%EC%96%B4%EC%98%A8-%EC%97%AC%EC%A0%95-98615d5a6b06)
