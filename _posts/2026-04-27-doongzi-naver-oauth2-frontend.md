---
title: "[둥지] 네이버 OAuth 2.0 소셜 로그인 프론트엔드 연동"
date: 2026-04-27 11:00:00 +0900
categories: [Project, 둥지]
tags: [Naver, OAuth2, TypeScript, React, Authentication, Frontend, Backend, CORS, CSRF, FastAPI, Python]
toc: true
comments: true
image: /assets/img/posts/2026-04-27-doongzi-naver-oauth2-frontend/1.png
description: "네이버 소셜 로그인을 OIDC로 시도했다가 OAuth 2.0으로 전환한 과정을 기록합니다. CORS 차단으로 백엔드 토큰 교환을 선택하고, URL 오류·state 누락·follow_redirects 등 서버 사이드 디버깅까지 정리합니다."
---

네이버 소셜 로그인을 카카오·구글처럼 OIDC로 시도했지만, 네이버가 OIDC를 공식 지원하지 않아 OAuth 2.0으로 전환했습니다. 최종 구조는 프론트가 code만 백엔드로 넘기고, 백엔드가 서버 사이드에서 토큰 교환과 프로필 조회를 모두 담당합니다.

---

## 전체 데이터 흐름

```
[약관동의 페이지 / 로그인 페이지]
  └─ "네이버로 가입/로그인" 클릭
       └─ consent를 sessionStorage에 저장 (가입 흐름만)
       └─ state를 생성해 sessionStorage에 저장 (CSRF 방어)
       └─ https://nid.naver.com/oauth2.0/authorize 로 리다이렉트

[네이버 서버]
  └─ 사용자 로그인 + 동의
  └─ /oauth/naver/callback?code=...&state=... 로 리다이렉트

[NaverCallbackPage]
  └─ URL에서 code, state 추출
  └─ sessionStorage의 state와 비교 → 불일치 시 약관 페이지로 이동 (CSRF 차단)
  └─ POST /api/v1/auth/login/NAVER
       { code, state, redirect_uri, terms_agreed, privacy_agreed, marketing_agreed }

[백엔드 - process_naver_login]
  └─ GET https://nid.naver.com/oauth2.0/token → access_token 획득
  └─ GET https://openapi.naver.com/v1/nid/me → 유저 정보 추출
  └─ _register_or_login_social_user → 사용자 upsert → JWT 발급
```

![네이버로 가입](/assets/img/posts/2026-04-27-doongzi-naver-oauth2-frontend/1.png)
*네이버로 가입*


---

## OIDC 시도에서 OAuth 2.0 전환까지

처음에는 카카오·구글처럼 `id_token` 기반 OIDC 방식으로 구현을 시도했습니다. Authorization Code 발급 후 토큰 교환 시 `id_token`을 수신하고, OIDC discovery 문서와 JWK endpoint로 공개키를 획득해 검증하는 흐름이었습니다.

문제는 네이버가 OIDC를 공식 지원하지 않는다는 점이었습니다. discovery 문서 조회, JWK fetch 등이 반복적으로 실패했고, `scope=openid`를 붙여봐도 `id_token`은 응답에 포함되지 않았습니다.

OIDC를 포기하고 네이버 공식 방식인 OAuth 2.0으로 전환했습니다.

| 항목 | OIDC 시도 (실패) | OAuth 2.0 (채택) |
|------|-----------------|-----------------|
| 페이로드 | `{"id_token": "..."}` | `{"code": "..."}` |
| 모킹 대상 | `PyJWKClient`, `jwt.decode` | `httpx.AsyncClient` |
| social_id 소스 | `idinfo["sub"]` | `user_info["id"]` |
| 프로필 URL 소스 | `idinfo["picture"]` | `user_info["profile_image"]` |
| 닉네임 소스 | `idinfo["name"]` | `user_info["nickname"]` |

---

## 토큰 교환 위치: 프론트엔드 vs 백엔드

OAuth 2.0으로 전환한 후, 카카오와 동일하게 프론트엔드에서 code → access_token 교환을 시도했습니다.

그런데 네이버 토큰 엔드포인트(`https://nid.naver.com/oauth2.0/token`)는 CORS를 허용하지 않습니다. 카카오의 `kauth.kakao.com/oauth/token`은 CORS를 허용하지만, 네이버는 브라우저 직접 호출을 막습니다.

```
Access to fetch at 'https://nid.naver.com/oauth2.0/token' from origin 'http://localhost:3000'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present.
```

**백엔드에서 토큰을 교환하기로 했습니다.** 프론트는 code를 백엔드로 전달하고, 백엔드 서버가 네이버 토큰 엔드포인트를 호출합니다. `client_secret`이 프론트 번들에서 완전히 제거되어 보안상으로도 더 올바른 구조가 됐습니다.

이에 따라 백엔드 스키마도 변경됐습니다.

