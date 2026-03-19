---
title: "[허수아비] GitLab CI 파이프라인 구축기 (DinD vs DooD)"
date: 2026-03-11 00:00:00 +0900
categories: [Project, 허수아비]
tags: [GitLab, CI/CD, Docker, DinD, DooD, GitLabRunner, DevOps, Backend, Infra]
toc: true
comments: true
image: 
description: "CI 파이프라인의 개념부터 도커 구조, DinD vs DooD 비교, GitLab Runner DooD 세팅까지 단계별로 정리합니다."
---

코드를 푸시하면 자동으로 빌드되고 이미지가 만들어지는 CI 파이프라인. 

내부에서 무슨 일이 벌어지는지, 그리고 왜 DooD 아키텍처를 선택했는지 정리합니다.

---

## CI 파이프라인이란?

CI(Continuous Integration, 지속적 통합) 파이프라인은 개발자가 작성한 코드를 깃랩에 푸시(Push)했을 때, **사람의 개입 없이 로봇(GitLab Runner)이 자동으로 코드를 검증하고 실행 가능한 형태(도커 이미지)로 포장해 주는 자동화된 컨베이어 벨트**입니다.

허수아비(birdybuddy) 프로젝트에 빗대어 설명하면 다음과 같은 일들이 일어납니다.

1. **트리거(Trigger):** 팀원이 프론트엔드 기능을 수정하고 `dev` 브랜치에 코드를 머지(Merge)합니다.
2. **빌드(Build):** 깃랩 러너가 깨끗한 Node.js 도커 방을 만들고, 그 안에서 `npm run build`를 실행하여 React 코드를 HTML/CSS/JS 덩어리로 압축합니다.
3. **패키징(Dockerize):** 만들어진 결과물을 Nginx나 Java 런타임이 포함된 도커 이미지(예: `birdybuddy_frontend:latest`)로 구워냅니다.
4. **저장(Push):** 구워진 도커 이미지를 우리 팀만 접근할 수 있는 깃랩 창고(Container Registry)에 안전하게 업로드해 둡니다.

이 과정을 거치면, 배포(CD) 단계에서는 단순히 창고에서 이미지를 꺼내서 EC2 서버에 띄우기만 하면 됩니다.


## 도커(Docker) 구조

### 일반 도커 구조의 3대 요소

**1. 도커 클라이언트 (Docker Client)**

- 사용자가 도커와 소통하는 창구(CLI)입니다.
- 터미널에 `docker build`, `docker pull`, `docker run` 같은 명령어를 치면, 클라이언트는 이 명령을 번역해서 도커 호스트(서버)로 전달합니다.

**2. 도커 호스트 (Docker Host)**

- 실제 도커가 설치되어 구동되는 물리적인 컴퓨터(예: EC2 서버)입니다. 이 안에는 두 가지 핵심이 있습니다.
- **도커 데몬 (Docker Daemon, `dockerd`):** 클라이언트의 명령을 수신하여 묵묵히 일하는 백그라운드 프로세스입니다. 이미지, 컨테이너, 네트워크, 볼륨 등 모든 도커 객체를 생성하고 관리하는 핵심입니다. (DooD에서 러너가 소켓으로 빌려 쓴다는 호스트의 데몬이 바로 이 녀석입니다!)
- **컨테이너 (Containers):** 데몬에 의해 실행된 격리된 애플리케이션들입니다. 각각의 컨테이너는 운영체제 커널(Kernel)은 호스트와 공유하지만, 자신만의 독립적인 파일 시스템과 네트워크를 가집니다.

**3. 도커 레지스트리 (Docker Registry)**

- 도커 이미지들이 보관되는 원격 창고입니다. (예: Docker Hub, GitLab Container Registry 등)
- 데몬이 컨테이너를 실행하려는데 호스트에 해당 이미지가 없다면, 레지스트리에서 다운로드(Pull) 해옵니다.

### 왜 일반 구조로는 파이프라인을 못 돌릴까요?

일반적인 도커 구조에서 각각의 컨테이너(예: `birdybuddy_backend`, `birdybuddy_postgresql`)는 **자기 자신의 역할(앱 실행, DB 구동)만 충실히 수행하도록 철저히 격리**되어 있습니다. 이 컨테이너들은 자기를 실행시켜 준 '도커 데몬'의 존재를 알 필요도 없고, 데몬에게 명령을 내릴 권한도 없습니다.

