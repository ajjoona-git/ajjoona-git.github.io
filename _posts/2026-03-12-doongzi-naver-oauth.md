---
title: "[둥지] 네이버 소셜 로그인: OIDC 시도 → OAuth 2.0 전환기"
date: 2026-03-12 00:00:00 +0900
categories: [Project, 둥지]
tags: [Naver, OAuth2, OIDC, JWT, FastAPI, Authentication, Backend, Python]
toc: true
comments: true
image: /assets/img/posts/2026-03-12-doongzi-naver-oauth/1.png
description: "네이버 소셜 로그인을 OIDC로 구현하려다 실패하고, OAuth 2.0 방식으로 전환한 과정과 API 테스트 기록을 정리합니다."
---

네이버 소셜 로그인을 **OIDC(OpenID Connect)** 방식으로 먼저 시도했지만, 인증 과정에서 필요한 API 호출이 반복적으로 실패했고(네이버에서 OIDC 관련 엔드포인트를 공식 제공하지 않는 것으로 추정), 최종적으로 **OAuth 2.0 Authorization Code Grant**로 전환해 정상 동작까지 확인했습니다.

---

## Naver OIDC 로그인 플로우

처음 목표는 구글·카카오와 동일하게 **`id_token` 기반** 흐름으로 구현하는 것이었습니다.

기대했던 흐름은 다음과 같습니다.
1. Authorization Code 발급
2. Token 교환 시 `id_token` 수신
3. `id_token` 검증(JWK fetch, `jwt.decode`)으로 사용자 식별


## OIDC 호출 오류

OIDC로 구현하려면 일반적으로 다음이 필요합니다.

- OIDC discovery 문서(`/.well-known/openid-configuration`)
- JWK endpoint(`jwks_uri`)를 통한 공개키 획득
- `id_token` 검증


![OIDC 응답 오류](/assets/img/posts/2026-03-12-doongzi-naver-oauth/4.png)
*OIDC(/oauth2/..) 응답 오류*

그런데 구현·테스트 과정에서 네이버 측 OIDC 흐름을 전제로 한 호출이 정상적으로 이어지지 않았습니다.

가이드에 안내된 API 주소 (https://nid.naver.com/oauth2/authorize)로 요청을 보낸 경우, 사진과 같이 200 OK이지만 응답 형태가 달랐습니다.

그래서 OAuth2.0의 API 주소에 `scope=openid`를 붙여서 (https://nid.naver.com/oauth2.0/authorize?scope=openid&...)로 요청을 보내보았지만, 여전히 `id_token`은 응답에 포함되지 않았습니다.

인터넷 서치 결과, 비슷한 현상을 겪은 사용자들이 있었고 문의글을 확인했지만, 네이버 측의 답변은 확인할 수 없었습니다.

이에, *"네이버가 OIDC를 공식 지원하지 않는 것 같다"*는 결론을 내렸습니다.


## OAuth 2.0으로 전환

OIDC의 `id_token` 검증 중심 접근을 버리고, **OAuth 2.0 표준 흐름**으로 전환했습니다.

핵심 변경점은 다음과 같습니다.
- 토큰 응답에서 `access_token`을 받아
- **User Info API**를 호출해 사용자 정보를 가져오는 방식


## 실제 API 테스트 기록

### 1. Authorization 요청 (code 발급)

```
https://nid.naver.com/oauth2.0/authorize?client_id={client_id}&response_type=code&redirect_uri=http://localhost:8000/docs&state=234&scope=openid
```

### 2. Redirect 결과 (code 수신)

```
http://localhost:8000/docs?code={code}&state=234
```

![OAuth 2.0 응답 성공](/assets/img/posts/2026-03-12-doongzi-naver-oauth/3.png)
*OAuth 2.0 응답 성공*

### 3. Token 교환 (access_token 발급)

```
https://nid.naver.com/oauth2/token?grant_type=authorization_code&client_id={client_id}&client_secret={client_secret}&code={code}&state=234
```

![로그인(회원가입) 요청](/assets/img/posts/2026-03-12-doongzi-naver-oauth/2.png)
*로그인(회원가입) 요청*

![Swagger UI 확인](/assets/img/posts/2026-03-12-doongzi-naver-oauth/1.png)
*Swagger UI 확인*


## OIDC vs OAuth2.0

| 항목 | 이전 (OIDC) | 변경 후 (OAuth 2.0) |
|------|------------|---------------------|
| 페이로드 | `{"id_token": "..."}` | `{"access_token": "..."}` |
| 모킹 대상 | `PyJWKClient`, `jwt.decode` | `httpx.AsyncClient` |
| social_id 소스 | `idinfo["sub"]` | `user_info["id"]` |
| 프로필 URL 소스 | `idinfo["picture"]` | `user_info["profile_image"]` |
| 닉네임 소스 | `idinfo["name"]` | `user_info["nickname"]` |
| 실제 API 테스트 환경변수 | `NAVER_TEST_ID_TOKEN` | `NAVER_TEST_ACCESS_TOKEN` |


---

### 레퍼런스

[Naver Developers 개발 가이드 - Open ID Connect로 네이버 로그인 연동하기](https://developers.naver.com/docs/login/devguide/devguide.md#3-5-open-id-connect%EB%A1%9C-%EB%84%A4%EC%9D%B4%EB%B2%84-%EB%A1%9C%EA%B7%B8%EC%9D%B8-%EC%97%B0%EB%8F%99%ED%95%98%EA%B8%B0)