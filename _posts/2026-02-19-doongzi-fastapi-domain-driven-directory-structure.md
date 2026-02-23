---
title: "[둥지] FastAPI 백엔드 폴더 구조 설계: 도메인 기반 아키텍처(DDD)"
date: 2026-02-19 11:00:00 +0900
categories: [Projects, 둥지]
tags: [FastAPI, Python, Architecture, DDD, Backend, DirectoryStructure, Docker]
toc: true
comments: true
description: "둥지 프로젝트의 FastAPI 백엔드 폴더 구조 설계 과정을 공유합니다. 레이어드 아키텍처와 도메인 기반 아키텍처 사이의 고민, 도메인 비대화 해결 방안, 공통 모듈 및 환경 설정 파일의 분리 전략을 상세히 다룹니다."
---

백엔드 프로젝트를 시작할 때 가장 먼저 고민하게 되는 것 중 하나가 바로 폴더 구조입니다. 
특히 팀 프로젝트에서는 코드 충돌을 최소화하고, 각자 맡은 기능을 독립적으로 개발할 수 있는 구조가 필요합니다. 
이번 포스트에서는 둥지 프로젝트의 백엔드 폴더 구조를 설계하면서 겪었던 고민과 최종 결정 사항을 공유합니다.

---

## 아키텍처 선택: 레이어드 vs 도메인 기반

가장 고민이 깊었던 곳은 실제 비즈니스 로직이 담기는 `app/` 폴더 내부입니다. 처음에는 흔히 쓰이는 MVC 패턴이나 레이어드 아키텍처(`routers/`, `services/`, `schemas/`를 폴더로 나누는 방식)를 고려했습니다.

### 레이어드 아키텍처 (Layered Architecture)

전통적인 MVC 패턴이나 레이어드 아키텍처는 `routers/`, `services/`, `schemas/`처럼 기능별로 폴더를 나누는 방식입니다.

**장점:**

- 구조가 직관적이고 이해하기 쉬움
- 작은 규모의 프로젝트에서 빠르게 시작 가능

**단점:**

- 프로젝트가 커질수록 각 폴더 내 파일이 많아져 관리가 어려움
- 기능별로 여러 폴더를 오가며 코드를 수정해야 함
- 팀원 간 코드 충돌 가능성이 높음

### 도메인 기반 아키텍처 (Domain-Driven Architecture)

도메인별로 폴더를 나누고, 각 도메인 내에 필요한 `router.py`, `service.py`, `schemas.py`를 배치하는 방식입니다.

**장점:**

- 기능별 응집도가 높아 관련 코드를 한 곳에서 관리 가능
- 팀원 간 코드 충돌 최소화 (각자 다른 도메인 담당)
- 확장성이 좋아 새로운 기능 추가 시 독립적으로 작업 가능

**단점:**

- 초기 구조 설계에 고민이 필요
- 도메인 간 의존성 관리가 복잡할 수 있음

### 최종 선택: 도메인 기반 아키텍처

둥지 프로젝트는 체크리스트, 인증, 프로필 등 여러 도메인으로 구성되어 있고, 각 도메인이 독립적으로 기능을 제공합니다. 또한 팀원 간 충돌을 방지하고 병렬 개발을 원활하게 하기 위해 **도메인 기반 아키텍처**를 선택했습니다.

## 주요 고민 사항

### 1. 체크리스트 도메인의 비대화 문제

도메인 기반으로 폴더를 나누고 나니, 실무적인 차원에서 몇 가지 설계 딜레마에 봉착했습니다. 가장 큰 문제는 **특정 도메인이 너무 뚱뚱**해지는 것입니다. 체크리스트 도메인은 다양한 자동화 액션을 포함하고 있어, 단일 도메인으로 관리하기에는 너무 커질 것 같다는 우려가 있었습니다. 

**고려했던 방안:**

1. **체크리스트를 하나의 도메인으로 유지:** 내부적으로 `services/` 폴더를 만들어 기능별로 분리
2. **자동화 액션을 별도의 도메인으로 분리:** 각 액션을 독립적인 도메인으로 관리

