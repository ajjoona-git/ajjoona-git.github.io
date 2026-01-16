---
title: "[Spring Boot] JPA vs MyBatis: 무엇을 선택해야 할까?"
date: 2026-01-16 09:00:00 +0900
categories: [Tech, Java]
tags: [Java, SpringBoot, JPA, MyBatis, ORM, SQLMapper, QueryDSL, Backend, Database]
toc: true
comments: true
description: "자바 백엔드의 양대 산맥인 JPA와 MyBatis를 비교합니다. 비즈니스 복잡도와 쿼리 복잡도에 따른 선택 기준, 프로젝트 구조의 차이, 그리고 QueryDSL을 활용한 최신 실무 트렌드까지 정리했습니다."
---

**"MyBatis = DAO (데이터 접근 중심)"**

**"JPA = Repository (도메인 객체 중심)"**

이 두 기술은 서로 대체재이기도 하지만, 때로는 상호 보완재가 되기도 한다.
개발자 커뮤니티에서 끊임없이 논쟁이 되는 주제지만, 결론은 **"상황에 맞는 도구를 써야 한다"**는 것이다. 현업에서의 선택 기준, 프로젝트 구조, 그리고 최신 트렌드까지 정리해 본다.

---

## 언제 무엇을 써야 할까?

결론부터 말하자면 **"비즈니스 로직이 복잡하면 JPA, 쿼리가 복잡하면 MyBatis"**가 일반적인 기준이다.

| 비교 항목 | **JPA (Spring Data JPA)** | **MyBatis (SQL Mapper)** |
| :--- | :--- | :--- |
| **기술 유형** | **ORM** (Object Relational Mapping) | **SQL Mapper** |
| **핵심 철학** | "개발자는 객체지향적으로 코딩해. <br>SQL은 내가 알아서 짤게." | "SQL은 개발자가 제일 잘 아니까 직접 짜. <br>매핑(변환)만 내가 도와줄게." |
| **주 사용처** | 스타트업, 자체 서비스 기업(네카라쿠배), <br>신규 프로젝트 | SI(통합 구축), 금융권, 공공기관, <br>레거시/통계 시스템 |
| **장점** | 생산성 압도적(CRUD 자동화), <br>DB 변경 용이, 유지보수성, 타입 안정성 | 복잡한 쿼리(Join, Union, 서브쿼리) 최적화 용이, <br>DBA 친화적, SQL 튜닝 용이 |
| **단점** | 높은 학습 곡선(영속성 컨텍스트, N+1), <br>통계성 쿼리 작성 어려움 | 단순 CRUD도 SQL을 다 짜야 함(반복 작업), <br>특정 DB에 종속적 |
| **추천 상황** | **도메인 설계**가 중요한 복잡한 로직의 서비스 | **데이터 조회/통계** 위주의 복잡한 화면이 많은 서비스 |


## 프로젝트 구조 비교 (Project Structure)
두 기술은 **Data Access Layer**를 구성하는 방식과 파일 구조에서 명확한 차이를 보인다.

### A. MyBatis 프로젝트 구조 (SQL 중심)
SQL을 Java 코드와 분리하여 별도의 **XML 파일**로 관리하는 것이 가장 큰 특징이다.

```text
src/main/java
├── controller
├── service
├── dto                 // 데이터 전달용 객체
└── mapper              // (또는 dao)
    └── UserMapper.java // [Interface] 메서드 정의 (@Mapper)

src/main/resources
└── mapper
    └── UserMapper.xml  // [XML] 실제 SQL 작성
                        // <select id="findById">SELECT * FROM ...</select>
```

* **특징:** Java 코드는 껍데기(인터페이스)만 있고, 실제 로직(SQL)은 XML에 존재한다. 보통 DTO와 DB 테이블 컬럼을 1:1로 매핑하여 사용한다.

### B. JPA 프로젝트 구조 (객체 중심)

SQL 파일이 존재하지 않으며, Java 인터페이스와 클래스만으로 동작한다. Entity 객체가 곧 DB 테이블 역할을 한다.

```text
src/main/java
├── controller
├── service
├── dto                 // [DTO] 요청/응답용 객체 (Entity와 분리 필수!)
├── domain              // (또는 entity)
│   └── User.java       // [Entity] DB 테이블과 매핑되는 핵심 객체
└── repository
    └── UserRepository.java // [Interface] 데이터 저장소
                            // extends JpaRepository<User, Long>
```

- **특징:** `UserRepository` 인터페이스를 만들기만 하면 `save()`, `findAll()` 같은 메서드가 자동으로 생성된다. 
- **주의:** Entity는 절대 Service 계층 밖(Controller 등)으로 유출시키지 않고 **DTO로 변환**해서 내보내야 한다.


### 최신 트렌드 (Modern Tech Stack)

현재 한국의 백엔드 개발 생태계는 크게 세 가지 흐름으로 나뉜다.

### A. JPA + QueryDSL (서비스 기업 표준)

JPA만으로는 복잡한 검색 조건(동적 쿼리)이나 조인을 처리하기 까다롭다. 그래서 **QueryDSL**이라는 기술을 붙여서 단점을 보완한다.

- **기본 CRUD:** JPA로 해결 (생산성 ⬆)
- **복잡한 조회:** QueryDSL로 Java 코드로 쿼리 작성 (컴파일 시점에 에러 잡음, 타입 안정성)
- **현황:** 배달의민족, 토스, 당근마켓 등 대부분의 IT 서비스 기업이 이 조합을 표준으로 사용

### B. JPA + MyBatis (하이브리드)

JPA를 메인으로 쓰되, **"아 이건 도저히 JPA로 못 하겠다"** 싶은 초고난도 통계/배치 쿼리만 MyBatis를 섞어서 쓰는 방식이다.

- **CUD (생성/수정/삭제):** JPA 사용 (객체 중심의 데이터 무결성 보장)
- **R (복잡한 조회):** MyBatis 사용 (세밀한 SQL 튜닝 및 최적화)

### C. SI/금융권은 여전히 MyBatis 강세

데이터 자체의 무결성보다 데이터베이스의 성능과 쿼리 최적화가 최우선인 곳, 그리고 **DBA(데이터베이스 관리자)**의 영향력이 강한 곳에서는 여전히 MyBatis를 선호한다. 복잡한 SQL을 튜닝하기에는 MyBatis가 훨씬 직관적이기 때문이다.

---

## 레퍼런스

[JPA vs Mybatis, 현직 개발자는 이럴 때 사용합니다.](https://www.elancer.co.kr/blog/detail/231)