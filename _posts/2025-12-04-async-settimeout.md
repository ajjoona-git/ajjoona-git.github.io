---
title: "자바스크립트 비동기 처리와 setTimeout의 동작 원리"
date: 2025-12-04 09:00:00 +0900
categories: [Tech, JavaScript]
tags: [JavaScript, EventLoop, Asynchronous, SetTimeout, Vue.js, Debouncing]
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-12-04-async-settimeout/cover.png
description: 자바스크립트의 싱글 스레드 특성과 이벤트 루프(Event Loop)의 관계를 파헤치고, setTimeout을 활용한 디바운싱 구현 원리를 설명합니다.
---

# 자바스크립트는 싱글 스레드인데 어떻게 동시에 여러 일을 할까?

자바스크립트를 공부하다 보면 한 번쯤 마주치는 당황스러운 상황이 있습니다. 바로 <u>`setTimeout`의 동작 순서</u>입니다.

```jsx
console.log('1. 시작');

setTimeout(() => {
  console.log('2. 중간 (0초 대기)');
}, 0);

console.log('3. 끝');
```

위 코드를 실행하면 결과는 어떻게 될까요? 직관적으로는 "대기 시간이 0초니까 바로 실행되겠지?"라고 생각하여 `1 -> 2 -> 3`을 예상하기 쉽습니다. 하지만 실제 결과는 다음과 같습니다.

```
1. 시작
3. 끝
2. 중간 (0초 대기)
```

![Console 창](/assets/img/posts/2025-12-04-async-settimeout/2.png)
*Console 창*

"아니, 0초 뒤에 실행하라며? 왜 맨 나중에 실행돼?"

이 질문에 대한 답을 찾으려면 자바스크립트 엔진이 돌아가는 거대한 시스템, **런타임 환경(Runtime Environment)**의 비밀을 파헤쳐야 합니다. 오늘은 자바스크립트의 비동기 처리와 `setTimeout`의 진짜 동작 원리에 대해 알아보겠습니다.

## 자바스크립트는 '싱글 스레드' 언어다

우선 가장 중요한 대전제입니다. **자바스크립트는 싱글 스레드(Single Thread) 언어**입니다.

쉽게 말해 한 번에 함수 하나만 처리합니다. 멀티태스킹이 불가능하죠. 그런데 우리가 쓰는 웹 사이트는 어떤가요? 데이터를 받아오면서 동시에 애니메이션도 보여주고, 버튼 클릭도 받습니다.

팔이 하나인데 어떻게 이 모든 걸 동시에 할까요? 사실 자바스크립트는 혼자 일하지 않습니다. **브라우저(Browser)**라는 든든한 친구들이 있기 때문입니다.

## 비동기 처리의 4대 요소

자바스크립트의 동시성을 이해하기 위해서는 아래 4가지 요소의 역할을 알아야 합니다.

### ① Call Stack (호출 스택)

자바스크립트 엔진(V8 등) 안에 있는 작업 공간입니다.

- 코드가 실행되면 이곳에 쌓이고(Push), 실행이 끝나면 제거(Pop)됩니다.
- 싱글 스레드이므로 스택은 딱 **하나**입니다.

### ② Web APIs (브라우저 제공 API)

자바스크립트 엔진 밖, 브라우저가 제공하는 영역입니다.

- `setTimeout`, `DOM 이벤트`, `fetch(AJAX)` 등이 여기서 실행됩니다.
- **중요:** 타이머의 시간 카운트다운은 자바스크립트가 아니라 **이 Web API가 수행**합니다. (그래서 논블로킹, 즉 딴짓이 가능합니다.)

### ③ Task Queue (Callback Queue)

Web API에서 작업이 끝난 콜백 함수들이 기다리는 **대기실**입니다.

- "준비 다 됐습니다! 실행해주세요!" 하고 줄을 서 있는 곳입니다.
- 먼저 온 녀석이 먼저 나갑니다 (FIFO).

### ④ Event Loop (이벤트 루프)

이 시스템의 **관리자**입니다. 하는 일은 단순하지만 매우 중요합니다.

1. **Call Stack**이 비어있는지 확인합니다.
2. **Task Queue**에 대기 중인 콜백이 있는지 확인합니다.
3. 스택이 비어있다면, 큐에서 콜백을 꺼내 스택으로 밀어 넣습니다.

