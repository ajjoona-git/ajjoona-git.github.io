---
title: "[둥지] 서비스 런칭을 위한 리팩토링: 하이브리드 클라우드 아키텍처와 기술 스택 선정의 이유"
date: 2026-01-25 09:00:00 +0900
categories: [Projects, 둥지]
tags: [Architecture, FastAPI, React, AWS, HybridCloud, Celery, Redis, Refactoring, RDS, AdapterPattern, ProxyPattern]
toc: true
comments: true
image: /assets/img/posts/2026-01-25-doongzi-refactoring-architecture-tech-stack/1.png
description: "둥지 프로젝트의 서비스화를 위해 AWS 프리티어의 한계를 극복하는 하이브리드 클라우드(AWS + Home PC) 아키텍처를 설계했습니다. FastAPI, React, RDS, Redis 등을 선정한 구체적인 이유와 도메인 주도 폴더 구조 설계를 공유합니다."
---

해커톤으로 시작했던 '둥지' 프로젝트를 실제 서비스로 런칭하기 위해 대대적인 **리팩토링**을 결정했다.
4인 팀, 1개월이라는 짧은 기간, 그리고 AWS 프리티어(`t3.micro`)라는 제약 속에서 고비용의 AI 연산 기능을 안정적으로 제공해야 한다.

이번 포스트에서는 이러한 제약 조건을 극복하기 위해 설계한 **'실용주의 아키텍처'**와 각 기술 스택의 선정 이유를 정리해 본다.

---

## 현재 상황은...

일단은 개강 시즌인 3월 전후를 노려 최대한 빨리 서비스를 배포하고, 실사용자 반응을 보기로 결정했다.
그래서 **빠른 개발**을 목표로 1차 MVP 개발을 계획하고 있다.

다음과 같은 3가지 원칙을 세웠다.

1.  **Time-Boxing:** 1개월 내에 핵심 기능(체크리스트와 자동화 액션)을 완성한다.
2.  **Cost-Efficiency:** AWS 비용을 최소화하되, AI 연산 비용은 0원으로 만든다. (집 컴퓨터 활용)
3.  **Stability:** 메모리가 1GB뿐인 `t3.micro` 서버가 죽지 않도록 **철저한 리소스 분리(Decoupling)**를 적용한다.


## 기술 스택 선정 및 사유

### ① Backend: FastAPI (Python)
처음에는 앱 서비스를 고려했었다. 그치만 문서 발급이나 업로드가 많은 사용자 경험과 앱 서비스 개발 경험이 없다는 점을 고려했을 때 반응형 웹 서비스 형태가 더 적절할 것이라고 판단했다.

SpringBoot(Java)와 Django(Python), FastAPI(Python)이 후보였다. 팀원 모두가 Python에 익숙하기도 했고 체크리스트 자동화 액션의 비동기 처리가 중요하기 때문에 최종적으로 FastAPI를 선택했다.

**선정 이유:**
* **AI 친화적:** Python 기반이라 AI 라이브러리 연동 및 데이터 전처리가 가장 자연스럽다.
* **비동기 성능:** `async/await`를 기본 지원하여, I/O 작업(DB 조회, 외부 API 호출) 시 동시 처리 능력이 탁월하다.
* **생산성:** Pydantic을 이용한 자동 검증과 Swagger 문서 자동 생성 덕분에 프론트엔드 팀과의 협업 비용이 획기적으로 줄어든다.
* *Tip:* Django Admin의 부재는 **`SQLAdmin`** 라이브러리를 도입하여 빠르게 해결할 예정.

### ② Frontend: React (Vite + TypeScript)
이전에 사용했던 React 파일을 사용하되, 체크리스트 위주의 MVP를 고려하여 수정하는 방향으로 결정했다.

**선정 이유:**
* **생산성:** Vite 번들러를 도입하여 빌드 및 개발 서버 구동 속도를 극대화했다.
* **안정성:** TypeScript를 필수로 도입하여 런타임 에러를 사전에 방지했다.

### ③ Database: AWS RDS (PostgreSQL)
**선정 이유 (핵심):**
* **리소스 분리:** 웹 서버(EC2)의 메모리가 1GB에 불과하다. 여기에 DB까지 띄우면 서버는 100% 뻗는다. 따라서 DB를 관리형 서비스(RDS)로 분리했다.
* **ID 체계:** 보안상 유추가 불가능한 **`UUID`**를 PK로 사용하여 데이터 무결성과 보안을 강화한다.
* **JSON 지원:** AI 분석 결과(JSON 형태)를 저장하고 쿼리하기에 PostgreSQL이 유리하다.

