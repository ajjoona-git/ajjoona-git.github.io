---
title: "n8n으로 카카오톡 자동 메시지 구현하기"
date: 2025-11-15 09:00:00 +0900
categories: [Tech, DevOps]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, Kakao, API, OAuth, NoCode, Automation]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-15-n8n-kakaotalk/cover.png # (선택) 대표 이미지
description: "노코드 자동화 툴 n8n과 카카오톡 REST API를 연동하여 '나에게 메시지 보내기' 기능을 구현하고 OAuth 인증 과정을 다룹니다."
---

본격적으로 n8n을 써보기에 앞서서, 간단한 기능을 구현해보았다.

바로 카카오톡 API를 이용해서 **카카오톡의 나에게 보내기를 자동화**하기!

## 카카오톡 (나에게 보내기) API

### 0. kakao developers 설정

#### 1. 로그인 및 앱 추가하기

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/26.png)

#### 2. 앱 > 일반 > 앱 키 > REST API 키 복사하기    

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/25.png)

#### 3.  앱 > 일반 > 플랫폼 > Web 플랫폼 등록
- 사이트 도메인: [`https://localhost:3000`](https://localhost:3000/)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/24.png)

#### 4. 제품 설정 > 카카오 로그인 > 일반 > 사용 설정 `ON`

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/23.png)

#### 5. 제품 설정 > 카카오 로그인 > 일반 > 리다이렉트 URI 등록

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/22.png)

#### 6. 제품 설정 > 카카오 로그인 > 동의항목 > 접근권한
- **이용 중 동의** 체크

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/21.png)

---

기본 설정을 마쳤다면, 

1) 수동으로 인가 코드를 받아 **액세스 토큰 발급 - 카카오톡 메시지 전송** 자동화를 구현하는 방법과

2) **Credential**을 생성해 자동으로 인가 코드를 받고 실행하는 방법

두 가지 방법을 소개하겠다.

---

### 1. 수동으로 인가 코드 받기

#### 1. 인가 코드 받기
    - `client_id`: 앞서 복사한 REST API 키
    - `redirect_url`: 등록한 Redirect URI
    - `response_type`: `code` (고정값)
    - `scope`: `talk_message` (메시지 전송 권한)

```
https://kauth.kakao.com/oauth/authorize?client_id=YOUR_REST_API_KEY&redirect_uri=https://localhost:3000&response_type=code&scope=talk_message
```

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/20.png)


- 카카오 로그인 후 동의하면 Redirect URI로 리다이렉트 

- URL에서 `code` 파라미터 값을 복사: `https://localhost:3000?code=AUTHORIZATION_CODE` 

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/19.png)

#### 2. 액세스 토큰 발급
- n8n에서 HTTP Request 노드 생성
- Import cURL command에서 다음 curl 명령어를 입력
    - `redirect_uri`: 인가 코드를 받을 때 사용했던 **Redirect URI**
    - `client_id`: REST API 키
    - `code`: 이전 단계(인가 코드 받기)에서 받은 **인가 코드**


> **주의사항**
> 
> 인가 코드 요청의 `redirect_uri`와 curl의 `redirect_uri`가 일치해야 하며,
> 
> 리다이렉션 URI에 등록되어 있어야 한다.
{: .prompt-tip }

```
curl -v -X POST "https://kauth.kakao.com/oauth/token" \
 -H "Content-Type: application/x-www-form-urlencoded" \
 -d "grant_type=authorization_code" \
 -d "client_id=YOUR_REST_API_KEY" \
 -d "redirect_uri=https://localhost:3000" \
 -d "code=AUTHORIZATION_CODE"
```

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/18.png)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/17.png)


![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/16.png)
*실행 결과*

#### 3. 토큰 테스트
- 다음 액션 노드로 HTTP Request를 생성한다.
- Import cURL로 다음 curl을 입력한다.
    - `Authorization`: YOUR_ACCESS_TOKEN 부분을 삭제하고, 왼쪽INPUT 탭에서 access_token을 드래그해 입력한다.

