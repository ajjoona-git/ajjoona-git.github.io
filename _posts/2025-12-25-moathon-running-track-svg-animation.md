---
title: "[모아톤] GSAP로 구현한 목표 달성 트랙(Track) 시각화 (feat. SVG 애니메이션)"
date: 2025-12-25 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Frontend, Vue.js, GSAP, SVG, Visualization, Gamification, UI/UX]
toc: true 
comments: true
image: /assets/img/posts/2025-12-25-moathon-running-track-svg-animation/4.png
description: "단순한 게이지 바 대신 육상 경기장 트랙을 달리는 사용자 프로필 애니메이션을 구현했습니다. GSAP MotionPathPlugin과 SVG stroke-dashoffset을 활용한 기술적 구현 디테일과 비동기 데이터 로딩 시점 문제를 해결한 트러블슈팅 로그입니다."
---


모아톤 프로젝트의 '게이미피케이션(Gamification)' 요소를 한층 업그레이드한 **"육상 트랙 시각화 컴포넌트"** 작업 기록을 공유한다.

단순한 직선 게이지 바(Progress Bar)로는 사용자의 '완주' 욕구를 자극하기 부족했다. 그래서 우리는 '모아톤'(마라톤)을 참가하고 있는 느낌을 살리기 위해 **"실제 육상 경기장을 달리는 내 모습"**을 구현하기로 했다. **GSAP**의 애니메이션 기능과 **SVG** 드로잉 기법을 결합하여, 목표를 향해 달리는 역동적인 UI를 완성한 과정을 정리해봤다.

---

## 디자인 및 기술적 구현

### 1. 시각화 전략: 왜 '육상 트랙'인가?

사용자의 저축 목표 달성 과정을 '마라톤'에 비유하는 프로젝트 컨셉에 맞춰, 실제 육상 경기장 모양의 트랙을 디자인했다.

* **배경 트랙:** `#F0E4E4` (채도가 빠진 연한 붉은 회색) - 아직 도달하지 못한 길을 표현
* **진행 바:** `#D9534F` (강렬한 벽돌색) - 사용자가 달려온 거리 표현
* **레인 디테일:** `rgba(255,255,255,0.3)` 색상의 **흰색 점선(Lane Line)**을 트랙 중앙에 배치하여 단순한 선이 아닌 '경기장'의 느낌을 살렸다.
* **마감 처리:** 두께가 굵은 선이 만날 때 모양이 어긋나는 것을 방지하기 위해 `stroke-linecap="butt"`(직각) 처리를 하여 깔끔하게 마감했다.

### 2. 기술 스택: GSAP & SVG

복잡한 곡선 경로를 따라 움직이는 애니메이션을 구현하기 위해 **GSAP(GreenSock Animation Platform)**을 도입했다.

* **SVG Path:** 타원형 트랙 경로(`path`)를 생성하고, `stroke-dashoffset` 기법을 활용하여 진행률(%)만큼 선이 그려지도록 했다.
* **MotionPathPlugin:** 사용자의 프로필 이미지(Runner)가 정확히 SVG 경로(Track) 위를 따라 움직이도록 GSAP의 플러그인을 활용했다.

```javascript
// MoathonTrack.vue (애니메이션 로직 일부)
import { gsap } from 'gsap'
import { MotionPathPlugin } from 'gsap/MotionPathPlugin'

gsap.registerPlugin(MotionPathPlugin)

const animateTrack = (percent) => {
  // 1. 트랙 라인 그리기 (Draw SVG)
  gsap.to(trackPath.value, {
    strokeDashoffset: totalLength - (totalLength * percent) / 100,
    duration: 1.5,
    ease: 'power2.out'
  })

  // 2. 프로필 이미지 이동 (Move Runner)
  gsap.to(runnerRef.value, {
    motionPath: {
      path: '#track-path', // SVG Path ID 참조
      align: '#track-path',
      alignOrigin: [0.5, 0.5], // 이미지 중심점 기준
      end: percent / 100 // 진행률만큼 이동
    },
    duration: 1.5,
    ease: 'power2.out'
  })
}

```

---

