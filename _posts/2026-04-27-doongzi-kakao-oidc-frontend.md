---
title: "[둥지] 카카오 OIDC 소셜 로그인 프론트엔드 연동"
date: 2026-04-27 10:00:00 +0900
categories: [Project, 둥지]
tags: [Kakao, OIDC, OAuth2, TypeScript, React, Authentication, Frontend, SessionStorage]
toc: true
comments: true
image: /assets/img/posts/2026-04-27-doongzi-kakao-oidc-frontend/2.png
description: "카카오 소셜 로그인을 프론트엔드에 연동하는 과정을 정리합니다. SDK 동적 로드, 프론트 측 토큰 교환, sessionStorage를 이용한 약관 동의 전달, scope 범위 결정까지 다섯 가지 결정을 중심으로 기록합니다."
---

![약관 동의 페이지](/assets/img/posts/2026-04-27-doongzi-kakao-oidc-frontend/2.png)
*약관 동의 페이지*

약관 동의 페이지(`/signup/terms`)와 로그인 페이지(`/login`)에 카카오 소셜 로그인을 연동했습니다. [백엔드 OIDC 검증 구조]({% post_url 2026-03-11-doongzi-kakao-oauth-vs-oidc %})는 이미 갖춰져 있었고, 프론트엔드에서는 SDK 로드 방식부터 토큰 교환 위치, 약관 동의 전달 방법까지 결정할 사항이 여러 개 있었습니다.

---

## 전체 데이터 흐름

```
[약관동의 페이지]
  └─ 필수 약관 동의 후 "카카오로 가입" 클릭
       └─ consent를 sessionStorage에 저장
       └─ Kakao.Auth.authorize() → 카카오 로그인 페이지로 리다이렉트

[카카오 서버]
  └─ 사용자 로그인 + 동의
  └─ /oauth/kakao/callback?code=... 로 리다이렉트

[KakaoCallbackPage]
  └─ URL에서 code 추출
  └─ POST https://kauth.kakao.com/oauth/token (JS Key 사용)
       └─ id_token 추출
  └─ POST /api/v1/auth/login/KAKAO { id_token, terms_agreed, privacy_agreed, marketing_agreed }
       └─ 백엔드: JWKS로 id_token 서명 검증 → 사용자 upsert → JWT 발급
  └─ 세션 저장 → /nests 이동
```

![카카오로 가입](/assets/img/posts/2026-04-27-doongzi-kakao-oidc-frontend/1.png)
*카카오로 가입*

로그인 페이지에서의 카카오 로그인도 동일한 콜백 흐름을 사용합니다. 다만 약관 동의 없이 바로 `authorizeWithKakao()`를 호출합니다.

---

## 토큰 교환 위치: 프론트엔드 vs 백엔드

카카오 OIDC에서 `id_token`을 얻으려면 authorization code를 카카오 토큰 엔드포인트에 교환해야 합니다. 이 교환을 프론트에서 할지 백엔드에서 할지가 첫 번째 갈림길이었습니다.

| 방식 | 특징 |
|------|------|
| **프론트에서 교환** | 카카오 토큰 엔드포인트에 직접 POST → `id_token` 획득 후 백엔드 전달 |
| **백엔드에서 교환** | 프론트가 code만 전달, 백엔드가 REST API Key + `client_secret`으로 교환 |

**프론트엔드 교환을 선택**했습니다. 백엔드가 이미 `id_token`을 받는 구조였고, 카카오 토큰 엔드포인트(`kauth.kakao.com/oauth/token`)는 CORS를 허용하기 때문에 브라우저에서 직접 호출이 가능합니다. 기존 `authAPI.loginWithProvider(provider, id_token, consent)` 스펙을 그대로 사용할 수 있어 백엔드 변경이 필요하지 않았습니다.

JS Key로 교환한 토큰의 `aud`가 JS Key와 동일하게 담겨 백엔드 JWKS 검증도 통과됨을 확인한 뒤 확정했습니다.


## Kakao SDK 로드 방식: 정적 삽입 vs 동적 로드

**`index.html`에 `<script>` 태그를 넣으면** 앱 진입 시 항상 SDK를 로드합니다. 카카오 로그인을 쓰지 않는 사용자도 로드 비용을 부담하게 됩니다.

**동적 로드 방식은** 카카오 버튼을 클릭하는 시점에 SDK script를 삽입합니다. 이미 로드된 경우 재로드 없이 재사용합니다.

**동적 로드를 선택**했습니다. SDK 용량이 작지 않고, 소셜 로그인을 사용하지 않는 사용자에게 불필요한 로드를 강제할 이유가 없습니다. 클릭 시점 로드는 체감 지연이 거의 없고 재사용도 보장됩니다.


## 약관 동의 consent 전달 방식

카카오 로그인은 외부 페이지로 리다이렉트됐다가 돌아오기 때문에, 리다이렉트 전에 수집한 약관 동의 값을 콜백 페이지에서 사용해야 합니다.

**URL state 파라미터** 방식은 `Kakao.Auth.authorize({ state: JSON.stringify(consent) })`로 전달하면 카카오가 콜백 URL에 state를 그대로 붙여줍니다. 하지만 URL에 약관 동의 여부가 노출됩니다.

**sessionStorage 방식은** 리다이렉트 전에 저장하고 콜백에서 읽은 뒤 즉시 삭제합니다. 탭을 닫으면 자동 소멸하고, 동일 탭 내에서만 유효합니다.

**sessionStorage를 선택**했습니다. 약관 동의 여부를 URL에 노출할 이유가 없고, 탭 단위 생명주기가 의도에 더 맞습니다.


## 재로그인 시 프로필 사진 덮어쓰기

백엔드 `_register_or_login_social_user`에는 기존 사용자가 재로그인할 때 카카오 `profile_url`이 DB와 다르면 업데이트하는 로직이 있었습니다.

```python
if profile_url and user.profile_url != profile_url:
    user.profile_url = profile_url
    await db.commit()
```

사용자가 앱 내에서 프로필 사진을 삭제(`profile_url = None`)해도, 재로그인 시 카카오 프로필 사진으로 복원되는 문제가 있었습니다. 원래 의도는 카카오에서 프로필 사진을 변경한 경우 앱에도 자동 반영하는 것이었지만, 이를 유지하면 사용자가 명시적으로 삭제한 데이터가 외부 소스로 덮어써집니다.

**앱 내 사용자 설정을 우선시하기로 했습니다.** 프로필 사진은 최초 가입 시에만 카카오에서 가져오고, 이후에는 앱 내 변경만 유효합니다. 카카오 프로필과의 자동 동기화는 해당 로직을 제거하면서 포기했습니다.

