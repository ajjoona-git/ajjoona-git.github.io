---
title: "[둥지] FastAPI 비동기 환경의 테스트 아키텍처 구축기"
date: 2026-03-08 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Pytest, SQLAlchemy, AsyncIO, Testing, Celery, Backend, Python, Integration]
toc: true
comments: true
description: "비동기 FastAPI + SQLAlchemy 환경에서 이벤트 루프 충돌과 트랜잭션 오염 없이 통합 테스트를 수행하는 방법을 공유합니다. NullPool, Savepoint 기반 롤백, dependency_overrides를 활용한 테스트 샌드박스 구축과 단위/통합 테스트 역할 분담 전략을 다룹니다."
---

비동기(Async) 기반의 FastAPI와 SQLAlchemy를 활용하여 백엔드 서버를 개발하다가, '테스트 환경 구축'을 어떻게 하면 좋을 지 고민하게 되었습니다. 실제 DB I/O를 발생시키며 검증하는 통합 테스트는 이벤트 루프 충돌과 트랜잭션 오염 때문에 까다롭습니다.

이러한 한계를 극복하고 안전한 샌드박스를 구축하기 위해 적용한 고급 테스트 아키텍처의 원리와, 단위/통합 테스트의 명확한 역할 분담 전략을 공유합니다.

---

## 1. 비동기 환경과 트랜잭션 롤백의 통제

안전한 통합 테스트를 위해서는 "비동기 환경에서의 완벽한 격리"와 "테스트 후 흔적을 남기지 않는 롤백"이 필요합니다. 이를 세 가지 단계로 나누어 통제했습니다.

### ① 비동기 이벤트 루프 격리와 `NullPool`
파이썬의 비동기 작업은 '이벤트 루프' 위에서 돌아갑니다. `pytest-asyncio`는 테스트 간의 독립성을 위해 테스트 함수마다 완전히 새로운 이벤트 루프를 생성하고 파기합니다.
이때 DB 엔진을 전역(Global)으로 선언하면 이 엔진은 첫 번째 테스트의 이벤트 루프에 귀속되어, 두 번째 테스트 실행 시 `RuntimeError`가 발생합니다. 이를 해결하기 위해 `db_session` 픽스처(Fixture) 내부에서 매번 새로운 `create_async_engine`을 호출하도록 구성했습니다. 여기에 성능 최적화를 위한 커넥션 풀링을 강제로 끄는 `NullPool` 옵션을 더해, 테스트 종료와 동시에 커넥션이 깔끔하게 해제되도록 강제했습니다. 보통 SQLAlchemy는 성능을 위해 커넥션을 끊지 않고 모아두는 '풀링(Pooling)'을 하기 때문입니다.

### ② 가짜 커밋을 만들다 (`Savepoint`)
통합 테스트 중에 DB에 데이터가 들어가더라도 테스트 종료 시점에는 반드시 롤백(Rollback)되어야 합니다. 서비스 로직(`process_signup` 등) 내부에는 이미 `await db.commit()`이 명시되어 있어, 이것이 실제로 동작하면 영구 저장이 발생합니다.
이를 방지하기 위해 `connection.begin()`으로 거대한 트랜잭션을 열고, 세션 생성 시 `join_transaction_mode="create_savepoint"` 옵션을 부여했습니다. 이 옵션이 켜진 세션에서는 로직 내부의 `commit()`이 실제 커밋이 아닌 트랜잭션 내부의 **임시 저장점(Savepoint)**으로 동작합니다. 테스트 종료 후 픽스처가 `await transaction.rollback()`을 호출하면 거대한 트랜잭션이 통째로 취소되어 완전히 사라집니다.

```python
@pytest_asyncio.fixture
async def db_session():
    """
    Input:
        없음

    Output:
        AsyncSession: 실제 DB에 연결되지만 테스트 종료 시 항상 롤백되는 안전한 세션

    Exception:
        없음

    Description:
        - 매 테스트마다 NullPool 기반의 새 엔진을 생성하여 이벤트 루프 충돌을 방지합니다.
        - join_transaction_mode="create_savepoint"를 통해 앱 내부의 commit()을 Savepoint로
          전환하여 테스트 종료 시 전체 트랜잭션을 롤백, 데이터 오염 없이 실제 DB를 검증합니다.
    """

    # 1. 매 테스트마다 해당 루프에 종속되는 새로운 엔진 생성 (NullPool 필수)
    engine = create_async_engine(
        str(settings.database_url), echo=False, poolclass=NullPool
    )

    async with engine.connect() as connection:
        transaction = await connection.begin()

        # 2. join_transaction_mode="create_savepoint"를 통해
        # 앱 내부나 테스트 코드에서 호출되는 commit()을 진짜 commit이 아닌 Savepoint로 전환!
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

        yield session

        # 3. 테스트 종료 후 안전하게 롤백 및 세션 종료
        await session.close()
        await transaction.rollback()

    # 4. 엔진 찌꺼기 폐기
    await engine.dispose()

```

### ③ FastAPI 의존성 가로채기 (`dependency_overrides`)
안전한 세션을 만들었더라도 실제 라우터가 이를 쳐다보지 않으면 소용이 없습니다. `client_with_db` 픽스처에서 `app.dependency_overrides[get_db] = lambda: db_session`을 선언하여 라우터가 DB 세션을 요청할 때, 원래 코드를 무시하고 우리가 방금 만든 '롤백이 보장된 안전한 테스트 세션'을 대신 꽂아 넣어줍니다. 서비스 로직은 실제 DB에 커밋한다고 인지하지만, 사실은 안전하게 쳐진 롤백 샌드박스 내부에서 동작하게 됩니다.

