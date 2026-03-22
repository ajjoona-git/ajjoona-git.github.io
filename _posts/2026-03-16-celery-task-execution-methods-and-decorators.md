---
title: "Celery 태스크 실행 메서드 정리: delay vs send_task, shared_task"
date: 2026-03-16 10:00:00 +0900
categories: [Tech, Backend]
tags: [Python, Celery, Asynchronous, TaskQueue, Decorator, Architecture]
toc: true
comments: true
description: "Celery를 활용한 비동기 백엔드 구축 시 자주 혼동되는 태스크 실행 메서드(.delay() vs .apply_async() vs send_task())와 데코레이터(@celery_app.task vs @shared_task)의 차이점 및 동작 원리를 실무 관점에서 상세히 정리합니다."
---

파이썬 환경에서 비동기 작업을 처리할 때 Celery는 사실상 표준으로 사용됩니다. 하지만 Celery를 프로젝트에 도입하다 보면, 태스크를 실행하는 다양한 메서드들과 데코레이터들 사이에서 어떤 것을 선택해야 할지 혼란스러울 때가 많습니다.

이번 포스트에서는 '둥지' 프로젝트의 비동기 아키텍처를 구축하며 정리한 Celery 태스크 실행 방식과 데코레이터의 차이점을 명확히 짚어봅니다.

---

##  태스크 실행 메서드

### `.delay()` vs `.apply_async()`

가장 기본적으로 태스크를 백그라운드 워커(Worker)로 던지는 두 가지 메서드입니다. 
결론부터 말하자면 **`.delay()`는 `.apply_async()`의 단축 메서드(Shortcut)**입니다.

```python
# 두 코드는 브로커에 동일한 메시지를 발행합니다.
send_verification_email.delay(email, code)
send_verification_email.apply_async(args=[email, code])
```

### 그렇다면 언제 `.apply_async()`를 써야 할까요? 

실행 시점이나 라우팅 큐(Queue) 등 **세밀한 옵션 제어**가 필요할 때 사용합니다.

```python
# 10초 뒤에 실행 예약 (countdown)
send_verification_email.apply_async(args=[email, code], countdown=10)

# 특정 시간에 실행 예약 (eta)
send_verification_email.apply_async(args=[email, code], eta=datetime.utcnow() + timedelta(minutes=5))

# 특정 워커 큐로 라우팅 지정 (queue)
send_verification_email.apply_async(args=[email, code], queue="high_priority")
```

| 메서드 | 실행 위치 | 특징 |
| :--- | :--- | :--- |
| **`.delay(*args)`** | Worker (비동기) | 가장 간편한 호출 방식 (`apply_async` 단축형) |
| **`.apply_async(args, **options)`** | Worker (비동기) | 실행 시점(countdown, eta), 큐(queue), 재시도 옵션 등 부여 가능 |
| **직접 호출 `func()`** | 현재 프로세스 (동기) | Celery 브로커를 거치지 않고 일반 파이썬 함수처럼 실행. 단위 테스트 시 유용함 |


## 결합도를 낮추는 `send_task()`

앞선 방식들은 태스크 함수 자체를 현재 파일로 `import` 해와야 사용할 수 있습니다. 
반면, `celery_app.send_task()`는 **함수의 이름(문자열 경로)만으로** 태스크를 발행합니다.

```python
# 1. .delay() 방식 (함수 직접 import 필수)
from app.domains.auth.tasks import send_verification_email
send_verification_email.delay(email, code)

# 2. send_task() 방식 (import 없이 문자열 경로만으로 호출)
celery_app.send_task("app.domains.auth.tasks.send_verification_email", args=[email, code])
```

### `send_task()`는 언제 유용할까?
API 서버와 Celery Worker 서버가 **물리적으로 완전히 분리되어 서로 코드를 공유하지 않는 마이크로서비스(MSA) 환경**에서 빛을 발합니다. API 서버에는 `tasks.py` 파일이 없어도, 문자열 이름만 브로커(Redis)로 던져주면 코드를 가진 Worker가 이를 받아서 실행합니다.

