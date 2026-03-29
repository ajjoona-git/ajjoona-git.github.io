---
title: "[둥지] Redis 파이프라인과 Celery 예외 처리: 분산 환경에서 데이터 일관성 지키기"
date: 2026-03-01 10:00:00 +0900
categories: [Project, 둥지]
tags: [FastAPI, Redis, Celery, Exception, Backend, Transaction, Rollback, Architecture, Troubleshooting]
toc: true
comments: true
image: /assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/2.png
description: "Redis 파이프라인(transaction=True)을 활용한 상태 동기화부터, Celery 비동기 작업 실패 시 발생하는 상태 불일치를 해결하기 위한 보상 트랜잭션(Compensating Transaction)과 on_failure 훅 패턴을 공유합니다."
---

이메일 인증 코드를 발송하는 API를 개발한다고 가정해 봅시다. 시스템은 두 가지 작업을 수행해야 합니다.

1. **Redis에 데이터 저장:** 어뷰징 방지를 위한 '1분 재발송 제한 키'와 '인증 코드 키'를 저장합니다.
2. **Celery에 작업 위임:** 실제 이메일 발송이라는 무거운 작업을 백그라운드 워커에 넘깁니다.

만약 1번(Redis)은 성공했는데 2번(Celery 발송)이 실패한다면 어떻게 될까요? 유저는 이메일을 받지도 못했는데, 1분 동안 재시도조차 할 수 없는 최악의 경험을 하게 됩니다.

이번 포스트에서는 이러한 분산 환경의 **상태 불일치(State Inconsistency)** 문제를 Redis 파이프라인과 Celery의 예외 처리 아키텍처로 어떻게 방어했는지 공유합니다.

---

## 1. Redis Pipeline: 원자성과 네트워크 최적화

보통 Redis에 명령을 보낼 때는 **"명령어 전송 -> 처리 -> 응답 수신"**의 과정(RTT, Round Trip Time)을 거칩니다. 명령어가 2개라면 이 과정을 2번 반복해야 합니다.

**Redis Pipeline**은 클라이언트가 여러 명령어를 큐(Queue)에 쌓아두었다가 단 한 번의 네트워크 통신으로 뭉쳐서 보내는 기술입니다.

우리 프로젝트의 이메일 발송 로직에서는 파이프라인에 `transaction=True` 옵션을 부여하여 사용했습니다.

```python
# app/domains/auth/services.py

async with redis.pipeline(transaction=True) as pipe:
    # 1. 명령어들을 로컬 큐에 예약 (실제 서버 전송 X)
    pipe.set(rate_limit_key, "1", ex=EMAIL_SEND_RATE_LIMIT)
    pipe.set(storage_key, payload, ex=ttl)
    
    # 2. execute() 호출 시점에 묶인 명령어들이 서버로 일괄 전송
    await pipe.execute()
```

### 왜 `transaction=True`인가?

- **데이터 일관성 보장:** '발송 제한 적용(Rate Limit)'과 '인증 코드 저장'은 반드시 **동시에 성공하거나 동시에 실패**해야 합니다.
    1. `rate_limit_key` 설정: "이 유저는 방금 메일을 보냈음" 기록 (어뷰징 방지)
    2. `storage_key` 설정: "이 이메일의 인증 코드는 123456임" 기록 (실제 인증 데이터)
- **원자성(Atomicity):** `transaction=True`를 설정하면 내부적으로 `MULTI`와 `EXEC` 명령어를 사용합니다. 즉, 파이프라인 안에 묶인 명령어들이 중간에 다른 클라이언트의 간섭 없이 연속적으로 실행됨을 보장하여 상태 불일치를 1차적으로 방지합니다.

### 이렇게 하면 뭐가 좋은가?

- **네트워크 성능 최적화**: 명령어가 많아질수록 RTT가 줄어들어 응답 속도가 비약적으로 빨라집니다.
- **비즈니스 무결성**: '인증 코드 존재'와 '발송 제한 적용'이라는 두 가지 상태를 동기화하여 서비스의 신뢰도를 높입니다.
- **가독성**: 비즈니스적으로 연관된 여러 Redis 조작을 하나의 `with` 블록으로 묶어 코드의 의도를 명확히 드러냅니다.


