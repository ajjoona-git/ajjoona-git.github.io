---
title: "[모아톤] 로그인 후 팔로우 목록 조회 오류 수정 (비동기 처리 & Race Condition)"
date: 2025-12-24 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Frontend, Vue.js, Async, Await, Pinia, Troubleshooting, RaceCondition, StateManagement, SPA]
toc: true 
comments: true
image: /assets/img/posts/2025-12-24-moathon-following-list-troubleshooting/3.png
description: "로그인 직후 메인 페이지로 이동했을 때 팔로우 목록이 로드되지 않고 401 Unauthorized 에러가 발생하는 문제를 해결한 기록입니다. 비동기 처리 시점(Race Condition)을 분석하고, async/await과 watch를 활용하여 데이터 동기화를 보장했습니다."
---

프론트엔드 개발, 특히 SPA(Single Page Application) 환경에서 가장 빈번하게 마주치는 문제는 **비동기 처리(Async)와 상태 관리(State Management)의 타이밍 이슈**다.

오늘 해결한 이슈는 로그인 직후 메인 페이지로 이동했을 때, 친구들의 모아톤 목록(팔로잉 목록)이 로드되지 않는 문제였다. 이 현상은 전형적인 **경쟁 상태(Race Condition)**로, 로그인이 완료되기도 전에 데이터를 요청해서 발생한 문제였다. 이를 분석하고 해결한 과정을 정리한다.

---

## 로그인 직후 팔로우 목록 조회 실패 (Race Condition)

### 문제 상황

![로그인 직후 팔로우 목록 조회 실패](/assets/img/posts/2025-12-24-moathon-following-list-troubleshooting/3.png)
*로그인 직후 팔로우 목록 조회 실패*

- **상황 (Situation):**
  로그인 페이지에서 로그인을 완료하고 메인 페이지(`/home`)로 자동 이동되었으나, **'팔로우한 친구들의 모아톤' 목록이 비어있는 현상**이 발생했다. 콘솔을 확인해 보니 `/moathon/following/` 요청에 대해 `401 Unauthorized` 에러가 떠 있었으며, 페이지를 새로고침(F5) 해야만 정상적으로 데이터가 로드되었다.

- **재현 단계**
    1. 로그인 되어 있다면 로그아웃한다.
    2. 로그인 페이지에서 아이디/비밀번호를 입력하고 로그인한다.
    3. 메인 페이지(`/home`)로 자동 이동된다.
    4. 개발자 도구(Console)를 확인한다.

- **실제 결과**
    - 화면에 팔로우 목록이 출력되지 않음.
    - 콘솔에 `/moathon/following/` 요청에 대해 **`401 Unauthorized`** 에러 발생.
    - 페이지를 새로고침(F5) 하면 그제야 정상적으로 데이터가 로드됨.

### 원인 분석

![콘솔 로그: 팔로우 목록 로드 후 로그인](/assets/img/posts/2025-12-24-moathon-following-list-troubleshooting/2.png)
*콘솔 로그: 팔로우 목록 로드 후 로그인*

- **원인 (Cause):**
  전형적인 **비동기 처리 시점 불일치(Race Condition)** 문제다.
  1.  기존 `logIn` 액션은 `axios` 요청을 보내놓고 응답(토큰 저장)을 기다리지 않은 채 종료되었다.
  2.  이로 인해 `router.push`가 먼저 실행되어 메인 페이지로 이동해버렸다.
  3.  메인 페이지가 마운트(`onMounted`)되는 시점에는 아직 토큰이 저장되지 않았거나 `isAuthenticated`가 `false` 상태였기 때문에, API 요청이 거부되거나 누락되었다.

### 해결 방법

- **해결 (Solution):**
  로그인 프로세스를 동기적으로 처리하도록 **이중 안전장치(Await + Watch)**를 적용했다.
  1.  **Action 동기화:** `logIn` 액션에 `async/await`를 적용하여 토큰 저장과 프로필 로드가 100% 완료될 때까지 기다리도록 수정했다.
  2.  **View 대기:** `LoginView`에서 `await accountStore.logIn()`을 호출하여 로그인이 끝난 후 페이지를 이동시켰다.
  3.  **상태 감지:** `HomeView`에서 `watch`를 사용해 로그인 상태가 `true`로 변하는 순간을 포착하여 데이터를 로드하도록 보완했다.

### 코드 수정

**1. 로그인 Store 액션 수정 (`accounts.js`)**
- `axios` 요청 앞에 `await`를 붙여, 응답이 오고 토큰이 저장될 때까지 다음 줄로 넘어가지 않도록 보장한다.

```javascript
// frontend/src/stores/accounts.js

// [Fix] async 키워드 추가
const logIn = async function (payload) {
  const { username, email, password } = payload

  try {
    // [Fix] await로 비동기 요청이 끝날 때까지 대기
    const res = await axios({
      method: 'post',
      url: `${API_URL}/accounts/login/`,
      data: { username, email, password }
    })

    console.log('로그인 완료, 토큰 저장 중...')
    
    // 이 시점에는 확실히 응답을 받은 상태임
    token.value = res.data.key
    localStorage.setItem('token', res.data.key)

    // 프로필 로드까지 대기
    await getProfile() 

  } catch (err) {
    console.error(err)
    throw err 
  }
}
```

**2. 로그인 뷰 수정 (`LoginView.vue`)**
- 스토어의 액션이 끝날 때까지 기다렸다가 페이지를 이동한다.

```js
// frontend/src/views/LoginView.vue

const handleLogin = async () => {
  try {
    // [Fix] 로그인이 100% 완료될 때까지 Blocking
    await accountStore.logIn(payload)
    
    // 완료 후 안전하게 이동
    router.push({ name: 'home' })
  } catch (err) {
    alert('로그인 실패')
  }
}
```

**3. 메인 뷰 수정 (`HomeView.vue`)**
- 혹시 모를 엣지 케이스를 대비해, 로그인 상태 변화를 감지하여 데이터를 로드한다.

```js
// frontend/src/views/HomeView.vue

// [Fix] 로그인 상태(isAuthenticated)가 false -> true로 변하는 순간 포착
watch(() => accountStore.isAuthenticated, async (isLoggedIn) => {
  if (isLoggedIn) {
    console.log('로그인 완료 감지 -> 데이터 로드 시작')
    await moathonStore.getFollowingMoathons()
  }
}, { immediate: true })
```

### 결과

![로그인 후 팔로우 목록 조회 성공](/assets/img/posts/2025-12-24-moathon-following-list-troubleshooting/1.png)
*로그인 후 팔로우 목록 조회 성공*

- **Before**: 로그인 → 메인 이동 → 401 에러 (데이터 없음) → 새로고침해야 나옴.
- **After**: 로그인 → (잠시 대기) → 메인 이동 → **즉시 데이터 렌더링 성공!**

---

## 마치며

비동기 로직을 동기적으로 제어(`async/await`)하고, Vue의 반응성 시스템(`watch`)을 활용하여 데이터 무결성을 보장했다. 이를 통해 새로고침 없이도 매끄러운 사용자 경험(UX)을 제공할 수 있게 되었다.