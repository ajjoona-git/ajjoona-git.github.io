---
title: "[둥지] FastAPI 비동기 DB 세팅: SQLAlchemy 2.0 세션 관리와 이중 방어 모델링"
date: 2026-02-23 20:30:00 +0900
categories: [Projects, 둥지]
tags: [FastAPI, Python, Backend, SQLAlchemy, Database, Asyncpg, Alembic, Architecture, Docker, TroubleShooting]
toc: true
comments: true
image: /assets/img/posts/2026-02-23-doongzi-fastapi-async-db-sqlalchemy-alembic/1.png
description: "FastAPI의 비동기 성능을 극대화하기 위한 asyncpg 및 SQLAlchemy 2.0 도입기를 공유합니다. 커넥션 풀을 활용한 세션 관리, 데이터 무결성을 위한 이중 방어(Defense in Depth) 패턴, 그리고 Alembic 마이그레이션 트러블슈팅 과정을 상세히 다룹니다."
---

백엔드 애플리케이션의 심장부는 단연 데이터베이스입니다. '둥지(Doongzi)' 프로젝트는 FastAPI의 강력한 비동기 성능을 100% 끌어내기 위해 **비동기 지원 데이터베이스 드라이버(`asyncpg`)와 SQLAlchemy 2.0**을 도입했습니다.

이번 포스트에서는 애플리케이션과 DB를 안전하게 이어주는 세션(`session.py`) 관리 전략부터, 어떠한 외부 접근에도 데이터 무결성을 보장하는 **'이중 방어(Defense in Depth)' 모델링 패턴**, 그리고 Alembic을 활용한 스키마 버전 관리 경험을 공유합니다.

---

## DB 통신망을 구축하다

FastAPI 애플리케이션과 PostgreSQL 데이터베이스 사이의 **'안전한 통신로'이자 '작업 관리자'** 역할을 합니다. 애플리케이션 코드가 데이터베이스에 직접 접근하는 대신, 이 파일을 거쳐서 모든 데이터를 주고받게 됩니다.

![데이터베이스 커넥션 풀링 개념도](/assets/img/posts/2026-02-23-doongzi-fastapi-async-db-sqlalchemy-alembic/2.png)
*데이터베이스 커넥션 풀링 개념도*

### 1. 데이터베이스 연결망 관리 (Engine)

매번 DB에 새로 접속하는 것은 시간이 오래 걸리고 비효율적입니다. `session.py`에 정의된 **엔진(Engine)**은 데이터베이스와의 연결(커넥션)을 여러 개 미리 만들어두고 대기시킵니다. 이를 **커넥션 풀(Connection Pool)**이라고 하며, 트래픽이 몰릴 때 서버가 안정적으로 버틸 수 있게 해줍니다.

### 2. 논리적 작업 단위 묶기 (Session)

세션(Session)은 데이터를 읽고, 쓰고, 수정하는 하나의 논리적인 작업 단위(트랜잭션)를 관리합니다. 파이썬 코드에서 객체를 수정하면 세션이 그 변경 사항을 기억하고 있다가, 안전하다고 판단될 때 데이터베이스에 일괄 적용(Commit)합니다. 중간에 에러가 나면 모든 작업을 취소(Rollback)하여 데이터가 꼬이는 것을 막아줍니다.

### 3. 자원의 안전한 할당과 회수 (`get_db`)

사용자로부터 API 요청이 들어올 때마다, FastAPI는 `get_db` 함수를 호출하여 임시로 쓸 세션을 빌려옵니다. API 응답이 끝나면 함수 내부의 `finally` 블록이 실행되어 세션을 데이터베이스에 안전하게 반납(Close)합니다. 이 과정이 없으면 '메모리 누수'가 발생하여 결국 서버가 다운됩니다.

### `db/session.py`

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import get_settings

# 서버 기동 시점에 설정 객체를 캐싱
settings = get_settings()

# 비동기 데이터베이스 엔진 생성
engine = create_async_engine(
    str(settings.database_url),
    echo=False,           # SQL 쿼리 로그 출력 여부 (개발 시 True로 변경 가능)
    pool_size=10,         # 유지할 기본 커넥션 수
    max_overflow=20,      # 트래픽 폭주 시 추가로 생성할 커넥션 최대치
    pool_recycle=3600,    # 1시간마다 커넥션을 갱신하여 DB 연결 끊김 방지
    pool_pre_ping=True,   # 쿼리 실행 전 커넥션 유효성 사전 검사 (안정성 확보)
)

# 비동기 세션 팩토리 생성
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    데이터베이스 비동기 세션을 생성하고 반환합니다.

    Input:
        없음

    Output:
        AsyncGenerator[AsyncSession, None]: 비동기 데이터베이스 세션 제너레이터

    Exception:
        SQLAlchemyError: 데이터베이스 연결 또는 세션 생성 실패 시 발생할 수 있음

    Description:
        - FastAPI 라우터나 서비스 로직에서 Depends(get_db) 형태로 주입받아 사용합니다.
        - 요청 단위로 새로운 세션을 열고, 처리가 완료되면(finally) 안전하게 세션을 닫아 커넥션 풀로 반환합니다.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
