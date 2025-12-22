---
title: "[모아톤] 모아톤 생성 프로세스 구현 (Direct vs Recommend 모드)"
date: 2025-12-22 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Django, Vue.js, Pinia, UX, Troubleshooting, Refactoring]
toc: true 
comments: true
image: /assets/img/posts/2025-12-22-moathon-creation-process/4.png
description: "사용자가 모아톤(저축 챌린지)을 생성하는 두 가지 UX 흐름(직접 생성, 추천 생성)을 설계하고, 이를 구현하기 위해 View를 분리하고 Store를 활용한 전략을 다룹니다. 또한 Django 모델의 __str__ 메서드 관련 트러블슈팅 경험을 공유합니다."
---

## 프로젝트 배경 및 목표

사용자가 저축 챌린지('모아톤')를 시작하는 두 가지 UX 흐름을 설계했다.

1. **다이렉트 모드 (Direct Mode)**: "나는 내가 가입할 상품을 이미 알고 있다." (상품 탐색 → 생성)
2. **추천 모드 (Recommend Mode)**: "내 목표에 맞는 상품을 추천해줘." (목표 입력 → AI 추천 → 생성)

이 두 흐름은 **진입점**과 **데이터 흐름**이 다르지만, 최종적으로 **"모아톤 생성 API (`POST /moathons/create/`)"를 호출한다**는 점은 같다. 이를 효율적으로 구현하기 위해 **View를 분리**하고 **Store를 활용**하는 전략을 세웠다.

---

## 시나리오 A: 다이렉트 모드 (Direct Mode)

금융 상품 상세 페이지에서 '시작하기' 버튼을 누르면, 해당 상품의 옵션 ID를 `Query Parameter`로 전달하여 생성 페이지의 복잡도를 낮춘다.

- **Flow**: `상품 목록` → `상품 상세` → `옵션 선택` → `모아톤 생성 폼` → `완료`

![다이렉트 모드 입력 폼](/assets/img/posts/2025-12-22-moathon-creation-process/4.png)
*다이렉트 모드 입력 폼*

### A-1. 상품 상세 페이지 (`ProductDetailView.vue`)

- 상품의 옵션(기간, 금리) 리스트를 보여주고, 각 카드에 **'모아톤 시작하기'** 버튼을 배치했다.
- 버튼 클릭 시 `router.push`를 통해 생성 페이지로 이동하며 **쿼리 파라미터**로 옵션 ID를 전달한다.
- `query: { productId: option.id }`

```jsx
<template>
  <div class="options-list">
    <div v-for="option in product.options" :key="option.id" class="option-card">
      <div class="opt-info">
        <span class="term">{{ option.save_trm }}개월</span>
        <span class="rate">최고 {{ option.intr_rate2 }}%</span>
      </div>
      <button @click="startMoathon(option.id)">모아톤 시작하기</button>
    </div>
  </div>
</template>

<script setup>
const startMoathon = (optionId) => {
  // Query Parameter 패턴 사용: /moathon/create?productId=123
  router.push({ 
    name: 'moathon-create', 
    query: { productId: optionId } 
  })
}
</script>
```

### A-2. 모아톤 생성 페이지 (`MoathonCreateView.vue`)

- 페이지 로드 시 URL의 `productId`를 확인하여 유효성을 검증한다.
- 사용자는 상품 정보는 신경 쓸 필요 없이 **제목**과 **목적**만 입력하면 된다.
- `MoathonCreateForm` 컴포넌트를 사용하여 입력 UI를 재사용한다.

```jsx
<script setup>
// ... imports
const route = useRoute()
// 1. URL 쿼리 파라미터 감지
const productId = computed(() => route.query.productId)

const handleCreate = async (formData) => {
  // 2. 폼 데이터(제목, 목적) + URL의 상품 ID 결합
  const payload = {
    ...formData,
    product_option: Number(productId.value)
  }
  await store.createMoathon(payload)
}
</script>
```

---

## 시나리오 B: 추천 모드 (Recommend Mode)

**핵심 전략**: 별도의 생성 페이지로 이동하지 않고, 추천 결과 화면에서 **'이 상품으로 시작하기'** 버튼 `One-Click`으로 즉시 생성 API를 호출한다. UX 단계를 축소함으로써 모아톤 생성률을 높인다.

- **Flow**: `추천 페이지` → `목표/자산 입력` → `AI 추천 결과(카드)` → `바로 시작` → `완료`

![추천 모드 입력 폼](/assets/img/posts/2025-12-22-moathon-creation-process/3.png)
*추천 모드 입력 폼*

![추천 상품 정보](/assets/img/posts/2025-12-22-moathon-creation-process/2.png)
*추천 상품 정보*

### B-1. 추천 로직 흐름 (`MoathonRecommendView.vue`)

- 입력 폼과 추천 결과 카드를 조건부 렌더링(`v-if/v-else`)으로 제어한다.
- `MoathonRecommendForm`을 통해 유저의 목표 금액, 기간 등을 입력받는다.
- `Store`의 `recommendProduct` 액션을 호출하여 최적의 상품 1개를 받아온다.
- `MoathonRecommendCard` 컴포넌트를 통해 추천된 상품의 스펙(금리, 우대조건)과 **유의사항(Warnings)**을 시각적으로 보여준다.
- 별도의 생성 페이지로 이동하지 않고, 추천 결과 카드에서 **'이 상품으로 시작하기'** 버튼을 누르면 즉시 생성 API를 호출하여 UX 단계를 축소함.

