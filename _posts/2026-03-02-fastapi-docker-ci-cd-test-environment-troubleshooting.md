---
title: "[둥지] FastAPI 테스트 환경 구축기: Mocking부터 Docker CI/CD 연동까지"
date: 2026-03-02 10:00:00 +0900
categories: [Projects, 둥지]
tags: [FastAPI, Pytest, Docker, GitHubActions, CI/CD, Troubleshooting, DevOps, Mocking, Backend]
toc: true
comments: true
description: "FastAPI 백엔드의 로컬 테스트 환경을 Docker 기반으로 전환하고 GitHub Actions CI와 연동하며 겪은 트러블슈팅 과정을 회고합니다. 외부 API Mocking, 환경변수 주입 시점 문제, Docker 볼륨 충돌(Race Condition) 등 다양한 인프라 이슈의 해결 방법을 다룹니다."
---

안정적인 백엔드 시스템을 구축하기 위해 테스트 코드는 필수입니다. 특히 둥지 프로젝트처럼 이메일 전송(SMTP), 주소 검색(JUSO API) 등 다양한 외부 인프라와 결합된 FastAPI 백엔드에서는 테스트 환경을 어떻게 격리하고 구성할 것인지가 매우 중요합니다.

이번 글에서는 **단위/통합 테스트의 분리 고민**부터 시작하여, **로컬 테스트 환경을 `uv run`에서 Docker 기반으로 전환**하고, 이를 **GitHub Actions CI에 연동하는 과정에서 마주친 수많은 트러블과 해결 과정**을 단계별로 회고해 봅니다.

---

## 미리보기

- **환경 변수 관리 일원화:** `.env.example`을 복사해 도커 인프라 구동 시점부터 변수가 기입되도록 `.env.example`에 목업 환경변수를 작성했습니다.
- **린터(Ruff) 버전 동기화:** 로컬 환경(uv.lock)과의 완벽한 포매팅 규칙 일치(재현성)를 위해 `uv sync` -> `uv run ruff` 순서로 파이프라인을 정규화했습니다.
- **테스트 환경의 Docker 통일:** 로컬(`make test`)과 CI 모두 `docker compose exec`를 통해 동일한 컨테이너 내부에서 테스트가 돌도록 일치시켰습니다.
- **인프라 대기 및 DB 스키마 초기화:** `docker compose up --wait`로 인프라가 완전히 Health 상태가 된 후 테스트를 시작하며, 실행 직전 `alembic upgrade head`를 통해 빈 DB 에러를 방지했습니다.
- **볼륨 충돌(Race Condition) 우회:** 도커 구동 시 `worker` 컨테이너를 명시적으로 제외(`up -d app db redis`)하여, 로컬 환경 설정(`docker-compose.local.yml`)의 가상환경 마운트 시 발생하는 Symlink 덮어쓰기 에러를 원천 차단했습니다.

---

## Phase 1. 단위 테스트와 통합 테스트의 분리: 외부 API는 어떻게 할 것인가?

테스트 코드를 작성하며 가장 먼저 부딪힌 고민은 "외부 API(SMTP, 공공데이터 등) 연동 로직을 매 테스트마다 진짜로 호출해야 하는가?"였습니다.

외부 API를 직접 호출하면 네트워크 상태에 따라 테스트가 실패할 수 있고(Flaky test), 비용이 발생하거나 Rate Limit에 걸릴 위험이 있습니다. 반면, 모든 것을 가짜(Mock)로 대체하면 실제 환경에서의 작동을 100% 보장하기 어렵습니다.

**해결: 전략적 분리** 

1. **단위/내부 통합 테스트 (Mocking):** 

CI 과정이나 평상시 개발 중에 수시로 돌아가야 하는 테스트입니다. `unittest.mock.patch`를 활용해 Celery 태스크(`send_email_task.delay`) 호출을 가로채어 실제 워커나 외부 인프라로 요청이 넘어가는 것을 차단했습니다. 이를 통해 FastAPI의 응답(200, 422, 429 등) 로직 자체만 빠르고 독립적으로 검증했습니다.

```python
# tests/domains/auth/test_email.py
@pytest.mark.asyncio
async def test_send_email_success(client: AsyncClient, redis: Redis) -> None:
    payload = {"email": "test@example.com", "purpose": "SIGNUP"}

    # Celery 워커(비동기 태스크)로 넘어가는 흐름을 Mocking하여 실제 발송 차단
    with patch("app.domains.auth.service.send_email_task.delay") as mock_task:
        response = await client.post("/api/v1/auth/email/send", json=payload)

        assert response.status_code == status.HTTP_200_OK
        mock_task.assert_called_once() # 백그라운드 태스크가 정확히 1회 호출되었는지 검증
```