## setTimeout 동작 과정 시뮬레이션

이제 앞서 봤던 코드가 내부에서 어떻게 움직이는지 단계별로 뜯어보겠습니다.

```jsx
console.log('A');

setTimeout(() => {
  console.log('B');
}, 1000);

console.log('C');
```

**Step 1. `console.log('A')`**

- Call Stack에 추가되고 실행됩니다. 화면에 'A'가 찍히고 스택에서 사라집니다.

**Step 2. `setTimeout` 호출**

- Call Stack에 `setTimeout`이 들어옵니다.
- **핵심:** 자바스크립트 엔진은 타이머를 직접 세지 않습니다. 브라우저의 **Web API**에게 *"야, 1초 세고 나서 이 콜백함수(B) 실행해줘"* 라고 명령(위임)만 내립니다.
- 명령을 내렸으니 `setTimeout`은 할 일을 마쳤습니다. **Call Stack에서 즉시 제거됩니다.** (시간을 기다리지 않습니다!)

**Step 3. `console.log('C')` & 타이머 작동**

- **Web API:** 백그라운드에서 1초 카운트다운을 시작합니다.
- **Call Stack:** 그 사이 자바스크립트는 쉬지 않고 바로 다음 줄인 `console.log('C')`를 실행합니다. 화면에 'C'가 찍힙니다.

**Step 4. 1초 경과 (Queue로 이동)**

- Web API에서 1초 카운트가 끝났습니다.
- 맡아뒀던 콜백 함수 `() => console.log('B')`를 **Task Queue**로 보냅니다. 이제 실행 대기 줄에 섰습니다.

**Step 5. 이벤트 루프의 개입**

- 이벤트 루프가 감시합니다. *"Call Stack이 비었나?"*
- 현재 모든 전역 코드가 실행 완료되어 스택이 텅 비었습니다.
- *"오케이, 스택 비었다. 큐에 있는 콜백 나와!"*

**Step 6. 콜백 실행**

- Task Queue에 있던 콜백 함수가 Call Stack으로 옮겨져 실행됩니다.
- 화면에 'B'가 찍힙니다.

## 다시 보는 setTimeout(..., 0)

그렇다면 처음에 봤던 `setTimeout(fn, 0)`이 왜 늦게 실행되는지 이제 설명할 수 있습니다.

1. 시간을 0초로 설정했더라도, 무조건 **Web API -> Task Queue**를 거쳐야 합니다.
2. 이벤트 루프는 **Call Stack이 완전히 텅 빌 때까지** 큐의 작업을 가져오지 않습니다.
3. 즉, `setTimeout(..., 0)`은 *"0초 뒤에 실행해줘"*가 아니라, **"지금 실행 중인 코드가 다 끝나면 가능한 한 빨리 실행해줘"**라는 의미입니다.

이러한 특성을 이용해 무거운 계산 작업을 뒤로 미루거나, 브라우저 렌더링 순서를 조절할 때 의도적으로 `setTimeout(fn, 0)`을 사용하기도 합니다.

## 실전 예제: 도서 검색과 디바운싱

이벤트 루프와 `setTimeout`의 원리를 이해했다면, 실무에서 자주 쓰이는 **검색어 자동완성(디바운싱)** 로직도 완벽하게 해석할 수 있습니다. 아래는 Vue.js로 구현한 실시간 도서 검색 예제 코드입니다.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Document</title>
  <script src="[https://unpkg.com/vue@3/dist/vue.global.js](https://unpkg.com/vue@3/dist/vue.global.js)"></script>
  <!-- 스타일 생략 -->
</head>
<body>
  <div id="app">
    <!-- 템플릿 생략 -->
  </div>

  <script>
    const { createApp, ref, watch } = Vue

    createApp({
      setup() {
        const searchQuery = ref('')
        // ... 변수 선언 ...

        // [1] 비동기 통신 시뮬레이션 (1초 지연)
        const fetchSearchResults = async (query) => {
          return new Promise((resolve) => {
            setTimeout(() => {
              // ... 데이터 필터링 로직 ...
              resolve(results)
            }, 1000) 
          })
        }

        let timer = null

        watch(searchQuery, (newQuery) => {
          // ... 초기화 로직 ...

          // [2] 디바운싱: 이전 타이머 취소
          if (timer) clearTimeout(timer)

          // 0.5초 뒤에 API 호출 실행
          timer = setTimeout(async () => {
            const data = await fetchSearchResults(newQuery)
            // ... 결과 처리 ...
          }, 500)
        })
        // ...
      }
    }).mount('#app')
  </script>
