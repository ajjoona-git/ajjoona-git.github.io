---
title: "[LIVErary] JPA Dirty Checking과 Bulk 연산 혼용 시 데이터 증발 문제 (feat. flushAutomatically)"
date: 2026-01-29 09:00:00 +0900
categories: [Projects, LIVErary]
tags: [SpringBoot, JPA, Troubleshooting, BulkUpdate, DirtyChecking, Scheduler, PersistenceContext, Modifying, Transactional]
toc: true
comments: true
description: "스케줄러 테스트 중 방 상태 변경(Dirty Checking)이 DB에 반영되지 않고 증발하는 문제를 해결했습니다. 트랜잭션 내에서 벌크 연산과 영속성 컨텍스트 관리가 충돌하는 원인을 분석하고 @Modifying 옵션으로 해결한 과정을 공유합니다."
---

**'방 종료 스케줄러(`autoCloseFinishedRooms`)'** 기능을 구현하고 테스트하는 과정에서, 로직상 완벽해 보이는 코드가 예상대로 동작하지 않는 문제가 생겼다.

트랜잭션 하나 안에서 **JPA의 변경 감지(Dirty Checking)**와 **JPQL 벌크 연산(Bulk Update)**을 함께 사용할 때 발생한 데이터 동기화 이슈였다.

---

## 배경: 방 종료 스케줄러 (`autoCloseFinishedRooms`)

스케줄러는 트랜잭션(`@Transactional`) 하나 안에서 다음 두 가지 작업을 순차적으로 수행해야 했다.

1.  **방 상태 변경:** 종료 시간이 지난 방(`Room`)의 상태를 `LIVE` → `FINISHED`로 변경 (JPA Dirty Checking 활용)
2.  **참여자 퇴장 처리:** 해당 방에 있는 참여자(`RoomHistory`)들의 상태를 `LEFT`로 일괄 변경 (JPQL Bulk Update 활용)

```java
@Transactional
public void autoCloseFinishedRooms() {
    // 1. 방 상태 변경 (Dirty Checking)
    room.updateStatus(RoomStatus.FINISHED);

    // 2. 참여자 일괄 퇴장 (Bulk Update)
    roomHistoryRepository.exitAllUsersByRoom(room);
}

```


## 문제: 테스트 실패

단위 테스트를 실행했는데, 참여자들은 모두 퇴장 처리(`LEFT`)가 되었으나, 정작 방의 상태는 변경되지 않고 `LIVE`로 남아있었다.

```text
// 테스트 실패 로그 
Expected : FINISHED 
Actual   : LIVE

```

로그를 확인해보니 `RoomHistory`를 업데이트하는 `UPDATE` 쿼리는 나갔지만, `Room`의 상태를 변경하는 `UPDATE` 쿼리는 **아예 실행조차 되지 않았다.**

## 원인 분석

### 원인 1: `@Modifying` 어노테이션의 부재

벌크 연산을 수행하는 쿼리에 `@Modifying`을 작성하지 않았을 때, 애플리케이션은 실행 시점에 즉시 에러가 발생했다.

- **발생 에러:** 
```text
org.springframework.dao.InvalidDataAccessApiUsageException: Query executed via 'getResultList()' or 'getSingleResult()' must be a 'select' query
```

- **에러 원인:** Spring Data JPA의 `@Query`는 기본적으로 **조회(SELECT) 전용**으로 설계되어 있다.
    - `@Modifying`이 없으면 JPA는 해당 쿼리를 실행할 때 내부적으로 `SELECT` 쿼리용 메서드인 `getResultList()` 등을 호출한다.
    - 하지만 실제 쿼리는 `UPDATE` 문이었기 때문에, JPA가 이를 실행하지 못하고 "이 메서드는 SELECT 쿼리만 지원한다"며 거부한 것.

따라서 변경 작업을 수반하는 쿼리에는 반드시 `@Modifying`을 명시하여, JPA가 해당 쿼리를 `executeUpdate()` (데이터 변경용 메서드) 방식으로 처리하도록 알려주어야 한다.


### 원인 2: 영속성 컨텍스트 관리 옵션 충돌

**"하나의 트랜잭션 내에서 Dirty Checking(지연 쓰기)과 Bulk 연산(즉시 실행)이 섞여 있을 때, 영속성 컨텍스트 관리 옵션(`clearAutomatically`)이 충돌했기 때문"**이었다.

