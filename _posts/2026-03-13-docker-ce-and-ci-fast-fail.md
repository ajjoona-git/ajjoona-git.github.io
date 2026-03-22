---
title: "Ubuntu 24.04 Docker CE 설치와 CI Fast-Fail 파이프라인 구축기"
date: 2026-03-13 10:00:00 +0900
categories: [Tech, DevOps]
tags: [CI/CD, Docker, Ubuntu, FastFail, Lint, DevOps, Infrastructure]
toc: true
comments: true
image: /assets/img/posts/2026-03-13-docker-ce-and-ci-fast-fail/1.png
description: "Ubuntu 24.04 환경에서 기본 패키지(docker.io) 대신 공식 Docker CE를 설치해야 하는 이유와 방법, 그리고 Lint/Test를 통해 빌드 전 에러를 차단하는 Fast-Fail CI 파이프라인 설계 과정을 공유합니다."
---

이번 포스트에서는 허수아비 프로젝트의 인프라를 세팅하며 마주한 **Ubuntu 24.04 LTS 환경에서의 Docker CE 설치 과정**과, 무의미한 빌드 시간을 줄여주는 **CI 파이프라인(Fast-Fail) 설계 전략**을 공유합니다.

---

## 왜 공식 `docker-ce`를 설치해야 할까?

Ubuntu 환경에서 도커를 설치할 때 가장 흔히 하는 실수는 기본 APT 저장소에 있는 `docker.io` 패키지를 설치하는 것입니다. 

기본 저장소의 도커 패키지는 버전이 구버전(Outdated)에 머물러 있는 경우가 많고, 최신 기능(특히 Buildx나 Compose 플러그인)을 연동하려면 별도의 의존성을 수동으로 잡아주어야 하는 등 **설치와 유지보수가 훨씬 복잡해집니다.**

따라서 도커 공식 저장소(Repository)를 직접 APT에 추가하여 최신 안정화 버전인 **Docker CE(Community Edition)** 패키지를 설치하는 것이 실무 표준입니다.

### Docker CE 설치 스크립트 (Ubuntu 24.04)

```bash
# 1. 패키지 업데이트 및 의존성 설치
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# 2. Docker 공식 GPG 키 추가
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 3. Docker apt 저장소 추가 (아키텍처 및 OS 코드네임 자동 매핑)
echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Docker CE 및 핵심 플러그인 설치
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 버전 및 명령어 확인 (`docker-compose` vs `docker compose`)

설치가 완료되면 버전을 확인합니다. 

과거 파이썬(pip) 기반으로 설치하던 `docker-compose`(하이픈 포함) 구버전 대신, 이제는 도커의 기본 플러그인으로 내장된 **`docker compose`(띄어쓰기)**를 사용하는 것이 호환성 면에서 안전합니다.

```bash
docker --version  # Docker version 29.3.0
docker compose version  # Docker Compose version v5.1.0
sudo systemctl status docker  # 서비스 실행 상태 확인
```
*루트 권한인 `sudo`를 매번 치는 것이 번거롭다면 사용자를 `docker` 그룹에 추가하는 방법도 있지만, 실행 명령어에 대한 완벽한 이해가 있다면 보안상 `sudo`를 유지하는 것도 나쁘지 않은 선택입니다.*

### Docker Hub 로그인

```bash
docker login -u [ID]
# 화면에 토큰 입력
```

![Docker Hub Login](/assets/img/posts/2026-03-13-docker-ce-and-ci-fast-fail/2.png)
*Docker Hub Login*

![서비스 상태 확인](/assets/img/posts/2026-03-13-docker-ce-and-ci-fast-fail/1.png)
*서비스 상태 확인*


## CI 파이프라인 설계: Fast-Fail (빠른 실패) 전략

안정적인 인프라 위에, 본격적인 배포(CD) 파이프라인을 얹기 전 **CI(Continuous Integration)**를 먼저 구성했습니다. 여기서 가장 중요한 설계 철학은 **"Fast-Fail(빠른 실패)"**입니다.

### 왜 빌드 전에 Lint와 Test를 해야 할까?

보통 Lint와 Test는 Docker 이미지 빌드 결과물(바이너리) 자체에 직접적인 영향을 주지 않습니다. 그럼에도 파이프라인의 가장 앞단에 배치하는 이유는 **"빌드할 가치가 있는 코드인지"**를 사전에 검증하는 문지기(Gate) 역할을 하기 때문입니다.

| 비교 항목 | Lint/Test 없는 파이프라인 | Fast-Fail 적용 파이프라인 |
| :--- | :--- | :--- |
| **에러 발견 시점** | 배포 후 런타임 (서비스 장애 발생) | Push 직후 (CI 단계에서 조기 종료) |
| **피드백 속도** | 10분 이상 소요 | 1~3분 내 즉시 피드백 |
| **자원 낭비** | Docker 빌드 + Push + EC2 배포 시간 낭비 | Lint 단계에서 즉시 프로세스 종료 (낭비 ❌) |

### `lint → build → deploy`

단순히 에러만 뱉고 끝나는 것이 아니라, CI가 자동으로 코드를 교정해 주는(Auto-fix) 프로세스를 구성했습니다.

1. **코드 Push** 발생
2. **Lint Fix 자동 실행:** 파이프라인 내에서 `eslint --fix`나 `ruff --fix`가 동작합니다.
3. **변경 사항 커밋:** CI가 코드를 수정했다면 무한 루프를 방지하기 위해 `[skip ci]` 태그를 달아 자동 커밋 & 푸시합니다.
4. **검증 및 빌드 판단:**
   * Fix 후에도 남은 오류가 있다면 → 잡(Job) 실패, 파이프라인 즉시 중단 (Fast-Fail)
   * 모두 통과했다면 → Docker 빌드 및 배포 단계로 진행

### 서비스별 Lint/Fix 도구 적용
마이크로서비스 아키텍처 특성에 맞게, 각 서비스의 언어/프레임워크에 최적화된 도구를 적용했습니다.

| 서비스 | Fix 도구 | 자동 수정 가능 항목 |
| :--- | :--- | :--- |
| **Frontend** | `eslint --fix` | import 정렬, 세미콜론 누락, 따옴표 교정 등 |
| **AI / Pipeline** | `ruff --fix` | import 정렬, 불필요한 import 제거, PEP-8 스타일 등 |
| **Backend** | (컴파일 체크) | Java 빌드 시 문법 및 타입 컴파일 체크 |

---

## 마치며

이번 인프라 정비를 통해 공식 Docker CE 환경을 깔끔하게 구축하고, 런타임 에러를 사전에 차단하는 견고한 CI 파이프라인을 완성했습니다. 
Fast-Fail 전략 덕분에 앞으로 팀원들은 무의미한 빌드 대기 시간(5~10분)을 낭비하지 않고, 코드의 로직과 품질에만 온전히 집중할 수 있게 되었습니다.