</body>
</html>
```

위 코드에는 두 가지 핵심적인 `setTimeout` 사용 패턴이 있습니다.

### ① 디바운싱 (Debouncing): 0.5초의 미학

```jsx
// [1] 변수 선언: 타이머의 'ID'를 저장할 공간
let timer = null 

watch(searchQuery, (newQuery) => {
  
  // [2] 취소 (Reset): "방금 전에 건 예약은 취소해줘!"
  if (timer) clearTimeout(timer) 

  // [3] 예약 (Schedule): "0.5초 뒤에 새로 실행해줘!"
  // 이 부분이 없으면 아예 실행이 안 됩니다.
  timer = setTimeout(() => {
    fetchSearchResults(newQuery)
  }, 500)
  
})
```

사용자가 검색창에 "Vue"를 입력할 때 `watch` 내부의 로직은 다음과 같이 작동합니다.

1. **`setTimeout(..., 500)` 호출:** 사용자가 키를 누르면 Web API에게 "0.5초 뒤에 검색 함수를 실행해줘"라고 요청합니다. 그리고 그 예약증(ID)을 `timer` 변수에 저장합니다.
2. **`clearTimeout(timer)`의 역할:** 사용자가 0.5초가 지나기 전에 다음 글자를 입력하면, `clearTimeout`이 실행됩니다. 이는 Web API에게 **"아까 그 예약 취소해!"** 라고 명령하는 것입니다. 덕분에 불필요한 검색 요청이 Task Queue에 들어가지도 못하고 사라집니다.
3. **최종 실행:** 사용자가 입력을 멈추고 0.5초가 온전히 지나면, 그제야 Web API는 콜백 함수를 Task Queue로 보냅니다.

### ② 비동기 통신 시뮬레이션: 1초의 지연

```jsx
// 가상의 API 호출 함수 (비동기 시뮬레이션)
const fetchSearchResults = async (query) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      const mockData = [
        'vue.js 3 기초',
        'vue Composition API',
        'vue Router 완벽 가이드',
        'Vite로 시작하는 웹 개발',
        'JavaScript 심화'
      ]
      // 검색어가 포함된 항목만 필터링
      const results = mockData.filter(item =>
        item.toLowerCase().includes(query.toLowerCase())
      )
      resolve(results)
    }, 1000) // 1초 지연
  })
}
```

`fetchSearchResults` 함수 내부의 `setTimeout(..., 1000)`은 서버 통신 시간을 흉내 냅니다.

1. Promise가 생성되면서 `setTimeout`이 실행됩니다.
2. Web API에서 1초 동안 대기합니다. (이 동안 브라우저는 멈추지 않고 로딩 메시지를 보여줍니다.)
3. 1초 후 `resolve` 함수가 Task Queue를 거쳐 실행되면, `await`로 기다리고 있던 로직이 재개되어 데이터를 화면에 뿌려줍니다.

결국 `setTimeout`은 **"지금 당장 하지 말고, 브라우저(Web API) 네가 시간 좀 재고 있다가 나중에 알려줘"**라는, 자바스크립트의 가장 대표적인 비동기 위임 패턴인 것입니다.

![검색어 자동완성](/assets/img/posts/2025-12-04-async-settimeout/1.gif)
*검색어 자동완성*

---

## 결론 (Summary)

- 자바스크립트는 싱글 스레드라서 한 번에 하나만 처리한다.
- 하지만 **Web API(브라우저)**에게 작업을 미루는 방식(비동기)으로 동시에 여러 일을 하는 것처럼 보인다.
- `setTimeout`은 시간을 보장하는 것이 아니라, **"최소 이 시간 뒤에 대기열(Queue)에 넣어달라"**는 약속이다.
- 이 모든 과정을 조율하는 것이 바로 **이벤트 루프(Event Loop)**다.