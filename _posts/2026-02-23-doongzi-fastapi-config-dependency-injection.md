---
title: "[둥지] FastAPI 환경 변수 관리: 전역 객체 대신 get_settings()와 DI를 선택한 이유"
date: 2026-02-23 21:20:00 +0900
categories: [Projects, 둥지]
tags: [Backend, FastAPI, Python, Pydantic, DependencyInjection, Testing, Architecture]
toc: true
comments: true
description: "FastAPI 프로젝트에서 환경 변수를 관리할 때 전역 객체 임포트 방식이 유발하는 강한 결합과 테스트 오염 문제를 분석하고, 의존성 주입(DI) 및 @lru_cache를 활용해 유연한 아키텍처를 구축한 과정을 공유합니다."
---


FastAPI 프로젝트를 세팅하면서 환경 변수(`.env`)를 관리하는 방식을 두고 깊은 고민에 빠졌다. 초기에는 가장 직관적인 전역 변수 임포트 방식을 사용했지만, 테스트 자동화와 프로젝트 확장성을 고려하면서 구조를 변경하게 된 과정을 기록해 둔다.

---

## 가장 쉽고 직관적인 전역 변수 방식

처음 앱을 세팅할 때는 `config.py`에 아래와 같이 전역 객체를 만들어 두고, 필요한 곳에서 임포트해서 썼다.

```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str

settings = Settings() # 전역 인스턴스 생성
```

사용할 때는 `from app.core.config import settings`로 가져다 쓰면 되니 코드가 아주 직관적이고 짧았다. 하지만 로컬에서 `make test`를 위해 별도의 테스트 DB를 구성하려고 하니 문제가 보이기 시작했다.

## 상태 오염과 강한 결합(Tight Coupling) 우려

전역 객체를 사용하면 파이썬 프로세스가 켜져 있는 내내 설정값이 메모리에 유지된다. 테스트 코드를 작성할 때 이 전역 객체의 `database_url`을 임시로 변경하면, 다른 테스트에 영향을 주는 **상태 오염**이 발생할 수 있다.

또한, 내부 서비스 로직(`services/`)이나 API 라우터에서 전역 변수를 직접 임포트해 쓰면 코드가 `config.py`에 강하게 결합된다. 유닛 테스트를 짤 때 설정값을 바꿔치기(Mocking)하려면 `mock.patch`를 써서 메모리를 강제 조작해야 하는 번거로움이 있었다.

결국, 테스트 환경의 독립성을 위해 **새로운 인스턴스를 만들어 주입하는 방식(`get_settings`)**을 고려하게 되었다.

### 인스턴스를 매번 생성하면 I/O 성능이 떨어지지 않을까?

새로운 인스턴스를 주입하는 구조로 바꾸려다 보니 현실적인 걱정이 생겼다.

> *"서버 사양이 빡빡한데, API 요청이 들어올 때마다 `Settings()`를 호출해서 인스턴스를 만들면 디스크 I/O와 연산 낭비가 너무 심하지 않을까?"*
> 

해결책은 의외로 간단했다. 파이썬 내장 라이브러리인 **`@lru_cache`**를 사용하는 것이다.

```python
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

이렇게 설정하면 앱 기동 후 최초 1회만 `.env` 파일을 읽어 객체를 생성하고, 이후 수만 번의 요청에는 메모리에 캐싱된 객체를 반환한다. 성능 저하 걱정이 해결됐다.

### 어차피 도커 컨테이너 환경인데 모킹(Mocking)이 꼭 필요해?

가장 고민했던 지점이다.

> *"어차피 로컬이든 CI/CD 서버든 도커 컨테이너를 그대로 띄워서 테스트할 텐데, 굳이 가짜 DB 주소를 위한 모킹이나 의존성 주입이 필요한가?"*
> 

맞는 말이다. 통합 테스트 위주의 환경이라면 운영과 똑같은 DB 컨테이너를 띄우고 CI 환경 변수를 주입하는 것이 가장 확실하다.

그럼에도 불구하고 **`get_settings() + Depends` 조합을 최종 선택한 이유**는 결국 **'설계의 유연성'** 때문이다. 특정 API 로직만 떼어내서 가볍게 유닛 테스트를 돌리고 싶을 때, 강하게 결합된 전역 변수는 발목을 잡는다. FastAPI가 제공하는 `app.dependency_overrides`를 활용하면 운영 코드는 1줄도 수정하지 않고 우아하게 설정값을 덮어쓸 수 있다.

## 최종 도입한 아키텍처

결과적으로 테스트의 유연성을 확보하고 강한 결합을 피하기 위해 **의존성 주입(DI) 방식**을 채택했다.

**[API 엔드포인트 적용 예시]**

```python
from fastapi import APIRouter, Depends
from app.core.config import Settings, get_settings

router = APIRouter()

@router.get("/example")
async def example_api(
    # Depends를 통해 강한 결합 없이 설정값 주입
    settings: Settings = Depends(get_settings) 
):
    return {"db_url": settings.database_url}
```

- **성능:** `@lru_cache`로 I/O 병목 해결
- **테스트:** `dependency_overrides`로 완벽한 격리 가능
- **유지보수:** 컴포넌트 간 결합도 감소

초기에 구조를 잡을 때 타이핑이 조금 더 들어가더라도, 나중에 프로젝트가 커졌을 때 겪을 리팩토링 비용을 생각하면 확실히 가치 있는 투자라고 생각한다.