| 구분 | `.delay()` / `.apply_async()` | `send_task()` |
| :--- | :--- | :--- |
| **태스크 함수 import** | 필수 | 불필요 |
| **타입 힌트 / 자동완성** | IDE 지원됨 | 지원 안 됨 (문자열) |
| **오류(오타) 발견 시점** | 컴파일 타임 | 런타임 (실행해봐야 앎) |
| **서로 다른 코드베이스** | 구축 불가 | 구축 가능 |


## `@celery_app.task` vs `@shared_task`

Celery 애플리케이션 객체를 태스크에 바인딩하는 두 가지 데코레이터입니다.

### `@celery_app.task`의 순환 참조 위험
특정 Celery 앱 인스턴스에 직접 묶는 방식입니다.

```python
from app.core.celery import celery_app

@celery_app.task
def send_email(...):
    ...
```

이 방식은 치명적인 단점이 있습니다. `celery_app`이 정의된 메인 파일(`celery.py`)은 태스크들을 찾기 위해 `tasks.py`를 탐색(autodiscover)해야 하는데, 정작 `tasks.py`는 `celery_app` 객체를 가져오기 위해 다시 `celery.py`를 `import`해야 하는 **순환 참조(Circular Import)**에 빠지기 쉽습니다.

### `@shared_task`의 유연성
`@shared_task`는 앱 인스턴스를 직접 참조하지 않습니다. 대신, **Worker가 구동되면서 초기화되는 시점에 현재 활성화된 Celery 앱 인스턴스를 스스로 찾아 자동으로 바인딩**됩니다.

```python
from celery import shared_task # 특정 앱 인스턴스 import 불필요!

@shared_task
def send_email(...):
    ...
```

| 구분 | `@celery_app.task` | `@shared_task` |
| :--- | :--- | :--- |
| **앱 인스턴스 import** | 필요 | 불필요 |
| **순환 import 위험** | 높음 (구조 복잡해짐) | 없음 |
| **바인딩 시점** | 데코레이터 적용 시 (Import 시점) | Worker 앱 초기화 시 |
| **재사용성** | 낮음 (해당 앱에 종속됨) | 높음 (다른 프로젝트에서도 재사용 용이) |


## task 함수는 어떻게 메서드를 갖게 될까?

우리가 만든 평범한 파이썬 함수(`def send_email`)가 어떻게 갑자기 `.delay()`나 `.apply_async()` 같은 객체 지향적인 메서드를 갖게 되는 것일까요? 

`@shared_task`나 `@celery_app.task` 데코레이터는 일반 함수를 **Celery `Task` 클래스의 인스턴스로 교체**합니다.

```python
# @shared_task 데코레이터의 내부 동작 원리를 풀어 쓰면:
send_verification_email = shared_task(send_verification_email)

# 이제 send_verification_email은 함수가 아니라 'Task 인스턴스'가 되었습니다!
# -> Task.__call__() 이 원래 작성한 함수의 비즈니스 로직을 실행하고,
# -> Task.delay() 가 브로커(Redis)에 작업 지시 메시지를 발행합니다.
```



결과적으로 데코레이터가 붙은 함수는 아래와 같은 기능을 가진 Task 클래스의 인스턴스 객체로 우리에게 돌아오게 됩니다.

```text
일반 파이썬 함수
       ↓ @shared_task 장착
Celery Task 객체로 변환
 ├── .delay()         — 비동기 실행 (가장 많이 씀)
 ├── .apply_async()   — 비동기 예약 실행 (옵션 포함)
 ├── .run()           — 원래 로직 동기 실행
 ├── .retry()         — 에러 발생 시 재시도 트리거
 └── .name            — "app.domains.auth.tasks.send_verification_email"
```

---

## 마치며

Celery의 겉모습만 보면 마법처럼 동작하는 것 같지만, 내부를 들여다보면 파이썬의 데코레이터 패턴과 객체 지향 프로그래밍의 원리가 아주 우아하게 결합되어 있음을 알 수 있습니다. 

비동기 백엔드 아키텍처를 고민하는 분들께 이 글이 Celery의 개념을 잡는 데 작은 도움이 되기를 바랍니다.