예를 들어, "등기부등본 분석" 기능은 계약 전/중/후 단계에서 모두 사용되지만 서비스 로직은 동일합니다. 이런 경우를 생각해볼 때 체크리스트를 하나의 도메인으로 두는 것보다 각각의 자동화 액션을 별개의 도메인으로 분리해야하나 고민했습니다. 하지만 자동화 액션과 체크리스트가 동일한 depth로 간주될 수 있어 부적절하다고 판단했습니다.

**최종 결정:**

초기에는 체크리스트를 하나의 도메인으로 유지하되, `services/` 서브폴더를 두어 기능별로 서비스 로직을 분리하기로 했습니다. 프로젝트가 진행되면서 필요하다면 점진적으로 별도 도메인으로 분리할 수 있습니다.

### 2. 공통 모듈 (Enums, Utils) 배치

여러 도메인에서 공통적으로 사용하는 기능(예: 주소 API), 체크리스트 도메인 내부에서도 여러 항목에서 공통적으로 사용하는 기능 (예: 시세 조회)과 Enums를 어디에 배치할지 고민했습니다.

**고려했던 방안:**

- **도메인 내부 배치:** 특정 도메인에서만 사용되는 경우 해당 도메인의 `utils/` 폴더에 배치
- **공통 모듈로 분리:** 여러 도메인에서 사용되는 경우 `core/` 또는 별도의 공통 폴더로 분리

**최종 결정:**

- **Enums:** DB 모델과 밀접한 관계가 있으므로 `models/enums.py`에 배치. 비즈니스 로직에서 자주 사용되는 상수는 `core/constants.py`로 분리
- **공통 Utils:** 초기에는 도메인 내부에 배치하고, 2개 이상의 도메인에서 사용되면 `core/`로 이동

### 3. DB 모델의 중앙 관리

순환 참조(Circular Import) 문제를 방지하기 위해 모든 DB 모델 정의는 `models/` 폴더에 중앙 집중화했습니다. 각 도메인에서는 이 모델을 import하여 사용합니다.

## 최종 결정 사항

현재 구조는 다음과 같은 원칙을 따릅니다:

1. **도메인 우선:** 각 도메인은 `router.py`, `service.py`, `schemas.py`를 기본으로 가지며, 필요시 `services/`, `utils/` 서브폴더로 확장
2. **공통 레이어 명확화:** DB 모델은 `models/`에, 설정은 `core/`에, 세션 관리는 `db/`에 배치
3. **점진적 리팩토링:** 초기에는 단순한 구조로 시작하되, 도메인이 복잡해지면 서브모듈로 분리하는 점진적 접근

### app/ 폴더 구조

```
└── 📂 app/
    ├── __init__.py
    ├── main.py             # 전체 앱 실행
    ├── core/               # [공통] 환경 설정, Celery/Redis 연결
    │   ├── __init__.py
    │   ├── config.py       # 환경 변수 (Pydantic Settings)
    │   ├── constants.py    # 비즈니스 상수
    │   └── celery_app.py   # Celery & Redis 연결 설정
    ├── db/                 # [공통] DB 세션 관리, SessionLocal
    │   ├── __init__.py
    │   └── session.py
    ├── models/             # [공통] ★ DB 테이블 정의
    │   ├── __init__.py     # 모든 모델 import
    │   ├── base.py
    │   ├── enums.py
    │
    └── domains/
        ├── auth/
        │   ├── router.py
        │   ├── service.py
        │   └── schemas.py
        │
        ├── checklist/
        │   ├── router.py      # API URL 정의
        │   ├── 📂 services/   # 비즈니스 로직
        │   ├── schemas.py     # Pydantic (입출력 DTO)
        │   └── 📂 utils/      # 공통 모듈
        │
        └── profile/
            ├── router.py
            ├── service.py
            └── schemas.py
```

### 환경별 설정 파일

개발 환경별로 다른 설정을 관리하기 위해 Docker Compose를 활용한 멀티 스테이지 빌드를 적용했습니다.

