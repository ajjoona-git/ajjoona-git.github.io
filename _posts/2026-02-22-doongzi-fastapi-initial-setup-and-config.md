---
title: "[둥지] FastAPI 프로젝트 초기 설정: Config와 Main 구성하기"
date: 2026-02-22 18:40:00 +0900
categories: [Project, 둥지]
tags: [Backend, FastAPI, Python, Pydantic, Configuration, EnvironmentVariables, Settings]
toc: true
comments: true
image: /assets/img/posts/2026-02-22-doongzi-fastapi-initial-setup-and-config/1.png
description: "FastAPI 애플리케이션의 뼈대인 main.py(CORS, Health Check) 초기화 과정과 Pydantic Settings를 활용한 타입 안전한 환경 변수(.env) 관리 및 분리 전략을 공유합니다."
---


이번 포스트에서는 **FastAPI 프로젝트의 초기 설정**과 **환경 변수 관리 전략**을 공유합니다. 특히 Pydantic Settings를 활용한 타입 안전한 설정 관리와 환경별 설정 파일 분리 방법을 다룹니다.

---

## 1. FastAPI 앱 초기화: `main.py`

FastAPI 애플리케이션의 시작점인 `app/main.py`는 프로젝트의 뼈대를 구성합니다.

### ① FastAPI 인스턴스 생성

FastAPI 앱을 생성할 때 메타데이터를 함께 설정하면, 자동으로 생성되는 API 문서(Swagger UI)에 프로젝트 정보가 표시됩니다.

```python
# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title="Doongzi Backend API",
    description="부동산 계약 체크리스트 및 권리분석 자동화 서비스 백엔드 API",
    version="1.0.0",
)
```

이 정보는 `/docs` 경로에서 확인할 수 있는 Swagger UI의 헤더 부분에 표시됩니다.

### ② CORS 미들웨어 설정

```python
# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: 운영 환경에서는 실제 도메인으로 제한해야 함
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

프론트엔드와 백엔드가 다른 도메인에서 실행될 때 발생하는 CORS(Cross-Origin Resource Sharing) 문제를 해결하기 위해 미들웨어를 추가합니다.

### ③ 헬스 체크 엔드포인트

```python
# Health Check API (서버 및 로드밸런서 상태 확인용)
@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, str]:
    """
    서버 및 로드밸런서 상태를 확인합니다.

    Input:
        없음

    Output:
        Dict[str, str]: 상태(status)와 확인 메시지(message)

    Exception:
        없음

    Description:
        - 도커 컨테이너, AWS 로드밸런서 등에서 서버가 정상적으로 응답하는지 주기적으로 찔러보는 용도의 엔드포인트입니다.
    """
    return {"status": "ok", "message": "Doongzi API server is running smoothly."}

```

서버가 정상적으로 동작하는지 확인하기 위한 간단한 헬스 체크 엔드포인트를 구성합니다. 이는 로드 밸런서나 모니터링 도구에서 활용됩니다.

![/health](/assets/img/posts/2026-02-22-doongzi-fastapi-initial-setup-and-config/2.png)
*/health*

![/docs](/assets/img/posts/2026-02-22-doongzi-fastapi-initial-setup-and-config/1.png)
*/docs (Swagger UI)*

## 2. 환경 설정 관리: config.py

프로젝트의 모든 설정을 한 곳에서 관리하는 것이 중요합니다. `app/core/config.py`에서 Pydantic의 `BaseSettings`를 활용하여 타입 안전한 설정 관리를 구현합니다.

### 왜 Pydantic Settings를 사용하나?

Python에서 환경 변수를 읽으면 모든 값이 문자열(`str`)로 반환됩니다. 이를 `int`나 `bool`로 변환하고, 필수 값이 누락되었는지 검증하는 작업은 번거롭고 실수하기 쉽습니다.

Pydantic Settings는 이 모든 과정을 자동화합니다:

- **자동 타입 변환:** 환경 변수 `PORT=5432`를 자동으로 `int`로 변환
- **필수 값 검증:** 기본값이 없는 필드는 반드시 환경 변수에 있어야 함
- **IDE 자동완성:** 설정 객체의 속성에 타입 힌트가 있어 개발 경험 향상

### Settings 클래스 구성

```python
class Settings(BaseSettings):
    """
    애플리케이션 전역 설정을 관리하는 환경변수 클래스입니다.

    Input:
        없음 (.env 파일 또는 OS 환경변수에서 자동으로 로드)

    Output:
        없음

    Exception:
        pydantic.ValidationError: 필수 환경변수가 누락되었거나 타입이 맞지 않을 때 발생

    Description:
        - 데이터베이스, Redis, AWS S3, 외부 스크래핑(등본 발급) 정보를 관리합니다.
        - .env.example 파일에 명시된 환경변수 규격을 엄격하게 따릅니다.
    """

    # 애플리케이션 기본 정보
    APP_NAME: str = "Doongzi API"
    APP_VERSION: str = "1.0.0"

    # [MODE] 운영 환경 구분 (local, dev, prod)
    ENV_MODE: str = "local"

    # [AWS] local 환경에서만 필요하므로 Optional 처리
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # [Database]
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432

    # [AWS S3]
    S3_BUCKET_NAME: str

    # [Redis]
    REDIS_HOST: str
    REDIS_PORT: int = 6379

    # [등본 발급 자동화]
    IROS_PHONE_NUMBER: str
    IROS_TEMPORARY_PASSWORD: str
    PAYMENT_CODE_1: str
    PAYMENT_CODE_2: str
    PREPAYMENT_PASSWORD: str

    # [건축물대장 발급 자동화]
    BUILDING_REGISTER_SERVICE_KEY: str

    @property
    def database_url(self) -> str:
        """
        데이터베이스 연결을 위한 비동기(asyncpg) URL 문자열을 생성합니다.

        Input:
            없음

        Output:
            str: SQLAlchemy 비동기 접속용 URL 반환

        Exception:
            없음

        Description:
            - 환경변수로 주입받은 POSTGRES_* 접속 정보들을 조합하여 DSN을 반환합니다.
        """
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # .env.local 파일에서 설정을 읽어올 수 있도록 Pydantic 설정
    model_config = SettingsConfigDict(
        env_file=".env.local", 
        env_file_encoding="utf-8", 
        case_sensitive=True, 
        extra="ignore",
    )
