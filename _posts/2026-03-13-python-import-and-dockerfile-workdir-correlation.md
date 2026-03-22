---
title: "파이썬 Import 에러와 Dockerfile WORKDIR의 상관관계"
date: 2026-03-13 14:00:00 +0900
categories: [Tech, DevOps]
tags: [Python, Docker, Dockerfile, Import, ModuleNotFoundError, Troubleshooting, Infrastructure]
toc: true
comments: true
description: "로컬 환경에서는 정상 작동하던 파이썬 코드가 도커 컨테이너에서 ModuleNotFoundError를 발생시키는 근본 원인을 분석합니다. 파이썬의 모듈 탐색 방식(CWD)과 Dockerfile의 WORKDIR 설정 간의 물리적 결합도를 명확히 이해해 봅니다."
---

파이썬 프로젝트를 도커(Docker)로 배포할 때, 파이썬의 `import` 동작 방식과 `Dockerfile`의 폴더 구조는 물리적으로 매우 강하게 결합되어 있습니다. 이 두 가지가 왜 완벽하게 일치해야 하는지 그 기술적인 인과관계를 파헤쳐 보겠습니다.

---

## 파이썬 모듈의 `import` 동작 방식

파이썬 스크립트 내부에서 `from common.config import KafkaConfig`라는 코드가 실행될 때, 파이썬 프로세스는 컴퓨터 전체를 뒤져서 `common` 폴더를 찾지 않습니다.

파이썬은 기본적으로 **스크립트가 실행된 현재 폴더(CWD, Current Working Directory)**를 최상위 루트로 인식합니다.

실행 위치 바로 아래에 `common`이라는 폴더가 있고, 그 안에 `config.py`가 정확히 존재해야만 정상적으로 메모리에 로드합니다. 단 한 칸의 폴더 뎁스(Depth)라도 어긋나면 즉시 `ModuleNotFoundError`를 뱉고 프로그램을 멈춰버립니다.


## Dockerfile의 역할: 독립된 파일 시스템 구축

`Dockerfile`은 컨테이너라는 텅 빈 리눅스 환경 안에 소스 코드가 놓일 폴더 구조를 물리적으로 빚어내는 작업 지시서입니다. 여기서 두 가지 핵심 명령어가 파이썬의 **'검색 기준점'**을 결정짓게 됩니다.

* **`WORKDIR /app`**: 컨테이너 내부의 기본 작업 위치(디렉토리)를 `/app`으로 지정합니다. 이는 곧 파이썬이 스크립트를 실행할 때 인식하는 절대적인 기준점이 됩니다.
* **`COPY . /app`**: 빌드를 실행하는 외부 환경(노트북 등)의 소스 코드 전체를 컨테이너 내부의 `/app` 폴더로 복사해 넣습니다.


## 왜 Dockerfile 작업 구조에 절대적인 영향을 받는가?

로컬 개발 환경의 폴더 구조와 컨테이너 환경의 폴더 구조가 단 한 칸이라도 엇갈릴 때 발생하는 시나리오입니다.

### [로컬 환경] 개발자의 의도
팀원은 로컬 노트북의 `data-pipeline/` 폴더를 최상위 경로로 잡고 개발했습니다.
* **구조:** `data-pipeline/common/config.py`, `data-pipeline/main.py`
* **실행:** 팀원은 `data-pipeline/` 폴더 안에서 `python main.py`를 실행하므로, 파이썬은 자신의 발밑에 있는 `common` 폴더를 정상적으로 찾아 `import`에 성공합니다.

### [도커 환경] 인프라 담당자의 실수
인프라 담당자가 코드를 도커 내부에 좀 더 깔끔하게 정리하겠다는 의도로 `Dockerfile`을 다음과 같이 임의로 작성했습니다.

```dockerfile
# 인프라 담당자가 코드를 깔끔하게 묶겠다고 /app/src 폴더에 복사함
WORKDIR /app
COPY ./data-pipeline /app/src

# 실행은 /app 위치에서 /app/src/main.py 를 호출함
CMD ["python", "src/main.py"]
```

### [결과] 실행 실패 및 에러 발생
이 컨테이너가 켜지면 다음과 같은 연쇄 작용이 일어납니다.

1.  컨테이너가 켜지고 `python src/main.py`가 실행됩니다.
2.  `main.py` 안에 있는 `from common.config import ...` 코드가 호출됩니다.
3.  현재 도커의 작업 위치(`WORKDIR`)는 `/app`이므로, 파이썬은 `/app/common/config.py`가 있는지 찾습니다.
4.  하지만 실제 코드는 인프라 담당자가 복사해 둔 `/app/src/common/config.py`에 들어있습니다.
5.  결국 파이썬은 파일을 찾지 못하고 **`ModuleNotFoundError`**를 내며 컨테이너를 즉시 종료시킵니다.

---

## 마치며

파이썬 애플리케이션을 도커라이징(Dockerizing)할 때는, **개발자가 로컬에서 파이썬을 실행했던 위치와 Dockerfile의 `WORKDIR` 구조를 완벽하게 동기화**해야 합니다. 인프라 관점에서의 폴더 정리가 자칫 애플리케이션의 모듈 탐색 트리를 완전히 망가뜨릴 수 있음을 항상 명심해야 합니다.

