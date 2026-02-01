---
title: "Dockerfile 최적화 전략: 가볍고 빠른 Python 이미지 만들기 (Slim vs Alpine, Layer Caching)"
date: 2026-02-01 09:00:00 +0900
categories: [Tech, DevOps]
tags: [Docker, Python, Optimization, DevOps, CI/CD, FastAPI, LayerCaching]
toc: true
comments: true
description: "Python 프로젝트를 위한 Dockerfile 작성 가이드입니다. Alpine 대신 Slim 이미지를 선택해야 하는 이유(glibc 호환성), 빌드 속도를 획기적으로 줄이는 레이어 캐싱(Layer Caching) 전략, 그리고 필수 환경 변수 설정법을 상세히 설명합니다."
---

컨테이너 기반 배포의 핵심은 **Dockerfile**이다.
이 스크립트 파일을 어떻게 작성하느냐에 따라 배포 속도가 10분이 걸릴 수도, 10초가 걸릴 수도 있다.

이번 포스트에서는 단순히 "돌아가는" 이미지가 아니라, **"가볍고 빠르며 안정적인"** Python 애플리케이션 이미지를 만들기 위한 3가지 핵심 전략을 정리한다.

---

## Dockerfile 기본 문법

Dockerfile은 Docker 이미지를 생성하기 위한 스크립트 파일이다. 이미지 빌드 과정에서 실행할 명령어와 설정을 작성한다.

전략을 논하기 전에, 자주 사용되는 명령어들을 짧게 짚고 넘어가자.

| 명령어 | 설명 | 비고 |
| :--- | :--- | :--- |
| **FROM** | 생성할 이미지의 베이스(기반)가 될 이미지 결정 | `python:3.12-slim` |
| **ENV** | 컨테이너 내부의 환경 변수 설정 | `ENV TZ=Asia/Seoul` |
| **WORKDIR** | 명령어를 실행할 작업 디렉토리 설정 | `cd`와 유사함 |
| **COPY** | 호스트(내 컴퓨터)의 파일을 이미지로 복사 | `COPY <src> <dest>` |
| **RUN** | 이미지 빌드 과정에서 실행할 명령어 | `pip install` 등 |
| **CMD** | 컨테이너가 **시작될 때** 실행할 명령어 | `uvicorn ...` |
| **EXPOSE** | 컨테이너가 수신 대기할 포트 명시 | 문서화 목적이 강함 |


## 최적화된 Dockerfile 예시

다음은 **Layer Caching**과 **Slim 이미지** 전략이 적용된 Dockerfile이다.

```dockerfile
# 1. Base Image Strategy: 호환성을 위해 slim 사용
FROM python:3.12-slim

# 2. Environment Strategy: 로그 버퍼링 제거 & .pyc 생성 방지
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Work Directory
WORKDIR /app

# 4. Install System Dependencies
# gcc, libpq-dev 등 빌드에 필요한 최소 패키지 설치 후 캐시 삭제
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Layer Caching Strategy ⭐
# 소스코드보다 requirements.txt를 먼저 복사해야 함
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy Project Code
COPY . .

# 7. Execution Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 전략 상세 분석
### ① Base Image 전략: 왜 `alpine`이 아니라 `slim`인가?
보통 용량을 극한으로 줄이기 위해 `alpine` 리눅스를 많이 사용한다. 하지만 Python 프로젝트, 특히 **AI/데이터 분석 라이브러리**를 쓴다면 `alpine`은 피하는 것이 좋다.

- **Alpine (Musl Lib):** C 표준 라이브러리로 `musl`을 사용한다. 하지만 Pandas, Numpy 같은 대부분의 Python 라이브러리는 `glibc`(GNU C Library)에 의존한다.

- **문제점:** `alpine`에서 이를 돌리려면 설치할 때마다 C 코드를 직접 컴파일해야 한다. 이 과정에서 빌드 시간이 엄청나게 길어지고, 원인 모를 호환성 에러가 자주 발생한다.

- **Slim (Glibc):** Debian 기반의 경량화 버전으로, `glibc`를 기본 지원하여 호환성이 완벽하다.

불필요한 툴을 뺀 **python:3.12-slim**이 AI/Backend 프로젝트의 표준이다.

### ② 레이어 캐싱 전략 (Layer Caching) ⭐
Docker 빌드 속도를 결정하는 가장 중요한 요소다. Docker는 Dockerfile을 위에서부터 한 줄씩 실행하며, 각 단계의 결과를 **레이어(Layer)**로 저장해 둔다.

- **안 좋은 예**
```Dockerfile
COPY . .  # 소스코드를 먼저 다 복사함
RUN pip install -r requirements.txt
```

소스코드(`main.py` 등)를 한 글자만 고쳐도, Docker는 "어? 파일이 바뀌었네? 다음 줄부터 다시 실행해!" 라고 판단한다. 결과적으로 코드를 고칠 때마다 **무거운 `pip install`을 매번 다시 수행**한다.

- **좋은 예**
```Dockerfile
COPY requirements.txt .  # 의존성 명세만 먼저 복사
RUN pip install -r requirements.txt # 설치 진행

COPY . . # 그 다음에 소스코드 복사
```

코드를 수정하더라도 `requirements.txt` 내용이 바뀌지 않았다면, Docker는 `pip install` 단계를 건너뛰고 **캐시된 레이어를 그대로 사용(0초 소요)**한다.

### ③ 환경 변수 전략
컨테이너 환경에 최적화된 Python 설정을 주입한다.

- `PYTHONDONTWRITEBYTECODE=1`: 파이썬은 실행 시 `.pyc` (컴파일된 캐시 파일)를 생성하는데, 컨테이너는 보통 한 번 실행하고 사라지므로 이 파일이 필요 없다. 이를 방지해 이미지 크기를 약간 줄이고 쓰기 작업을 방지한다.

- `PYTHONUNBUFFERED=1`: 파이썬은 로그를 버퍼(Buffer)에 모았다가 출력하는 습성이 있다. 이 옵션을 켜면 로그가 발생하는 즉시 콘솔에 출력되므로, **앱이 비정상 종료되었을 때 로그가 잘리는 것을 방지**할 수 있다. 디버깅을 위해 필수다.

---

## 마치며

Dockerfile은 한 번 잘 짜두면 개발 생산성을 지속적으로 높여주는 자산이다. 특히 **Layer Caching** 순서는 CI/CD 파이프라인의 배포 시간을 획기적으로 줄여주므로 반드시 적용하자.

---

### 레퍼런스

- [브라더댄 🐳 Docker 강의 3강: Dockerfile을 이용한 커스텀 이미지 생성](https://brotherdan.tistory.com/53)