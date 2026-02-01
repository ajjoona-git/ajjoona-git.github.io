---
title: "Docker Compose로 완벽한 로컬 개발 환경 구축하기 (Healthcheck, Resource Limit, YAML Anchor)"
date: 2026-02-01 09:00:00 +0900
categories: [Tech, DevOps]
tags: [Docker, DockerCompose, DevOps, FastAPI, Redis, PostgreSQL, Celery, Infrastructure, Healthcheck]
toc: true
comments: true
description: "다중 컨테이너 애플리케이션을 정의하는 Docker Compose의 핵심 전략을 정리합니다. DB 연결 오류를 막는 Healthcheck, 시스템 멈춤을 방지하는 Resource Limit, 그리고 설정 중복을 줄이는 YAML Anchor 활용법을 상세히 다룹니다."
---

`Dockerfile`이 악기 하나를 만드는 설계도라면, **`docker-compose.yml`**은 그 악기들이 모여 어떻게 합주할지를 정하는 **지휘 악보**와 같다.

단일 서버라면 Docker 명령어만으로 충분하지만, **둥지(Doongzi)** 프로젝트처럼 Web Server, Worker, Database, Cache가 서로 통신해야 하는 환경에서는 **Docker Compose**가 필수적이다.

---

## Dockerfile vs Docker Compose

"Dockerfile이 있는데 왜 Compose가 또 필요한가요?"

| 구분 | **Dockerfile** | **docker-compose.yml** |
| :--- | :--- | :--- |
| **목적** | 이미지(Image) **생성** (Build) | 컨테이너(Container) **실행 & 연결** (Run) |
| **대상** | 단일 프로그램 (예: FastAPI 서버 1개) | 전체 시스템 (FastAPI + DB + Redis + Worker) |
| **역할** | OS 설치, 라이브러리 설치, 코드 복사 | 포트 포워딩, 볼륨 연결, 실행 순서 제어, 환경변수 주입 |
| **명령어** | `docker build` | `docker compose up` |

### 언제 무엇을 쓰는가?
* **남이 만든 프로그램 (DB, Redis)**은 Dockerfile 없이 `image: postgres` 처럼 바로 가져와서 Compose에 적는다.
* **내가 만든 프로그램 (FastAPI)**은 Dockerfile을 작성하고, Compose에서 `build: .`으로 불러온다.

| **구분** | **Dockerfile 없음 (image 사용)** | **Dockerfile 있음 (build 사용)** |
| --- | --- | --- |
| **대상** | 남이 만든 프로그램 (DB, Redis, Nginx) | **내가 만든 프로그램 (FastAPI 서버)** |
| **방식** | 다운로드 → 실행 | **소스코드 복사 → 라이브러리 설치 → 실행** |


## doongzi의 `docker-compose.yml`

다음은 **FastAPI(App) + Celery(Worker) + PostgreSQL(DB) + Redis**를 한 번에 띄우는 설정 파일이다. 꼭 챙겨야 할 **3가지 핵심 전략**이 녹아 있다.

```yaml
name: doongzi-backend

# [전략 3] YAML Anchor: 공통 환경변수 설정 재사용
x-common-env: &common-env
  env_file:
    - .env

services:
  # [1] Database
  db:
    image: postgres:15-alpine
    container_name: doongzi-db
    restart: always
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # [전략 1] Healthcheck: DB가 진짜 준비됐는지 확인
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M

  # [2] Redis
  redis:
    image: redis:7-alpine
    container_name: doongzi-redis
    restart: always
    ports:
      - "6379:6379"
    command: redis-server --requirepass "${REDIS_PASSWORD}"
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M

  # [3] FastAPI App
  app:
    build: .
    container_name: doongzi-api
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    <<: *common-env  # 공통 환경변수 주입
    depends_on:
      db:
        condition: service_healthy # DB가 건강해질 때까지 대기
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: '1.5'
          memory: 1G

  # [4] Celery Worker
  worker:
    build: .
    container_name: doongzi-worker
    command: celery -A app.core.celery_app worker --loglevel=info
    <<: *common-env
    depends_on:
      redis:
        condition: service_healthy
      app:
        condition: service_started
    # [전략 2] Resource Limits: AI 연산을 위한 자원 격리
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G

volumes:
  postgres_data:

```


## 전략 상세 분석
### ① 헬스체크 & 의존성 전략 (`healthcheck` + `depends_on`)
보통 `depends_on: - db`만 사용한다. 하지만 이건 **"DB 컨테이너가 켜졌니?"**만 확인한다. DB 프로세스는 켜졌어도 내부 초기화에 시간이 걸리는데, 이때 API 서버가 접속을 시도하면 "Connection Refused" 에러로 죽어버린다.

그래서 아래와 같은 전략을 사용했다.

1. **Healthcheck:** DB 컨테이너에게 pg_isready 명령어로 스스로 건강검진을 하게 시킨다.

2. **Service Healthy:** API 서버는 `condition: service_healthy` 옵션을 통해 DB가 **연결 가능 상태**가 될 때까지 기다렸다가 시작한다. 재부팅 시 발생하는 레이스 컨디션(Race Condition)을 방지한다.

### ② 리소스 격리 전략 (`limits`)
Docker는 기본적으로 호스트 머신의 자원을 무제한으로 끌어다 쓴다. 만약 AI Worker가 메모리 누수로 32GB를 다 써버리면 개발자 컴퓨터 전체가 멈춘다.

이를 방지하기 위해 `deploy.resources.limits`를 사용하여 **Hard Limit**을 건다.

- **App (API):** 비동기 처리가 많으므로 CPU 위주 할당.
- **Worker (AI):** OCR/LLM 모델 로딩을 위해 RAM 위주 할당.

설정된 한도를 넘으면 Docker가 해당 컨테이너만 강제로 종료(OOM Killed)시켜, 내 컴퓨터를 보호한다.

### ③ YAML 앵커 전략 (`x-common-env`)
App 컨테이너와 Worker 컨테이너는 같은 코드를 공유하므로 환경변수(`.env`) 설정도 똑같다. 하지만 각각 `env_file:`을 적어주면 중복이 발생하고, 실수하기 쉽다.

프로그래밍의 변수처럼 `x-common-env`로 공통 설정을 정의(`&common-env`)하고, 필요한 곳에서 `<<: *common-env`로 불러와 덮어씌운다. **DRY(Don't Repeat Yourself)** 원칙을 YAML에도 적용한 것이다.

---

## 마치며
이제 복잡한 설치 과정 없이 다음 명령어 하나면 로컬 개발 환경이 완성된다.

```Bash
docker compose up
```

---

### 레퍼런스

- [Docker Documentation - Docker Compose](https://docs.docker.com/compose/)
- [NHN Cloud Meetup - Docker Compose와 버전별 특징 : NHN Cloud Meetup](https://meetup.nhncloud.com/posts/277/)
- [islove8587 - [Docker] docker-compose.yml 파일 구성 알아보기](https://m.blog.naver.com/islove8587/223443300022)