하지만 **GitLab Runner 컨테이너**는 다릅니다. 이 녀석은 단순한 앱이 아니라, 코드를 가져와서 **또 다른 도커 이미지를 구워내야 하는 특별한 임무**를 띠고 있습니다. 즉, 컨테이너 내부에서 `docker build` 명령어를 써야만 하는데, 일반 컨테이너는 철저히 격리되어 있어 그럴 권한이 없습니다. 따라서 **DinD(내부에 데몬 새로 깔기)나 DooD(호스트 데몬 심장 빌려오기)** 같은 특수한 아키텍처의 도움을 받아야만 합니다.


## DinD vs DooD

DinD(Docker-in-Docker)와 DooD(Docker-out-of-Docker)는 CI/CD 파이프라인처럼 도커 컨테이너 내부에서 또 다른 도커 컨테이너를 빌드하고 실행해야 할 때 사용하는 두 가지 핵심 아키텍처입니다.

### DinD (Docker-in-Docker)

도커 컨테이너 내부에 완전히 독립된 새로운 도커 데몬(서버)을 구동하는 구조입니다.

- **동작 원리:** 부모 컨테이너가 자신의 내부에 격리된 가상 공간을 만들고 자식 컨테이너를 생성합니다. '인셉션'처럼 꿈속의 꿈을 꾸는 형태입니다.
- **볼륨 마운트 문제:** 호스트 장비(EC2)와 부모 컨테이너 내부의 파일 시스템이 완전히 단절됩니다. `-v /app:/app` 옵션을 주면 물리적인 EC2의 `/app`이 아닌 부모 컨테이너 내부의 엉뚱한 경로를 찾게 되어 볼륨이 꼬이는 현상이 발생합니다.
- **보안 위험:** 부모 컨테이너 안에서 시스템 레벨의 도커 데몬을 띄워야 하므로, 호스트 시스템의 최고 권한을 넘겨주는 `--privileged` 옵션이 강제됩니다. 해킹에 매우 취약한 구조입니다.

### DooD (Docker-out-of-Docker)

컨테이너 내부에 새로운 데몬을 띄우는 대신, 호스트 장비의 도커 심장부인 `docker.sock`(유닉스 소켓 파일) 통로만 컨테이너에게 빌려주는 구조입니다.

- **동작 원리:** GitLab Runner 안에서 `docker build` 명령어를 치면, 이 명령이 소켓 통로를 타고 빠져나가 **호스트 장비의 도커 데몬**으로 곧바로 전달됩니다. 새로 만들어진 컨테이너는 Runner의 내부에 갇히는(자식) 것이 아니라, EC2 호스트 장비 위에 나란히(형제) 배치됩니다.
- **볼륨 일관성 확보:** 명령을 실제로 수행하는 주체가 호스트의 도커 데몬이므로, 볼륨 마운트 시 호스트의 물리적 경로를 정확하게 인식하여 파일 꼬임 현상이 사라집니다.
- **자원 공유:** 호스트 장비에 이미 다운로드되어 있는 도커 이미지 캐시를 그대로 공유해서 쓸 수 있어 빌드 속도가 빠릅니다. `--privileged` 옵션도 필요하지 않습니다.

### DinD vs DooD 비교

| 구분 | DinD (Docker-in-Docker) | DooD (Docker-out-of-Docker) |
| --- | --- | --- |
| **구조** | 컨테이너 안의 컨테이너 (부모-자식) | 컨테이너 옆의 컨테이너 (형제) |
| **데몬 위치** | 컨테이너 내부 | 호스트 장비 (EC2) |
| **볼륨 마운트** | 직관적이지 않음 (경로 단절 발생) | 호스트 기준 경로로 완벽하게 매핑됨 |
| **보안** | `--privileged` 권한 필수 (매우 취약) | 소켓 바인딩만 필요 (상대적 안전) |
| **CI/CD 적용** | 특수한 완전 격리 환경이 필요한 경우 | 볼륨과 캐시 활용이 중요한 일반적 파이프라인의 표준 |


