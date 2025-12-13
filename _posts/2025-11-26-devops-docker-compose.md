---
title: "[둥지] Ubuntu 서버에서 Docker Compose로 React 앱 배포하기 (feat. 수동 배포의 맛)"
date: 2025-11-26 09:00:00 +0900
categories: [Projects, 둥지]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [DevOps, Docker, DockerCompose, Ubuntu, React, Nginx, Deployment]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-26-devops-docker-compose/cover.png # (선택) 대표 이미지
description: "AWS EC2(Ubuntu) 환경에서 Docker Compose와 Nginx를 사용하여 React 애플리케이션을 수동으로 빌드하고 배포한 과정을 정리했습니다."
---

Figma에서 디자인된 UI를 코드로 변환하여 React 앱을 만들고, 이를 AWS EC2(Ubuntu) 서버에 배포하여 둥지 서비스를 운영하고 있다. 오늘은 개발 초기 단계에서 사용했던 **Docker Compose 기반의 배포 워크플로우**를 정리해 보려 한다.

자동화(CI/CD)를 구축하기 전, 서버에서 직접 명령어를 치며 배포하는 과정은 리눅스와 도커의 동작 원리를 이해하는 데 도움이 되었다.

---

## 배포 환경 및 도구

- **OS**: Ubuntu 22.04 LTS (AWS EC2)
- **Runtime**: Node.js 20 (Alpine Linux)
- **Container**: Docker & Docker Compose
- **Web Server**: Nginx
- **Framework**: React + Vite + TypeScript

---

## 배포 시나리오

로컬 컴퓨터에서 코드를 수정하고 GitHub에 푸시(Push)한 뒤, 서버에 접속해서 변경된 내용을 반영하는 과정이다. 터미널(CLI) 환경에서 다음 4단계의 명령어를 주로 사용했다.

### 1. 변경 사항 받아오기 (`git pull`)

가장 먼저 할 일은 원격 저장소(GitHub)에 올라간 최신 코드를 서버로 가져오는 것입니다.

```bash
# 프로젝트 폴더로 이동
cd DoongziFrontend

# 최신 코드 당겨오기
git pull
```

이 명령어를 입력하면 `src/` 폴더 내의 변경된 리액트 코드들이 서버의 로컬 디렉토리로 다운로드됩니다.

### 2. 현재 실행 중인 컨테이너 확인 (`docker ps`)

도커가 잘 떠있는지, 혹은 내가 삭제해야 할 컨테이너의 ID가 무엇인지 확인한다.

```bash
docker ps
```

- **CONTAINER ID**: 컨테이너의 고유 식별자 (예: `c5c0fbb00b68`)
- **IMAGE**: 사용 중인 이미지 이름 (`doongzi-frontend-webserver`)
- **STATUS**: 가동 시간 (예: `Up 46 minutes`)

### 3. 기존 서버 내리기 (`docker rm`)

새로운 코드를 반영하려면 기존에 돌고 있던 컨테이너를 삭제해야 한다.

```bash
docker rm -f <CONTAINER_ID>
# 예: docker rm -f c5c0fbb00b68
```

- `rm`: Remove, 컨테이너를 삭제합니다.
- `f`: Force, 실행 중인 컨테이너를 강제로 중지시키고 삭제합니다.

### 4. 새로운 서버 빌드 및 실행 (`docker compose up`)

가장 중요한 단계. 변경된 코드를 기반으로 이미지를 새로 굽고(Build), 컨테이너를 실행한다.

```bash
docker compose up -d --build
```

1. **`-build` (빌드의 의미)**:
    - 단순히 코드를 복사하는 게 아니라, `Dockerfile`에 정의된 절차대로 소스 코드를 실행 가능한 형태로 변환한다.
    - **Multi-Stage Build**를 사용했다.
        - **Stage 1 (Builder)**: Node.js 환경에서 `npm run build`를 실행하여 TypeScript/React 코드를 브라우저가 이해할 수 있는 정적 파일(HTML, CSS, JS)로 변환(컴파일/번들링)한다.
        - **Stage 2 (Final)**: 가벼운 Nginx 이미지에 위에서 만든 정적 파일만 쏙 가져와서 웹 서버를 구동한다.
2. **`d` (Detached)**:
    - 컨테이너를 백그라운드에서 실행한다. 이 옵션이 없으면 터미널을 끄는 순간 서버도 같이 꺼지게 된다.

![프론트 서버 띄우기 (1/2)](/assets/img/posts/2025-11-26-devops-docker-compose/2.png)

프론트 서버 띄우기 (1/2)

![프론트 서버 띄우기 (2/2)](/assets/img/posts/2025-11-26-devops-docker-compose/1.png)

프론트 서버 띄우기 (2/2)

---

## 왜 Docker Compose를 썼나?

단일 컨테이너인데 굳이 `docker run` 대신 `docker compose`를 쓴 이유는 **설정 관리의 편리함** 때문이다.

`docker-compose.yml` 파일을 보면 알 수 있다.

```yaml
version: '3.8'

services:
  webserver:
    build: .
    container_name: doongzi-app
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    # ...
```

만약 `docker run`을 썼다면 매번 아래처럼 긴 명령어를 쳐야 했을 겁니다.

```bash
docker run -d --name doongzi-app -p 80:80 -p 443:443 -v ./nginx.conf:/etc/nginx/conf.d/default.conf:ro ... (생략)
```

Docker Compose를 사용하면 설정 파일(`docker-compose.yml`) 하나로 포트 포워딩, 볼륨 마운트(SSL 인증서 연동 등), 환경 변수 관리를 한 번에 할 수 있어, `up` 명령어 하나로 배포가 끝난다.

---

## 마무리

지금은 터미널에 접속해서 직접 명령어를 치고 있지만, 이 과정은 **'빌드'와 '배포'가 실제로 어떻게 일어나는지** 이해하는 데 아주 중요한 경험이었다.

- **소스 코드**가
- **빌드** 과정을 거쳐 **정적 파일**이 되고,
- **Docker 이미지**로 패키징되어
- **컨테이너**라는 격리된 환경에서 실행된다!

이 다음 단계가 GitHub Actions를 도입해서, `git push`만 하면 이 모든 과정이 자동으로 수행되도록(CI/CD)하는 것이다.