```

### Settings 클래스 설계 원칙 3가지

**💡 1. `.env` 파일의 값이 무조건 1순위 (우선 적용)**

`config.py`에 `DB_USER: str = "postgres"`라고 적어두었더라도, `.env.local` 파일에 `DB_USER=doongzi_admin`이라고 적혀있다면 코드의 값은 무시되고 `.env` 파일의 값이 덮어쓰기(Override) 됩니다.

**💡 2. 값이 안 적힌 변수는 필수(Required) 조건**

코드에 `DB_PASSWORD: str`처럼 `=` 기호 뒤에 기본값을 주지 않은 변수들이 있습니다. 이 변수들은 `.env` 파일에 이 값이 없으면 서버를 아예 켜지 말라는 뜻입니다. 보안상 중요한 비밀번호나 API 키는 실수로라도 기본값이 들어가면 안 되기 때문에 이렇게 설정합니다.

**💡 3. 변수명은 `.env` 키와 완벽히 일치해야 함**

Pydantic이 자동으로 값을 찾아 매핑해주기 때문에, `config.py`의 변수명(예: `DB_HOST`)과 `.env.local` 파일 안의 키 이름은 반드시 똑같아야 합니다.

## 3. Settings 인스턴스 생성과 활용

### 전역 인스턴스 vs 의존성 주입 함수

Settings를 사용하는 방법은 두 가지입니다.

### ① 전역 인스턴스 (`settings`)

```python
# app/core/config.py
# 전역에서 settings 객체를 import 해서 사용할 수 있도록 인스턴스 생성
settings = Settings()
```

해당 `Settings` 클래스의 인스턴스(여기서는 `settings` 객체)를 생성하면 Pydantic이 환경 변수를 읽고 데이터를 변환하고 검증합니다. 그래서 그 `settings` 객체를 사용할 때는 선언한 타입의 데이터를 갖게 됩니다(예: `POSTGRES_PORT`는 `int`가 됩니다).

`app.core.config.settings`는 앱이 켜질 때 한 번 만들어지는 **전역 객체**입니다. `main.py`의 `FastAPI(title=settings.APP_NAME)`처럼 전역 스코프에서 즉시 값이 필요할 때 사용합니다.

### ② 의존성 주입 함수 (`get_settings()`)

```python
# app/main.py

@lru_cache()
def get_settings() -> Settings:
    """
    애플리케이션 설정을 반환하는 함수입니다.

    Input:
        없음

    Output:
        Settings: 애플리케이션 설정 객체

    Exception:
        없음

    Description:
        - FastAPI의 Depends()를 통해 의존성 주입 시 사용하기 위한 설정 반환 함수입니다.
        - @lru_cache를 사용하여 매번 파일을 읽지 않고 메모리에 캐싱된 인스턴스를 반환하여 성능을 최적화합니다.
    """
    return Settings()

```

`@lru_cache` 데코레이터를 사용하고 있으므로, `Settings` 객체는 최초 호출 시 딱 한 번만 생성됩니다.

`get_settings()`는 나중에 각 API 엔드포인트(라우터) 내부에서 의존성 주입(`Depends`)으로 안전하게 설정값을 꺼내 쓰고 싶을 때 사용할 수 있습니다.

FastAPI 공식 문서에서도 적극 권장하는 방식입니다.

## 4. 환경별 설정 파일 분리 전략

로컬 개발 환경과 운영 환경은 DB 주소, API 키 등이 다릅니다. 하나의 `.env` 파일로 관리하면 실수로 운영 DB를 로컬에서 건드릴 위험이 있습니다.

### 동적 .env 파일 선택

```python
# OS 환경변수에서 현재 운영 환경을 읽어와서 .env 파일 결정
current_env = os.getenv("ENV_MODE", "local")
env_filename = f".env.{current_env}"

```

"지금 내가 실행된 환경이 어디인지"를 파악해서 바라보는 `.env` 파일의 이름을 **동적으로 바꾸도록** 코드를 수정합니다.

이렇게 하면 로컬에서 돌릴 때는 `.env.local`을 찾고, 개발 서버에서는 `.env.dev`를 찾게 됩니다!

### 환경별 파일 구조

- **`.env.local`**: 로컬 개발 환경용 설정 (DB: localhost, 테스트용 API 키)
- **`.env.dev`**: 개발 서버 환경용 설정 (개발 DB, 스테이징 API 키)
- **`.env.prod`**: 운영 서버 환경용 설정 (운영 DB, 실제 API 키)
- **`.env.example`**: 깃허브에 올리는 예시 파일 (실제 값은 제거)

이렇게 환경을 분리하면 `ENV_MODE` 환경 변수 하나만 바꿔주면 자동으로 적절한 설정 파일을 불러오게 됩니다.

---

## 마치며

이제 **"타입 안전하게 설정을 관리하고, 환경별로 설정 파일을 분리한"** FastAPI 프로젝트의 기초를 갖추었습니다.

다음 포스트에서는 이 설정을 활용하여 데이터베이스 연결을 구성하고, 실제 API 엔드포인트를 구현하는 과정을 다루겠습니다.

### 레퍼런스

https://fastapi.tiangolo.com/ko/advanced/settings/