```

## 데이터 검증은 어디서 하지?

데이터베이스 모델링 시 가장 깊게 고민했던 부분은 

*애플리케이션(파이썬) 레벨의 검증만 믿을 것인가, 데이터베이스(PostgreSQL) 레벨에서도 방어할 것인가?*

였습니다. 양쪽 모두에서 무결성을 지키는 **이중 방어(Defense in Depth)** 패턴을 채택했습니다.

### 1. 파이썬 `default` vs DB `server_default`

월세(rent)나 체크리스트 완료 여부(is_checked)처럼 기본값이 필요한 컬럼이 있습니다. 우리는 이 두 가지 속성을 **모두** 사용하기로 결정했습니다.

- **`default=0` (파이썬 레벨)**: 파이썬에서 새 객체를 만들 때 즉시 `0`이 할당됩니다. DB에 쿼리를 날리기 전에도 비즈니스 로직에서 해당 값을 바로 사용할 수 있어 개발 편의성이 뛰어납니다.
- **`server_default="0"` (DB 레벨)**: 파이썬 서버를 거치지 않고 DB 툴에서 직접 데이터를 삽입하거나 마이그레이션을 진행할 때도 빈칸이면 DB가 알아서 `0`을 채워 넣습니다.
    
    (*참고: 순수 SQL 구문으로 전달되어야 하므로 숫자라도 `"0"`처럼 문자열로 감싸서 작성해야 합니다.*)
    

### 2. UUID 생성 주체 위임 (`gen_random_uuid()`)

기존에는 `uuid.uuid4`를 통해 파이썬이 UUID를 생성해 DB에 넣었습니다. 하지만 아키텍처 고도화 과정에서 **PostgreSQL의 내장 함수인 `gen_random_uuid()`**를 사용하도록 변경했습니다.

```python
# 파이썬과 DB 레벨 모두에서 이중 방어로 UUID 생성
id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True), 
    primary_key=True, 
    default=uuid.uuid4, 
    server_default=text("gen_random_uuid()")
)
```

이렇게 `text()` 함수를 활용해 순수 SQL을 전달하면, 데이터베이스 엔진 스스로 고유 식별자를 발급할 수 있어 성능과 범용성이 크게 향상됩니다.

### 3. JSONB 구조 최적화 (`list` vs `dict`)

미충족 사유 등 비정형 데이터를 저장하는 `JSONB` 컬럼의 타입 힌팅을 고민했습니다. 초기엔 `list[dict]` 구조였으나, **특정 에러 코드가 포함되어 있는지 탐색하는 속도(O(1))를 극대화하고 코드를 직관적으로 만들기 위해 `dict[str, Any]` 구조로 변경**했습니다.

## Alembic을 도입하다

아무리 코드를 잘 짜도 실제 DB 테이블과 모양이 다르면 의미가 없습니다. 

**Alembic**은 파이썬 코드로 작성한 SQLAlchemy 모델(예: `User`, `Checklist` 클래스)과 실제 PostgreSQL 데이터베이스의 테이블 구조를 똑같이 맞춰주는 역할을 합니다. 즉, 테이블의 변경 이력을 관리하는 '데이터베이스의 Git(버전 관리 시스템)'이라고 할 수 있습니다.

![Alembic 마이그레이션 워크플로우](/assets/img/posts/2026-02-23-doongzi-fastapi-async-db-sqlalchemy-alembic/1.png)
*Alembic 마이그레이션 워크플로우*

1. **자동 번역 및 스키마 동기화 (`autogenerate`)**
파이썬 코드에 `age = Column(Integer)`라는 속성을 추가하면, Alembic이 기존 DB 상태와 파이썬 코드를 비교하여 `ALTER TABLE users ADD COLUMN age INTEGER;`같은 SQL 명령어를 자동으로 작성해 줍니다.

2. **버전 기록 및 롤백 (Migration History)**
Git에서 커밋을 남기고 과거로 돌아갈 수 있듯, 스키마 구조의 변경 이력을 파이썬 스크립트 파일 형태로 차곡차곡 쌓아둡니다. 배포 후 스키마에 치명적인 문제가 생기면, 명령어 하나로 이전 상태로 안전하게 되돌릴(`Downgrade`) 수 있습니다.

3. **팀 협업과 배포 안정성 확보**
로컬 개발 환경, 테스트 서버, 운영 서버의 데이터베이스 구조가 제각각 틀어지는 것을 막아줍니다. 마이그레이션 파일만 공유하면 팀원 모두가 동일한 DB 뼈대를 오차 없이 구축할 수 있습니다.

### 마이그레이션 적용 및 명령어

```bash
# asyncpg라는 비동기 드라이버를 사용하고 있기 때문에 
# -t async 옵션을 붙여서 비동기 전용 템플릿으로 생성합니다.
alembic init -t async alembic

# 파이썬 모델을 읽어 현재 DB 상태와의 차이점을 계산하고, 
# 변경 지시서(마이그레이션 스크립트)를 생성합니다.
alembic revision --autogenerate -m "add_user_model"

# 생성된 지시서를 DB에 실제로 실행하여 테이블을 생성하거나 수정합니다.
alembic upgrade head
```

### [트러블슈팅] Docker 컨테이너 내 환경변수 로드 문제

도커(Docker) 환경에서 Alembic 스크립트를 생성할 때, 컨테이너 내부에 `JWT_SECRET_KEY` 등 필수 환경변수가 주입되지 않아 Pydantic 검증 에러가 발생하며 앱이 뻗는 문제가 있었습니다.

단순히 로그를 지우는 수준이 아니라 **앱이 에러 없이 구동되도록 만들기 위해**, Makefile의 `docker compose` 명령어에 `--env-file .env.local` 옵션을 명시했습니다. 환경변수를 컨테이너로 통째로 밀어 넣는 방식으로 구조를 개편함으로써 해결했습니다.

```makefile
# Makefile 공통 변수화 패턴 적용
COMPOSE_BASE  := -f $(COMPOSE_DIR)/docker-compose.yml
COMPOSE_LOCAL := -f $(COMPOSE_DIR)/docker-compose.local.yml
ENV_FILE      := --env-file .env.local

revision:
	docker compose $(ENV_FILE) $(COMPOSE_BASE) $(COMPOSE_LOCAL) exec app alembic revision --autogenerate -m "$(m)"

```