## 2. 분산 환경의 딜레마: Redis는 성공했는데 Celery가 실패한다면?

Redis 저장은 성공적으로 끝났는데, 바로 다음 줄에 있는 Celery 태스크 발행(`delay()`)에서 에러가 발생하면 어떻게 될까요? 이를 완벽히 방어하려면 실패 지점에 따라 두 가지 방어선이 필요합니다.

### 방어선 1. API 서버 측 실패 방어 (보상 트랜잭션)

**상황:** Celery 브로커(Redis/RabbitMQ) 연결 오류 등으로 `delay()` 호출 자체가 실패하여 큐에 들어가지도 못한 경우. 유저는 "1분 뒤에 시도하라"는 제한은 걸렸는데 정작 메일은 받지 못하는 상태가 됩니다.

**해결:** 이미 실행된 Redis 작업을 수동으로 되돌리는 **보상 트랜잭션(Compensating Transaction)** 로직이 필요합니다.

`try...except` 블록을 활용하여 Celery 호출이 실패할 경우 Redis에 저장된 데이터를 수동으로 삭제(Rollback 대용)하는 로직을 추가합니다.

```python
# app/domains/auth/services.py

async def process_email_sending(...):
    # ... (Redis 파이프라인 실행 완료) ...

    try:
        # Celery 태스크 발행
        send_email_task.delay(email=email, purpose=purpose.value, payload=payload)
    except Exception as e:
        # [보상 트랜잭션] Celery 실패 시 Redis 키 수동 삭제
        # 유저가 즉시 재시도할 수 있도록 롤백 대용으로 상태를 복구함
        async with redis.pipeline() as pipe:
            pipe.delete(rate_limit_key)
            pipe.delete(storage_key)
            await pipe.execute()
        
        raise AppBaseException(status_code=500, detail="이메일 발송 큐 등록에 실패했습니다.")
```

### (참고) Redis 트랜잭션 vs PostgreSQL 트랜잭션**

Redis의 트랜잭션은 RDBMS처럼 강력한 `ROLLBACK` 명령어를 지원하지 않습니다. 에러가 발생한 명령어만 실패하고 나머지 명령어는 그대로 실행됩니다. 따라서 애플리케이션 레벨에서 위와 같이 보상 트랜잭션을 직접 구현해 주는 것이 필수적입니다.

| **구분** | **Redis (MULTI/EXEC)** | **PostgreSQL (ACID)** |
| --- | --- | --- |
| **원자성 (Atomicity)** | 명령어들이 순차적으로 실행됨을 보장하지만, 중간 실패 시 이전 명령어를 되돌리지 않음. | 전체 성공 또는 전체 실패(All-or-Nothing)를 완벽히 보장. |
| **롤백 (Rollback)** | 공식적인 롤백 명령어가 없음. (`DISCARD`는 실행 전 취소일 뿐임) | `ROLLBACK` 명령어를 통해 이미 실행된 데이터 변경을 이전 상태로 복구. |
| **격리성 (Isolation)** | 단일 스레드 기반이므로 트랜잭션 도중 다른 클라이언트의 명령어가 끼어들지 못함. | MVCC(다중 버전 동시성 제어) 등을 통해 복잡한 격리 수준(Isolation Level) 제공. |


### 방어선 2. Worker 측 실행 실패 방어 (Custom Task Hook)

**상황:** 태스크는 큐에 잘 들어갔으나, 메일 서버(SMTP) 장애 등으로 인해 백그라운드 워커에서 실제 발송에 실패하는 경우.

**해결:** 이때는 API 서버가 개입할 수 없으므로, **Celery의 `on_failure` 훅(Hook)**을 사용해야 합니다.

`on_failure`는 태스크가 브로커(Redis)에 정상적으로 전달되어 워커(Worker)가 실행을 시작한 뒤, **실행 과정에서 예외가 발생했을 때** 워커 내부에서 동작합니다.