### ④ Infrastructure: Hybrid Cloud (AWS + Home PC)
비용과 성능의 딜레마를 해결하기 위한 **'신의 한 수'**!

* **AWS EC2 (Web Server):** 24시간 가동되는 웹 서버와 Redis만 호스팅한다. `t3.micro`의 부족한 메모리는 **Swap Memory 2GB** 설정으로 방어한다.
* **Home PC (AI Worker):** 집에 있는 고성능 데스크탑(GPU)을 활용한다. 클라우드 GPU 비용 부담을 줄였다.
    * *동작 원리:* 집 컴퓨터가 AWS의 Redis를 구독(Subscribe)하고 있다가, 작업이 들어오면 가져가서 처리한다. (Pull 방식이라 복잡한 네트워크 설정 불필요)

### ⑤ Async & Queue: Redis + Celery
FastAPI가 비동기 작업에 최적화되어있다고 하지만, 결국에 Single Thread이기 때문에 동시에 100건 이상의 요청이 들어온다면 감당하기 힘들 것이다.
사용자가 몰려도 요청을 받아서 서버가 감당할 수 있을 정도로 일을 분배해주는 역할이 필요했다. Message Queue가 그런 역할을 한다. 그중에서도 Kafka는 우리 서비스에 오버 스펙이기 때문에 너무 무거울 것이라 판단했고, 최종적으로 Redis를 선택했다.

**선정 이유:**
* **트래픽 제어 (Dam Effect):** 사용자가 몰려도 Redis가 댐 역할을 하여 요청을 쌓아두고, AI 워커가 감당할 수 있는 속도로 처리하게 만들어 서버 폭주를 막는다.
* **사용자 경험:** 웹 서버(FastAPI)는 요청만 받고 즉시 응답하며, 무거운 작업은 백그라운드에서 처리된다.


## 아키텍처 설계

![system architecture diagram](/assets/img/posts/2026-01-25-doongzi-refactoring-architecture-tech-stack/1.png)
*system architecture diagram*


## Backend (FastAPI) 폴더 구조

도메인 주도 설계(DDD)에서 착안했다. 기능별로 폴더를 격리하여 유지보수성을 높였다.


```
doongzi-backend/
├── .env                  # [보안] DB_URL, REDIS_URL, API_KEYS
├── docker-compose.yml    # [배포] FastAPI + Redis + Nginx 실행 명세
└── app/
    ├── main.py           # 앱 진입점
    ├── core/             # 공통 설정 (Config, Security)
    ├── db/               # DB 세션 관리
    ├── models/           # ★ DB 테이블 정의 (순환 참조 방지)
    │   ├── user.py
    │   └── checklist.py
    │
    └── domains/          # ★ 핵심 비즈니스 로직 (도메인별 분리)
        ├── auth/
        │   ├── router.py 
        │   ├── service.py 
        │   └── schemas.py
        │
        ├── checklist/
        │   ├── router.py      # API 엔드포인트
        │   ├── service.py     # 비즈니스 로직
        │   ├── schemas.py     # 입출력 DTO (Pydantic)
        │   ├── ai_client.py   # AI 통신 대리자 (Adapter Pattern)
        │   └── tasks.py       # Celery 워커가 실행할 코드
        │
```

### `ai_client.py`

이 파일의 역할은 "복잡한 HTTP 통신 코드를 감춰주고(Wrapping), 서비스 로직(service.py)이 편하게 AI를 부려먹을 수 있게 해주는 대리인"이다. 
이 패턴을 **[Adapter Pattern]** 또는 **[Proxy Pattern]**이라고 부른다.


---

### 레퍼런스

[FastAPI 공식 문서](https://fastapi.tiangolo.com/ko/)

[프록시(Proxy) 패턴 - 완벽 마스터하기](https://inpa.tistory.com/entry/GOF-%F0%9F%92%A0-%ED%94%84%EB%A1%9D%EC%8B%9CProxy-%ED%8C%A8%ED%84%B4-%EC%A0%9C%EB%8C%80%EB%A1%9C-%EB%B0%B0%EC%9B%8C%EB%B3%B4%EC%9E%90#%ED%94%84%EB%A1%9D%EC%8B%9C_%ED%8C%A8%ED%84%B4_%EA%B5%AC%EC%A1%B0)

[어댑터(Adaptor) 패턴 - 완벽 마스터하기](https://inpa.tistory.com/entry/GOF-%F0%9F%92%A0-%EC%96%B4%EB%8C%91%ED%84%B0Adaptor-%ED%8C%A8%ED%84%B4-%EC%A0%9C%EB%8C%80%EB%A1%9C-%EB%B0%B0%EC%9B%8C%EB%B3%B4%EC%9E%90)