2. **외부 연동 통합 테스트 (Marker 적용):** 

실제 네트워크 통신이 필요한 테스트는 `conftest.py`에 `@pytest.mark.integration` 마커를 등록하여 논리적으로 분리했습니다. 평소에는 제외하고, 배포 전이나 필요할 때만 선택적으로 실행(`pytest -m integration`)하도록 구성했습니다.


## Phase 2. 로컬 환경의 딜레마: `uv run pytest` vs `docker compose`

초기 로컬 환경에서는 `uv run pytest`를 통해 파이썬 가상환경에서 직접 테스트를 실행했습니다. DB 연결을 위해 `conftest.py` 내부에 `POSTGRES_HOST="localhost"`와 같은 목업(Mock) 환경변수 딕셔너리를 만들어 테스트 런타임에 주입하는 방식을 썼습니다.

**문제 인식: "내 컴퓨터에서는 되는데?"**

이 방식은 빠르지만 치명적인 단점이 있었습니다. 파이썬 코드만 단독으로 돌다 보니, 실제 운영될 도커(Docker) 인프라 환경과의 괴리가 컸습니다.

**해결: 테스트 실행 환경의 도커화**

실제 인프라와 100% 동일한 흐름을 검증하기 위해, 파이썬 내부의 환경변수 주입 코드를 과감히 지우고 `Makefile`을 수정하여 도커 컨테이너 내부에서 테스트가 돌도록 통일했습니다.

```makefile
test:
	docker compose $(ENV_FILE) $(COMPOSE_BASE) $(COMPOSE_LOCAL) exec app pytest tests/
```


## Phase 3. CI 환경에서의 연쇄 붕괴: `exec` 명령어의 함정

로컬 환경을 성공적으로 도커로 전환한 뒤, 이를 GitHub Actions CI 워크플로우(`ci.yml`)에 동일하게 적용했습니다. 하지만 여기서부터 지옥의 트러블슈팅이 시작되었습니다.

**트러블: `no such container`**

CI 서버에서 `docker compose exec app pytest`가 곧바로 실패했습니다. 로컬은 백그라운드에 이미 컨테이너가 켜져 있지만, 매번 빈 깡통 우분투에서 시작하는 CI 서버는 컨테이너 자체가 없었기 때문입니다.

**해결** 

테스트 실행 전, `-wait` 옵션을 주어 인프라 컨테이너들이 헬스 체크를 통과할 때까지 기다리는 단계를 추가했습니다.

```yaml
- name: Start services
  run: |
    docker compose -f deploy/docker-compose.yml up -d --wait
```


## Phase 4. 환경변수 주입 시점의 역전: 뻗어버린 데이터베이스

컨테이너를 띄우도록 수정하자, 이번엔 PostgreSQL 컨테이너(`db`)가 `POSTGRES_USER variable is not set` 경고와 함께 뻗어버렸습니다.

**에러 로그**

```
time="2026-03-01T10:46:55Z" level=warning msg="The \"POSTGRES_USER\" variable is not set. Defaulting to a blank string."
time="2026-03-01T10:46:55Z" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
...
dependency failed to start: container doongzi-db exited (1)
```

**원인 분석**

과거 `uv run` 시절에는 Pytest가 켜질 때 `conftest.py`가 가짜 환경변수를 넣어주었습니다. 하지만 Docker 구조에서는 **Pytest가 실행되기도 전에 도커 컴포즈가 먼저 DB 컨테이너를 띄워야 합니다.** 즉, 인프라가 뜰 때 가짜 비밀번호조차 없어서 DB 자체가 구동에 실패한 것입니다.

**해결: `.env.example`을 통한 인프라 레벨 환경변수 주입**

파이썬 코드(`conftest.py`)가 환경변수를 책임지는 안티 패턴을 버리고, `.env.example` 파일에 테스트 통과를 위한 필수 더미 값(DB 계정 등)을 명시했습니다. CI 스크립트에서는 `cp .env.example .env.local`로 파일을 복사하여 도커가 이를 읽고 튼튼하게 인프라를 띄우도록 구조를 개선했습니다.

```yaml
- name: Prepare environment variables
  run: cp .env.example .env.local  # 도커가 구동될 때 읽을 더미 설정 파일 생성
```


## Phase 5. CI 속도와 안정성의 줄다리기: `uvx` vs `uv run`

CI 속도를 높이기 위해 패키지 설치(`uv sync`) 단계를 날리고, 일회성 실행 명령어인 `uvx ruff`를 사용해 린트 검사를 시도했습니다.

