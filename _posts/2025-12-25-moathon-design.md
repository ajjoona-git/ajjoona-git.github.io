---
title: "[모아톤] UI/UX 최종 디자인 적용 및 프론트엔드 트러블슈팅 로그"
date: 2025-12-25 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Frontend, Vue.js, CSS, UI/UX, DesignSystem, Troubleshooting, Refactoring]
toc: true 
comments: true
image: /assets/img/posts/2025-12-25-moathon-design/21.png
description: "모아톤 프로젝트의 최종 디자인을 적용하며 전역 CSS 변수를 설정하고, 마이페이지 레이아웃 깨짐, 페이지네이션 계산 오류, 무한 API 호출, 스크롤 위치 유지 등 다양한 프론트엔드 이슈를 해결한 과정을 정리했습니다."
---

프로젝트의 기능 구현을 마치고, 사용자에게 완성도 높은 경험을 제공하기 위해 **최종 디자인 적용(Polishing)** 작업을 진행했다.
전역 스타일 시스템을 구축하여 일관성을 확보하고, 이 과정에서 발견된 레이아웃 버그와 로직 오류들을 체계적으로 해결했다.

---

## Design System: 전역 스타일 변수 설정

프로젝트 전체에서 공통으로 사용할 색상과 폰트 스타일을 정의하여 유지보수성을 높였다. 하드코딩된 색상 값을 제거하고 CSS 변수(`var(--name)`)를 사용함으로써 테마 변경이나 일괄 수정이 용이해졌다.

```css
/* src/assets/main.css */

:root {
  /* Moathon Green Theme */
  --moathon-green: #1b5e20;       /* 메인 브랜드 컬러 (짙은 초록) */
  --moathon-light: #e8f5e9;       /* 배경용 연한 초록 */
  --moathon-deep: #144a18;        /* 호버용 더 짙은 초록 */
  
  /* Backgrounds */
  --bg-primary: #ffffff;
  --bg-secondary: #f8f9fa;        /* 전체 페이지 배경색 */
  
  /* Text Colors */
  --text-primary: #1d1d1f;
  --text-secondary: #86868b;
  
  /* Accent */
  --accent-blue: #0071e3;
  --accent-red: #e0245e;
}

body {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
```

---

## UI/UX 트러블슈팅 로그 (Troubleshooting Log)

디자인을 입히는 과정에서 발생한 5가지 주요 이슈와 해결 방법을 정리한다.

### Issue 1: 마이페이지 레이아웃 중첩 및 스타일 깨짐

* **증상:** `RateChart`와 `MoathonCard` 영역의 높이가 맞지 않고, 테두리와 그림자가 이중으로 겹쳐 보이는(Box inside Box) 현상 발생.
* **원인:**
    1. **중복 래핑:** 자식 컴포넌트가 이미 `.card` 스타일을 가지고 있는데, 부모 뷰(`MyPageView`)에서 또다시 `.card` 클래스로 감싸서 스타일이 중첩됨.
    2. **변수 누락:** 일부 컴포넌트에서 정의되지 않은 CSS 변수를 참조함.
* **해결:**
    * 부모 뷰의 불필요한 래퍼 `div`를 제거하고 컴포넌트 자체를 그리드에 배치.
    * `MoathonCard`에 `flex-column` 및 `h-100` 클래스를 적용하여 형제 요소인 차트와 높이 균형을 맞춤.

### Issue 2: 페이지네이션(Pagination) 계산 오류

* **증상:** 전체 데이터가 61개일 때, 12개씩 보여주는 그리드에서 페이지 수가 잘못 계산되거나 네비게이션 숫자가 범위를 벗어나는(음수 또는 초과) 현상.
* **원인:**
    1. `itemsPerPage` 기본값(10)과 실제 출력 개수(12)의 불일치.
    2. 슬라이딩 윈도우 계산 시 `start < 1` 또는 `end > totalPages`에 대한 방어 로직 미비.
* **해결:** `itemsPerPage`를 12로 통일하고, `computed` 속성 내에서 범위를 보정(Clamping)하는 로직을 강화했다.

```javascript
// Pagination.vue
const pageNumbers = computed(() => {
  // ... (기본 변수 선언)

  // 슬라이딩 윈도우 계산 및 보정 로직
  let start = current - Math.floor(displayCount / 2)
  let end = start + displayCount - 1

  // [보정 1] 시작점이 1보다 작으면 1로 고정
  if (start < 1) {
    start = 1
    end = Math.min(total, start + displayCount - 1)
  }

  // [보정 2] 끝점이 전체 페이지를 넘으면 역산하여 조정
  if (end > total) {
    end = total
    start = Math.max(1, end - displayCount + 1)
  }
  // ...
})

```

### Issue 3: 상세 페이지 무한 API 호출 (Infinite Loop)

* **증상:** 상세 페이지 진입 시 로딩이 끝나지 않고 API가 무한으로 호출되거나, 데이터가 로드되기 전에 렌더링을 시도하여 JS 에러 발생.
* **원인:**
    1. `watch`의 `immediate: true` 옵션이 라우트 초기화 시점과 맞물려 불필요한 중복 호출 유발.
    2. 데이터가 `null`인 상태에서 템플릿이 `user_info.nickname` 등에 접근.
