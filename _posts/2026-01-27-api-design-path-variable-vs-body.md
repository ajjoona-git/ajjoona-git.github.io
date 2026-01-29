---
title: "API Design: Path Variable vs Request Body (RESTful, 확장성, 보안)"
date: 2026-01-27 09:00:00 +0900
categories: [Tech, Web]
tags: [APIDesign, RESTful, API, Security, Logging, SpringBoot, Refactoring]
toc: true
comments: true
description: "API 엔드포인트 설계 시 ID 값을 Path Variable(/resource/{id})로 넘길지, Request Body로 넘길지 고민될 때의 판단 기준을 정리했습니다. 확장성, RESTful 의미론, 그리고 서버 로그와 관련된 보안 이슈를 비교 분석합니다."
---


API 엔드포인트를 설계하던 중 흥미로운 고민이 생겼다.
예약 신청 API를 만들 때, 방 ID(`roomId`)를 어디에 담아야 할까?

* **1안 (Path Variable):** `POST /reservation/{roomId}/apply`
* **2안 (Request Body):** `POST /reservation/apply` (Body: `{ "roomId": "..." }`)

결론부터 말하자면 **정답은 없다.** 하지만 각 방식이 가지는 장단점은 명확하다. RESTful 설계 철학, 확장성, 그리고 보안 관점에서 두 방식을 비교해 본다.

---

## Path Variable vs Request Body

| 비교 항목 | **Path Variable** (`/{id}/apply`) | **Request Body** (`/apply`) |
| :--- | :--- | :--- |
| **RESTful 의미** | **더 명확함.** "이 방(Resource)에 신청(Verb)한다"는 구조가 URL에 드러난다 | URL만 봐서는 "어디에" 신청하는지 알 수 없다 (Body를 까봐야 함) |
| **확장성** | **낮음.** 추후 비밀번호나 메시지를 추가하려면 구조가 복잡해진다 | **높음.** DTO에 필드만 추가하면 URL 변경 없이 기능 확장이 가능하다 |
| **보안 (로그)** | **취약함.** URL은 서버 로그(Nginx, AWS)에 평문으로 기록된다 | **안전함.** Body 내용은 기본적으로 액세스 로그에 남지 않는다 |
| **데이터 크기** | URL 길이 제한에 걸릴 수 있다 | 제한이 거의 없다 |


## 왜 Request Body 방식을 제안했는가?

나는 초기 설계 단계에서 **Request Body** 방식을 제안했다. 가장 큰 이유는 **"확장성(Future-proofing)"** 때문이다.

### 상황: "비공개 방 비밀번호" 기능이 추가된다면?
지금은 `roomId`만 필요하지만, 나중에 비밀번호를 입력해야 들어갈 수 있는 방이 생긴다고 가정해 보자.

* **Path Variable 방식:**
    * URL: `POST /reservation/{roomId}/apply`
    * Body: `{ "password": "1234" }`
    => **데이터가 분산**된다. 식별자는 URL에, 인증 정보는 Body에 나뉘어 있어 처리가 번거롭다.

* **Request Body 방식:**
    * URL: `POST /reservation/apply`
    * Body: `{ "roomId": "...", "password": "1234" }`
    => **깔끔한 DTO.** 모든 신청 데이터가 하나의 JSON 객체에 묶여 전송된다. Spring의 `@Valid` 어노테이션으로 한곳에서 검증하기도 편하다.


## 보안 이슈: "URL은 로그에 남는다"

*"어차피 개발자 도구(F12) 켜면 URL이든 Body든 다 보이는데, 보안상 무슨 차이가 있나요?"*

맞다. **클라이언트(해커) 입장**에서는 두 방식에 차이가 없다.

하지만 **서버(인프라) 입장**에서는 결정적인 차이가 있다. 바로 **'액세스 로그(Access Log)'** 때문이다.

### 서버 로그의 차이
Nginx, Apache, AWS ELB 같은 웹 서버들은 기본적으로 **"누가 어떤 URL을 호출했는지"**를 파일로 기록한다.

* **Path Variable 사용 시:**
    * 로그 기록: `[INFO] POST /reservation/secret-room-1234/apply`
    * 만약 `roomId`가 노출되면 안 되는 **비밀 초대 코드**라면? 시스템 관리자나 로그 분석 툴이 이 값을 훤히 볼 수 있게 된다. 이를 **"URL을 통한 정보 누수"**라고 한다.

* **Request Body 사용 시:**
    * 로그 기록: `[INFO] POST /reservation/apply`
    * 대부분의 서버는 Body(본문) 내용을 로그에 남기지 않는다. 데이터가 너무 크고 민감 정보가 많기 때문이다.


## 그래서 API를 어떻게 설정해야 하지?

프로젝트의 상황에 따라 유연하게 선택하면 된다.

### Path Variable 추천 상황
* **RESTful**한 설계를 중요시할 때.
* `roomId`가 단순한 식별자(UUID)이고, **공개된 정보**일 때.
* 로그를 통해 "어떤 방에 신청이 몰리는지" 쉽게 파악하고 싶을 때.

### Request Body 추천 상황
* **확장성**을 고려하여, 추후 파라미터가 늘어날 가능성이 높을 때.
* `roomId`가 비밀키(Secret Key) 성격을 띠어 **로그에 남으면 안 될 때**.
* DTO 하나로 깔끔하게 데이터를 받고 싶을 때.


---

## 마치며

현재 우리 프로젝트의 `roomId`는 공개된 UUID이므로 Path Variable을 쓰기로 했다. 