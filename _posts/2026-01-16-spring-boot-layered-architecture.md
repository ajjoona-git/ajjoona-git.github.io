---
title: "[Spring Boot] Django 개발자의 스프링 계층형 아키텍처 적응기 (feat. 비즈니스 로직이란?)"
date: 2026-01-16 09:00:00 +0900
categories: [Tech, Java]
tags: [SpringBoot, Architecture, LayeredArchitecture, MVC, Refactoring, Backend]
toc: true
comments: true
image: /assets/img/posts/2026-01-16-spring-boot-layered-architecture/1.png
description: "Python(Django)에서 Java(Spring Boot)로 넘어가며 겪은 패키지 구조와 계층별 역할(Controller, Service, Repository)의 차이를 정리했습니다. 특히 모호했던 '비즈니스 로직'의 개념을 웨이터와 쉐프의 비유를 통해 명확히 정의합니다."
---

새로운 프로젝트를 시작하며, Python이 주언어인 나와 달리, 다른 팀원은 모두 Java에 익숙한 상황이라 급하게 Java를 공부해야 했다.
Python(Django)에 익숙한 상태에서 Java(Spring)의 계층 분리(Layered Architecture)를 적용하려다 보니, 디렉토리도 많고 처음부터 조각을 하나하나씩 만들어 끼워 만드는 느낌이었다.

Spring 프레임워크의 폴더 구조와 MVC 패턴, 데이터와 로직의 흐름 등을 위주로 큰 그림을 익혀 나가는 데 집중했다.
프로젝트의 백엔드 개발 컨벤션 중 **Spring Boot 백엔드 패키지 구조**를 뜯어보았다.

---

## 1. 패키지 구조 (Directory Structure)

`com.liverary.backend` 하위의 패키지 구조이다. Django의 MVT 패턴과 비교하면서 이해해보았다.

```text
com.liverary.backend
├── common
│   └── dto
│       └── BaseResponse.java       // 공통 응답 포맷
├── config
│   └── ...                         // 설정 파일 (Security, Swagger 등)
├── exception
│   ├── GlobalExceptionHandler.java // 전역 예외 처리 (AOP)
│   ├── BaseException.java
│   └── ErrorCode.java              // 에러 코드 관리 (Enum)
└── {domain}                        // 도메인별 패키지 (예: user, board, room)
    ├── controller                  // 진입점 (= views.py + urls.py)
    │   └── SampleController.java
    ├── service                     // 비즈니스 로직 (= services.py)
    │   └── SampleService.java
    ├── repository                  // DB 접근 (= models.objects)
    │   └── SampleRepository.java
    ├── dto                         // 데이터 교환 객체 (= serializers.py)
    │   ├── request                 // @RequestBody
    │   └── response
    └── domain                      // DB 테이블 매핑 (= models.py)
        └── Sample.java             // Entity

```


## 2. 데이터 흐름 (Request Processing Flow)

클라이언트의 HTTP 요청이 서버에 들어와서 응답으로 나갈 때까지, 데이터의 흐름을 따라가보았다.

[Request Processing Flow](/assets/img/posts/2026-01-16-spring-boot-layered-architecture/1.png)
*Request Processing Flow*

1. **Client → Controller**: HTTP 요청(JSON)을 받아 `Request DTO`로 변환.
2. **Controller → Service**: 비즈니스 로직 실행 요청.
3. **Service → Repository**: DTO를 `Entity`로 변환 후 DB 작업 요청.
4. **Repository ↔ DB**: 실제 쿼리 실행 및 `Entity` 반환.
5. **Service → Controller**: 조회된 Entity를 `Response DTO`로 변환하여 반환.
    - 만약 service 로직 처리 중 오류가 발생하면, errorCode Enum에 정의한 에러 메세지가 즉시 반환된다.
6. **Controller → Client**: `Response DTO`를 최종적으로 `BaseResponse`로 감싸서 응답.


## 3. 계층별 상세 역할 (Roles & Responsibilities)

### ① Domain (Entity)

* **역할:** DB 테이블과 1:1로 매핑되는 클래스.
* **특징:** 
    - `@Entity`, `@Id`, `@Column` 등의 JPA 어노테이션 사용. 
    - 영속성 컨텍스트(Persistance Context)가 관리하는 객체.
* **주의:** **절대 API 응답으로 직접 반환하지 않는다.** (DB 스키마 노출 및 순환 참조 방지)

### ② Repository (Data Access Layer)

* **역할:** DB에 접근하는 인터페이스. (Django의 ORM 역할)
* **특징:** 
    - `JpaRepository<Entity, UUID>`를 상속받으면 Spring이 구현체를 자동 생성하여 Bean으로 등록해준다. 
    - 비즈니스 로직 없이 순수하게 CRUD만 담당한다.

### ③ DTO (Data Transfer Object)

* **역할:** 계층 간(특히 Controller ↔ Service) 데이터 교환을 위한 객체.
* **Request DTO:** 클라이언트의 JSON 데이터를 받음 (`@RequestBody`), 유효성 검사(`@Valid`).
* **Response DTO:** 클라이언트에게 필요한 데이터만 선별해서 담음. Entity의 내부 구현을 숨기는 역할.