1. **`room.setStatus(FINISHED)` 호출:**
* JPA의 변경 감지 메커니즘에 의해, 변경 사항은 즉시 DB로 가지 않고 **영속성 컨텍스트(메모리)**에 대기한다. (쓰기 지연)


2. **`repository.exitAllUsersByRoom(...)` 호출 (Bulk Update):**
* 이 메서드에는 `@Modifying(clearAutomatically = true)` 옵션이 걸려 있었다.
* 벌크 연산은 영속성 컨텍스트를 무시하고 DB에 직접 쿼리를 날린다.


3. **문제 발생 (Data Loss):**
* 쿼리 실행 직후 `clearAutomatically = true`에 의해 영속성 컨텍스트가 **초기화(Clear)** 되었다.
* 이때, 1번에서 대기 중이던 `Room` 상태 변경 쿼리가 **DB로 전송(Flush)되기도 전에 메모리에서 삭제(증발)**되어 버렸다.


4. **트랜잭션 커밋:**
* 트랜잭션이 끝날 때 JPA가 할 일을 찾았지만, 영속성 컨텍스트는 이미 비워져 있었기에 아무런 쿼리도 날리지 않았다.



## 시도 및 해결

### 시도 1: 순서 변경 (실패)

벌크 연산을 먼저 하고, 방 상태를 나중에 변경해 보았다.

* **결과:** 벌크 연산 후 `clear` 되면서 `Room` 객체가 **준영속(Detached)** 상태가 되어버려, 이후의 `setStatus`가 무시되었다.

### 시도 2: 수동 Flush (성공했으나 비권장)

테스트 코드 중간에 `em.flush()`를 강제로 호출했다.

* **결과:** 테스트는 통과했지만, 비즈니스 로직의 결함을 테스트 코드로 덮는 임시방편이라 채택하지 않았다.

### 최종 해결: `@Modifying` 옵션 수정

Repository의 벌크 연산 메서드에 **`flushAutomatically = true`** 옵션을 추가했다.
이는 **"메모리를 비우기(Clear) 전에 변경 사항을 먼저 DB에 반영(Flush)하도록"** 강제하는 옵션이다.

```java
// RoomHistoryRepository.java
@Modifying(clearAutomatically = true, flushAutomatically = true) // [해결 핵심]
@Query("UPDATE RoomHistory rh SET rh.status = :newStatus ...")
void exitAllUsersByRoom(...);

```

이 옵션을 적용하자 실행 순서가 다음과 같이 정상화되었다.

**Flush(방 상태 변경 반영) → Bulk Update(참여자 퇴장) → Clear(영속성 컨텍스트 초기화)**


---

## 마치며

이 문제를 통해 JPA의 영속성 컨텍스트 관리와 트랜잭션의 동작 원리를 이해할 수 있었다.

1. **쓰기 지연 (Write Behind):**
    - JPA는 엔티티 수정 시 바로 쿼리를 날리지 않고, 트랜잭션 커밋 시점이나 `flush` 호출 시점에 모아서 보낸다.
2. **벌크 연산 (Bulk Operation):**
    - `@Query`로 작성된 `UPDATE`/`DELETE` 문은 영속성 컨텍스트를 거치지 않고 DB에 바로 실행된다. 이로 인해 'DB'와 '애플리케이션 메모리' 간의 데이터 불일치가 생길 수 있다.
3. **`@Modifying`의 옵션:**
    - JPA 인터페이스에서 `@Query`를 통해 커스텀 쿼리를 작성할 때, 조회(SELECT)가 아닌 변경(UPDATE, DELETE, INSERT) 작업이라면 반드시 `@Modifying` 어노테이션을 붙여야 한다.
    - `clearAutomatically = true`: 벌크 연산 후 영속성 컨텍스트를 비워 데이터 불일치를 막는다. (조회 시 DB에서 새로 가져옴)
    - `flushAutomatically = true`: 벌크 연산 전 영속성 컨텍스트의 변경 사항을 DB에 미리 반영하여, **변경 사항 증발**을 막는다.


---

### 레퍼런스

{% linkpreview "https://ajjoona-git.github.io/posts/jpa-transaction-and-persistence-context/" %}

{% linkpreview "https://ajjoona-git.github.io/posts/liverary-room-scheduler-logic/" %}