공통 처리를 위해 `AuthTask`라는 베이스 클래스를 만들어 활용했습니다.

```python
# app/domains/auth/tasks.py

from celery import Task

class AuthTask(Task):
    """인증 관련 비동기 태스크의 공통 실패 처리를 담당하는 베이스 클래스"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """태스크 실행 최종 실패 시 Redis에 저장된 제한 데이터를 정리합니다."""
        if args:
            email = args[0]
            # 비동기 환경이 아닐 경우 동기 Redis 클라이언트 사용
            redis_client.delete(f"auth:email_verify:{email}")
            redis_client.delete(f"auth:rate_limit:{email}")
```

이 패턴을 적용하면 향후 `@celery_app.task(base=AuthTask)` 한 줄만 붙여주어도 실패 시 Redis 상태 롤백 로직이 일괄 적용되어 코드 중복이 획기적으로 줄어듭니다.


## 3. 실제 테스트 및 로그 검증

### Celery on_failure 예외 처리 테스트

정말 의도한 대로 동작하는지 검증하기 위해, `.env.local`의 SMTP 비밀번호를 일부러 틀린 값으로 바꾼 뒤 메일 발송 API를 호출해 보았습니다.

**[Celery Worker 로그]**

```python
doongzi-api     | "POST /api/v1/auth/email/send HTTP/1.1" 200 OK
doongzi-worker  | Task auth.send_email_task[...] received
doongzi-worker  | Task auth.send_email_task[...] retry: Retry in 0s: SMTPAuthenticationError(535, b'5.7.8 Username and Password not accepted.')
doongzi-worker  | Task auth.send_email_task[...] raised unexpected: SMTPAuthenticationError(...)
...
doongzi-worker  | smtplib.SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted.')
```

![Redis 적재 상태](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/9.png)
*Redis 적재 상태*

**[분석 결과]**

1. API 서버는 200 OK를 응답하고 즉시 통신을 종료했습니다.
2. Celery Worker가 백그라운드에서 SMTP 인증 실패를 겪고 재시도(`retry`)를 수행합니다.
3. 재시도 횟수를 모두 소진하여 최종 실패(`raised unexpected`) 판정이 납니다.
4. **결과:** 바로 이 시점에 우리가 정의한 `AuthTask.on_failure`가 남몰래 동작하여 Redis의 제한 키들을 싹 지워주었습니다(Rollback).
5. 덕분에 사용자는 1분을 기다리지 않고 오류 수정 후 **즉시 재전송을 요청할 수 있게 되었습니다.**

### Rate Limit 예외 처리 테스트

1분 이내에 여러 번의 요청을 보냈을 경우, **429 Too Many Requests** 응답을 뱉어냅니다.

![API 응답](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/8.png)
*API 응답*

![Celery 로그](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/7.png)
*Celery 로그*

### 잘못된 이메일 형식 예외 처리 테스트

올바른 이메일 형식이 아닌 경우, **422 Unprocessable Entity** 응답을 뱉어냅니다.

![API 응답](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/6.png)
*API 응답*

![Celery 로그](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/5.png)
*Celery 로그*

### 성공 시나리오

1. API 응답

![API 응답](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/4.png)
*API 응답*

2. 실제 메일함

![실제 메일함](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/3.png)
*실제 메일함*

3. Celery 로그

![celery 로그](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/2.png)
*celery 로그*

4. Redis 적재 상태

![Redis 적재 상태](/assets/img/posts/2026-03-01-redis-pipeline-celery-failure-handling/1.png)
*Redis 적재 상태*

---

## 마치며

이메일 발송 하나를 구현할 때도 **'네트워크는 언제든 실패할 수 있다'**는 전제 하에 설계해야 합니다.

- **API 서버 단:** `try-except`를 통한 지연 발송 실패 방어 (Redis 보상 트랜잭션)
- **Worker 단:** `on_failure` 훅을 통한 실행 실패 방어 (Custom Task)

이 이중 방어 구조를 통해 데이터 정합성을 지키고, 사용자에게는 매끄러운 경험을 제공하는 견고한 비동기 아키텍처를 완성할 수 있었습니다.