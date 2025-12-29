---
title: "[모아톤] 금융 상품 리스트 성능 최적화 (Client-side Filtering & Caching)"
date: 2025-12-23 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Frontend, Vue.js, Pinia, Performance, Caching, Refactoring, Architecture, UX]
image: /assets/img/posts/2025-12-23-moathon-products-list/4.png
toc: true 
comments: true
description: "서버 API의 정렬 한계를 극복하기 위해 전체 데이터를 초기에 로딩하여 클라이언트 사이드에서 필터링과 정렬을 처리하도록 아키텍처를 변경했습니다. 또한 pinia-plugin-persistedstate를 활용해 데이터를 로컬 스토리지에 캐싱하여 불필요한 네트워크 요청을 줄였습니다."
---

이번 포스트에서는 사용자 경험(UX)을 극대화하기 위해 **금융 상품 리스트의 데이터 로딩 방식**을 전면 개편하고, **캐싱 전략**을 도입하여 성능을 최적화한 과정을 정리해보았다.

사용자가 자신에게 맞는 금융 상품을 더 쉽게 찾을 수 있도록 리스트 페이지의 필터링/정렬 기능을 대폭 강화하고, 반응 속도를 높이기 위해 아키텍처를 개선했다. 또한 코드의 재사용성을 높이기 위해 페이지네이션과 상세 옵션 리스트를 컴포넌트로 분리하는 리팩토링을 진행했다.

---

## 1. 아키텍처 변경: 클라이언트 사이드 처리 (Client-Side Processing)

### 기존 방식의 문제점
기존에는 페이지를 넘길 때마다 서버에 데이터를 요청하는 **서버 사이드 페이지네이션** 방식을 사용했다. 하지만 백엔드 API 구조상, 상품 내부의 '옵션(기간별 금리)'을 기준으로 정렬하거나 복합 필터링을 수행하는 데 한계가 있었다.

### 변경된 아키텍처 (Fetch All Strategy)
초기 로딩 시 약 700~800개의 금융 상품 데이터를 **모두 메모리(Pinia Store)에 적재**하고, 이후의 필터링, 정렬, 페이지네이션은 **브라우저(Client)**에서 처리하도록 변경했다.

1.  **초기 로딩 (Fetch All):** `store.getProducts()`가 백엔드 API를 호출하여 전체 데이터를 Store에 저장한다.
2.  **즉각적인 피드백:** 데이터가 브라우저 메모리에 있으므로, 탭 전환(예금/적금)이나 필터 변경(12개월 등) 시 네트워크 요청 없이 **즉시(0.01초 이내)** 화면이 갱신된다.
3.  **정교한 정렬:** 전체 데이터를 가지고 있으므로, "전체 상품 중 특정 조건에서 금리가 가장 높은 상품"을 정확하게 추출할 수 있다.

---

## 2. Period 정렬 로직

### 정교한 필터링 및 정렬 로직 (`ProductListView.vue`)
단순히 상품의 대표 금리(`max_rate`)로 정렬하는 것이 아니라, 사용자가 선택한 **기간(예: 12개월)**에 해당하는 옵션의 우대 금리를 찾아 비교하도록 구현했다.

-   **필터링:** 예금/적금 탭, 은행명 선택
-   **정렬:** 가입 기간(6/12/24/36개월) 선택 시, 해당 기간 옵션의 `intr_rate2`(우대금리) 기준 내림차순 정렬

```javascript
// 필터링 및 정렬 로직 예시
const filteredProducts = computed(() => {
  let result = productStore.products;

  // 1. 은행 필터링
  if (selectedBank.value) {
    result = result.filter(p => p.kor_co_nm === selectedBank.value);
  }

  // 2. 기간별 금리 정렬
  if (selectedPeriod.value) {
    result.sort((a, b) => {
      // 해당 기간(12개월 등)에 맞는 옵션을 찾아 금리 비교
      const rateA = getRateForPeriod(a, selectedPeriod.value);
      const rateB = getRateForPeriod(b, selectedPeriod.value);
      return rateB - rateA; // 내림차순
    });
  }

  return result;
});
```

### 컴포넌트 분리 (Refactoring)
비대해진 뷰 컴포넌트를 기능 단위로 분리하여 재사용성과 가독성을 높였다.

- `Pagination.vue`: 하드코딩되어 있던 페이지네이션 로직을 공통 컴포넌트로 분리하여 `MoathonListView` 등 다른 곳에서도 재사용 가능하게 함.
- `ProductOptionList.vue`: 상세 페이지의 복잡한 옵션 목록 UI를 별도로 분리하고, `자유적립식/복리` 등의 정보를 뱃지 형태로 시각화.

### 결과

![금융 상품 전체 조회](/assets/img/posts/2025-12-23-moathon-products-list/3.png)
*금융 상품 전체 조회*

![금융 상품 필터링 (적금, 24개월)](/assets/img/posts/2025-12-23-moathon-products-list/2.png)
*금융 상품 필터링 (적금, 24개월)*

## 3. 성능 최적화: 로컬 스토리지 캐싱 (Caching)
### 개요
매번 상품 목록 페이지에 진입할 때마다 전체 데이터를 다시 불러오는 것은 비효율적이다. `pinia-plugin-persistedstate`를 활용하여 데이터를 로컬 스토리지에 저장하고 재사용하기로 했다.

### 구현 내용 (`stores/products.js`)
- **Persist 설정**: `products`, `banks`, `lastFetched` 상태를 영구 저장소에 저장.
- **유효성 검사 (TTL):** 데이터를 요청할 때 `lastFetched` 시간을 확인하여, **24시간 이내**라면 API 호출을 건너뛰고 캐시된 데이터를 사용한다.
- **강제 갱신**: 데이터가 오래되었거나 사용자가 원할 경우를 대비해 *'최신 데이터로 새로고침'* 버튼을 추가했다.
- 상세 페이지(`productDetail`)는 실시간성이 중요할 수 있어 캐싱에서 제외했다.


```js
// stores/products.js
export const useProductStore = defineStore('product', {
  state: () => ({
    products: [],
    lastFetched: null,
  }),
  actions: {
    async getProducts() {
      const now = Date.now();
      // 24시간(86400000ms) 이내면 API 호출 스킵
      if (this.products.length > 0 && this.lastFetched && (now - this.lastFetched < 86400000)) {
        console.log('Using cached products');
        return;
      }
      
      // API 호출 및 데이터 갱신
      await fetchAllProducts();
      this.lastFetched = now;
    }
  },
  persist: true // 플러그인 활성화
});
```

![로컬 스토리지 캐싱 적용](/assets/img/posts/2025-12-23-moathon-products-list/1.png)
*로컬 스토리지 캐싱 적용*

### 결과

이번 작업을 통해 서버 부하를 줄이면서도 사용자 경험은 획기적으로 개선되었다.

- **속도**: 초기 로딩 후 필터링/정렬 시 지연 시간 제로 (Instant UI)
- **데이터 효율**: 24시간 캐싱을 통해 불필요한 API 호출 방지
- **정확도**: 클라이언트 사이드 로직을 통해 사용자가 원하는 복잡한 조건의 상품을 정확하게 추천 가능