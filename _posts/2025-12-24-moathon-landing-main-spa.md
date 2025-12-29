---
title: "[모아톤] 메인/랜딩 페이지 구현과 SPA 상태 관리 트러블슈팅"
date: 2025-12-24 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Vue.js, Pinia, SPA, Troubleshooting, Lifecycle, Authentication, Refactoring]
toc: true 
comments: true
image: /assets/img/posts/2025-12-24-moathon-landing-main-spa/4.png
description: "모아톤의 메인 및 랜딩 페이지를 구현하면서 발생한 Pinia 상태 동기화 문제, 로그아웃 시 401 에러, 데이터 오염 문제, 그리고 Vue 라이프사이클 관련 이슈들을 해결한 과정을 정리했습니다."
---

오늘은 프로젝트의 얼굴인 **메인 페이지**와 서비스를 소개하는 **랜딩 페이지**를 구현하고, 전반적인 서비스 흐름을 연결하는 작업을 진행했다.
이 과정에서 SPA(Single Page Application)의 특성으로 인한 **데이터 동기화 문제**와 **상태 관리 이슈**들이 다수 발생했다.

백엔드 DB와 프론트엔드 메모리(Pinia) 사이의 간극을 메우기 위해 고군분투했던 기록을 남긴다.

---

## 트러블슈팅 로그 (Troubleshooting Log)

### 1. 데이터 동기화 이슈 (Stale Data Issue)

![새로고침을 해도 getFollowingMoathons 함수가 실행되지 않음](/assets/img/posts/2025-12-24-moathon-landing-main-spa/6.png)
*새로고침을 해도 getFollowingMoathons 함수가 실행되지 않음*

- **상황 (Problem):**
  모아톤을 새로 생성하거나 삭제하고 메인 페이지로 돌아왔을 때, 변경 사항(진행 중인 모아톤 표시, 리스트 갱신 등)이 즉시 반영되지 않고 **새로고침을 해야만 보이는 현상**이 발생했다.

- **원인 (Cause):**
  SPA 특성상, 페이지 이동(`router.push`)을 하더라도 **Pinia Store에 저장된 `user` 정보는 이전에 로드된 상태(캐시) 그대로 유지**된다. 즉, DB는 업데이트되었으나 프론트엔드 메모리 상의 데이터는 갱신되지 않은 'Stale Data' 상태였다.

- **해결 (Solution):**
  데이터 변경(Create, Delete, Follow)이 발생하는 시점에 `accountStore.getProfile()` 액션을 강제로 호출하여, **Store의 상태를 최신 DB 데이터와 동기화한 후 페이지를 이동**하도록 수정했다.

```javascript
// frontend/src/components/moathon/MoathonCreateForm.vue

const submitForm = async () => {
  try {
    // 1. 모아톤 생성 API 호출
    await moathonStore.createMoathon(formData)

    // [Fix] 2. 내 프로필 정보(user state)를 서버에서 다시 받아와 갱신
    await accountStore.getProfile()

    alert('모아톤이 성공적으로 개설되었습니다!')
    router.push({ name: 'home' })
  } catch (err) { 
    console.error(err)
  }
}
```

![로그인 시 메인 페이지](/assets/img/posts/2025-12-24-moathon-landing-main-spa/5.png)
*로그인 시 메인 페이지*

### 2. 로그아웃 401 에러 및 상태 잔존 (Logout Robustness)

- **상황 (Problem):** 로그아웃 버튼을 눌렀을 때 콘솔에 `401 Unauthorized` 에러가 발생하고, 실제 화면에서는 로그아웃이 되지 않거나(유저 정보 잔존), 에러 때문에 스크립트 실행이 중단되었다.

- **원인 (Cause):**

    - **헤더 누락**: 로그아웃 요청 시 `Authorization` 헤더에 토큰을 실어 보내지 않아 서버가 거부한다.
    - **예외 처리 미흡**: 토큰 만료 등의 이유로 API 요청이 실패하면 `catch` 블록으로 빠지면서, 그 뒤에 있는 `token = null` 초기화 로직이 실행되지 않는다.

- **해결 (Solution):** API 요청 헤더에 토큰을 추가하고, `finally` 블록을 사용하여 성공/실패 여부와 관계없이 무조건 클라이언트 상태를 초기화하도록 방어 코드를 작성했다.

