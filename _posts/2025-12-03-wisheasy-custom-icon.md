---
title: "[쉽길] Font Awesome에 원하는 아이콘이 없을 때? (Feat. CSS로 에스컬레이터 구현하기)"
date: 2025-12-03 09:00:00 +0900
categories: [Projects, 쉽길]
tags: [Frontend, CSS, UI/UX, FontAwesome, Troubleshooting]
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-12-03-wisheasy-custom-icon/2.png # (선택) 대표 이미지
---


가장 중요한 아이콘인 **에스컬레이터 아이콘(`fa-escalator`)이 화면에 나오지 않는 문제**가 발생하다!

Font Awesome 무료 버전을 사용할 때 발생하는 아이콘 누락 문제를 해결하고, CSS를 활용해 커스텀 아이콘을 기존 시스템에 자연스럽게 녹여낸 과정을 공유합니다.

## "에스컬레이터를 의미하는지 모르겠어요"

![기존 에스컬레이터 아이콘](/assets/img/posts/2025-12-03-wisheasy-custom-icon/3.png)
*기존 에스컬레이터 아이콘*

> "저 화살표가 뭔 뜻인지 모르겠어요." 
> "계단이랑 구분이 안 되는 것 같아요"

프로젝트를 마무리하면서 마지막으로 테스트를 하면서 받은 피드백이다.

곧바로 에스컬레이터 아이콘을 찾아봤다. 지금 쉽길 프로젝트에서는 아이콘 라이브러리로 "Font Awesome (Free 버전)"을 사용하고 있다.
경로 안내 페이지에서 에스컬레이터 정보를 시각화하기 위해 `fas fa-escalator` 클래스를 적용했는데, 화면에는 아이콘 대신 빈 공간만 출력되었다.

확인 결과, `fa-escalator` 아이콘은 **Pro(유료) 버전에서만 제공**되는 아이콘이었습니다.
Free 버전에서는 `fa-walking`(걷기), `fa-info`(정보) 등은 사용할 수 있지만, 정작 우리 서비스의 핵심인 에스컬레이터는 지원하지 않았다.

## 어떻게 하지?

이 문제를 해결하기 위해 세 가지 방법을 고려해봤다.

1.  **Pro 라이브러리 결제:** 비용 발생 (MVP 단계에서는 부담).
2.  **대체 아이콘 사용:** `fa-level-up-alt` 등을 써봤지만, '에스컬레이터'라는 의미가 직관적으로 전달되지 않음.
3.  **커스텀 이미지 적용 (채택):** 별도의 PNG 아이콘을 구해서 적용하되, **기존의 `<i>` 태그 기반 아이콘 시스템을 그대로 유지**하는 방식을 선택.

## 커스텀 아이콘을 만들자!

HTML 구조를 뜯어고쳐서 `<img>` 태그를 넣는 대신, **CSS 클래스만 교체하면 작동하도록** 설계를 유지하고 싶었다.

### Step 1. 무료 아이콘 이미지 찾기

먼저 직관적인 에스컬레이터 PNG 이미지를 확보했다. Icons8 에서 PNG 링크로 아이콘을 받아올 수 있어서 해당 링크를 사용했다.

```
https://img.icons8.com/?size=100&id=10639&format=png&color=000000
```

### Step 2. CSS로 '가짜 폰트 아이콘' 클래스 만들기

Font Awesome 아이콘은 기본적으로 `<i>` 태그에 클래스를 부여하여 작동한다. 이와 똑같이 동작하는 `.icon-escalator-custom` 클래스를 만들었다.

```css
/* static/css/route.css */

.icon-escalator-custom {
    display: inline-block;
    width: 100%;
    height: 100%;
    
    /* 배경 이미지를 활용해 아이콘처럼 보이게 처리 */
    background-image: url('https://img.icons8.com/?size=100&id=10639&format=png&color=000000');
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    
    vertical-align: middle; /* 텍스트와 높이 정렬 */
}
```

이렇게 하면 HTML에서 `<i class="icon-escalator-custom"></i>`라고 썼을 때, 폰트 아이콘처럼 이미지가 나타난다.

### Step 3. JS 파일과 HTML 파일 업데이트

기존에는 시설물 설정 객체(`FACILITY_CONFIG`)에서 `fas fa-walking` 같은 Font Awesome 클래스명을 관리하고 있었기 때문에, 이 부분을 방금 만든 커스텀 클래스로 교체해 준다.

경로 안내 페이지(`route.html`)의 렌더링 로직에서도 해당 클래스를 커스텀 클래스로 교체해주었다.

```javascript
// static/js/station_info.js

const FACILITY_CONFIG = {
    // ... 기존 설정들
    '에스컬레이터': {
        // icon: 'fas fa-walking',  <-- 기존: Font Awesome 제공 클래스
        icon: 'icon-escalator-custom', // <-- 수정: 커스텀 클래스 적용!
        showInRoute: false,
    }
};
```

```javascript
// journeys/route.html

if (text.includes('에스컬레이터')) {
    // 기존 로직
    // Font Awesome 클래스(fas)가 전제되어 있었음 (작동 안 함)
    // iconElement.className = 'fas fa-escalator'; 

    // 수정된 로직
    // 'fas' 접두사 없이 커스텀 클래스만 깔끔하게 적용
    iconElement.className = 'icon-escalator-custom';
}
```

## 수정 결과

![에스컬레이터 아이콘 적용](/assets/img/posts/2025-12-03-wisheasy-custom-icon/2.png)
*에스컬레이터 아이콘 적용*

적용 결과, 이제 사용자들은 이상한 화살표 아이콘 대신 **진짜 에스컬레이터 아이콘**을 볼 수 있게 되었다.

## 편의시설에서는 색깔과 크기가 달라야 한다

앗차차, 같은 클래스를 역 정보 페이지에도 적용하려하니 스타일이 안 맞는다.

주변 스타일에 맞게 하늘색을 적용하고, 크기도 작게 만들었다. 역 정보 페이지에서 사용하는 클래스는 `station_info.css`에 별도로 작성하기 때문에 같은 클래스 이름을 사용해도 문제되지 않는다.

```css
/* static/css/station_info.css */

.icon-escalator-custom {
    display: inline-block;
    width: 16px;  
    height: 16px;
    background-image: url('https://img.icons8.com/?size=100&id=10639&format=png&color=2E9AFE');
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    vertical-align: middle; /* 텍스트와 높이 맞춤 */
}
```

주변 아이콘들과 어울리는 우리의 커스텀 에스컬레이터 아이콘을 확인할 수 있다.

![스타일 변경된 에스컬레이터 아이콘](/assets/img/posts/2025-12-03-wisheasy-custom-icon/1.png)
*스타일 변경된 에스컬레이터 아이콘*

---

### 인사이트

이번 작업을 통해 다음과 같은 인사이트를 얻었다.

1.  **유연한 설계의 중요성:** 아이콘을 하드코딩하지 않고 `config` 객체와 CSS 클래스로 관리했기 때문에, HTML 구조 변경 없이 디자인을 수정할 수 있었다.
2.  **사용자 경험(UX) 최우선:** 개발 편의를 위해 무료 아이콘으로 타협하기보다, 조금 번거롭더라도 유저에게 직관적인 UI를 제공하는 것이 옳다는 것을 다시 확인했다.

