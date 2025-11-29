---
title: "서버는 어떻게 클라이언트의 요청에 응답할까?"
date: 2025-11-06 16:00:00 +0900
categories: [Tech, CS]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [WebServer, Nginx, Gunicorn, WSGI, Django]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
# image: /assets/img/posts/my-post-banner.png # (선택) 대표 이미지
---

## 서버란 무엇인가?

우리가 웹페이지에 접속해서 무언가를 하는 행위 자체는 **클라이언트의 요청**과 **서버의 응답**의 연속이라고 볼 수 있다. 간단히 말해서 클라이언트는 브라우저, 즉 사용자인 우리이고 서버는 그 웹페이지를 제공해주는 시스템이다.

### CGI (Common Gateway Interface)

웹 서버가 동적 컨텐츠를 요청하기 위해 외부 프로그램을 호출하는 규약이다.

CGI는 아주 초기의 인터페이스이기 때문에 조금 느리고 서버 부하가 크다. 그 이유는 요청 1개당 1개의 프로세스가 생성되고 종료되기 때문이다. 이 과정을 자세하게 보면 다음과 같다.

1. 웹 서버가 HTTP request을 받아, OS에게 ‘프로세스 생성’을 요청한다.
2. 웹 서버는 요청 정보를 두 가지 경로로 새 프로세스에 전달한다.
    1. `QUERY_STRING`, `REQUEST_METHOD` 같은 요청 메타데이터는 '**환경 변수**'로 전달
    2. (POST 요청의 경우) 본문에 담긴 실제 데이터는 스크립트의 '**stdin (표준 입력)**'으로 전달
3. 스크립트가 stdout (표준 출력) 형식 (예: print)으로 응답하면, 이를 다시 HTTP 형식으로 바꾼다.
4. 웹 서버는 1회용 프로세스가 표준 출력으로 인쇄하는 모든 내용을 실시간으로 캡쳐한다.
5. 스크립트 실행이 끝나면 이 CGI로 만들었던 1회용 프로세스를 종료하고, OS에서 파괴한다.

과정을 보면, 요청 한 번에 프로세스를 한 번 만들고 버린다. 요청이 1000개 들어온다면 1000개의 프로세스를 만들어 버려야 한다. CGI가 프로세스를 한 번 쓰고 버리는 게 너무 비효율적이라 WSGI나 ASGI 같은 새로운 인터페이스(규격)가 등장했다.

### WSGI (Web Server Gateway Interface)

Python 언어로 웹 애플리케이션을 만들 때 WAS (Gunicorn)와 웹 애플리케이션 (Django)이 서로 데이터를 주고 받기 위해 ‘대화하는 방식’을 표준화한 규격 (Interface)이다. 프로그램도, 언어도, 소프트웨어도 아니다. 그저 “이렇게 데이터를 주고받자”라고 정해둔 ‘규칙’이자 ‘명세(specification)’이다.

이 약속이 없다면 Django 개발자는 Gunicorn 서버에서만 돌아가는 코드를 짜야 하고, Gunicorn 개발자는 Django만 지원해야 한다. WSGI를 지원하는 여러 애플리케이션(Django, Flask 등)에서 호환될 수 있다.

