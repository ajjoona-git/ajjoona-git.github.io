---
title: "[둥지] Google OIDC 로그인 플로우"
date: 2026-03-09 00:00:00 +0900
categories: [Project, 둥지]
tags: [Google, OIDC, OAuth2, JWT, FastAPI, Authentication, Backend, Python]
toc: true
comments: true
image: /assets/img/posts/2026-03-09-doongzi-google-oidc/1.png
description: "구글 소셜 로그인이 실제로 어떻게 동작하는지, 프론트엔드부터 백엔드 검증, DB 처리, 세션 발급까지 4단계 플로우를 정리합니다."
---

소셜 로그인 중 첫 번째로 Google을 구현해보았습니다. OAuth2.0 방식보다 진화된 Google OIDC 로그인 플로우를 4단계로 나눠 정리합니다.

---

## Google OIDC 로그인 플로우

![Google OIDC 로그인 플로우](/assets/img/posts/2026-03-09-doongzi-google-oidc/1.png)
*Google OIDC 로그인 플로우*

### 1단계: 프론트엔드와 구글의 통신 (인증 획득)

백엔드가 개입하지 않고 프론트엔드와 구글 서버 사이에서만 일어나는 단계입니다.

1. **로그인 요청:** 사용자가 프론트엔드 화면에서 '구글로 시작하기' 버튼을 클릭합니다.
2. **구글 팝업 및 동의:** 프론트엔드에 심어진 구글 SDK가 구글 로그인 팝업을 띄우고, 사용자에게 이메일 제공 동의를 받습니다.
3. **ID 토큰 발급:** 로그인이 성공하면, 구글 서버는 프론트엔드에게 사용자의 정보(이메일 등)가 암호화되어 담긴 **`id_token` (구글이 서명한 JWT)**을 반환합니다.


### 2단계: 백엔드의 토큰 검증 (위변조 방어)

프론트엔드가 확보한 구글 토큰을 우리 백엔드로 넘겨주면서 본격적인 비즈니스 로직이 시작됩니다.

1. **API 호출:** 프론트엔드가 `POST /api/v1/auth/login/google` API를 호출하며 Request Body에 `id_token`을 담아 보냅니다.
2. **서명 및 만료 검증:** 백엔드는 이 토큰을 들고 구글 서버에 다시 물어보는 대신, 구글이 공개해 둔 **공개키(Public Key)**를 이용해 자체적으로 서명을 검증합니다. 이 덕분에 네트워크 지연 없이 즉시 위변조 여부와 만료 시간을 파악할 수 있습니다.
3. **정보 추출:** 검증이 통과되면 토큰의 페이로드를 열어 사용자의 `email`을 안전하게 추출합니다. 이메일 정보가 없다면 400 예외를 던집니다.

> **왜 구글 서버에 재요청하지 않나요?**
> 구글 공개키로 서명을 직접 검증하면 네트워크 왕복 없이 로컬에서 즉시 처리할 수 있습니다. 이것이 JWT + 공개키 방식의 핵심 장점입니다.


### 3단계: DB 조회 및 비즈니스 로직 (회원가입/충돌 처리)

추출한 이메일을 바탕으로 둥지 서비스의 정책에 맞게 PostgreSQL 데이터베이스를 조작합니다.

1. **유저 조회:** DB의 `User` 테이블에서 해당 이메일이 존재하는지 조회합니다.
2. **분기 처리:**

| 케이스 | 조건 | 처리 |
|--------|------|------|
| 일반 계정 충돌 | 이미 로컬 계정으로 가입된 이메일 | `LocalAccountAlreadyExistsException(400)` 반환 |
| 최초 로그인 (자동 가입) | DB에 유저 없음 | 랜덤 닉네임 생성 후 `password=None`, `provider="GOOGLE"`로 Insert |
| 기존 소셜 계정 | 이미 가입된 구글 유저 | 그대로 통과 |

3. **집 주소(Nest) 확인:** 해당 유저의 `Nest` 테이블 데이터를 조회하여, 등록된 주소가 있는지 확인하고 프론트엔드로 보낼 `redirect_url`을 결정합니다.


### 4단계: 둥지 세션 발급 (토큰 교환 완료)

이제 구글 유저가 아닌 완벽한 '둥지 유저'로서 자체 세션을 부여합니다.

1. **자체 JWT 발급:** 백엔드는 구글 토큰은 버리고, 둥지의 Secret Key를 사용해 자체 Access Token과 Refresh Token을 새로 생성합니다.
2. **Redis 화이트리스트 등록:** 생성된 Refresh Token을 Redis에 저장(`auth:refresh_token:{user_id}`)하여 다중 기기 제어 및 세션 관리를 준비합니다.
3. **최종 응답:** 프론트엔드에게 `200 OK`와 함께 발급된 토큰 2개, 그리고 `redirect_url`을 JSON으로 응답하며 모든 플로우가 종료됩니다.

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "redirect_url": "/home"
}
```

---

## 전체 플로우 요약

```
[사용자]
   │ 구글로 시작하기 클릭
   ▼
[프론트엔드] ──── Google SDK ────► [Google 서버]
                                        │ id_token 발급
                                        ▼
[프론트엔드] ──── POST /auth/login/google (id_token) ────►   [백엔드]
                                                               │
                                                   ┌───────────┴───────────┐
                                                   │ Google 공개키로        │
                                                   │ 서명 검증 (로컬)       │
                                                   └───────────┬───────────┘
                                                               │ email 추출
                                                               ▼
                                                        [PostgreSQL]
                                                    신규/기존/충돌 분기 처리
                                                                │
                                                                ▼
                                                            [Redis]
                                                    Refresh Token 저장
                                                                │
                                                                ▼
[프론트엔드] ◄──── 200 OK + Access/Refresh Token + redirect_url ────
```

---

### 레퍼런스

[Google OAuth 2.0 공식 문서](https://developers.google.com/identity/protocols/oauth2?hl=ko)