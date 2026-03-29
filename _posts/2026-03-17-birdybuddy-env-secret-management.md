---
title: "[허수아비] GitLab CI/CD 환경변수 관리 — .env를 이미지에 절대 넣지 않는 법"
date: 2026-03-17 09:00:00 +0900
categories: [Project, 허수아비]
tags: [GitLab, CI/CD, Docker, EnvironmentVariables, Security, EC2, DevOps]
toc: true
comments: true
image: /assets/img/posts/2026-03-17-birdybuddy-env-secret-management/1.png
description: "로컬, GitLab Runner, EC2 운영 환경별 .env 보안 관리 전략과, GitLab Variables File 타입을 활용해 .env를 이미지 없이 EC2에 자동 전달하는 방법을 정리합니다."
---

프로젝트에 민감한 정보가 생기는 순간, 자연스럽게 `.env` 파일을 만들게 됩니다. 그런데 막상 배포 단계가 되면 고민이 시작됩니다.

*"이 `.env` 파일을 Docker 이미지에 COPY해버리면 편한데, 그러면 안 되는 거 맞죠?"*

맞습니다. 이미지에 넣는 순간 Docker Hub에 올라가고, 팀원 모두가 `docker pull`로 받을 수 있고, `docker history`로도 내용이 노출될 수 있습니다. 허수아비 프로젝트에서는 이 문제를 환경별로 역할을 나눠서 해결했습니다.

---

## 환경별 정책, 한눈에 보기

먼저 어떤 환경에서 `.env`가 어떻게 관리되는지 전체 그림을 잡고 시작합니다.

| 환경 | `.env` 존재 여부 | 관리 방법 |
|---|---|---|
| 로컬 | ✅ 존재 | `.env.example` 복사 후 직접 작성 |
| GitLab 레포 | ❌ 없음 | `.env.example`만 템플릿으로 커밋 |
| CI (Runner) | ❌ 없음 | 인증 정보만 GitLab Variables에 등록 |
| EC2 (운영) | ✅ 존재 | GitLab Variables → CI deploy 잡이 자동 전송 |

핵심은 **GitLab 레포와 Docker 이미지 어디에도 `.env`가 포함되지 않는다**는 것입니다. 민감한 값은 항상 GitLab Variables에서 출발해 필요한 곳에만 도달합니다.

## 로컬에서는?

로컬 개발 환경은 가장 단순합니다. `.env.example`을 복사해서 쓰면 됩니다.

```bash
cp mock-radar/.env.example mock-radar/.env
cp data-pipeline/.env.example data-pipeline/.env
# 실제 값을 채운 후 docker compose up
```

`.env.example`은 키 목록과 형식만 담은 템플릿 파일로, 값은 비워두거나 더미값을 넣어 레포에 커밋합니다. `.env`는 `.gitignore`에 등록되어 있어 절대 레포에 올라가지 않습니다. 새 팀원이 합류해도 `.env.example`만 보면 어떤 값을 채워야 하는지 파악할 수 있습니다.

## GitLab CI에서 인증 정보를 어떻게 관리할까?

CI 파이프라인에서 Docker 이미지를 빌드하고 EC2에 배포하려면 외부 서비스에 접근하기 위한 인증 정보가 필요합니다. 이 값들은 GitLab의 **CI/CD Variables**에 등록해서 파이프라인이 실행될 때 자동으로 주입되도록 합니다.

| Key | 용도 |
|---|---|
| `DOCKER_HUB_USERNAME` | Docker Hub 이미지 push |
| `DOCKER_HUB_PASSWORD` | Docker Hub 이미지 push |
| `SSH_PRIVATE_KEY` | EC2 SSH 접속 |
| `EC2_USER` | EC2 SSH 접속 |
| `EC2_APP_HOST` | EC2 #2 (app 서버) 주소 |
| `EC2_DATA_HOST` | EC2 #1 (data 서버) 주소 |

> `docker build` 시에는 `.env`가 필요하지 않습니다. 이미지 빌드는 소스 코드와 의존성만으로 이루어지고, 환경변수는 컨테이너가 **실행될 때** 주입됩니다.

이 Variables들은 파이프라인 스크립트 안에서 `$DOCKER_HUB_USERNAME`처럼 환경변수로 참조할 수 있습니다. GitLab UI에서 "Masked" 옵션을 켜두면 파이프라인 로그에서도 값이 마스킹됩니다.

## EC2 운영 환경 — `.env`는 어떻게 전달될까?

### `.env`가 이미지에 포함되지 않는 이유

`docker-compose.yml`에서 `env_file` 옵션을 사용하면, `.env` 파일을 이미지에 굽지 않고 **컨테이너가 실행되는 시점에 주입**할 수 있습니다.