**에러 로그**

```
Run uvx ruff check . --output-format=github
Would reformat: app/domains/checklist/utils/automatic_issuance_test/registry_issuance.py
1 file would be reformatted, 63 files already formatted
Error: Process completed with exit code 1.
```

**트러블: 로컬은 Pass, CI는 Fail**

로컬에서 포매팅을 맞추고 푸시했는데 CI 서버의 Ruff가 줄바꿈 에러를 뱉었습니다. `uvx`는 버전을 명시하지 않으면 무조건 '가장 최신 버전'의 도구를 다운로드합니다. 로컬의 `uv.lock`에 고정된 버전(예: 0.3.0)과 최신 버전 간의 PEP-8 준수 룰셋 차이 때문에 발생한 문제였습니다.

**해결: 재현성 보장**

CI에서 몇 초를 아끼는 것보다 '팀원과 CI 서버 간의 완벽한 린터 버전 일치'가 훨씬 중요합니다. 다시 `uv sync`를 통해 락파일(`uv.lock`) 기준의 의존성을 설치하고 `uv run ruff`를 실행하여 버전 파편화를 막았습니다.

```yaml
- name: Install dependencies
  run: uv sync --frozen

- name: Lint and Format check with Ruff
  run: |
    uv run ruff check . --output-format=github
    uv run ruff format . --check
```


## Phase 6. 극악의 난이도: 도커 공유 볼륨의 Race Condition

마침내 테스트가 도는가 싶었지만, 도커가 구동되면서 `failed to create symlink: ... file exists`라는 기괴한 에러가 발생했습니다.

**에러 로그**

```
Container doongzi-api  Creating
Container doongzi-worker  Creating
Error response from daemon: failed to create symlink: /var/lib/docker/volumes/deploy_venv_data/_data/bin/python: symlink /usr/local/bin/python3 /var/lib/docker/volumes/deploy_venv_data/_data/bin/python: file exists
```

**원인 분석**

로컬 개발 편의성을 위해 `docker-compose.local.yml`에 가상환경(`.venv`) 폴더를 공유 볼륨(`deploy_venv_data`)으로 잡아두었습니다. CI에서 `up`을 실행하자, **API 컨테이너(`app`)와 비동기 워커 컨테이너(`worker`)가 정확히 같은 밀리초에 하나의 볼륨에 파일을 쓰려고 경쟁(Race Condition)**하다가 충돌한 것입니다.

**해결: 불필요한 자원 제거**

통합 테스트 코드들은 Celery 태스크를 모킹(Mocking)해두었기 때문에, 굳이 워커 컨테이너를 띄울 필요가 없었습니다. 워커를 명시적으로 제외하고 테스트에 필요한 컨테이너(`app`, `db`, `redis`)만 구동하도록 수정했습니다.

```yaml
- name: Start services
  run: |
    # app, db, redis만 구동하여 worker와의 볼륨 충돌을 완벽하게 우회
    docker compose --env-file .env.local -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml up -d --wait app db redis
```


## Phase 7. 텅 빈 데이터베이스와 마이그레이션

마지막으로 테스트 코드가 돌기 시작했지만 **DB 구조가 없다**는 에러가 발생했습니다.

**에러 로그**

```
E   sqlalchemy.exc.ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class 'asyncpg.exceptions.UndefinedTableError'>: relation "user" does not exist
```

**해결: 마이그레이션 실행 및 캐시 무효화**

갓 생성된 DB 컨테이너는 내부에 스키마가 없는 상태입니다. CI 스크립트의 테스트 실행 직전에 `alembic upgrade head` 명령어를 추가했습니다. 더불어 도커 내부의 Pytest 캐시 폴더 생성 권한 오류(`Permission denied`)를 막기 위해 `-p no:cacheprovider`옵션을 추가하여 마침내 통과했습니다.

```yaml
- name: Run DB migrations
  run: |
    docker compose --env-file .env.local -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml exec -T app alembic upgrade head

- name: Run tests
  run: |
    docker compose --env-file .env.local -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml exec -T app pytest -p no:cacheprovider
```

---

## 마치며

새로운 프로젝트를 할 때마다 새로운 고민거리와 배움이 있습니다다. 

이번에는 테스트 환경과 방법에 대한 고민이 새롭게 추가되었습니다. Pytest 라이브러리만 실행하면 끝일 줄 알았던 테스트 환경 구축은, Docker 인프라 생명주기와 CI 러너의 동작 방식, 파일 시스템 볼륨 충돌까지 이해해야 했습니다.