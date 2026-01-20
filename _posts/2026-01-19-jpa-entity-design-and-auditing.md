---
title: "JPA Entity 설계: 주요 어노테이션과 시간 관리(Auditing vs Manual)"
date: 2026-01-19 09:00:00 +0900
categories: [Tech, Java]
tags: [SpringBoot, JPA, Entity, Auditing, Lombok, Refactoring]
toc: true
comments: true
description: "JPA Entity 클래스를 작성할 때 사용되는 주요 어노테이션(@Entity, @Id, @Column 등)의 역할을 상세히 설명하고, 생성일/수정일과 같은 타임스탬프를 관리하는 두 가지 방법(JPA Auditing vs 수동 주입)을 비교합니다."
---

프로젝트의 도메인 설계를 코드로 옮기는 과정에서 **Entity(엔티티)** 클래스 작성은 가장 기초적이면서도 중요한 단계다.

이번 포스트에서는 **LIVERARY** 프로젝트의 `Room` 엔티티를 예시로, JPA의 주요 어노테이션들의 정확한 의미와 역할, 그리고 데이터의 생성/수정 시간을 관리하는 방법에 대해 정리해 본다.

---

## Entity 구현 순서

엔티티 클래스를 작성할 때는 **"의존성이 없는 것부터"** 만드는 것이 원칙이다. 다른 클래스를 참조하지 않는 독립적인 요소부터 만들어야 컴파일 에러 없이 매끄럽게 진행된다.

> **작성 순서:** Enum(상수) → 부모 엔티티(`Room`) → 자식 엔티티(`RoomHistory`)


## 주요 어노테이션 (Annotation Dictionary)

JPA와 Lombok 어노테이션들이 덕지덕지 붙어 있는 것 같지만, 하나하나가 데이터의 무결성과 성능을 위해 필수적인 역할을 한다.

### ① 객체와 테이블 매핑
* **`@Entity`**: "이 클래스는 DB 테이블과 1:1로 매핑된다"는 선언이다. JPA가 이 어노테이션을 보고 스키마를 관리한다.
* **`@Table(name="room")`**: DB에 생성될 실제 테이블 이름을 명시한다. 생략하면 클래스 이름(Room)을 따라가지만, 명시적으로 적어주는 것이 관례다.

### ② 식별자(PK) 전략
* **`@Id`**: 테이블의 **Primary Key(PK)**임을 지정한다.
* **`@GeneratedValue`**: PK 값을 직접 입력하지 않고 자동 생성하겠다는 뜻이다.
* **`@Column(columnDefinition = "BINARY(16)")`**:
    * **UUID 최적화:** UUID를 문자열(VARCHAR, 36자)로 저장하면 인덱스 성능이 떨어지고 공간 낭비가 심하다. 이를 이진 데이터(16바이트)로 압축 저장하여 성능을 높이는 설정이다.

### ③ 필드 및 컬럼 설정
* **`@Column(nullable = false)`**: SQL의 `NOT NULL` 제약조건이다. 필수 값임을 보장한다.
* **`@Enumerated(EnumType.STRING)`**: Enum(열거형) 타입을 저장하는 방식을 정한다.
    * **STRING (권장):** "READING" 문자열 그대로 저장한다. 직관적이다.
    * **ORDINAL (비권장):** 0, 1, 2 숫자로 저장한다. 중간에 Enum 순서가 바뀌면 데이터가 꼬일 위험이 크다.

### ④ Lombok(편의 기능) 설정
* **`@Getter`**: 모든 필드의 조회 메서드(`getXXX`)를 자동 생성한다. (Entity에는 `@Setter`를 가급적 쓰지 않는다.)
* **`@NoArgsConstructor(access = AccessLevel.PROTECTED)`**:
    * **필수:** JPA는 리플렉션을 통해 객체를 생성하므로 **기본 생성자**가 반드시 필요하다.
    * **PROTECTED:** 아무나 무분별하게 `new Room()`으로 빈 객체를 만들지 못하도록 막아 객체의 안정성을 높인다.
* **`@Builder`**: 생성자 대신 빌더 패턴(`Room.builder()...build()`)을 사용하여 가독성 있게 객체를 생성할 수 있게 한다.


## JPA Auditing vs 수동 관리

데이터베이스를 운영하다 보면 **"이 데이터 언제 만들어졌지?", "누가 수정했지?"**를 추적해야 할 일이 반드시 생긴다. 이를 위해 보통 4가지 필드를 공통으로 관리한다.

* `createdAt` (생성일시)
* `createdBy` (생성자)
* `updatedAt` (수정일시)
* `updatedBy` (수정자)

이것을 처리하는 방식은 크게 두 가지가 있다.

### 방식 A. JPA Auditing (자동화)
스프링 데이터 JPA가 제공하는 기능을 사용하여, 어노테이션만 붙이면 알아서 시간을 채워주는 방식이다.

```java
@EntityListeners(AuditingEntityListener.class) // 감시자 붙이기
public class Room {
    @CreatedDate // 생성 시 자동 주입
    private LocalDateTime createdAt;

    @LastModifiedDate // 수정 시 자동 주입
    private LocalDateTime updatedAt;
}
```

### 방식 B. 수동 주입 (Explicit Assignment)
현재 우리 프로젝트 코드에 적용된 방식이다. Auditing 기능을 끄고, 객체가 생성되는 시점(생성자)에 명시적으로 시간을 넣어주는 방식이다.

```java
// domain/Room.java

@Getter
@Table(name = "room")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
// @EntityListeners(AuditingEntityListener.class) // 제거됨
public class Room {

    // ... (필드 생략)

    @Column(updatable = false)
    private LocalDateTime createdAt; // @CreatedDate 제거

    @Column(updatable = false)
    private LocalDateTime updatedAt; // @LastModifiedDate 제거

    @Builder
    public Room(String title, User host, Integer maxUser, ...) {
        this.title = title;
        // ...
        
        // 생성 시점에 직접 시간 주입
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }
}
```

### 왜 수동으로 변경했는가? (Check Point)
보통은 편의성 때문에 JPA Auditing을 많이 사용한다. 하지만 다음과 같은 이유로 수동 코드를 선택하기도 한다.

1. **순수 단위 테스트:** 스프링 부트 컨텍스트를 띄우지 않는 순수 Java 단위 테스트에서는 JPA Auditing이 동작하지 않아 `createdAt`이 `null`이 되는 문제가 있다. 생성자에 `LocalDateTime.now()`를 넣으면 테스트 코드에서도 시간이 보장된다.

2. **명시성:** "객체가 생성될 때 시간이 설정된다"는 로직을 코드상에서 명확하게 보여주고 싶을 때 사용한다.

---

## 마치며

Entity는 데이터와 비즈니스 로직을 같이 고려해야 한다. `@Entity`, `@Id` 같은 어노테이션으로 DB와의 관계를 정의하고, `PROTECTED` 생성자와 `Builder` 패턴으로 객체 생성의 안정성을 확보했다. 시간 관리의 경우, 프로젝트의 상황(테스트 용이성 등)에 맞춰 **자동화(Auditing)**와 수동 관리 중 적절한 방법을 선택하여 적용하면 된다.


---

### 레퍼런스

[Auditing :: Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/auditing.html)