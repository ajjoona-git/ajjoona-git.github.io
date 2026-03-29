---
title: "[Spring Boot] @Valid 유효성 검증 실패가 500 에러를 뱉는 이유와 해결법 (MethodArgumentNotValidException)"
date: 2026-01-26 09:00:00 +0900
categories: [Tech, Backend]
tags: [Java, SpringBoot, Validation, ErrorHandling, GlobalExceptionHandler, Troubleshooting]
toc: true
comments: true
image: /assets/img/posts/2026-01-26-handling-validation-exceptions/1.png
description: "DTO 유효성 검증(@Valid) 실패 시 400 Bad Request가 아닌 500 Internal Server Error가 발생하는 원인을 분석합니다. MethodArgumentNotValidException을 전역 예외 처리기에서 핸들링하여 커스텀 에러 코드로 응답하는 방법을 정리했습니다."
---

예약 시스템 API를 개발하고 `.http` 클라이언트로 테스트하던 중 이상한 점을 발견했다.
비즈니스 로직에서 막힌 경우(중복 예약 등)에는 의도한 대로 **409 Conflict**가 떴지만, 입력값 자체가 잘못된 경우(과거 날짜 등)에는 **400 Bad Request**가 아니라 뜬금없이 **500 Internal Server Error**가 반환되었다.

---

## 분명 유효성 검증(`@Valid`)을 걸어놨는데 왜 서버 에러가 날까?

`test.http`를 이용해 다양한 시나리오를 테스트했다.

### Case 1. 정상 요청 (200 OK)
```http
POST {{host}}/api/room/reservation
Content-Type: application/json

{
  "title": "주말 아침 딥워크 모임",
  "startAt": "2026-02-01T09:00:00",
  "endAt": "2026-02-01T11:00:00",
  ...
}

```

* **결과:** 성공. DB에 잘 저장됨.

### Case 2. 비즈니스 예외 (409 Conflict)

* **조건:** 1번과 동일한 시간에 중복 예약 시도.
* **결과:** **409 Conflict** (정상).
* **이유:** Service 계층에서 중복을 감지하고 `BaseException(RESERVATION_CONFLICT)`을 던졌고, `GlobalExceptionHandler`가 이를 잡아 처리했기 때문.

### Case 3. 유효성 검증 실패 (500 Error ??)

* **조건:** 종료 시간이 시작 시간보다 빠름 (`@AssertTrue` 위반) 또는 과거 날짜 입력 (`@Future` 위반).

```http
POST {{host}}/api/room/reservation
Content-Type: application/json

{
  "title": "시간 역행 모임",
  "startAt": "2026-02-01T15:00:00",
  "endAt": "2026-02-01T14:00:00" 
}

```

* **기대 결과:** 400 Bad Request ("시간 범위가 잘못되었습니다")
* **실제 결과:** **500 Internal Server Error**
* **로그:**
```text
ERROR ... GlobalExceptionHandler : 🚨 Unhandled Exception: 
org.springframework.web.bind.MethodArgumentNotValidException: Validation failed for argument [1] ...
default message [종료 시각은 시작 시각보다 이후여야 합니다.]

```

로그를 자세히 보면 범인은 `MethodArgumentNotValidException`이다.

### 예외 발생 흐름 비교

![Error Flow](/assets/img/posts/2026-01-26-handling-validation-exceptions/1.png)
*Error Flow*

1. **비즈니스 예외(`BaseException`):** 내가 직접 만든 예외 클래스다. 이미 핸들러(`@ExceptionHandler(BaseException.class)`)를 등록해 뒀기에 예쁘게 처리된다.
2. **유효성 예외(`MethodArgumentNotValidException`):** Spring 프레임워크가 발생시키는 예외다. **내 핸들러에는 이 예외를 처리하는 로직이 없었다.**
3. **결과:** 핸들러가 없으니 Spring은 이를 "알 수 없는 시스템 에러"로 간주하고 500을 뱉어버린 것이다.



## GlobalExceptionHandler에 MethodArgumentNotValidException를 추가하자

`GlobalExceptionHandler`에 `MethodArgumentNotValidException` 전용 처리 로직을 추가해야 한다.

### 수정된 GlobalExceptionHandler.java

```java
/**
 * @Valid 유효성 검사 실패 예외 처리
 *
 * 목적: 500 에러 대신 400 에러와 명확한 메시지를 반환하기 위함
 */
@ExceptionHandler(MethodArgumentNotValidException.class)
public ResponseEntity<BaseResponse<?>> handleValidationException(MethodArgumentNotValidException e) {
    // 1. 에러 메시지 추출 (첫 번째 에러만 가져옴)
    String errorMessage = e.getBindingResult().getFieldError() != null
            ? e.getBindingResult().getFieldError().getDefaultMessage()
            : ErrorCode.INVALID_INPUT_VALUE.getMessage();

    // 2. 기본 에러 코드는 C002 (INVALID_INPUT_VALUE)로 설정
    ErrorCode errorCode = ErrorCode.INVALID_INPUT_VALUE;

    // 커스텀 검증 어노테이션(@AssertTrue)의 경우 필드명을 통해 특정 에러 코드로 매핑
    if (e.getBindingResult().getFieldError() != null) {
        String fieldName = e.getBindingResult().getFieldError().getField();
        
        // DTO의 메서드명 isEndAtAfterStartAt() -> 필드명 endAtAfterStartAt
        if ("endAtAfterStartAt".equals(fieldName)) {
            errorCode = ErrorCode.INVALID_TIME_RANGE; // R007 (시간 범위 오류)로 교체
        }
    }

    log.warn("🚨 Validation Error: {} ({}) - {}", errorCode.getCode(), errorCode.getMessage(), errorMessage);

    // 3. 400 Bad Request 반환
    return ResponseEntity
            .status(errorCode.getHttpStatus())
            .body(BaseResponse.error(errorCode.getCode(), errorMessage));
}

```

### 코드 포인트

* **`e.getBindingResult()`**: 어떤 필드에서 검증이 실패했는지 정보를 담고 있다.
* **`@AssertTrue` 매핑**: 클래스 레벨이나 메서드 레벨의 검증(`isEndAtAfterStartAt`)이 실패하면 필드명이 메서드 이름에서 유래한다. 이를 잡아내어 단순한 "입력값 오류"가 아닌 "시간 범위 오류"라는 더 구체적인 에러 코드(`INVALID_TIME_RANGE`)로 바꿔주었다.


## 다시 테스트를 해보자!

핸들러 추가 후 서버를 재시작하고 동일한 요청(Case 3)을 보냈다.

### 수정 후 응답 (400 Bad Request)

```json
{
  "code": "R007",
  "message": "종료 시각은 시작 시각보다 이후여야 합니다.",
  "result": null,
  "success": false
}

```

이제 클라이언트는 500 에러를 보고 "서버가 터졌나?" 하고 당황하는 대신, 400 에러와 메시지를 보고 "아, 시간을 잘못 입력했구나"라고 인지할 수 있게 되었다.

---

### 마치며

* `@Valid` 검증 실패는 `MethodArgumentNotValidException`을 발생시킨다.
* 이 예외는 Service 로직 진입 전에 발생하므로, 전역 예외 처리기에서 별도로 잡아주지 않으면 500 에러가 된다.
* 반드시 핸들러를 추가하여 명확한 400 에러로 변환해주자.
