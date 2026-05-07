---
title: "[SAN] GlobalExceptionHandler 설계: BindException 통합과 ErrorCode 인터페이스"
date: 2026-05-04 12:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, ExceptionHandler, BindException, Validation, ErrorCode, RestControllerAdvice, Troubleshooting]
toc: true
comments: true
description: "GlobalExceptionHandler가 필요한 이유, ErrorCode 인터페이스로 도메인별 에러코드를 일원화하는 방법, @ModelAttribute 검증 실패가 500을 반환한 원인과 BindException 단일 핸들러로 통합하기까지 정리합니다."
---

`SearchController`에 `@Valid @ModelAttribute SearchRequest`를 적용한 뒤 검증 실패 시 500 응답이 발생했습니다. 원인을 파악하는 과정에서 `GlobalExceptionHandler` 설계 전반을 정리하게 됐습니다.

## GlobalExceptionHandler가 필요한 이유

Spring MVC에서 예외가 발생하면 각 Controller에서 직접 처리하거나 전역 핸들러에 위임할 수 있습니다. Controller마다 예외를 처리하면 동일한 예외에 대해 응답 형식이 제각각이 되고, 새로운 예외 처리 로직 추가 시 모든 Controller를 수정해야 합니다. 공통 로깅도 한 곳에서 관리할 수 없습니다.

`@RestControllerAdvice` 기반의 `GlobalExceptionHandler`를 두면 모든 Controller에서 발생한 예외를 한 곳에서 처리하고, `ApiResponse` 형식으로 일관된 오류 응답을 보장합니다.

```
Controller에서 예외 발생
  → GlobalExceptionHandler가 타입 매칭
  → ApiResponse.error()로 포맷
  → 클라이언트에 일관된 응답 반환
```

## ErrorCode 인터페이스로 도메인 예외를 일원화

`BusinessException`은 `ErrorCode` 인터페이스 타입으로 에러 코드를 보관합니다.

```java
// handleBusinessException 내부
ErrorCode errorCode = e.getErrorCode();
return ResponseEntity.status(errorCode.getStatus())
        .body(ApiResponse.error(errorCode, e.getMessage()));
```

`KnowledgeErrorCode`, `TilErrorCode`, `CommonErrorCode` 등 도메인별 구현체는 다르지만, 핸들러는 구체 타입을 알 필요 없이 `ErrorCode` 인터페이스의 `getStatus()`, `getCode()`, `getMessage()`만 호출합니다. 새로운 도메인 ErrorCode가 추가되더라도 핸들러를 수정할 필요가 없습니다.

반대로 `var`나 구체 타입으로 선언하면 각 도메인 ErrorCode에 직접 의존하게 되어 도메인이 늘어날수록 핸들러가 변경됩니다.

## BindException: @ModelAttribute 검증 실패가 500을 반환한 원인

Spring `@Valid` 검증 실패 예외의 상속 구조는 다음과 같습니다.

```
BindException                          ← @ModelAttribute 검증 실패 시 발생
  └── MethodArgumentNotValidException  ← @RequestBody 검증 실패 시 발생
```

`@ExceptionHandler`는 선언된 타입과 정확히 일치하거나 그 하위 타입인 예외만 처리합니다. 기존 핸들러는 `MethodArgumentNotValidException`만 선언했습니다.

| 상황 | 발생 예외 | 처리 결과 |
|------|----------|---------|
| `@RequestBody` 검증 실패 | `MethodArgumentNotValidException` | 400 ✓ |
| `@ModelAttribute` 검증 실패 | `BindException` | 핸들러 없음 → fallback → **500** ✗ |

`SearchController`에 `@Valid @ModelAttribute SearchRequest`가 추가되면서 `@ModelAttribute` 검증 실패 케이스가 새로 발생했고, 기존 핸들러로는 잡을 수 없었습니다.

두 핸들러의 처리 로직이 동일하므로 `MethodArgumentNotValidException` 핸들러를 제거하고 부모 타입인 `BindException` 단일 핸들러로 통합했습니다. `MethodArgumentNotValidException`은 `BindException`의 하위 타입이므로 기존 `@RequestBody` 검증도 동일하게 처리됩니다.

```java
@ExceptionHandler(BindException.class)
public ResponseEntity<ApiResponse<Void>> handleBindException(BindException e) {
    // @RequestBody, @ModelAttribute 검증 실패 모두 처리
}
```

## 현재 핸들러 구성 요약

| 핸들러 | 처리 예외 | HTTP 상태 | 비고 |
|--------|----------|----------|------|
| `handleBusinessException` | `BusinessException` | ErrorCode 정의값 | 도메인 예외 전담 |
| `handleBindException` | `BindException` (+ 하위 타입) | 400 | `@RequestBody`, `@ModelAttribute` 검증 실패 통합 |
| `handleMessageNotReadableException` | `HttpMessageNotReadableException` | 400 | JSON 파싱 오류, 요청 본문 누락 |
| `handleException` | `Exception` | 500 | 처리되지 않은 모든 예외 (fallback) |