```
├── .env.local                # [local] 로컬 개발 시 사용
├── .env.dev                  # [dev] 모든 설정 + 비밀번호 포함
├── .env.prod                 # [prod] 비밀번호 뺀 껍데기 설정
├── .env.example              # [git] 깃허브에 올라가는 예시 파일
├── 📂 secrets/              # [prod] 비밀번호 파일 폴더
│   └── db_password.txt
├── 📂 secrets.example/      # [git] 깃허브에 올라가는 예시 파일
│   └── db_password.txt
```

- `.env.local`: 로컬 개발 환경
- `.env.dev`: 개발 서버 (모든 설정 포함)
- `.env.prod`: 프로덕션 서버 (비밀번호는 별도 파일로 분리)
- `secrets/`: 프로덕션 환경의 민감한 정보 저장 (Docker Secrets)

### Docker Compose 구성

```
├── 📂 deploy/                     # [인프라 설정]
│   ├── Dockerfile                 
│   ├── docker-compose.yml         # (Base: 공통)
│   ├── docker-compose.local.yml   # (Local: local 개발용 Override)
│   └── docker-compose.cloud.yml   # (Cloud: dev/prod용 Override)
```

- `docker-compose.yml`: 기본 공통 설정
- `docker-compose.local.yml`: 로컬 개발용 오버라이드
- `docker-compose.cloud.yml`: 클라우드(dev/prod)용 오버라이드

---

## 마치며

백엔드 폴더 구조 설계는 정답이 없습니다. 프로젝트의 규모, 팀 구성, 개발 방식에 따라 최적의 구조는 달라질 수 있습니다. 
중요한 것은 **초기에는 단순하게 시작하되, 프로젝트가 성장하면서 점진적으로 리팩토링**하는 것입니다.

### 최최최종 폴더 구조

```
doongzi-backend/
├── 📂 tests/                # [테스트 코드]
│   ├── conftest.py
│   ├── test_main.py          # (Pytest) 자동화 테스트 코드
│   └── api.http              # (Http Client) 수동 테스트 명세서
├── 📂 deploy/                   # [인프라 설정]
│   ├── Dockerfile                # (멀티 스테이지 적용됨)
│   ├── docker-compose.yml        # (Base: 공통)
│   ├── docker-compose.local.yml  # (Local: local 개발용 Override)
│   └── docker-compose.cloud.yml  # (Cloud: dev/prod용 Override)
├── .env.local                # [local] 로컬 개발 시 사용
├── .env.dev                  # [dev] 모든 설정 + 비밀번호 포함
├── .env.prod                 # [prod] 비밀번호 뺀 껍데기 설정
├── .env.example              # [git] 깃허브에 올라가는 예시 파일
├── 📂 secrets/              # [prod] 비밀번호 파일 폴더
│   └── db_password.txt
├── 📂 secrets.example/      # [git] 깃허브에 올라가는 예시 파일
│   └── db_password.txt
├── .gitignore
├── .dockerignore
├── Makefile                 # [실행 단축키]
├── pyproject.toml           # 모든 의존성 및 툴 설정 (자동 생성)
├── uv.lock                  # 버전 잠금 파일 (자동 생성)
└── 📂 app/
    ├── __init__.py
    ├── main.py             # 전체 앱 실행
    ├── core/               # [공통] 환경 설정, Celery/Redis 연결
    │   ├── __init__.py
    │   ├── config.py       # 환경 변수 (Pydantic Settings)
    │   ├── constants.py    # 비즈니스 상수
    │   └── celery_app.py   # Celery & Redis 연결 설정
    ├── db/                 # [공통] DB 세션 관리, SessionLocal
    │   ├── __init__.py
    │   └── session.py
    ├── models/             # [공통] ★ DB 테이블 정의
    │   ├── __init__.py     # 모든 모델 import
    │   ├── base.py
    │   ├── enums.py
    │
    └── domains/
        ├── auth/
        │   ├── router.py
        │   ├── service.py
        │   └── schemas.py
        │
        ├── checklist/
        │   ├── router.py      # API URL 정의
        │   ├── 📂 services/   # 비즈니스 로직
        │   ├── schemas.py     # Pydantic (입출력 DTO)
        │   └── 📂 utils/      # 공통 모듈
        │
        └── profile/
            ├── router.py
            ├── service.py
            └── schemas.py
```