---
title: "JPA 영속성 컨텍스트(Persistence Context)와 DB의 동기화"
date: 2026-01-29 10:00:00 +0900
categories: [Tech, Java]
tags: [SpringBoot, Java, JPA, Hibernate, PersistenceContext, Transaction, BulkUpdate, Memory]
toc: true
comments: true
image: /assets/img/posts/2026-01-29-jpa-transaction-and-persistence-context/2.png
description: "JPA 사용 시 데이터가 증발하는 현상을 이해하기 위해 트랜잭션과 영속성 컨텍스트(메모리)의 관계를 파헤칩니다. 쓰기 지연(Write Behind)과 벌크 연산의 충돌 원리, 그리고 @Modifying을 통한 동기화 방법을 시스템 구조도와 함께 정리했습니다."
---

스프링 데이터 JPA를 사용하다 보면, 분명 코드로 데이터를 수정했는데 DB에는 반영되지 않고 **증발**해버리는 유령 같은 현상을 겪곤 한다.
단순히 `@Modifying`을 붙이면 해결된다는 것은 알지만, **도대체 내부에서 무슨 일이 벌어졌길래 데이터가 사라진 걸까?**

이 문제를 이해하려면 JPA가 데이터를 다루는 독특한 공간인 **'메모리(영속성 컨텍스트)'**와 **'트랜잭션'**의 관계를 먼저 이해해야 한다.

---

## 1. JPA 메모리 (Persistence Context)

개발자들이 흔히 **"JPA는 메모리에서 작업한다"**라고 말할 때, 그 메모리는 **JVM의 힙 메모리(Heap Memory)**, 더 구체적으로는 **영속성 컨텍스트(Persistence Context)**를 의미한다.

JPA는 DB와 대화할 때 효율성을 위해 **'중간 관리자'**를 하나 둔다.
* **코드:** "이 방 상태를 `FINISHED`로 바꿔."
* **영속성 컨텍스트:** "네, 알겠습니다. (DB에 바로 안 가고 기록해둠)"
* **DB:** (아직 아무 소식 못 들음)

이 중간 관리자는 **트랜잭션(Transaction)**이라는 업무 시간 동안 변경 사항을 차곡차곡 모아두었다가, 업무가 끝날 때(Commit) 한꺼번에 DB로 가져간다. 

이것이 바로 **'쓰기 지연(Write Behind)'**이자 **'변경 감지(Dirty Checking)'**의 핵심이다.

![시스템 구조도](/assets/img/posts/2026-01-29-jpa-transaction-and-persistence-context/2.png)
*시스템 구조도*

## 2. 문제의 발생: Bulk Operation

그런데 **벌크 연산(Bulk Operation)**은 이 규칙을 깬다.
`@Query("UPDATE ...")`로 작성된 JPQL은 메모리를 거치지 않고 **DB에 바로 쿼리를 날려버린다.**

여기서 **하나의 트랜잭션** 안에서 두 가지 방식이 섞일 때 사고가 터진다.

### 데이터 증발 시나리오

1.  **Dirty Checking:** `room.setStatus(FINISHED)`
    * 메모리에 **"Room 수정함 (대기 중)"**이라고 적어둔다.
2.  **Bulk Operation:** `repository.bulkUpdate()`
    * 이 쿼리는 DB로 직행한다.
    * **문제점:** 벌크 연산은 데이터 정합성을 위해 수행 후 **메모리를 강제로 비워버린다(`clear`).**
3.  **메모리 초기화:**
    * 메모리를 지운다. 메모리에는 아까 적어둔 **"Room 수정함"** 기록도 포함되어 있다.
4.  **트랜잭션 종료:**
    * 업무가 끝나고 메모리가 DB에 보고하려는데, 기록이 텅 비어있다.
    * **결과:** Room 상태 변경 내역은 DB에 반영되지 못하고 증발한다.



## 3. `@Modifying`의 동기화 옵션

