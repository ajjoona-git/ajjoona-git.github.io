---
title: "[LIVErary] Spring Boot 실행 에러: application.yml 들여쓰기와 @Value 바인딩 문제"
date: 2026-01-20 09:00:00 +0900
categories: [Projects, LIVErary]
tags: [SpringBoot, Troubleshooting, YAML, Configuration, JWT, ErrorLog]
toc: true
comments: true
description: "Spring Boot 애플리케이션 실행 시 발생한 'Could not resolve placeholder' 에러의 원인과 해결 과정을 정리했습니다. application.yml 파일의 들여쓰기 실수로 인해 @Value 어노테이션이 값을 찾지 못했던 사례를 분석합니다."
---

협업 과정에서 인증 로직(Spring Security + JWT) 코드를 `pull` 받은 후, 서버를 실행하자마자 `ApplicationContext`가 로드되지 않으며 장렬하게 실패하는 문제를 마주했다.
분명 팀원의 로컬에서는 잘 돌아가는데, 내 환경에서만 발생하는 유령 같은 에러였다.

이번 포스트에서는 단순한 오타 문제인 줄 알았으나, 알고 보니 **YAML의 엄격한 계층 구조** 때문이었던 트러블슈팅 과정을 공유한다.

---

## 문제

서버 실행 시 `JwtProvider` 빈(Bean)을 생성하는 과정에서 `@Value`로 설정값을 불러오지 못해 `UnsatisfiedDependencyException`이 발생했다.

### 에러 로그
로그가 매우 길지만, 가장 밑바닥(`Caused by`)을 보면 원인이 적혀 있다.

```text
Error starting ApplicationContext...

Caused by: org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'jwtProvider' ...
Caused by: org.springframework.util.PlaceholderResolutionException: Could not resolve placeholder 'jwt.secret-key' in value "${jwt.secret-key}"
```

Spring이 `application.yml` (또는 환경 변수) 어디를 뒤져봐도 `jwt.secret-key`라는 키를 찾을 수 없다는 뜻이다.

## 실패한 시도들

처음에는 단순히 값이 비어있거나 환경 변수가 로딩되지 않은 문제라고 판단하여 온갖 방법을 시도했다.

1. `application.yml` 및 `.env` 파일 최신화 (오타 확인)
2. `.env` 파일에서 secret-key 값을 따옴표(`""`)로 감싸기
3. IntelliJ 환경 변수(Environment Variables) 설정에 키 직접 추가
4. 키 이름을 변경해봄 (`jwt.access-expiration` 등)
5. IntelliJ 캐시 삭제(Invalidate Caches) 및 버전 업데이트
6. Docker Compose Down/Up 재실행
7. **`application.yml`에 변수(`${}`) 대신 문자열을 하드코딩**

값을 직접 때려 넣어도 못 찾는 것을 보고, 이것은 단순한 값(Value)의 문제가 아니라 **구조(Structure)**의 문제임을 직감했다.


## 원인 분석

수많은 삽질 끝에 발견한 범인은 **`application.yml` 파일의 '들여쓰기(Indentation)'**였다.

YAML 파일에서 들여쓰기는 곧 **계층 구조(부모-자식 관계)**를 의미한다. 내가 작성한 설정 파일은 `jwt` 설정이 최상위(Root)가 아니라, `spring` 설정의 하위 요소로 들어가 있었다.

### 무엇이 달랐을까?

#### [상황 A] 내가 의도했던 구조 (Root 레벨)

Java 코드에서 `@Value("${jwt.secret}")`으로 찾으려면 이렇게 되어 있어야 한다.

```yaml
# application.yml
jwt:           # 맨 앞에 붙어있음 (Root)
  secret: "my-secret-key"

```

#### [상황 B] 실제 작성되어 있던 구조 (Nested 레벨)

실제 파일은 `spring` 속성 안쪽으로 들여쓰기 되어 있었다.

```yaml
# application.yml
spring:
  datasource:
    url: ...
  jwt:         # spring 아래에 들여쓰기 됨! (자식 요소)
    secret: "my-secret-key"

```

이 경우 실제 접근 키는 `jwt.secret`이 아니라 **`spring.jwt.secret`**이 된다. 그러니 Spring 입장에서는 `jwt.secret`을 죽어도 찾을 수 없었던 것이다.


## 해결 방법

원인을 파악했으니 해결책은 간단하다. Java 코드의 경로를 실제 YAML 구조에 맞춰 수정해 주었다.
반대로 YAML의 들여쓰기를 수정해서 `jwt`를 밖으로 꺼내도 된다.

**수정 전 (`JwtProvider.java`):**

```java
@Value("${jwt.secret-key}") // 못 찾음
private String secretKey;

```

**수정 후 (`JwtProvider.java`):**

```java
@Component
public class JwtProvider {

    // 해결책: 경로 앞에 'spring.'을 붙여서 실제 계층 구조 반영
    @Value("${spring.jwt.secret}") 
    private String secretKey;

    @Value("${spring.jwt.expiration-time.access}")
    private long accessExpirationTime;

    // ...
}
```

---

## 마치며

1. **YAML은 들여쓰기에 매우 민감하다.** 눈으로 훑어볼 때는 `jwt`가 `spring` 밑에 종속되어 있는지, 독립된 Root인지 구별하기 어렵다. 편집기의 안내선(Indent Guide)을 잘 확인하자.
2. `Could not resolve placeholder` 에러가 났을 때, 값(Value)만 의심하지 말고 **키(Key)의 계층 구조**가 올바른지 가장 먼저 확인하자.
3. 설정 파일 에러 로그는 무섭게 길지만, 항상 **`Caused by`의 마지막 줄**에 정답이 숨어 있다.