```yaml
# 안전한 방식 (현재 구조)
services:
  backend:
    image: ${REGISTRY_URL}:backend
    env_file: ../../backend/.env   # 실행 시 주입 — 이미지에는 포함되지 않음
```

이와 반대로 Dockerfile 안에서 `COPY .env ./`를 하는 경우, 해당 `.env` 파일의 내용이 이미지 레이어에 영구적으로 박힙니다. `docker history` 명령으로 레이어를 까보면 파일 내용이 그대로 노출될 수 있고, Docker Hub에 push하는 순간 누구든 pull해서 확인할 수 있게 됩니다.

```yaml
# 위험한 방식 (사용 금지)
# Dockerfile 내부에서
COPY .env ./   # ← 이미지에 .env가 포함됨
```

### GitLab Variables File 타입으로 EC2에 자동 전송

운영 환경의 EC2에는 `.env` 파일이 실제로 존재해야 합니다. 그런데 EC2에 직접 SSH 접속해서 파일을 만드는 방식은 수동 작업이고, 값이 바뀔 때마다 반복해야 합니다.

허수아비에서는 GitLab Variables의 **File 타입**을 활용해 이 문제를 해결했습니다. File 타입으로 등록된 Variable은 파이프라인 실행 시 CI Runner에 실제 파일로 마운트되고, 이 파일을 `scp`로 EC2에 전송하는 방식입니다.

| Variable 이름 | 타입 | EC2 전송 경로 |
|---|---|---|
| `ENV_EC2_DATA` | File | `~/birdybuddy/infra/ec2-data/.env` |
| `ENV_EC2_APP` | File | `~/birdybuddy/infra/ec2-app/.env` |
| `ENV_MOCK_RADAR` | File | `~/birdybuddy/mock-radar/.env` |
| `ENV_DATA_PIPELINE` | File | `~/birdybuddy/data-pipeline/.env` |

GitLab UI에서 Variable 값을 수정하고 파이프라인을 재실행하면, CI가 알아서 최신 `.env`를 EC2에 덮어씁니다. EC2에 직접 접속할 필요가 없습니다.

![GitLab Variables](/assets/img/posts/2026-03-17-birdybuddy-env-secret-management/1.png)
*GitLab Variables*

### `.env` 값을 바꿔야 할 때

절차가 단순합니다.

1. GitLab → Settings → CI/CD → Variables에서 해당 Variable 수정
2. 파이프라인 재실행 (또는 push 트리거)
3. CI의 setup 잡이 EC2에 최신 `.env` 파일을 자동으로 전송

인프라 담당자가 바뀌어도, EC2 접속 권한 없이 GitLab만으로 시크릿을 관리할 수 있다는 점도 장점입니다.

## 전체 배포 흐름

로컬에서 push 하나로 시작해 EC2에 배포되기까지의 흐름입니다.

```
로컬 PC
  └─ git push

      ↓

GitLab Runner (CI 서버)
  ├─ lint     : 코드 정적 검사
  ├─ build    : Docker 이미지 빌드 → Docker Hub push
  ├─ setup    : GitLab Variables File → EC2에 .env 전송 (scp)
  └─ deploy   : Docker Hub에서 pull → EC2에 SSH로 배포

      ↓  (SSH_PRIVATE_KEY로 접속)

EC2 서버
  └─ docker compose up --no-deps [서비스]
```

`setup` 잡이 `.env`를 먼저 전송하고, `deploy` 잡이 그 `.env`를 읽으며 컨테이너를 실행하는 순서입니다. 두 잡의 순서가 바뀌면 이전 `.env`로 컨테이너가 뜰 수 있으니 파이프라인 스테이지 순서를 주의해야 합니다.

## Docker Secret이 필요한 경우는?

현재 허수아비 프로젝트는 EC2 2대 규모의 단일 서버 구성이기 때문에, `.env + env_file` 방식으로 충분합니다. Docker Secret은 보통 다음 상황에서 고려합니다.

| 방식 | 사용 시점 |
|---|---|
| `.env` + `env_file` | 단일 서버, 소규모 팀 (현재 프로젝트) |
| Docker Secret | Docker Swarm / K8s 클러스터, 여러 노드에 동일한 시크릿 배포가 필요할 때 |

Docker Secret은 `docker inspect`로도 값이 노출되지 않고, 메모리에서만 읽히기 때문에 보안 수준이 더 높습니다. 다만 설정 복잡도가 올라가고 Swarm 또는 K8s 환경이 전제되어야 합니다. 지금 규모에서는 오버엔지니어링이라고 판단했습니다.