```jsx
<template>
  <div v-if="!store.recommendationResult">
    <MoathonRecommendForm @submit="handleRecommend" />
  </div>

  <div v-else>
    <MoathonRecommendCard 
      :detail="detail" 
      @create="createWithProduct" 
    />
  </div>
</template>

<script setup>
const savedFormData = ref(null) // [Point] 폼 데이터 임시 저장소

// Step 1 핸들러: 추천 요청
const handleRecommend = async (formData) => {
  // 사용자가 입력한 제목, 목표금액 등을 메모리에 저장 (나중에 쓰기 위해)
  savedFormData.value = { ...formData } 
  await store.recommendProduct(formData)
}

// Step 2 핸들러: 최종 생성 (One-Click)
const createWithProduct = async () => {
  // 저장해둔 폼 데이터 + 추천받은 상품 ID 병합
  const payload = {
    ...savedFormData.value,
    product_option: detail.value.option_id 
  }
  await store.createMoathon(payload)
}
</script>
```

---

## 트러블슈팅 (Troubleshooting)

### 추천 생성 시 Payload 데이터 누락

- **현상**: 추천 모드에서 '시작하기'를 눌렀는데, 백엔드로부터 `400 Bad Request` 에러가 발생하거나 데이터가 일부만 저장됨. 확인 결과 `product_option` ID만 전송되고, 유저가 입력한 `title`, `target_amount` 등이 누락됨.
- **원인**: 추천 API를 호출한 후, 결과 화면으로 전환되면서 입력 폼의 데이터(`formData`)가 초기화되거나, 최종 생성 함수(`createWithProduct`)에서 해당 데이터를 참조하지 못함.
- **해결**:
    - `handleRecommend` 함수에서 추천 요청을 보내기 전에, 유저의 입력 데이터를 **`savedFormData`라는 별도 Ref 변수에 깊은 복사(`{ ...formData }`)** 하여 보존.
    - 최종 생성 시 `savedFormData`와 추천 결과의 `option_id`를 병합(Merge)하여 Payload를 구성함.

```jsx
// [Before] 참조만 복사되어 원본 변경 시 위험
// savedFormData.value = formData 

// [After] Spread Operator로 새로운 객체 생성하여 보존
savedFormData.value = { ...formData }
```

### 유저 프로필 정보 부재로 인한 로직 오류

- **현상**: 신규 가입자가 바로 추천 페이지로 진입했을 때, 자산 정보나 연봉 정보가 없어 추천 알고리즘이 동작하지 않거나 부정확한 결과를 줌.
- **해결**:
    - `MoathonRecommendView`의 `onMounted` 훅에 **가드 로직** 추가.
    - `accountStore.user` 정보를 확인하여 필수 필드(`salary`, `assets`, `tender`)가 비어있으면 `alert`을 띄우고 **마이페이지로 리다이렉트** 처리.
    - Store에 `getProfile` 액션을 추가하여 최신 유저 정보를 확실하게 로드하도록 보장.

```jsx
onMounted(async () => {
  await accountStore.getProfile()
  const user = accountStore.user

  // 필수 필드 유효성 검사
  if (!user || user.salary === null || user.assets === null) {
    alert('정확한 추천을 위해 자산 정보를 설정해주세요.')
    router.replace({ name: 'my-page' })
  }
})
```

### Backend 모델의 `__str__` 이슈

- **현상**: 모아톤 제목을 자동 생성할 때, 제목이 `"User object (1)'s moathon"` 처럼 내부 객체명으로 지저분하게 저장됨.
- **원인**: Django Model의 `DEFAULT_TITLE_BASE` 클래스 변수 선언 시점이 서버 시작 시점이라, 인스턴스의 데이터를 동적으로 가져오지 못함.
- **해결**: `save()` 메서드 오버라이딩을 통해 **동적으로 닉네임을 바인딩**하도록 수정.

```python
# backend/moathons/models.py

# [Before] 클래스 변수로 선언 (오류 원인)
# DEFAULT_TITLE_BASE = f"{user}'s moathon" 

# [After] 메서드 내부에서 동적 생성
def _next_default_title(self) -> str:
    # user 객체의 nickname 필드를 우선 사용, 없으면 username
    nickname = getattr(self.user, 'nickname', self.user.username)
    base = f"{nickname}'s moathon"
    # ... (중복 넘버링 로직) ...
    return base
```

![모아톤 제목(`test1’s moathon`) 생성](/assets/img/posts/2025-12-22-moathon-creation-process/1.png)
*모아톤 제목(`test1’s moathon`) 생성*

---

## 리팩토링: 컴포넌트 분리

### **컴포넌트 분리 (`MoathonRecommendCard`)**

`MoathonRecommendView`의 템플릿 코드가 비대해져 유지보수가 어려워짐에 따라, **추천 결과 카드** 영역을 독립적인 컴포넌트로 분리했다.

- **컴포넌트**: `MoathonRecommendCard.vue`
- **역할**: 복잡한 금융 상품 정보(우대금리, 유의사항, 만기 이자율)를 시각화.
- **Props**: `detail` (상품 정보 객체), `warnings` (유의사항 배열)
- **성과**: View 파일의 라인 수를 **40% 감소**시키고, 데이터 흐름과 UI 렌더링 로직을 명확히 분리함.

### **API 응답 구조 대응 (Computed 활용)**

- 추천 API 응답이 깊은 중첩 객체(`result.final_recommendation.option_detail...`) 형태라 템플릿 코드가 지저분해짐.
- `detail`, `warnings` 같은 `computed` 속성을 만들어 템플릿에서는 깔끔하게 변수명만 사용할 수 있도록 개선.