```
curl -v -X POST "https://kapi.kakao.com/v2/api/talk/memo/default/send" \
 -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
 -H "Content-Type: application/x-www-form-urlencoded" \
 -d 'template_object={"object_type":"text","text":"안녕하세요! n8n 테스트 메시지입니다.","link":{"web_url":"https://n8n.io"}}'

```

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/15.png)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/14.png)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/13.png)
*실행 결과*

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/12.png)
*워크플로우*

---

### 2. Credential을 사용해서 토큰 자동 발급

#### 1. kakao developers에서 앱 > 제품 설정 > 카카오 로그인 > 일반 > Client Secret 발급받기
#### 2. 리다이렉트 URI에 [`https://oauth.n8n.cloud/oauth2/callback`](https://oauth.n8n.cloud/oauth2/callback) 추가

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/11.png)

#### 3. Credential 생성
- HOME > Credentials > Create credential > OAuth2 API 선택 (혹은 Kakao)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/10.png)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/9.png)

- `Authorization URL`: [https://kauth.kakao.com/oauth/authorize](https://kauth.kakao.com/oauth/authorize)
- `Access Token URL`: [https://kauth.kakao.com/oauth/token](https://kauth.kakao.com/oauth/token)
- `Client ID`:  REST API 키
- `Client Secret`: kakao developers에서 발급받은 클라이언트 시크릿 코드
- `Scope`: talk_message
- `Authentication`: 카카오는 중요 토큰 등을 본문에 제공하기 때문에 Body로 설정
- Connect my account 까지 완료

#### 4. HTTP Request 노드 생성
- Authentication > Generic Credential Type > OAuth2 API > Kakao (이전에 만든 credential)
- Send Body 섹션 설정
    - Body Content Type: Form Urlencoded
    - Name: template_object
    - Value:
    
    ```
    {"object_type":"text","text":"안녕하세요! n8n 테스트 메시지입니다.","link":{"web_url":"https://n8n.io"}}
    ```
    

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/8.png)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/7.png)

---

### 3. 웹훅(Webhook) 연결하기

#### 1. n8n 워크플로우에서 Webhook 노드 생성
- Production URL 복사
- HTTP Method: POST

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/6.png)

#### 2. 기존 HTTP Request (카카오톡) 노드 수정
- Body Parameters의 Value를 Expression으로 변경하고 다음 코드를 입력한다.

```
{
  "object_type": "text",
  "text": "🔔 새 방명록 도착!\n작성자: {{ $json.body.name }}\n내용: {{ $json.body.message }}",
  "link": {
    "web_url": "https://ajjoona-git.github.io/"
  }
}
```

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/5.png)

#### 3. 워크플로우를 저장(Save)하고 꼭 Active 스위치를 켜서 활성화

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/4.png)

#### 4. 가짜 폼으로 웹훅 트리거 작동하는지 확인하기
- 코드의 YOUR_N8N_WEBHOOK_PRODUCTION_URL 부분을 1번에서 복사했던 n8n Production URL로 교체
- test.html로 저장

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>n8n 웹훅 테스트 폼</title>
</head>
<body>
    <h1>n8n 웹훅 테스트</h1>
    <p>이 폼을 제출하면 n8n 웹훅이 실행됩니다.</p>

    <form action="YOUR_N8N_WEBHOOK_PRODUCTION_URL" method="POST">
        <div>
            <label for="name">이름:</label>
            <input type="text" id="name" name="name">
        </div>
        <br>
        <div>
            <label for="message">메시지:</label>
            <textarea id="message" name="message"></textarea>
        </div>
        <br>
        <button type="submit">카톡 알림 전송 테스트</button>
    </form>
</body>
</html>
```

#### 5. test.html 실행하고 폼 제출

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/3.png)

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/2.png)
*실행 결과*

![image.png](/assets/img/posts/2025-11-15-n8n-kakaotalk/1.png)
*워크플로우*

---

### 레퍼런스

[Kakao Developers 공식 문서 - REST API](https://developers.kakao.com/docs/latest/ko/rest-api/getting-started)

[kakaoTalk(나에게) API](https://wikidocs.net/290905)

[뒷방늙은이 n8n - Credential으로 토큰 관리 [Kakao REST API/Oauth2 API]](https://www.youtube.com/watch?v=70EHza7oNRQ&t=2s)