```javascript
// frontend/src/stores/accounts.js

const logOut = async function () {
  try {
    if (token.value) {
      // [Fix 1] 헤더에 토큰 포함하여 요청
      await axios({
        method: 'post',
        url: `${API_URL}/accounts/logout/`,
        headers: { Authorization: `Token ${token.value}` }
      })
    }
  } catch (err) {
    console.warn('서버 로그아웃 실패(무시):', err)
  } finally {
    // [Fix 2] 에러가 나더라도 무조건 실행되는 구역 (클라이언트 강제 로그아웃)
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }
}
```

### 3. 타 스토어 데이터 오염 (Cross-Store Pollution)

- **상황 (Problem):** A 유저가 로그아웃 후 B 유저로 로그인했는데, 메인 페이지에서 **A 유저가 팔로우했던 친구 목록이 그대로 노출**되는 심각한 보안/데이터 오염 문제가 발생했다.

- **원인 (Cause):** `accountStore`의 유저 정보는 초기화했지만, `moathonStore`에 저장된 `followingMoathons` 리스트는 초기화하지 않았다. Pinia는 새로고침 전까지 메모리에 데이터를 유지하므로 이전 유저의 데이터가 남아있던 것이다.

- **해결 (Solution):** 각 Store에 `resetState()` 함수를 구현하고, 로그아웃 시 이를 호출하거나 브라우저를 강제로 새로고침하여 데이터를 완벽히 격리했다.

```js
// frontend/src/stores/moathon.js
const resetState = () => {
  moathons.value = []
  followingMoathons.value = [] // [Fix] 팔로잉 목록 초기화
  moathonDetail.value = null
}

// frontend/src/components/common/HeaderNav.vue (로그아웃 핸들러)
const logOut = function () {
  accountStore.logOut()
  moathonStore.resetState()   // 모아톤 관련 데이터 삭제
  window.location.href = '/'  // [Fix] 브라우저 새로고침으로 완벽 격리
}
```
  
![비로그인 시 메인 페이지](/assets/img/posts/2025-12-24-moathon-landing-main-spa/4.png)
*비로그인 시 메인 페이지*

### 4. 랜딩 페이지 스크립트 마이그레이션 (Vue Lifecycle)

- **상황 (Problem):** 기존 HTML/JS로 작성된 랜딩 페이지를 Vue 컴포넌트(`LandingView.vue`)로 옮겼으나, 스크롤 애니메이션(`IntersectionObserver`)이 작동하지 않았다.

- **원인 (Cause):** 일반 HTML 파일에서는 `<script>`가 `<body>` 끝에 있어 요소 로딩 후 실행되었으나, Vue의 `<script setup>`은 컴포넌트 생성 시점에 실행된다. 즉, **DOM 요소가 아직 렌더링되지 않은 상태에서 `document.querySelectorAll`을 실행**했기 때문에 요소를 찾지 못한 것이다.

- **해결 (Solution):** Vue의 생명주기 훅인 `onMounted` 내부로 DOM 조작 로직을 이동시켜, 화면이 실제로 그려진 이후에 옵저버가 실행되도록 수정했다.

```js
// frontend/src/views/LandingView.vue
import { onMounted } from 'vue'

onMounted(() => {
  // [Fix] 마운트 이후에 DOM 요소 선택
  const revealElements = document.querySelectorAll('.reveal')
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.classList.add('active')
    })
  })
  
  revealElements.forEach(el => observer.observe(el))
})
```

![랜딩 페이지 (1/3)](/assets/img/posts/2025-12-24-moathon-landing-main-spa/3.png)
*랜딩 페이지 (1/3)*

![랜딩 페이지 (2/3)](/assets/img/posts/2025-12-24-moathon-landing-main-spa/2.png)
*랜딩 페이지 (2/3)*

![랜딩 페이지 (3/3)](/assets/img/posts/2025-12-24-moathon-landing-main-spa/1.png)
*랜딩 페이지 (3/3)*

---

## 마치며

이번 작업에서는 단순히 기능을 구현하는 것을 넘어, **사용자 경험의 연속성(Data Sync)**과 **보안 및 데이터 격리(Logout/Reset)** 측면에서 많은 개선이 있었다.

특히 프론트엔드 상태 관리(Pinia)와 백엔드 데이터(DB) 간의 타이밍 이슈를 해결하며, **SPA 개발에서 생명주기(Lifecycle)와 상태 동기화**가 얼마나 중요한지 다시 한번 깨닫게 되었다.