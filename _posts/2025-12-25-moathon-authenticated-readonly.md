---
title: "[모아톤] 전역 권한 정책 재수립 및 비로그인 사용자 UX 개선"
date: 2025-12-25 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Django, DRF, Vue.js, Permissions, UX, Authentication, Refactoring]
toc: true 
comments: true
image: /assets/img/posts/2025-12-25-moathon-authenticated-readonly/1.png
description: "서비스의 전역 권한 정책을 IsAuthenticatedOrReadOnly로 변경하여 보안을 강화하고, 비로그인 사용자가 상세 페이지나 기능에 접근할 때 발생하는 무한 로딩 및 UX 문제를 해결한 과정을 정리했습니다."
---

서비스의 전역 권한 정책을 재수립하고, 비로그인 사용자가 상세 페이지나 추천 기능에 접근할 때 발생하는 UX 문제(무한 로딩, 동작 없음, 잘못된 리다이렉트 등)를 해결했다.
보안은 강화하되, 게스트(Guest) 사용자에게는 탐색의 자유를 보장하는 것이 이번 작업의 핵심이다.

---

## Backend: 전역 권한 정책 변경

기존에는 개발 편의를 위해 `AllowAny`로 열려있던 권한을, 실서비스 기준에 맞춰 **`IsAuthenticatedOrReadOnly`**로 변경했다. 이제 비로그인 사용자도 조회(GET)는 자유롭게 가능하지만, 데이터의 생성/수정/삭제(POST/PUT/DELETE)는 로그인한 사용자만 가능하다.

### settings.py 설정

랜딩 페이지를 제외한 모든 View에 기본적으로 적용된다.

```python
# backend/settings.py

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication', # Swagger 테스트용
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        # 읽기(GET)는 누구나, 쓰기(POST/PUT/DELETE)는 인증된 사용자만
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}
```
## Frontend: UX 개선 및 예외 처리
권한 정책 변경에 맞춰 프론트엔드에서도 비로그인 사용자가 겪을 수 있는 에러 상황(401 Unauthorized)을 처리해야 한다.

### 모아톤 상세 페이지 (401 vs 404 처리)
**문제 상황:** 비로그인 사용자가 상세 페이지에 접근 시, 백엔드에서 401 에러를 반환하면 프론트엔드에서 이를 처리하지 못해 화면이 멈추거나 무한 로딩에 빠지는 현상이 있었다.

**해결 전략:** Pinia Store에서 에러를 `throw`하고, View 컴포넌트에서 이를 `catch`하여 에러 상태 코드에 따라 분기 처리했다.

**구현 코드:**
- **Store** (`moathon.js`): `catch` 블록에서 에러를 상위로 던진다.
- **View** (`MoathonDetailView.vue`): `watch` 내부에서 에러를 잡아 로그인 페이지로 리다이렉트한다.

![접근 권한에 따른 처리](/assets/img/posts/2025-12-25-moathon-authenticated-readonly/5.png)
*접근 권한에 따른 처리*

![결과: 401 에러 발생 시 로그인 페이지로 이동](/assets/img/posts/2025-12-25-moathon-authenticated-readonly/4.png)
*결과: 401 에러 발생 시 로그인 페이지로 이동*


### 금융 상품 상세 및 생성 가드
비로그인 사용자도 금융 상품의 상세 정보는 볼 수 있어야 한다(AllowAny). 하지만 *'이 옵션으로 시작하기'* 버튼을 눌러 실제로 모아톤을 생성하려 할 때는 로그인을 요구해야 한다.

```js
// ProductDetailView.vue

// 1. 상품 정보 로딩 (비로그인 허용)
const fetchProduct = async (productId) => {
  isLoading.value = true
  try {
    // 인증 헤더 없이 호출
    await store.getProductDetail(productId)
  } catch (err) {
    console.error('상품 정보 로딩 실패:', err)
  } finally {
    isLoading.value = false
  }
}

// 2. 생성 버튼 클릭 시 가드 (Guard Logic)
const goMoathonCreate = (optionId) => {
  if (!accountStore.isLogin) {
    const userConfirm = confirm('로그인이 필요한 서비스입니다.\n로그인 페이지로 이동하시겠습니까?')
    
    if (userConfirm) {
      router.push({ name: 'login' })
    }
    return
  }

  router.push({
    name: 'moathonCreate',
    query: { productId: optionId }
  })
}
```

![비로그인 사용자가 모아톤 생성하려고 할 때, 로그인 페이지로 이동](/assets/img/posts/2025-12-25-moathon-authenticated-readonly/3.png)
*비로그인 사용자가 모아톤 생성하려고 할 때, 로그인 페이지로 이동*



### 메인 페이지: 추천 기능 분기 처리 (3-Step Guard)

**문제 상황:** 기존에는 비로그인 사용자가 '내 맞춤 모아톤 만들기'를 클릭하면 엉뚱하게 프로필 수정 페이지(`/mypage`)로 이동하는 문제가 있었다.

![문제: 비로그인 사용자가 모아톤 추천하기 접근 시, 프로필 정보 입력(/mypage) 으로 이동](/assets/img/posts/2025-12-25-moathon-authenticated-readonly/2.png)
*문제: 비로그인 사용자가 모아톤 추천하기 접근 시, 프로필 정보 입력(/mypage) 으로 이동*

**해결 전략:** 사용자의 상태를 3단계로 구분하여 적절한 페이지로 안내하는 `handleStartRecommendation` 함수를 구현했다.

- **비로그인 사용자** → 로그인 안내 & 로그인 페이지
- **로그인 했으나 정보 누락** → 추가 정보 입력 안내 & 프로필 수정 페이지
- **정상 사용자** → 모아톤 추천 페이지

```js
const handleStartRecommendation = () => {
  // Case 1: 비로그인
  if (!accountStore.isAuthenticated) {
    const userConfirm = confirm('로그인이 필요한 서비스입니다.\n로그인 페이지로 이동하시겠습니까?')
    if (userConfirm) router.push({ name: 'login' })
    return
  }

  const user = accountStore.user
  // Case 2: 프로필 정보 불완전
  const isProfileIncomplete = user?.gender === null || 
                              user?.credit_score === null || 
                              user?.assets === null || 
                              user?.salary === null

  if (isProfileIncomplete) {
    const confirmMsg = confirm(
      '상품 추천을 위해 추가 정보가 필요합니다.\n\n프로필 수정 페이지로 이동하여 정보를 입력하시겠습니까?'
    )
    if (confirmMsg) {
      router.push({ 
        name: 'mypage',
        query: { edit: 'true' }
      })
    }
    return
  }

  // Case 3: 정상 진입
  router.push({ name: 'moathonRecommend' })
}
```

![해결: 비로그인 사용자가 내 맞춤 모아톤 만들기 누르면, 로그인 페이지로 이동](/assets/img/posts/2025-12-25-moathon-authenticated-readonly/1.png)
*해결: 비로그인 사용자가 내 맞춤 모아톤 만들기 누르면, 로그인 페이지로 이동*

---

## 마치며
이번 작업을 통해 백엔드는 보안성을 챙기고, 프론트엔드는 사용자의 인증 상태에 따라 물 흐르듯 자연스러운 UX를 제공하게 되었다. 특히 권한 없음(401) 상황에서 단순히 에러를 띄우는 것이 아니라, **"로그인이 필요합니다"라고 안내하고 적절한 곳으로 데려다주는 친절한 내비게이션**을 구축했다.