### ④ Service (Business Layer) ⭐

* **역할:** **비즈니스 로직**을 처리하고 트랜잭션(`@Transactional`)을 관리하는 계층.
* **할 일:** 
    - Repository를 호출해 Entity 조회/저장.
    - DTO ↔ Entity 변환.
    - 비즈니스 규칙 검증 및 예외(`BaseException`) 발생.

### ⑤ Controller (Presentation Layer)

* **역할:** HTTP 요청의 **진입점(Entry Point)**이자 반환점.
* **특징:** 
    - URL과 HTTP Method 매핑.
    - Service를 호출한 뒤 결과를 `BaseResponse<T>` 규격에 맞춰 반환.


## 4. 비즈니스 로직 (Business Logic)

### 비즈니스 로직(Business Logic)이란?

**"우리 서비스만의 업무 규칙이자 판단 기준"**이다.

비밀방에 입장하는 상황을 예로 들면,

- *"이 방 **정원이 꽉 찼나?**"* (꽉 찼으면 에러)
- *"이 방이 **Private 방**인가?"* (아니면 그냥 통과)
- *"Private이라면 유저가 입력한 **비밀번호가 방 비밀번호와 일치하나?**"* (틀리면 에러)
- *"혹시 이 유저, 방장한테 **강퇴당한 기록**이 있나?"* (있으면 재입장 불가)

이렇게 **판단**이 필요한 로직은 Service에 작성한다.

### 비즈니스 로직인 것과 아닌 것

**비즈니스 로직이 아닌 것:**

- "DB에서 데이터 꺼내줘" (Repository 역할)
- "JSON으로 바꿔줘" (DTO/Controller 역할)
- "값이 비었는지 체크해줘" (Validation 역할)

**비즈니스 로직인 것:**

- **계산:** "할인 쿠폰이 있으니까 가격을 10% 깎아주자."
- **판단:** "재고가 없으니까 주문을 막자."
- **흐름 제어:** "A 작업을 성공하면 B를 하고, 실패하면 C를 하자."

### Controller vs Service

개발을 하다 보면 *"이 코드를 Controller에 써야 하나 Service에 써야 하나?"* 헷갈릴 때가 많다. Controller가 Django의 `views.py` + `urls.py`와 대응되고, Service가 비즈니스 로직과 트랜젝션을 처리하는 핵심 로직이라는데, `views.py`가 service가 아닌 controller와 대응되는 이유가 궁금했다.

**안 좋은 예 (Controller가 로직을 수행함)**

웨이터가 주문을 받고 주방에 들어가서 고기를 굽는 상황이다.

```java
// Controller
@PostMapping("/enter")
public Response enterRoom(@RequestBody Request req) {
    Room room = roomRepository.findById(req.getRoomId());
    
    // 여기가 비즈니스 로직인데, 왜 웨이터(Controller)가 판단하죠?
    if (room.getCount() >= room.getMaxUser()) {
        return new Response("꽉 찼어요");
    }
    
    room.setCount(room.getCount() + 1);
    roomRepository.save(room);
    return new Response("성공");
}
```

**좋은 예 (로직은 Service에게 위임)**

웨이터는 주문만 받고, 판단과 요리는 쉐프가 한다.

```java
// Controller (웨이터)
@PostMapping("/enter")
public Response enterRoom(@RequestBody Request req) {
    // 쉐프에게 토스
    sessionService.enterRoom(req.getUserId(), req.getRoomId());
    return new BaseResponse("성공");
}

// Service (쉐프)
@Transactional
public void enterRoom(UUID userId, UUID roomId) {
    Room room = roomRepository.findById(roomId);
    
    // 비즈니스 로직: 규칙 검증
    if (room.isFull()) {
        throw new BusinessException(ErrorCode.ROOM_FULL); // 쫓아냄
    }
    
    // 데이터 가공
    room.addCount();
    
    // 저장
    roomRepository.save(room);
}
```

**요약하자면:**

* **Controller:** "누구에게(Service) 시킬 것인가?" 매핑
* **Service:** "된다/안된다(검증)", "어떻게 한다(계산)" 판단


## 5. 개발 순서 가이드

**의존성(Dependency)이 없는 쪽에서 있는 쪽으로** 개발해야 컴파일 에러 없이 매끄럽게 진행된다.

**"데이터 정의(Entity) → 접근(Repository) → 규격(DTO) → 로직(Service) → 노출(Controller)"**

1. **Domain (Entity):** 뼈대 만들기 
    - 가장 기초가 되는 데이터 모델. 다른 모든 계층이 이 클래스를 참조한다.
2. **Repository:** 뼈대를 이용해 DB 접근법 정의
    - Entity가 있어야 DB 접근 메서드를 정의할 수 있다.
3. **DTO:** 어떤 데이터를 주고받을지 껍데기 정의
    - 서비스 로직을 짤 때 입출력 데이터 타입이 필요하다.
4. **Service:** 실제 로직 구현
    - Repository와 DTO가 준비되어야 비즈니스 로직을 구현할 수 있다.
5. **Controller:** 외부와 연결
    - Service가 완성되어야 API 엔드포인트를 연결할 수 있다.
