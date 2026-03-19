---
title: "[둥지] 카카오 OAuth 2.0 vs OIDC 비교 및 OIDC 채택기"
date: 2026-03-11 00:00:00 +0900
categories: [Project, 둥지]
tags: [Kakao, OIDC, OAuth2, JWT, FastAPI, Authentication, Backend, Python]
toc: true
comments: true
image: /assets/img/posts/2026-03-11-doongzi-kakao-oauth-vs-oidc/1.png
description: "카카오 로그인의 OAuth 2.0 방식과 OIDC 방식을 비교하고, 구글 OIDC와 통일성을 위해 카카오 OIDC를 채택한 이유와 구현 핵심을 정리합니다."
---

카카오 로그인을 연동하기 전에, 데이터 흐름의 차이를 아는 것이 매우 중요합니다. 현재 구현된 구글 로그인은 **OIDC(OpenID Connect)의 `id_token` 방식**을 사용하고 있는데, 한국에서 가장 흔히 쓰이는 카카오 로그인은 **전통적인 OAuth 2.0의 `access_token` 방식**을 주로 사용하기 때문입니다.

---

## OIDC vs OAuth 2.0

### 구글 로그인 (OIDC 방식)

구글 로그인은 백엔드가 구글 서버와 직접 통신하지 않는 '자체 검증' 방식입니다.

1. 프론트엔드가 구글로부터 `id_token`(JWT)을 받아 백엔드로 보냅니다.
2. 백엔드는 구글 API를 호출하지 않고, **구글의 공개키를 이용해 자체적으로 JWT 서명을 검증**합니다.
3. 검증이 통과되면 토큰 안의 페이로드를 열어 이메일과 고유 ID(`sub`)를 즉시 꺼내어 사용합니다.
- **장점:** 속도가 매우 빠르고 서버 간 네트워크 지연(Latency)이나 장애의 영향을 받지 않습니다.

### 카카오 로그인 (OAuth 2.0 방식)

![카카오 로그인 시퀀스 다이어그램](/assets/img/posts/2026-03-11-doongzi-kakao-oauth-vs-oidc/1.png)
*카카오 로그인 시퀀스 다이어그램*

일반적으로 프론트엔드 개발자들이 연동하는 카카오 로그인의 표준 흐름입니다.

1. 프론트엔드가 카카오로부터 **`access_token`**(단순한 난수 문자열)을 받아 백엔드로 보냅니다.
2. 이 토큰 자체에는 유저 정보가 없습니다. 따라서 백엔드는 이 토큰을 Authorization 헤더에 담아 **카카오의 사용자 정보 조회 API(`https://kapi.kakao.com/v2/user/me`)로 HTTP GET 요청**을 직접 보내야 합니다.
3. 카카오 서버가 토큰을 확인하고 유저 정보(이메일, 카카오 고유 ID 등)를 JSON으로 백엔드에 응답해 줍니다.
- **단점:** 로그인할 때마다 둥지 백엔드와 카카오 서버 간의 HTTP 통신이 1회 필수적으로 발생하므로 구글 방식보다 약간 느립니다.

---

## 카카오 OIDC 채택 배경 및 구현

### 구글 로그인과의 통일성

| 방식 | 프론트엔드 전달 값 | 백엔드 처리 |
|------|-------------------|------------|
| OAuth 2.0 | `access_token` | 카카오 API 서버에 HTTP 요청 필요 |
| OIDC | `id_token` | 공개키로 자체 검증 (외부 통신 불필요) |

구글 로그인(OIDC)과 완전히 동일한 데이터 흐름을 가지게 되어, `SocialLoginRequest` 스키마 수정 없이 빠르고 일관된 아키텍처를 유지할 수 있습니다.

### RS256과 PyJWT

- **비대칭키(RS256) 암호화:** 카카오가 발급한 토큰은 카카오의 '개인키'로 잠겨있습니다. 둥지 백엔드는 카카오가 공개해 둔 '공개키(JWKS)'를 이용해 이 토큰이 진짜인지 해독합니다.
- **JWKS URL (`.well-known`):** 카카오의 공개키가 담긴 주소(`https://kauth.kakao.com/.well-known/jwks.json`)는 국제 표준에 따라 누구나 볼 수 있도록 열려있는 주소이므로, `.env`에 숨길 필요 없이 코드 상단에 상수로 선언해도 안전합니다.
- **Audience (수신자) 검증:** `jwt.decode` 시 `audience` 파라미터에 `KAKAO_CLIENT_ID`를 넣습니다. 이는 해커가 다른 앱에서 탈취한 정상적인 카카오 토큰을 둥지 서버로 찔러넣는 **'토큰 가로채기(Confused Deputy)' 공격**을 막아내는 핵심 방어벽입니다.

### OIDC 표준 클레임 (데이터 규격)

- **`sub` (Subject):** 유저를 구별하는 고유한 '회원번호'입니다. 카카오가 무조건 알아서 넣어주기 때문에 동의 항목 설정 화면에는 존재하지 않으며, 둥지 DB의 `social_id`로 매핑하여 사용합니다.
- **표준 프로필 정보:** `email`, `nickname`, `picture` 등은 카카오 독자 규격이 아닌 OIDC 국제 표준 이름입니다. 덕분에 구글과 카카오의 데이터를 동일한 키값으로 일관성 있게 꺼내 쓸 수 있습니다.

### 카카오 디벨로퍼스 설정

- **REST API 키:** 이것이 둥지 백엔드의 `KAKAO_CLIENT_ID`가 됩니다.
- **OIDC 활성화:** 카카오 로그인 설정 메뉴에서 반드시 **[OpenID Connect 활성화 설정]을 ON**으로 켜야 프론트엔드가 `id_token`을 받아올 수 있습니다.
- **동의 항목:** 이메일, 닉네임, 프로필 사진 등 필요한 정보를 수집하도록 설정합니다.

### 테스트 전략 (Mocking)

단위 및 통합 테스트 작성 시 외부 인프라(카카오 서버)와의 의존성을 끊어내기 위해, `PyJWT`의 `jwt.decode`와 `kakao_jwks_client.get_signing_key_from_jwt`를 `@patch`로 덮어씌워 가짜 페이로드를 반환하도록 모킹(Mocking)합니다.

---

## 레퍼런스

- [카카오 OIDC 공식 문서](https://developers.kakao.com/docs/latest/ko/kakaologin/utilize#oidc)
- [카카오 로그인 REST API 문서](https://developers.kakao.com/docs/latest/ko/kakaologin/rest-api)
- [카카오 OIDC 정리 블로그](https://andantej99.tistory.com/65)