* **해결:**
    * `watch`에서 `immediate` 옵션을 제거하고, 초기 로딩은 `onMounted`에서 명시적으로 실행.
    * `v-if="!isLoading && moathon"` 조건을 강화하여 데이터가 완벽할 때만 렌더링.

```javascript
// MoathonDetailView.vue
const fetchData = async (id) => {
  if (!id) return
  isLoading.value = true
  store.clearMoathonDetail() // 잔상 제거
  
  try {
    await store.fetchMoathonDetail(id)
  } finally {
    isLoading.value = false // 로딩 종료 보장
  }
}

// 초기 로딩과 라우트 변경 감지를 분리
onMounted(() => fetchData(route.params.id))
watch(() => route.params.id, (newId) => fetchData(newId))

```

### Issue 4: 추천 페이지 이중 카드 스타일링

* **증상:** 추천 폼 내부에 또 다른 카드 박스가 있는 것처럼 보이는 디자인 불일치.
* **해결:**
    * 부모 컴포넌트(`RecommendView`)는 투명한 레이아웃 컨테이너 역할만 수행하도록 스타일(배경, 그림자) 제거.
    * 자식 컴포넌트(`RecommendForm`)가 독립적인 카드 스타일을 갖도록 CSS 이관.



### Issue 5: 페이지 이동 시 스크롤 위치 유지 (Scroll Behavior)

* **증상:** 목록을 보다가 상세 페이지로 들어갔다 나오면 스크롤이 초기화되거나, 새 페이지 진입 시 스크롤이 중간에 머무는 현상.
* **해결:** `Vue Router`의 `scrollBehavior`를 설정하여 **"일반 이동은 최상단, 뒤로 가기는 이전 위치 복원"** 규칙을 적용.

```javascript
// router/index.js
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [ ... ],
  
  // [핵심] 스크롤 동작 제어
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition // 뒤로가기 시 위치 복원
    } else {
      return { top: 0 }    // 새 페이지 이동 시 최상단
    }
  }
})

```

---

## 최종 디자인 화면

### Landing
- parallex 디자인 도입

![랜딩 페이지](/assets/img/posts/2025-12-25-moathon-design/20.png)
*랜딩 페이지*

### Home
![HomeView-A.png](/assets/img/posts/2025-12-25-moathon-design/19.png)
*메인 페이지 - 모아톤, 팔로우가 없는 초기 화면*
![HomeView-B.png](/assets/img/posts/2025-12-25-moathon-design/18.png)
*메인 페이지 - 활성 유저*

### 회원가입/로그인
![SignupView.png](/assets/img/posts/2025-12-25-moathon-design/17.png)
*회원가입*
![OnboardingView.png](/assets/img/posts/2025-12-25-moathon-design/16.png)
*온보딩 페이지 - 프로필 정보 입력*
![LoginView.png](/assets/img/posts/2025-12-25-moathon-design/15.png)
*로그인*

### 모아톤

![MoathonCreateView.png](/assets/img/posts/2025-12-25-moathon-design/14.png)
*모아톤 생성*

![MoathonUpdateView.png](/assets/img/posts/2025-12-25-moathon-design/13.png)
*모아톤 수정*

![MoathonRecommendView-input.png](/assets/img/posts/2025-12-25-moathon-design/12.png)
*모아톤 추천*

![MoathonRecommendView-output.png](/assets/img/posts/2025-12-25-moathon-design/11.png)
*모아톤 추천 결과*

![MoathonCommunityView.png](/assets/img/posts/2025-12-25-moathon-design/10.png)
*모아톤 커뮤니티*

![MoathonDetailView.png](/assets/img/posts/2025-12-25-moathon-design/9.png)
*모아톤 상세*

### 금융 상품
![ProductsView.png](/assets/img/posts/2025-12-25-moathon-design/8.png)
*금융 상품 리스트*

![ProductDetailView.png](/assets/img/posts/2025-12-25-moathon-design/7.png)
*금융 상품 상세*

### 마이페이지
![MyPageView.png](/assets/img/posts/2025-12-25-moathon-design/6.png)
*마이페이지*

![ProfileUpdateView.png](/assets/img/posts/2025-12-25-moathon-design/5.png)
*프로필 수정*

### 부가 금융 서비스

![BankView.png](/assets/img/posts/2025-12-25-moathon-design/4.png)
*은행 위치 검색 페이지*
![CommodityView.png](/assets/img/posts/2025-12-25-moathon-design/3.png)
*금/은 시세 차트 페이지*
![VideoListView.png](/assets/img/posts/2025-12-25-moathon-design/2.png)
*금융튜브 페이지*
![VideoDetailView.png](/assets/img/posts/2025-12-25-moathon-design/1.png)
*금융튜브 상세 페이지*

---

## 📝 마치며

이번 최종 디자인 작업을 통해 **랜딩 페이지**부터 **마이페이지**까지 서비스의 모든 화면이 일관된 톤앤매너(Tone & Manner)를 갖추게 되었다. 단순히 시각적인 개선뿐만 아니라, **스크롤 경험**이나 **로딩 상태 처리** 같은 UX 디테일을 다듬음으로써 실제 사용 가능한 수준의 애플리케이션으로 완성도를 높였다. 

처음 기획했던 와이어프레임과 유사하게 결과물이 나와서 아주 만족한다. 뿌듯하다:)
