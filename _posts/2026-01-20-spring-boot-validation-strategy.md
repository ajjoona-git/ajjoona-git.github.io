---
title: "데이터 유효성 검증: DTO와 Service"
date: 2026-01-20 09:00:00 +0900
categories: [Tech, Java]
tags: [Java, SpringBoot, Validation, DTO, Service, Controller, Transactional, Architecture]
toc: true
comments: true
description: "데이터 유효성 검증을 Controller(DTO)와 Service 계층으로 나누어 처리하는 이유와 방법을 정리했습니다. @Valid를 이용한 입력 형식 검증(Fail Fast)과 DB 조회가 필요한 비즈니스 로직 검증의 차이를 실제 코드로 분석합니다."
---


API를 개발하다 보면 "이 데이터가 올바른지 어디서 검사해야 할까?"라는 고민에 빠진다.
Controller에서 다 검사하자니 코드가 지저분해지고, Service에서 다 하자니 엉뚱한 데이터 때문에 DB까지 갔다 오는 게 비효율적이다.

개발에서는 이 두 단계를 **"입력 형식 검증(Format Validation)"**과 **"비즈니스 로직 검증(Business Logic Validation)"**으로 구분하여 처리하는 것이 정석이다. LIVERARY 프로젝트의 '방 만들기' 기능을 통해 그 기준을 명확히 정리해 본다.

---

## 유효성 검증의 두 단계 (Two-Layer Validation)

### 1차: DTO 유효성 검증 (Format Validation)

**"형식(Format)이 올바른가?"** 

Service까지 데이터가 도달하기도 전에, 문법적으로 말도 안 되는 데이터를 걸러낼 수 있다. DB 접근 없이 어노테이션(`@NotNull`, `@Size`, `@Email`)만으로 즉시 판단 가능하다(Fail Fast).

* **예시:**
    * "방 제목이 비어있는가?" (`@NotBlank`)
    * "최대 인원이 16명을 넘었는가?" (`@Max(16)`)

### 2차: Service 유효성 검증 (Business Logic Validation)

**"현재 상황에서 처리가 가능한가?"**

형식은 완벽하지만, DB의 현재 상태나 서비스 정책상 받아들일 수 없는 데이터를 걸러낸다. DB 조회가 필요하거나, 여러 필드 간의 복합적인 관계를 통해 데이터의 정합성을 판단한다.

* **예시:**
    * "입력받은 `bookId`가 실제 DB에 존재하는 책인가?" (DTO는 형식이 UUID인 것만 알지, 실제 존재 여부는 모른다)
    * "책을 선택 안 했는데, 카테고리도 안 보냈는가?" (두 필드 간의 복합 로직)

### DTO 검증 vs Service 검증

| 구분 | **DTO 검증 (Controller)** | **Service 검증 (Business Layer)** |
| :--- | :--- | :--- |
| **담당** | `@Valid`, `@NotNull`, `@Max` | `if-else`, `repository.findById` |
| **질문** | "데이터 생김새가 멀쩡해?" | "이 데이터로 진짜 처리해도 돼?" |
| **비용** | 매우 저렴 (단순 연산) | 비쌈 (DB 조회 등 I/O 발생) |
| **예시** | `maxUser`가 100명이면 컷! | `bookId`에 해당하는 책이 DB에 없으면 컷! |


## Controller 구현

Controller는 `@Valid`를 사용하여 DTO 검증을 수행하고, 검증된 데이터를 Service로 넘기는 역할만 수행한다.

```java
@RestController
@RequiredArgsConstructor
@RequestMapping("/room")
public class RoomController {

    private final RoomService roomService;

    @PostMapping
    public BaseResponse<RoomCreateResponse> createRoom(
            @Valid @RequestBody RoomCreateRequest request, // ① 1차 검증
            @AuthenticationPrincipal UserDetails user      // ② 보안 (User)
    ) {
        // 1. 사용자 ID 추출 (인증된 유저)
        UUID userId = UUID.fromString(user.getUsername());

        // 2. 서비스 호출 (비즈니스 로직 위임)
        RoomCreateResponse response = roomService.createRoom(userId, request);

        // 3. 결과 반환
        return new BaseResponse<>(response);
    }
}
```

- `@Valid`: `RoomCreateRequest` DTO 안에 설정된 제약조건(`@NotBlank` 등)을 검사한다. 실패 시 `MethodArgumentNotValidException`이 발생하며 400 에러로 즉시 응답한다.

- `@AuthenticationPrincipal`: Spring Security가 인증한 사용자 정보를 주입해 준다.

## Service 구현
Service는 DB와 통신하며 실제 데이터의 무결성을 검증하고 트랜잭션을 관리한다.

```Java
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true) // ① 기본 읽기 전용
public class RoomService {

    private final RoomRepository roomRepository;
    private final BookRepository bookRepository;
    private final UserRepository userRepository;
    private final CategoryRepository categoryRepository;

    @Transactional // ② 쓰기 허용
    public RoomCreateResponse createRoom(UUID userId, RoomCreateRequest request) {
        
        // 1. User 조회 (FK 제약조건 확인)
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BaseException(ErrorCode.USER_NOT_FOUND));

        // 2. 비즈니스 검증
        if (request.getBookId() == null && request.getCategoryId() == null) {
            throw new BaseException(ErrorCode.CATEGORY_REQUIRED);
        }

        // 3. Book & Category 결정 로직
        Book book = null;
        Category category = null;

        if (request.getBookId() != null) {
            // 책이 있으면 책의 카테고리 강제 적용
            book = bookRepository.findById(request.getBookId())
                    .orElseThrow(() -> new BaseException(ErrorCode.BOOK_NOT_FOUND));
            category = book.getCategory(); 
        } else {
            // 책이 없으면 요청받은 카테고리 사용
            category = categoryRepository.findById(request.getCategoryId())
                    .orElseThrow(() -> new BaseException(ErrorCode.CATEGORY_NOT_FOUND));
        }

        // 4. Room 생성 (Builder)
        Room room = Room.builder()
                .title(request.getTitle())
                .creator(user)
                .book(book)
                .category(category)
                // ... 기타 필드
                .build();

        roomRepository.save(room);

        return RoomCreateResponse.from(room);
    }
}
```

### 코드 분석 및 기술 포인트
- `@Transactional(readOnly = true)` (Class Level):
클래스 전체를 읽기 전용으로 설정하여 성능(Dirty Checking 생략)을 최적화한다.

- `@Transactional` (Method Level):
`createRoom`은 데이터 저장이 필요하므로, 메서드 레벨에서 다시 트랜잭션을 열어 쓰기를 허용한다. 예외 발생 시 자동 롤백된다.

- `if (request.getBookId() == null && request.getCategoryId() == null)` (복합 검증 로직):
이 로직은 DTO의 `@NotNull` 하나로는 해결할 수 없다. "A가 없으면 B라도 있어야 한다"는 **서비스의 정책(Rule)**이기 때문에 Service 계층에서 Java 코드로 검증해야 한다.

---

## 정리

**Controller(DTO)**는 "데이터가 **예쁘게** 생겼는가?"를 검사하여 이상한 요청을 **빠르게 차단(Fail Fast)**한다.

**Service**는 "데이터가 **논리적으로** 맞는가?"를 검사하여 데이터베이스의 **무결성(Integrity)**을 지킨다.

이 구조를 지키면 불필요한 DB 조회를 줄여 성능을 높이고, 비즈니스 로직을 한곳에 응집시켜 유지보수하기 좋은 코드를 만들 수 있다.
