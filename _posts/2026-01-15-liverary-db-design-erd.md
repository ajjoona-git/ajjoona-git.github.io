---
title: "[LIVErary] 메타버스 독서 플랫폼 DB 설계: 단일 테이블 전략과 데이터 분리"
date: 2026-01-15 09:00:00 +0900
categories: [Projects, LIVErary]
tags: [DatabaseDesign, DB, ERD, SystemArchitecture, Refactoring, Redis, Optimization, RBAC]
toc: true 
comments: true
image: /assets/img/posts/2026-01-15-liverary-db-design-erd/1.jpg
description: "서로 다른 성격의 3가지 공간(열람실, 북토크, 북콘서트)을 단일 테이블 전략(Single Table Strategy)으로 통합하고, 글로벌 권한과 세션 권한을 분리하여 유연성을 확보한 DB 설계 과정입니다. 실시간 데이터와 영속성 데이터를 분리한 최적화 전략도 포함합니다."
---

프로젝트 **LIVErary**는 2층 열람실(독서), 3층 북토크(소통), 4층 북콘서트(강연)라는 각기 다른 성격의 공간을 제공하는 메타버스 독서 모임 플랫폼이다.

기획 단계에서는 "공간이 다르니 테이블도 나눠야 하지 않을까?"라고 생각했지만, 설계를 구체화하며 **유지보수성**과 **확장성**을 고려했다. 이번 포스팅에서는 ERD 설계 과정에서 마주쳤던 3가지 의문점과 그 해결책을 공유한다.

---

## Issue 1. 다형성(Polymorphism) 데이터 처리

### 성격이 다른 3개의 층(Room), 테이블을 쪼갤 것인가 합칠 것인가?

각 층의 비즈니스 로직은 판이하게 다르다.

- **2층:** WebRTC 불필요. 타이머 기능 중요.
- **3층:** Public/Private 구분, 다인원 WebRTC 기능 필요.
- **4층:** 저자/청중 구분 필요. 저자의 화면 공유 기능 필요. 매니저에 발언권 제어 권한 부여.

처음에는 `READING_ROOM`, `TALK_ROOM`, `CONCERT_ROOM` 3개의 테이블로 나누는 **TPC(Table Per Concrete class)** 전략을 고려했다. 하지만 이 경우 **"현재 라이브 중인 모든 방을 보여주세요"**라는 메인 페이지 쿼리가 복잡해질 수 있다.

### 데이터의 본질에 집중하자.

그래서 다시 데이터의 본질에 집중했다. 층별 로직은 다르지만, **데이터의 90%는 공통 속성(제목, 인원수, 상태, 시작시간)**이라는 점을 발견했다.

단일 테이블 전략(Single Table Strategy)으로 변경하고, 모든 방을 **`ROOM`** 테이블 하나로 통합했다. 여기에 `room_type` (Enum: READING, TALK, CONCERT) 컬럼으로 층을 구분한다. 3층에만 필요한 `invite_code`나 4층에 필요한 `book_id` 같은 필드는 Nullable로 두어 유연하게 대처했다.

조회 쿼리가 단순해졌고(`SELECT * FROM ROOM WHERE status = 'LIVE'`), 추후 '5층 명상실'이 추가되어도 DB 스키마 변경 없이 Enum만 추가하면 되는 확장성을 얻었다.

---

## Issue 2. 맥락에 따른 역할(Contextual Role) 분리

### Author이지만, 가끔은 User가 되고 싶어.

**"유저 테이블의 Role과 방 안에서의 Role은 다르다."**

USER 테이블에는 ADMIN, USER, MANAGER, AUTHOR 같은 권한이 존재한다. 하지만 북콘서트(4층)에서는 특정 유저가 '저자(AUTHOR)'가 되어야 하고, 스태프는 '관리자(MANAGER)'가 되어야 한다.

단순히 USER 테이블의 Role을 믿고 권한을 부여하면, 저자가 2층 열람실에 공부하러 갔는데 화면 공유 버튼이 활성화되는 문제가 발생할 수 있다. 혹은 저자가 본인이 저자임을 숨기고 한 명의 유저로서 다른 유저들과 소통하고 싶을 수도 있다.

### Gloabal Role과 Session Role을 분리하자.

그래서 **신분증**과 **완장**을 분리했다. 유저를 생성할 때의 권한을 USER, ADMIN 두 가지로 제한하고, 각 방에서의 역할을 별도로 만들었다.

- **Global Role (`USER` 테이블):** 사이트 전체의 회원 등급 (USER, ADMIN)
- **Session Role (`ROOM_HISTORY` 테이블):** **해당 방 안에서만** 유효한 역할 (GUEST, MANAGER, AUTHOR)

이를 통해 유저는 사이트 내에서 일반 회원이지만, **특정 방에 들어갈 때만 `MANAGER` 완장**을 차고 활동할 수 있다. 또한 모호했던 `HOST` 역할을 제거하고 **`MANAGER`**로 통합하여 로직을 단순화했다.

---

## Issue 3. 실시간성 데이터와 영속성 데이터의 분리

### 마이크 On/Off와 독서 타이머 로그, 어디에 저장할까?

LIVERARY는 실시간 상호작용이 핵심이다.

1. 사용자가 마이크를 껐다 켰다 하는 상태 (`MUTE` / `UNMUTE`)
2. 사용자의 누적 독서 시간

이 모든 것을 DB에 `UPDATE` 쿼리로 날린다면? 수십 명의 유저가 1초마다 상태를 바꿀 때 DB 부하가 감당할 수 없을 만큼 커진다.

### Volatile in Memory, Persistent in DB

데이터의 성격에 따라 저장소를 철저히 분리했다.

1. **휘발성 데이터 (마이크 상태):**
    - DB에 저장하지 않는다.
    - **WebSocket**과 메모리(Redis)를 통해 실시간으로 브로드캐스팅만 수행한다.
    - 지연 시간(Latency)을 최소화한다.
2. **영속성 데이터 (독서 시간):**
    - 타이머가 돌아가는 동안에는 메모리에서만 카운트한다.
    - 유저가 **퇴장하는 순간**에만 `USER` 테이블의 `total_reading_time` 컬럼에 `UPDATE` 한다.
    - DB 트랜잭션을 세션당 딱 1번(입장) + 1번(퇴장)으로 최소화한다.

---

## 마치며

이번 ERD 설계의 핵심 철학은 **"DB 테이블 구조는 최대한 단순하게(Simple) 가져가고, 복잡한 비즈니스 로직은 애플리케이션 계층(Java)에서 처리하자"**는 것이었다.

ERD를 직접 설계하는 것은 처음이었는데 생각보다 고려해야 할 사항들이 많다는 것을 느꼈다. 개발 중에 최대한 수정이 필요 없도록 현재 MVP 뿐만 아니라 추가 기능까지 고려해서 ERD를 작성했다. 그래도 기능 정의하면서 DB 필드를 간략하게나마 정해두어서 빠르고 완성도있는 ERD를 그릴 수 있었다.

![ERD Diagram](/assets/img/posts/2026-01-15-liverary-db-design-erd/1.jpg)
*ERD Diagram*