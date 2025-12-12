---
title: "[쉽길] 경로 안내 페이지 UI/UX 개선 (Grid 레이아웃 & 모달 적용)"
date: 2025-11-18 09:00:00 +0900
categories: [Projects, 쉽길]
tags: [Frontend, CSS, UI/UX, Refactoring, JavaScript]
toc: true 
comments: true 
image: /assets/img/posts/2025-11-18-wisheasy-route-page/6.png
description: 경로 안내 화면의 가독성을 높이기 위해 Flex 레이아웃을 Grid로 변경하고, Alert 창을 모달(Modal)로 교체하여 사용자 경험을 개선했습니다.
---

경로 안내 페이지의 전달력과 자잘한 버그 박멸을 위해 디자인을 수정했다.

### 경로 안내 화면 디자인 수정

1. **"스텝 1/2"** : 아이콘 상단에 작은 글씨로
2. **{{ step_text }}** : 이전/다음 버튼과 겹치지 않도록, 작은 글씨로, 가독성 있게
3. **이전/다음 버튼** : 더 작게, 더 화면 외곽으로 배치, '<' '>' 화살표 모양으로 변경
4. **지하철 마커** : 출발/도착역과 일치하게 변경

![Before](/assets/img/posts/2025-11-18-wisheasy-route-page/8.png)
*Before*

![image.png](/assets/img/posts/2025-11-18-wisheasy-route-page/7.png)

![image.png](/assets/img/posts/2025-11-18-wisheasy-route-page/6.png)

![image.png](/assets/img/posts/2025-11-18-wisheasy-route-page/5.png)


### 레이아웃 디자인 수정 (Flex vs Grid)

하단 액션 버튼('처음부터', '편의 시설', '이용 불가')의 너비가 균등하지 않은 문제가 발생했다. '처음부터' 버튼만 `form` 태그로 감싸져 있어 `flex` 속성이 제대로 적용되지 않았기 때문이다. 이를 해결하기 위해 컨테이너의 스타일을 `display: flex`에서 `display: grid`로 변경하고, 3등분(`1fr 1fr 1fr`)하여 공간을 균등하게 분배했다.

```css
/* route.css */
.action-buttons {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    ...
}

.action-buttons > form {
    margin: 0;
    padding: 0;
    display: contents;
}

.action-btn {
    /* flex: 1; */
    ...
    width: 100%;
    height: 100%;
    justify-content: center;
}
```

![액션 버튼 수정 전](/assets/img/posts/2025-11-18-wisheasy-route-page/4.png)
*액션 버튼 수정 전*

![액션 버튼 수정 후](/assets/img/posts/2025-11-18-wisheasy-route-page/3.png)
*액션 버튼 수정 후*

### '이용불가' 안내창을 모달로 수정

‘이용 불가’ 액션 버튼을 누르면 신고할 수 있도록 하는 기능을 위한 요소로 남겨두었다. 다만 이 기능은 MVP에 포함되지 않아 껍데기뿐인 기능이다. 단순 `alert` 창에서 모달(Modal) UI로 변경하여 디자인 일관성 확보했다. 

![‘이용 불가’ 안내창](/assets/img/posts/2025-11-18-wisheasy-route-page/2.png)
*BEFORE: ‘이용 불가’ 안내창*

![‘이용 불가’ 모달](/assets/img/posts/2025-11-18-wisheasy-route-page/1.png)
*AFTER: ‘이용 불가’ 모달*


```html
<!-- route.html -->
  {# 이용 불가 모달 #}
  <div id="reportClosureModal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3><i class="fas fa-exclamation-triangle"></i> 기능 안내</h3>
        <button class="close-btn" onclick="closeReportClosureModal()">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="report-modal-body"> 
        <p>
          '이용 불가' 신고 기능은 현재 준비 중입니다.
          <br>
          빠른 시일 내에 더 좋은 서비스로 찾아뵙겠습니다.
        </p>
      </div>
    </div>
  </div>
```

```jsx
// route.js
// '이용 불가' 버튼 -> 모달 창 띄우기
function reportClosure() {
    document.getElementById('reportClosureModal').classList.add('show');
}

// (추가) '이용 불가' 모달 닫기
function closeReportClosureModal() {
    document.getElementById('reportClosureModal').classList.remove('show');
}
```

```css
/* route.css */
/* '이용 불가' 모달 전용 스타일 */
#reportClosureModal .report-modal-body {
    padding: 24px 16px 16px 16px; 
    text-align: center; 
}

#reportClosureModal .report-modal-body p {
    margin: 0 0 24px 0;   
    font-size: 16px;
    line-height: 1.6;
    color: var(--text-color-secondary); 
}
```
