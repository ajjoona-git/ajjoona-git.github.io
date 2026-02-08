---
title: "[둥지] Docker 환경 분리와 보안 전략: Multi-stage Build부터 Secrets 관리까지"
date: 2026-02-08 09:00:00 +0900
categories: [Projects, 둥지]
tags: [Docker, DockerCompose, DevOps, Security, Makefile, MultiStageBuild, Secrets, Python]
description: "Docker 이미지를 경량화하기 위한 Multi-stage Build 전략과 Non-root User 설정, Docker Compose Override 패턴을 이용한 개발/운영 환경 분리 과정을 공유합니다. 또한 Makefile을 통한 명령어 관리와 Docker Secrets를 활용한 안전한 시크릿 관리법을 다룹니다."
---

이번 포스트에서는 **Docker를 활용한 환경 분리**, **보안을 고려한 시크릿 관리** 전략을 공유합니다.

---

## 1. Dockerfile 전략: 보안과 최적화의 균형

처음엔 `FROM python:3.12`로 시작했지만, 운영 환경을 고려하니 두 가지 문제가 보였습니다. **이미지 용량**과 **보안**입니다.

`deploy/Dockerfile`에 두 가지 핵심 전략을 적용했습니다.

### ① Multi-stage Build

*“Docker 이미지를 최대한 가볍게 만들고 싶어요”*

`uv` 같은 빌드 도구나 컴파일러는 이미지를 빌드할 때만 필요하고, 실행할 땐 필요 없습니다. 그래서 **빌드하는 단계(Builder)**와 **실행하는 단계(Runner)**를 물리적으로 나눴습니다.

```Dockerfile
# Stage 1: Builder (무거움 - 컴파일러, 빌드 도구 포함)
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
RUN uv sync --frozen --no-dev  # 의존성 설치

# Stage 2: Runner (가벼움 - 순수 런타임)
FROM python:3.12-slim AS runner
COPY --from=builder /app/.venv /app/.venv  # 설치된 패키지만 쏙 가져옴
```

결과적으로 운영 이미지는 불필요한 파일 없이, 순수하게 Python 런타임과 라이브러리만 남겨 가볍게 유지할 수 있습니다.

### ② Non-root User

컨테이너가 루트(Root) 권한을 가지면, 만약 해킹당했을 때 호스트 시스템까지 위험해질 수 있습니다.

```Dockerfile
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser
```

`appuser`라는 권한 없는 유저를 생성하여 애플리케이션을 실행함으로써, 만약의 보안 사고 시 피해 범위를 최소화했습니다.

## 2. Docker Compose 전략: 환경의 완벽한 분리

로컬 개발 환경과 운영 환경은 요구사항이 정반대입니다.

- **로컬:** 코드를 고치면 바로 반영(Hot Reload)돼야 하고, DB도 도커로 띄워야 편합니다.
- **운영:** 코드가 변하면 안 되고(Immutable), DB도 AWS RDS 같은 관리형 서비스를 써야 합니다.

이를 파일 하나로 관리하면 조건문과 주석으로 코드가 지저분해집니다. 우리는 **Override(덮어쓰기) 패턴**을 이용해 3단 분리했습니다.

### 3단 분리 (Base - Dev - Prod)

`docker-compose` 파일을 역할별로 나누어 관리합니다.

1. **`docker-compose.yml` (Base):** 공통 뼈대. (이미지 이름, 네트워크 설정 등)
2. **`docker-compose.dev.yml` (Dev):**
    - **Volumes:** 로컬 소스 코드를 마운트하여 수정 사항 즉시 반영.
    - **Services:** 로컬용 DB(Postgres)와 Redis 컨테이너 실행.
3. **`docker-compose.prod.yml` (Prod):**
    - **No Volumes:** 코드를 마운트하지 않고 빌드된 이미지를 그대로 사용.
    - **External Links:** DB와 Redis 컨테이너를 띄우지 않고, AWS RDS/ElastiCache 주소를 환경변수로 주입.
    - **Resources:** CPU/Memory 제한 설정 (서버 폭주 방지).

### Makefile

파일을 쪼개면 실행 명령어가 너무 길어지는 단점이 있습니다. 

이 복잡함을 해결하기 위해 **Makefile**을 도입했습니다. Makefile은 긴 도커 명령어를 `make up`이라는 짧은 단축키(Target)로 매핑해줍니다.

