---
title: "[둥지] Figma Make로 프로토타입 구현하기"
date: 2025-11-18 09:00:00 +0900
categories: [Projects, 둥지]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [Figma, FigmaMake, Prototype, UI/UX, Design]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-18-frontend-prototype/11.png # (선택) 대표 이미지
description: \'집 찾는 어미새\' 컨셉에 맞춰 Figma Make를 활용해 둥지 프로젝트의 UI/UX 프로토타입을 제작하고 디자인을 고도화한 과정입니다.
---

기획서에 포함할 우리 서비스의 프로토타입을 만들기 위해 Figma Make를 갈궈봤다.

우선 BEFORE 버전에서도 우리가 의도한 기능들이 대부분 작동했기 때문에 GPT에게 코드를 주고, 기능명세서를 뽑아내라고 했다.

그리고 그 기능 명세서를 다시 AI에게 넘겨서 서비스와 기능에 어울리는 화면을 재구성해달라고 했다.


어느 정도 수정되기는 했지만, 여전히 화면이 너무 못생기고 가독성도 떨어지는 문제가 있어서, 요소 하나하나를 선택해서 어떻게 수정해달라는 구체적인 프롬프트를 작성하기 시작했다.

그 결과, 버전 151까지 만들어졌으며... 많이 예뻐졌다!

---

### UI/UX 디자인

특히 신경쓴 부분은 **'아무것도 모르는 사회초년생들이 주택 계약할 때 이것만 보고 따라와도 중간은 갈 수 있게 해주자'**는 서비스 기획 의도를 반영하는 것이었다. 그래서 체크리스트 항목을 설명하는 부분에 **'중1 수준의 WHAT (이 체크리스트가 무슨 내용인지), WHY (왜 이걸 해야 하는지)'** 설명을 추가하고 생소한 용어 같은 경우는 챗봇에게 바로 물어볼 수 있는 UX를 고안했다.

그리고 우리의 서비스의 컨셉이 '아기새'가 엄마 품에서 벗어나 '새로운 둥지'를 찾아 나서는 여정을 함께하는 것이기 때문에 이 세계관을 보여줄 수 있도록 UI를 디자인했다. 둥지, 아기새, 어미새를 로고와 서비스 대표 이미지에 적절히 배치해서 **'집 찾는 어미새'**를 컨셉으로 귀엽게 디자인했다. 이에 맞춰서 기존의 체크리스트, 챗봇 등 기능 이름으로 두었던 서비스명을 '둥지 짓기 플랜', '어미새 챗봇' 등으로 톤을 맞추어주었다. 특히 진행상황에 따라 둥지를 찾아 날아가는 아기새의 모습을 그려 귀여운 포인트를 주었다.

- 체크리스트 → **둥지 짓기 플랜**
- 둥지 AI 챗봇 → **어미새 챗봇**
- 판례/법률 검색 → **똑똑한 법률 사전**
- 진행상황 progress bar를 **새가 둥지에 안착하는 모습**으로 형상화

![둥지 안착](/assets/img/posts/2025-11-18-frontend-prototype/13.png)
*둥지 안착*

---

## BEFORE

![BEFORE](/assets/img/posts/2025-11-18-frontend-prototype/12.png)
*BEFORE*

## AFTER

> [프로토타입 시연 영상 보러가기](https://youtu.be/zenYaThc5hw)
{: .prompt-info }

### 메인페이지

![메인페이지](/assets/img/posts/2025-11-18-frontend-prototype/11.png)
*메인페이지*

### 둥지 짓기 플랜

![체크리스트](/assets/img/posts/2025-11-18-frontend-prototype/10.png)
*체크리스트*

![체크리스트 세부 항목](/assets/img/posts/2025-11-18-frontend-prototype/9.png)
*체크리스트 세부 항목*

![체크리스트 액션](/assets/img/posts/2025-11-18-frontend-prototype/8.png)
*체크리스트 액션*

### 어미새 챗봇

![어미새 챗봇](/assets/img/posts/2025-11-18-frontend-prototype/7.png)
*어미새 챗봇*

### 똑똑한 법률 사전

![똑똑한 법률 사전](/assets/img/posts/2025-11-18-frontend-prototype/6.png)
*똑똑한 법률 사전*

![검색 결과 자세히 보기](/assets/img/posts/2025-11-18-frontend-prototype/5.png)
*검색 결과 자세히 보기*

### 마이페이지

![내 프로필](/assets/img/posts/2025-11-18-frontend-prototype/4.png)
*내 프로필*

![내 주택 정보](/assets/img/posts/2025-11-18-frontend-prototype/3.png)
*내 주택 정보*

![대화 기록](/assets/img/posts/2025-11-18-frontend-prototype/2.png)
*대화 기록*

![저장한 링크](/assets/img/posts/2025-11-18-frontend-prototype/1.png)
*저장한 링크*

