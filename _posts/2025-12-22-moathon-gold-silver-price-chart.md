---
title: "[모아톤] 금/은 시세 시각화 구현 (feat. Google Charts & Vue.js)"
date: 2025-12-22 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Vue.js, GoogleCharts, Frontend, Visualization, Troubleshooting, Refactoring]
toc: true 
comments: true
image: /assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/5.png
description: "핀테크 프로젝트의 핵심인 금/은 시세 차트를 Google Charts와 Vue.js로 구현한 과정입니다. 스크립트 로딩 효율화를 위한 Composable 설계와 데이터 매핑, 렌더링 이슈 해결 경험을 공유합니다."
---

이번 포스팅에서는 핀테크 프로젝트의 핵심 기능 중 하나인 '금/은 시세 차트'를 구현하는 과정을 정리해봤다. Google Charts 라이브러리를 Vue 3 환경에 통합하고, 백엔드 데이터 생성부터 프론트엔드 시각화까지의 전체 흐름을 담았다.

---

## 개발 과정

### 1. 기반 구조 설계 (Frontend Infrastructure)
Google Charts 외부 라이브러리를 컴포넌트마다 중복 로드하지 않고, 앱 전역에서 효율적으로 관리하기 위해 `useGoogleCharts` Composable을 개발했다.

**Singleton 패턴**을 적용하여 스크립트가 단 한 번만 로드되도록 했다. 또한 `Promise`를 활용해 로드 완료 시점을 보장함으로써 `google is not defined` 에러를 방지했다.

```javascript
// src/composables/useGoogleCharts.js
import { ref } from 'vue';

const isLoaded = ref(false);
const isLoading = ref(false);
let loadPromise = null;

export function useGoogleCharts() {
  const loadCharts = () => {
    // 1. 이미 로드 완료되었다면 즉시 해결
    if (isLoaded.value) return Promise.resolve();

    // 2. 로딩 중이라면 기존 프로미스 반환 (중복 요청 방지)
    if (loadPromise) return loadPromise;

    isLoading.value = true;

    // 3. 스크립트 로드 시작
    loadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '[https://www.gstatic.com/charts/loader.js](https://www.gstatic.com/charts/loader.js)';
      script.async = true;
      
      script.onload = () => {
        // Google Charts 패키지 로드
        window.google.charts.load('current', { packages: ['corechart'] });
        window.google.charts.setOnLoadCallback(() => {
          isLoaded.value = true;
          isLoading.value = false;
          resolve();
        });
      };
      
      script.onerror = (err) => {
        isLoading.value = false;
        reject(err);
      };

      document.head.appendChild(script);
    });

    return loadPromise;
  };

  return { isLoaded, isLoading, loadCharts };
}
```

### 2. 차트 컴포넌트 프로토타이핑
금/은 시세의 변동성(시가, 종가, 고가, 저가)을 가장 직관적으로 보여주는 차트를 선정한다. 주식 및 금융 데이터 시각화의 표준인 **봉 차트(Candlestick)**를 선택했다. 시가/종가/고가/저가 정보를 하나의 캔들에 모두 담을 수 있어 데이터 전달력이 좋기 때문이다.

### 3. 백엔드 API 및 데이터 연동
- **Backend**: 금/은 시세 조회 API 구현
- GET `/visualizations/commodities/prices/`
- Parameters: `asset` (필수, glod 혹은 silver), `start` (시작일), `end` (종료일)

![금/은 시세 조회 API](/assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/6.png)
*금/은 시세 조회 API*

- **Frontend**: 데이터 매핑 (Mapping)

백엔드의 JSON 객체 리스트를 Google Charts가 요구하는 2차원 배열 포맷으로 변환했다.

```js
// API 응답 데이터 변환 로직
const transformData = (apiData) => {
  // Google Charts Header
  const result = [['Date', 'Low', 'Open', 'Close', 'High']];
  
  apiData.forEach(item => {
    result.push([
      item.date,
      item.low,
      item.open,
      item.close_last, // API의 'close_last'를 'Close' 자리에 매핑
      item.high
    ]);
  });
  return result;
};
```