```makefile
# Makefile 예시
COMPOSE_BASE = -f deploy/docker-compose.yml
COMPOSE_DEV  = -f deploy/docker-compose.dev.yml
COMPOSE_PROD = -f deploy/docker-compose.prod.yml

# 개발 환경 실행 (Base + Dev 설정을 합쳐서 실행)
up:
	docker compose $(COMPOSE_BASE) $(COMPOSE_DEV) up -d --build

# 운영 환경 실행 (Base + Prod 설정을 합쳐서 실행)
up-prod:
	docker compose $(COMPOSE_BASE) $(COMPOSE_PROD) up -d --build
```

이제 개발자는 복잡한 플래그를 몰라도, **`make up`**만 입력하면 됩니다.

## 3. 시크릿 관리: `.env`를 넘어서

보안의 핵심은 **비밀번호를 어디에 두느냐**입니다.

*"`.env` 파일에 비밀번호를 넣으면 `docker inspect` 명령어로 환경변수를 까봤을 때 비밀번호가 평문으로 다 보여요."*

개발 편의성과 운영 보안 사이의 트레이드오프를 해결하기 위해 하이브리드 방식을 택했습니다.

### ① 개발 환경 (.env): "편의성 우선"

로컬에서는 보안 위협이 적으므로 `.env` 파일에 비밀번호를 적고 환경변수(`ENV_VAR`)로 주입합니다. 개발 속도를 위해 타협한 것입니다.

그리고 개발 환경과 운영 환경에서 사용하는 `.env`파일을 구분했습니다. `.env`는 개발용, `.env.prod`는 운영용으로 사용합니다.

### ② 운영 환경 (secrets/): "보안 우선"

운영 서버에서는 **Docker Secrets** 방식을 사용합니다. 이는 환경변수 주입이 아니라 **"파일 마운트"** 방식입니다.

1. **파일 생성:** 서버의 `secrets/` 폴더에 `db_password.txt` 파일을 만들고 비밀번호를 적습니다.
2. **마운트:** `docker-compose.prod.yml`에서 이 파일을 컨테이너 내부의 `/run/secrets/db_password` 경로로 연결합니다.
3. **읽기 권한 제어:** `mode: 0400` 설정을 통해 오직 컨테이너 소유자만 읽을 수 있게 제한합니다.

```yaml
# docker-compose.prod.yml
secrets:
  db_password:
    file: ../secrets/db_password.txt  # 호스트의 파일
services:
  app:
    secrets:
      - source: db_password
        target: db_password           # 컨테이너 내부 /run/secrets/db_password 로 연결
```

이렇게 하면 해커가 `docker inspect`로 컨테이너 설정을 훔쳐봐도 비밀번호는 보이지 않습니다. 애플리케이션은 환경변수가 아닌 **"파일을 읽어서"** 비밀번호를 가져옵니다.

---

## 마치며

이제 **"로컬에서 편하게 개발하고(`make up`), 서버에선 안전하게 배포하며(`make up-prod`), 비용은 최소화한"** 시스템을 갖추었습니다.

마지막으로 이 모든 고민이 담긴 최종 폴더 구조를 공개합니다.

### 최최종(아마도) 둥지 백엔드 폴더 구조

```
doongzi-backend/
├── 📂 app/                  # [소스 코드]
│   ├── main.py
│   ├── core/
│   └── ...
├── 📂 tests/                # [테스트 코드] (app과 분리)
│   ├── conftest.py
│   ├── test_main.py          # (Pytest) 자동화 테스트 코드
│   └── api.http              # (Http Client) 수동 테스트 명세서
├── 📂 deploy/               # [인프라 설정] (여기로 이사옴!)
│   ├── Dockerfile              # (멀티 스테이지 적용됨)
│   ├── docker-compose.yml      # (Base: 공통)
│   ├── docker-compose.dev.yml  # (Local: 개발용 Override)
│   └── docker-compose.prod.yml # (Prod: 운영용 Override)
├── .env                      # [dev] 모든 설정 + 비밀번호 포함
├── .env.prod                 # [prod] 비밀번호 뺀 껍데기 설정
├── .env.example              # [git] 깃허브에 올라가는 예시 파일
├── 📂 secrets/              # [prod] 비밀번호 파일 폴더
│   └── db_password.txt
├── 📂 secrets.example/      # [git] 깃허브에 올라가는 예시 파일
│   └── db_password.txt
├── .gitignore
├── .dockerignore
├── Makefile                 # [실행 단축키] (필수!)
├── pyproject.toml           # [New] 모든 의존성 및 툴 설정
└── uv.lock                  # [New] 버전 잠금 파일 (자동 생성)

```