이 문제를 막으려면 메모리와 DB 사이의 **동기화(Synchronization)** 절차가 필요하다. Spring Data JPA는 `@Modifying` 어노테이션을 통해 이 절차를 제어한다.

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("UPDATE ...")
void bulkUpdate(...);

```

### ① `flushAutomatically = true` (실행 전 데이터 보존)

* **의미:** "이 벌크 연산 쿼리를 날리기 직전에, 영속성 컨텍스트에 쌓인 변경 사항(Dirty Checking)을 전부 DB에 밀어넣어라(Flush)."
* **효과:** 메모리에 대기 중이던 `setStatus(FINISHED)` 쿼리가 즉시 DB로 전송된다. **데이터가 증발하지 않고 저장된다.**

### ② `clearAutomatically = true` (실행 후 데이터 갱신)

* **의미:** "쿼리 실행 직후에, 영속성 컨텍스트(캐시)를 깨끗이 비워라(Clear)."
* **효과:** 벌크 연산으로 DB 데이터가 바뀌었다. 옛날 데이터를 들고 있으면 안 되므로, 메모리를 비워서 다음 조회 시 **DB에서 최신 데이터를 가져오게 강제**한다.


## 트랜잭션의 흐름 제어

결국 이 문제는 **"하나의 트랜잭션 안에서 `지연 쓰기(JPA)`와 `즉시 쓰기(JPQL)`가 충돌해서 생긴 일"**이다.

옵션을 통해 트랜잭션 내부의 데이터 흐름을 다음과 같이 안전하게 바꿨다.

![데이터 흐름](/assets/img/posts/2026-01-29-jpa-transaction-and-persistence-context/1.png)
*데이터 흐름*

---

## 핵심 개념 정리

### ① `@Transactional` (테스트 환경)

- **역할:** 테스트 시작 시 트랜잭션을 시작하고, 테스트가 끝나면 **자동으로 롤백(Rollback)**한다.
- **특징:** 트랜잭션이 유지되는 동안 **영속성 컨텍스트(1차 캐시)**가 계속 살아있다.
- **문제점:** `room.setStatus(FINISHED)` 같은 변경 감지(Dirty Checking) 코드는 트랜잭션이 끝날 때(commit 시점) DB에 반영된다. 즉, 테스트 도중에는 **DB에 반영되지 않고 메모리에만 떠 있는 상태**가 된다.

### ② JPQL (`@Query`) & 벌크 연산

- **역할:** 엔티티 객체 대상이 아닌, DB에 직접 쿼리를 날리는 방식. (예: `UPDATE RoomHistory ...`)
- **특징:** JPA의 영속성 컨텍스트를 거치지 않고 **DB에 바로 꽂힌다.**
- **위험성:** 영속성 컨텍스트에 아직 DB로 안 넘어간 변경 사항이 있는데 JPQL이 먼저 실행되면, 데이터 순서가 꼬이거나 덮어씌워질 수 있다.

### ③ `@Modifying`

- **역할:** "이 쿼리는 조회가 아니라 데이터를 변경(INSERT, UPDATE, DELETE)하는 쿼리다"라고 스프링에게 알려준다.
- **필요성:** 이걸 안 붙이면 Hibernate가 조회(`executeQuery`)를 시도하다가 에러를 뱉는다. 데이터 변경 시엔 **필수**.


---

## 결론

JPA를 쓴다면 **영속성 컨텍스트(메모리)**의 존재를 항상 의식해야 한다. 특히 `@Query`로 `UPDATE/DELETE`를 할 때는, 내 메모리에 남아있는 수정 사항들이 안전하게 DB로 넘어갔는지(`Flush`) 확인하는 습관을 들이자.

1. `INSERT`, `UPDATE`, `DELETE` 쿼리를 직접 작성할 땐 **@Modifying**이 필수다.

2. 같은 트랜잭션 내에서 엔티티 수정이 있다면 **flushAutomatically = true**를 켜라.

3. 벌크 연산 후 같은 엔티티를 다시 조회해야 한다면 **clearAutomatically = true**를 켜라.