```python
@pytest_asyncio.fixture
async def client_with_db(redis, db_session):
    """
    Input:
        redis (Redis): 테스트 격리용 Redis 클라이언트
        db_session (AsyncSession): 롤백 보장 DB 세션

    Output:
        AsyncClient: get_db, get_redis가 실제 인프라로 교체된 통합 테스트용 HTTP 클라이언트

    Exception:
        없음

    Description:
        - get_db, get_redis 의존성을 실제 DB/Redis로 교체하여 모킹 없는 엔드투엔드 테스트를 지원합니다.
        - DB 세션은 db_session 픽스처가 관리하므로 테스트 종료 시 자동 롤백됩니다.
    """
    # get_db 의존성을 Rollback 되는 테스트 세션으로 교체!
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

```


## 2. 단위 테스트와 통합 테스트의 명확한 역할 분담

테스트 환경이 구축되었다면 검증 범위를 명확히 나누어야 합니다. 둥지에서는 두 테스트의 목표와 방식을 철저히 분리했습니다.

### 단위 테스트 (Unit Test)

- **목표:** 외부 시스템(DB, Redis)이 정상 동작한다고 가정했을 때, 비즈니스 로직(If-else, 계산식 등)이 정확히 동작하는지 검증합니다.
- **동작 방식:** 실제 DB나 Redis를 연결하지 않고, `AsyncMock`을 활용해 "DB에 중복된 이메일이 없다"는 식의 가상 상황(Mocking)을 연출합니다.
- **확인할 수 있는 것:**
    - **조건문 및 예외 분기:** 생년월일을 계산해서 만 14세 미만이면 `UnderAgeSignupException`을 정확히 던지는가?
    - **함수 호출 여부 (Behavior Verification):** 로직이 끝난 뒤 `db.add()`와 `db.commit()` 함수가 '실행(Called)'되었는가? Redis의 키를 삭제하는 `await redis.delete()` 코드를 타긴 탔는가?
- **확인할 수 없는 것:**
    - 실제로 데이터가 DB에 예쁘게 들어갔는지는 모릅니다. (가짜 DB에 던졌기 때문)
    - API의 HTTP 응답 코드(201, 400 등)를 모릅니다. (`router.py`를 거치지 않고 `service.py`의 함수만 직접 실행했기 때문)

### 통합 테스트 (Integration Test)

- **목표:** 클라이언트의 API 호출부터 Pydantic 검증, DB/Redis 적재까지 전체 파이프라인이 하나의 유기체로 잘 작동하는지 검증합니다.
- **동작 방식:** `httpx.AsyncClient`를 이용해 실제 API URL을 호출하며, 트랜잭션 롤백이 적용된 실제 DB와 Redis를 사용합니다.
- **확인할 수 있는 것:**
    - **API 호출 및 응답 비교 (Router & Schema):** Pydantic 정규식(특수문자 누락 등)에 걸렸을 때 `422 Unprocessable Content`와 정확한 에러 메시지가 튀어나오는가? 정상 가입 시 `201 Created`가 떨어지는가?
    - **실제 DB 적재 (Service & DB):** API 응답이 끝난 뒤, 테스트 코드에서 `SELECT` 쿼리를 날려봤을 때 내가 방금 보낸 유저(이메일, 닉네임)가 실제로 DB에 존재하는가? 비밀번호는 평문이 아니라 Bcrypt로 잘 암호화되어 들어갔는가?
    - **실제 Redis 키 조작 (Service & Redis):** 가입 로직이 성공적으로 끝난 후, 테스트 코드에서 `await redis.get("auth:email_verified:...")`를 해봤을 때 데이터가 정말로 삭제(None)되었는가?

> **Swagger(실제 운영) vs 통합 테스트의 흐름 차이**
> 
> - **실제 운영:** API 요청 ➔ 라우터 ➔ 로직 ➔ DB INSERT ➔ **COMMIT (영구 저장)** ➔ 201 응답
> - **통합 테스트:** API 요청 ➔ 라우터 ➔ 로직 ➔ DB INSERT ➔ **SAVEPOINT (가짜 커밋)** ➔ SELECT 검증 ➔ **ROLLBACK (영구 삭제)** ➔ 테스트 종료


## 3. 특수 케이스: Celery Worker의 테스트 전략

회원가입 로직과 연결된 이메일 전송 API(`/email/send`)에는 비동기 메시지 큐인 Celery Worker 호출(`send_email_task.delay()`)이 포함되어 있습니다.

이 경우 API 통합 테스트를 돌릴 때마다 실제 이메일이 발송되는 것을 막기 위해 두 레이어로 나누어 테스트합니다.

1. **통합 테스트 레이어:** `conftest.py`에서 Celery 설정을 `task_always_eager = True`로 덮어씌워 큐 대기 없이 즉시 실행하게 하거나, `delay` 함수를 Mocking하여 API가 작업 지시서(Task)를 메시지 큐에 정상적으로 던졌는지만 확인합니다.
2. **워커 전용 테스트:** 메일을 발송하는 `tasks.py` 내부 로직은 별도의 테스트 파일로 분리하여, SMTP 서버와의 통신을 Mocking한 뒤 템플릿 렌더링 로직 등을 독립적으로 검증합니다.