```python
# 프론트에서 교환한 access_token을 받던 구조 (폐기)
access_token: Optional[str]

# 최종: 인가 코드를 받아 서버에서 교환
code: Optional[str]
state: Optional[str]
redirect_uri: Optional[str]
```

## 토큰 엔드포인트 URL: `oauth2/token` vs `oauth2.0/token`

초기 구현에서 토큰 엔드포인트를 `https://nid.naver.com/oauth2/token`으로 호출했습니다. 네이버 서버가 302 리다이렉트로 응답했고, `follow_redirects=True`를 추가해 따라가면 네이버 로그인 HTML 페이지가 반환됐습니다.

인증 URL이 `oauth2.0/authorize`인 것처럼 토큰 URL도 `oauth2.0/token`이어야 합니다. `.0`이 빠진 `oauth2/token`은 잘못된 경로입니다.

```python
# 잘못된 URL
"https://nid.naver.com/oauth2/token"

# 올바른 URL
"https://nid.naver.com/oauth2.0/token"
```

## `redirect_uri` · `state` 필수 전달

토큰 교환 요청에 `state`와 `redirect_uri`를 누락했을 때 네이버 서버가 요청을 거부하며 로그인 페이지로 리다이렉트했습니다.

프론트가 `state`와 `redirect_uri`를 백엔드로 함께 전달하고, 백엔드는 이 값들을 토큰 교환 요청에 그대로 포함합니다. `redirect_uri`는 인가 요청 시 사용한 값과 정확히 일치해야 하므로, 프론트엔드에서 `window.location.origin + "/oauth/naver/callback"`으로 동적으로 생성해 전달합니다.

```python
params={
    "grant_type": "authorization_code",
    "client_id": settings.NAVER_CLIENT_ID,
    "client_secret": settings.NAVER_CLIENT_SECRET,
    "code": payload.code,
    "state": payload.state,
    "redirect_uri": payload.redirect_uri,
}
```

## httpx `follow_redirects=True`

httpx는 기본적으로 리다이렉트를 따라가지 않습니다. 네이버 토큰 엔드포인트가 302를 반환하는 경우가 있어 이 옵션 없이는 정상 응답을 받을 수 없었습니다.

```python
async with httpx.AsyncClient(follow_redirects=True) as client:
    token_response = await client.get("https://nid.naver.com/oauth2.0/token", ...)
```

## CSRF 방어: state 파라미터

OAuth 2.0 code 방식은 리다이렉트 전후로 요청 주체를 검증해야 합니다. 네이버가 콜백 URL에 `state`를 그대로 반환하므로 이를 이용해 CSRF를 방어합니다.

- 리다이렉트 전: `crypto.getRandomValues`로 랜덤 state 생성, `sessionStorage`에 저장
- 콜백 수신 시: URL의 `state`와 `sessionStorage`의 값을 비교, 불일치 시 약관 페이지로 이동
- 검증 후 즉시 `sessionStorage`에서 삭제 (one-time use)

```typescript
const STATE_KEY = 'naver_oauth_state';

export const authorizeWithNaver = (clientId: string): void => {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  const state = Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('');
  sessionStorage.setItem(STATE_KEY, state);

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: `${window.location.origin}/oauth/naver/callback`,
    state,
  });
  window.location.href = `https://nid.naver.com/oauth2.0/authorize?${params.toString()}`;
};

export const consumeNaverState = (): string | null => {
  const state = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(STATE_KEY);
  return state;
};
```

## 네이버 앱 환경별 분리

카카오·구글은 앱 하나에 redirect URI를 여러 개 등록할 수 있어 환경별 키를 통합 관리할 수 있습니다. 네이버는 앱 하나에 서비스 URL을 하나만 등록할 수 있습니다.

환경별로 네이버 앱을 각각 생성하고 `VITE_NAVER_CLIENT_ID`를 환경 파일별로 분리했습니다.

| 환경 | 프론트 env 파일 | 백엔드 env 파일 |
|------|----------------|----------------|
| local | `.env.local` | `.env.local` |
| dev | `.env.development` | `.env.dev` |
| prod | `.env.production` | `.env.prod` |

---

## 카카오·구글과의 비교

| 항목 | 카카오 | 구글 | 네이버 |
|------|--------|------|--------|
| 인증 방식 | OIDC | OIDC | OAuth 2.0 |
| OIDC 지원 | ✓ | ✓ | ✗ |
| 프론트 → 백엔드 전달값 | `id_token` | `id_token` | `code` + `state` + `redirect_uri` |
| 토큰 교환 위치 | 프론트 (CORS 허용) | 불필요 | 백엔드 (CORS 차단) |
| 백엔드 검증 방식 | JWKS 서명 검증 | JWKS 서명 검증 | 프로필 API 호출 |
| client_secret 위치 | 불필요 | 불필요 | 백엔드 환경변수 |
| 환경별 앱 분리 | 불필요 | 불필요 | 필요 (URL 1개 제한) |