[공식 문서 (PEP-3333)](https://peps.python.org/pep-3333/)에서는 WSGI에 대해 다음과 같이 서술하고 있다.

> a simple and universal interface between web servers and web applications or frameworks
> 

> to facilitate easy interconnection of existing servers and applications or frameworks, not to create a new web framework
> 

---

## 웹페이지는 도대체 어떻게 우리의 요청에 응답하는 것인가?

서버를 뜯어 보면 그 안에는 각각의 역할을 하는 여러 조직들이 있다.

### 1. 웹 서버(Web Server): Nginx

가장 먼저 클라이언트의 요청을 받는 곳은 **‘웹 서버’**라는 곳이다. 우리 프로젝트는 Nginx를 웹 서버로 사용하고 있다.

웹 서버는 사용자의 모든 요청 (HTTP request)을 가장 앞에서 받는 ‘문지기’라고 생각하면 된다. 꽤나 여러 가지 역할을 하고 있는데, 주요 역할은 다음과 같다.

1. **정적 파일 (Static Files) 처리**
    
    사용자가 `style.css`, `logo.png`, `index.html` 같은 정적 파일 (Static Files)을 요청할 때가 있다. 이 파일들은 미리 만들어져 있고 변하지 않는 파일들이다. 웹 서버는 이런 간단한 요청에 대해서는 직접 응답한다. 
    
2. **리버스 프록시 (Reverse Proxy)**: 서버를 위한 대리인 역할.
    
    실제 서버들을 앞단에서 대신하기 때문에 Proxy, 안으로 들어오는 inbound 요청을 받아 처리하기 때문에 Reverse 라고 부른다. 클라이언트가 서버에 접속할 때 ‘리버스 프록시’를 만나기 때문에 실제 서버인 Gunicorn이나 django를 보호할 수 있다.
    
    만약 사용자가 ‘경로 검색’처럼 동적 컨텐츠 (Dynamic Content)를 요청한다면, 웹 서버는 자신이 직접 처리하지 않고 뒤에 있는 웹 어플리케이션 서버 (WAS)에 전달한다. 이처럼 클라이언트 요청을 서버로, 서버의 응답을 클라이언트에게 전달하는 역할을 한다.
    
    **[비교] 포워드 프록시 (Forward Proxy)**: 클라이언트를 위한 대리인 역할. 
    
    서버에 접속할 때 ‘포워드 프록시’를 거쳐서 나가기 때문에 서버 입장에서는 실제 클라이언트가 누구인지 모르고 ‘포워드 프록시’가 요청한 것으로 인식한다. 그래서 클라이언트의 익명성을 보장하거나 특정 사이트 접근을 차단(필터링)할 수 있다.
    
3. **HTTPS 리디렉션**
    
    Nginx에는 2개의 포트가 있다. 평문 통신을 받는 HTTP: 80번 포트와 암호문 통신을 위한 HTTPS: 443번 포트이다. 
    
    만약 사용자가 80번 포트(HTTP)로 접속을 시도한다면, Nginx는 80번 포트에서 이 요청을 받는다. 이때 Nginx는 실제 페이지를 주는 대신 `301 Moved Permanently`, 즉 “앞으로 https://site.com (443번)으로만 접속하세요”라는 정보를 전달한다. 사용자의 브라우저는 `301 Moved Permanently` 응답을 받고 즉시  https://site.com 페이지로 자동으로 재요청(redirection)한다.
    
    이 과정을 통해 모든 사용자가 암호화된, 안전한 HTTPS 통신을 사용하도록 강제할 수 있다.
    

### 2. 웹 어플리케이션 서버 (WAS, Web Application Server): Gunicorn

WAS (웹 어플리케이션 서버)는 웹 서버 (Nginx)가 뒤쪽 서버에 전달한 동적 컨텐츠 요청을 수행하는 곳이다. 이름 그대로 ‘웹 어플리케이션(코드)을 실행하는 서버’를 의미하는, 다소 광범위한 용어라고 생각된다. 동적 컨텐츠 요청이 들어올 때마다 앱을 실행하고 일을 시키는 역할을 담당한다.

1. **앱 실행**
    
    WAS는 CGI 처럼 요청마다 프로그램을 띄우는 비효율을 극복하기 위해서 생겨났다. 그래서 애플리케이션 코드 (Django 등)를 서버 메모리에 미리 로드하고, 요청을 처리할 일꾼(worker)들을 생성해 대기시킨다. 
    
    워커는 OS가 관리하는, 실제 메모리와 CPU를 점유하고 있는 프로세스를 의미한다. Gunicorn은 Prefork 방식을 채택하고 있어서 ‘마스터 프로세스’가 자신과 똑같은 ‘워커 프로세스’들을 여러 개 복제(fork)해둔다. 각 워커는 한 번에 하나의 요청을 처리하는 동기 방식을 사용한다.
    
2. **일 분배**
    
    웹 서버 (Nginx)로부터 전달된 수많은 요청을 동시에 처리한다. 앞서 복제해둔 워커들이 일이 주어지기를 기다리고 있다. WAS는 대기 중인 워커들에게 일을 적절히 분배하고 지시한다. 여러 사용자의 요청을 동시에 처리하기 위해 프로세스나 스레드를 관리한다.
    
3. **환경 제공**
    
    애플리케이션 실행에 필요한 환경을 제공한다. 앱을 실행하는 데 필요한 데이터베이스를 연결해주는 것이 그 예시이다.
    

WAS의 종류에 따라 일꾼의 형태와 일을 분배하는 방법이 다르다. 즉, 어떤 표준 규격을 따르고 어떤 언어 진영에서 사용하는지가 다르다. 

Gunicorn이 Python을 위한 WAS이고, 이 WAS가 Python 진영의 표준 규격인 WSGI를 사용하기 때문에 **WSGI 서버**라고 부른다. WSGI 서버는 WAS의 한 종류로서, WAS보다 더 좁은 용어이다.

| 종류 | 언어 | 표준 규격 |
| --- | --- | --- |
| Gunicorn (WSGI Server) | Python | WSGI (Web Server Gateway Interface) |
| Uvicorn | Python | ASGI (Asynchronous Server Gateway Interface) - 비동기 방식 |
| Tomcat | Java | Servlet |

### 3. 애플리케이션 (Application): Django

WSGI 서버 (Gunicorn)에서 WSGI 규격으로 번역해서 전달받은 요청을 실질적으로 수행하는 곳이다.

애플리케이션은 다시 WSGI 미들웨어와 WSGI 애플리케이션으로 나눌 수 있다. 

WSGI 미들웨어는 서버 (Gunicorn)과 앱 (Django) 사이에 끼는 코드 조각을 지칭한다. 엄밀히 말하면 미들웨어는 서버도, 애플리케이션도 아니다. WAS (Gunicorn)에서 분배된 일이 워커에게 전달되기 과정에서, 요청이나 응답을 전처리하는 역할을 한다.로깅, 압축, 인증, 정적 파일 처리 등의 자잘한 일들을 수행한다. 

실제 코드(로직)를 실행하는 곳은 WSGI 애플리케이션 (Django)이다. 로직을 수행해서 클라이언트의 요청에 대한 응답을 생성한다. 생성한 응답은 다시 WSGI 미들웨어 - WSGI 서버 - 웹 서버를 거쳐 클라이언트에게 전달된다.

### 정리!

전체 흐름을 정리해보면 아래 그림과 같다.

여기서 사용자(브라우저)가 **‘클라이언트’**, 웹 서버 (Nginx)로 박스쳐져 있는 부분이 모두 **‘서버’**이다.

- **웹 서버 (Nginx)**는
    - 정적 요청이라면 직접 응답하고,
    - 동적 요청은 WSGI 서버에 전달한다.

- **WSGI 서버 (Gunicorn)**는
    - HTTP 요청을 받아 WSGI에 맞춰 데이터를 가공한 뒤,
    - WSGI 애플리케이션 (Django 코드)을 품고 있는 워커 프로세스에게 일을 분배(지시)한다.
    - Django 앱이 실행될 수 있는 환경을 제공한다.
    
- **WSGI 애플리케이션 (Django)**은
    - 작성된 Django 코드를 통해 로직을 수행하여
    - 응답을 생성하고, 반환한다.

![클라이언트 요청 - 서버 응답 흐름](/assets/img/posts/2025-11-06-client-server/1.jpeg)
*클라이언트 요청 - 서버 응답 흐름*


---

### 레퍼런스

[PEP 3333 - Python Web Server Gateway Interface v1.0.1](https://peps.python.org/pep-3333/)

[Nginx와 Gunicorn 둘 중 하나만 써도 될까?](https://velog.io/@jimin_lee/Nginx%EC%99%80-Gunicorn-%EB%91%98-%EC%A4%91-%ED%95%98%EB%82%98%EB%A7%8C-%EC%8D%A8%EB%8F%84-%EB%90%A0%EA%B9%8C)

[Django에서 초기화 과정 살펴보기](https://hann2a.tistory.com/20)

[asgi.py와 wsgi.py 이제는 이해하지](https://hann2a.tistory.com/19)