## GitLab Runner 생성 및 DooD 세팅 가이드

파이프라인이라는 컨베이어 벨트를 돌리려면 공장 노동자인 'GitLab Runner'를 EC2 서버 중 한 대에 설치해야 합니다. 부하를 분산하기 위해 App & DB 서버인 **EC2 #2**에 설치하는 것을 권장합니다.

### 1단계: GitLab에서 러너 등록 토큰 발급받기

1. GitLab 프로젝트 페이지에 접속합니다.
2. 좌측 메뉴에서 **[Settings] → [CI/CD]**를 클릭하고, **Runners** 섹션의 `Expand`를 누릅니다.
3. **[New project runner]** 버튼을 클릭하고, 플랫폼을 `Linux`로 선택한 뒤 러너를 생성합니다.
4. 화면에 나타나는 **URL**(예: `https://lab.ssafy.com/`)과 **Token**(예: `glrt-xxx...`) 값을 복사해 둡니다.

```bash
gitlab-runner register --url https://lab.ssafy.com --token glrt-xxx...
```

### 2단계: EC2에 Runner 컨테이너 실행 (호스트 소켓 마운트)

MobaXterm으로 EC2 서버에 접속합니다. Runner 컨테이너를 백그라운드에서 실행하며, 이때 호스트의 도커 소켓(`docker.sock`)을 마운트해 줍니다.

```bash
docker run -d --name gitlab-runner --restart always \
  -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  -v /var/run/docker.sock:/var/run/docker.sock \
  gitlab/gitlab-runner:latest
```

### 3단계: Runner 등록 (Register) 명령어 실행

EC2 터미널에서 아래 명령어로 러너를 깃랩과 연결(등록)합니다.

```bash
docker exec -it gitlab-runner gitlab-runner register
```

명령어를 치면 몇 가지 질문이 나옵니다.

- **GitLab instance URL:** 복사해 둔 URL 입력
- **Registration token:** 복사해 둔 Token 입력
- **Description:** `birdybuddy-docker-runner`
- **Tags:** `docker` (파이프라인 스크립트에서 이 러너를 호출할 때 쓸 이름입니다)
- **Executor:** `docker` (반드시 docker로 입력해야 합니다!)
- **Default image:** `docker:24.0.5` (빌드 작업을 수행할 기본 도커 이미지입니다.)

### 4단계: DooD 소켓 연결

러너가 등록되었지만, 아직 EC2 호스트의 도커 소켓(`docker.sock`)과 연결되지 않았습니다. 설정 파일을 열어 소켓을 추가해 주어야 볼륨이 꼬이지 않습니다.

```bash
sudo vi /srv/gitlab-runner/config/config.toml
```

파일 내용 중 `[runners.docker]` 섹션을 찾아서 `volumes` 항목을 아래와 같이 수정합니다.

```toml
# 수정 전
volumes = ["/cache"]

# 수정 후 (소켓 경로를 정확히 추가합니다)
volumes = ["/cache", "/var/run/docker.sock:/var/run/docker.sock"]
```

저장하고 나옵니다. (`ESC` → `:wq` → `Enter`)

### 5단계: GitLab Runner 백그라운드 실행

모든 세팅이 끝났습니다. 러너를 24시간 돌아가는 도커 컨테이너로 영구적으로 띄웁니다.

```bash
docker run -d --name gitlab-runner --restart always \
  -v /srv/gitlab-runner/config:/etc/gitlab-runner \
  -v /var/run/docker.sock:/var/run/docker.sock \
  gitlab/gitlab-runner:latest
```

명령어 실행 후 GitLab 웹페이지의 Runners 섹션을 새로고침해 보면, 초록색 불이 들어온 `birdybuddy-docker-runner`가 온라인 상태로 대기 중인 것을 확인할 수 있습니다!

![GitLab Runners 섹션에서 초록불 확인](/assets/img/posts/2026-03-11-birdybuddy-ci-dind-vs-dood/1.png)
*GitLab Runners 섹션에서 초록불 확인*

---

### 레퍼런스

- [GitLab Runner Docker 설치 공식 문서](https://docs.gitlab.com/runner/install/docker/)
