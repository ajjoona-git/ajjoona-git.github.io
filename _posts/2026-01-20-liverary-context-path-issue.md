---
title: "[LIVErary] Spring Boot context-path 설정 시 403 에러 해결 (경로 매핑 중복 문제)"
date: 2026-01-20 15:00:00 +0900
categories: [Projects, LIVErary]
tags: [SpringBoot, Troubleshooting, ContextPath, SpringSecurity, 403Forbidden, API]
toc: true
comments: true
description: "application.yml에 server.servlet.context-path를 설정했을 때, Spring Security와 Controller에서 403 Forbidden 에러가 발생하는 원인과 해결 방법을 정리했습니다."
---

API 버전을 관리하기 위해 `application.yml`에 `context-path`를 설정했다.
그런데 분명히 권한을 다 열어주었는데도(`permitAll`), API 요청 시 **403 Forbidden** 에러가 계속 발생했다.

알고 보니 **Spring이 URL을 해석하는 방식**을 오해해서 발생한 문제였다. `context-path`의 동작 원리와 해결 과정을 정리한다.

---

## 문제 상황

`application.yml`에 API의 기본 경로를 `/api/v1`으로 설정해 두었다.

```yaml
# application.yml
server:
  servlet:
    context-path: /api/v1  # 모든 요청 앞에 이 경로가 붙음

```

그리고 `SecurityConfig`와 `Controller`에서도 명확하게 경로를 지정해 주었다. (라고 생각했다.)

```java
// 실수한 코드 (SecurityConfig)
.requestMatchers("/api/v1/room/**").permitAll() // 전체 경로를 다 적음

// 실수한 코드 (Controller)
@RequestMapping("/api/v1/room") // 전체 경로를 다 적음

```

하지만 Postman으로 `http://localhost:8080/api/v1/room`을 호출하면 **403 Forbidden**이 반환되었다.


## 원인 분석

Spring Boot에서 `context-path`를 설정하면, 서버는 들어오는 모든 요청의 맨 앞부분(`context-path`)을 **자동으로 잘라내고(Strip)**, 그 **뒷부분(Path)**만 가지고 내부 로직을 수행한다.

### Spring의 시선

1. **실제 요청 URL:** `http://localhost:8080/api/v1/room`
2. **Spring이 잘라내는 부분 (Context Path):** `/api/v1`
3. **Security & Controller가 보는 주소:** `/room` (**앞부분이 이미 제거됨!**)

그런데 내 코드는 `/api/v1/room`이 들어오는지 검사하고 있었다.
Spring 입장에서는 `/room`만 들어왔는데, 설정 파일에서는 `/api/v1/room`을 찾으라고 하니 **매칭되는 규칙이 없어** 기본 설정인 '거절(403)' 처리를 해버린 것이다.


## 해결 방법

SecurityConfig와 Controller에서 **중복된 경로(`/api/v1`)를 제거하고 상대 경로만 남겨야 한다.**

### SecurityConfig.java 수정

```java
@Bean
public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http
        .csrf(AbstractHttpConfigurer::disable)
        .authorizeHttpRequests(auth -> auth
            // [수정] 앞에 /api/v1을 제거하고 뒷부분만 명시
            .requestMatchers("/room/**").permitAll()   
            .requestMatchers("/auth/**").permitAll()
            .anyRequest().authenticated()
        );
    return http.build();
}

```

### Controller 수정

Controller도 마찬가지다. `context-path`가 이미 앞단을 처리해 주므로, 여기서는 `/room`만 적어야 한다.

```java
// [수정] /api/v1/room (X) -> /room (O)
@RequestMapping("/room") 
@RestController
@RequiredArgsConstructor
public class RoomController {
    // ...
}

```

## 최종 확인

코드를 수정하고 서버를 재시작한다.

1. **Postman 요청:** `http://localhost:8080/api/v1/room`
* *(주의: 클라이언트(Postman)는 서버 밖에서 요청하므로 여전히 전체 주소를 써야 한다!)*


2. **결과:** `200 OK`