### 4. 기능 고도화 및 UI/UX 폴리싱
- **필터링 및 유효성 검사**
날짜 범위 선택(`start`, `end`) 시 종료일이 시작일보다 앞서는 경우를 방지했다. 탭(Gold/Silver) 전환 시 `watch`를 통해 데이터를 즉시 리페칭한다.

- **UI 이슈 해결**: X축 라벨 겹침
데이터 포인트가 많아지면 X축 날짜가 ...으로 생략되거나 겹치는 현상이 발생했다. 이를 `options` 설정으로 해결했다.

```javascript
const chartOptions = {
  legend: 'none',
  bar: { groupWidth: '90%' },
  chartArea: { 
    width: '90%', 
    height: '70%'
  },
  hAxis: {
    slantedText: true,       // 라벨 45도 회전
    slantedTextAngle: 45,
    showTextEvery: 1,        // 모든 날짜 강제 출력 (생략 방지)
    textStyle: { fontSize: 10 }
  },
  candlestick: {
    fallingColor: { strokeWidth: 0, fill: '#a52714' },
    risingColor: { strokeWidth: 0, fill: '#0f9d58' } 
  }
};
```

![금/은 시세 조회](/assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/5.png)
*금/은 시세 조회*


---

## 트러블슈팅 리포트 (Troubleshooting)
### Issue 1: 외부 스크립트 로딩 비동기 처리 문제
- 현상: 페이지 진입 시 간헐적으로 `google is not defined` 에러 발생. 라이브러리 로드보다 차트 그리기 함수가 먼저 실행됨.

- 원인: `<script>` 태그 로딩은 비동기적으로 이루어지는데, Vue 라이프사이클(`onMounted`)은 이를 기다리지 않음.

- 해결: `useGoogleCharts` 훅을 생성하여 `Promise`를 반환하게 함. `onMounted`에서 `await loadCharts()`를 호출하여 스크립트 로드 완료를 보장한 후 차트 렌더링 로직을 실행함.

```javascript
// Component.vue
onMounted(async () => {
  try {
    await loadCharts(); // 스크립트 로드 완료 대기
    drawChart();        // 그 후 차트 그리기
  } catch (e) {
    console.error("Google Charts 로드 실패", e);
  }
});
```

### Issue 2: 데이터 구조 불일치 (Mapping)
- 현상: 차트가 그려지지만 캔들(Body) 모양이 이상하거나 값이 잘못 표시됨.

- 원인: 백엔드 응답 필드명(`close_last`)과 Google Charts가 기대하는 배열 인덱스 순서(`[Label, Low, Open, Close, High]`)가 매칭되지 않음.

- 해결: `Array.map()`을 사용하여 백엔드 응답 객체를 Google Charts 포맷의 배열로 명시적으로 변환.

```jsx
// Before: 단순 값 전달
// After: 순서 매핑
return [item.date, item.low, item.open, item.close_last, item.high]
```

### Issue 3: X축 라벨 가독성 저하
- 현상: x축 데이터가 많을 경우 날짜가 겹치거나 자동으로 생략되어 날짜 식별 불가.

- 해결: 차트 옵션 객체(`options`)의 `hAxis` 속성 튜닝.
    - 텍스트를 45도 기울여 공간 확보 (`slantedTextAngle: 45`)
    - 모든 라벨 강제 출력 (`showTextEvery: 1`)
    - 차트 하단 여백 확보를 위해 `chartArea.height` 축소

|수정 전 (겹침) | 수정 후 (45도 회전)|
|---|---|
|![xtick 수정 전](/assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/4.png)|![xtick 수정 후](/assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/3.png)|

### Issue 4: 404 Not Found Error

![404 Not Found Error](/assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/2.png)
*404 Not Found Error*

- 현상: API 호출 시 404 에러 발생.

- 원인: 프론트엔드에서 `/commodities/prices/` 경로로 요청하였으나, Django `urls.py`에 정의된 경로는 `/commodities/prices` (슬래시 누락) 이었음.

- 해결: URL 경로 끝에 슬래시(`/`)를 포함하도록 axios 요청 코드를 수정하여 해결.

![URL 경로 수정](/assets/img/posts/2025-12-22-moathon-gold-silver-price-chart/1.png)
*URL 경로 수정*