## 트러블슈팅 로그 (Troubleshooting Log)

멋진 애니메이션을 구현했지만, 실제 데이터(DB)와 연동하는 과정에서 몇 가지 타이밍 이슈가 발생했다.

### 1. 비동기 데이터 처리와 애니메이션 실행 시점 (Async Timing)

* **상황 (Problem):**
상세 페이지(`MoathonDetailView`) 진입 시, 트랙이 그려지지 않거나 프로필 이미지가 엉뚱한 곳(0% 지점)에 멈춰있는 현상이 발생했다. 콘솔에는 간헐적으로 `undefined` 에러가 찍혔다.
* **원인 (Cause):**
`onMounted` 훅은 컴포넌트가 DOM에 부착되자마자 실행된다. 하지만 백엔드에서 목표 진행률(`percent`) 데이터를 가져오는 것은 **비동기(Async)** 작업이다.
데이터가 도착하기도 전에 `onMounted`에서 애니메이션 함수를 실행해버려, `percent`가 `null`이거나 `0`인 상태로 애니메이션이 끝나버린 것이다.
* **해결 (Solution):**
`onMounted` 대신 **`watch`**를 사용하여, 데이터(`moathonDetail`)가 실제로 로드되어 값이 변경된 시점에 애니메이션을 실행하도록 수정했다.

```javascript
// frontend/src/views/MoathonDetailView.vue

// [Before] 데이터 로딩 여부와 상관없이 실행 -> 실패 가능성 높음
// onMounted(() => {
//   if (moathonDetail.value) animateTrack(moathonDetail.value.percent)
// })

// [After] 데이터가 로드되면 감지하여 실행 -> 안전함
watch(() => moathonDetail.value, (newVal) => {
  if (newVal && newVal.percent !== undefined) {
    // DOM 업데이트를 위해 nextTick 사용 권장
    nextTick(() => {
        animateTrack(newVal.percent)
    })
  }
}, { immediate: true }) // 이미 데이터가 있는 경우(캐시 등)를 위해 immediate 설정

```

### 2. 프로필 이미지 예외 처리 (Fallback Image)

* **상황 (Problem):**
프로필 이미지를 등록하지 않은 유저의 경우, 트랙 위를 달리는 '러너' 이미지가 깨져서(Broken Image) 엑박으로 표시되었다.
* **해결 (Solution):**
`MoathonTrack` 컴포넌트 내부에서 `computed` 속성을 활용하여, 전달받은 `profileImage`가 없으면 미리 준비한 `default-profile.png`를 반환하도록 로직을 추가했다.

```javascript
// MoathonTrack.vue
const runnerImage = computed(() => {
  // 이미지가 없거나 빈 문자열이면 기본 이미지 사용
  return props.profileImage || new URL('@/assets/images/default-profile.png', import.meta.url).href
})

```

## 컴포넌트 적용 결과

### 메인 페이지

![메인 페이지에 트랙 컴포넌트 적용](/assets/img/posts/2025-12-25-moathon-running-track-svg-animation/3.png)
*메인 페이지에 트랙 컴포넌트 적용*

### 모아톤 상세 페이지

![BEFORE](/assets/img/posts/2025-12-25-moathon-running-track-svg-animation/2.png)
*BEFORE*

![AFTER](/assets/img/posts/2025-12-25-moathon-running-track-svg-animation/1.png)
*AFTER*


---

## 마치며

이번 작업을 통해 메인 페이지(대시보드)의 UI가 획기적으로 개선되었다.
기존의 정적인 카드 UI를 **"좌측 트랙 시각화 + 우측 상세 정보"**의 2단 그리드 구조로 변경함으로써, 사용자는 들어오자마자 자신의 목표 달성 현황을 직관적으로 파악할 수 있게 되었다.

특히 **SVG의 `stroke-dashoffset`**과 **GSAP의 `MotionPath**` 조합은 복잡한 게이지 애니메이션을 구현할 때 유용한 솔루션임을 확인했다. "달리는 즐거움"을 시각적으로 전달하는 이 컴포넌트가 사용자의 저축 동기 부여에 큰 도움이 되길 바란다.

