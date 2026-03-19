---
title: "[둥지] 로그인/로그아웃 코드리뷰: 보안 취약점 발굴과 트러블슈팅"
date: 2026-03-09 10:00:00 +0900
categories: [Projects, 둥지]
tags: [FastAPI, Redis, JWT, Security, CodeReview, Troubleshooting, Backend, Python, Auth]
toc: true
comments: true
description: "로그인/로그아웃 API 구현 후 팀원 코드리뷰에서 발굴된 이슈 4개(소셜 계정 500, Refresh Token Race Condition, DB-Redis 불일치, 401 vs 403)와 자체 분석에서 추가로 발견한 예외 처리 허점 2개의 원인과 해결 과정을 정리합니다."
---

로그인/로그아웃 API를 구현한 뒤, 팀원 코드리뷰(TD-147)를 통해 고심각도 이슈 1개와 중간 심각도 이슈 3개를 발굴했습니다. 리뷰를 반영하는 과정에서 자체 코드 분석으로 추가 이슈 2개를 더 발견했습니다. 이 글에서는 각 이슈의 원인, 해결 방식, 설계 근거를 정리합니다.

---

## 미리보기

| 심각도 | 이슈 | 핵심 원인 |
| --- | --- | --- |
| 🔴 HIGH | 소셜 계정 로컬 로그인 시도 시 500 에러 | provider 체크보다 `verify_password()` 먼저 실행 → `None.encode()` AttributeError |
| 🟡 MEDIUM | Refresh Token Rotation 경쟁 상태 | `GET → SET` 분리 연산으로 동시 요청 2개가 모두 통과 |
| 🟡 MEDIUM | 회원가입 DB commit ↔ Redis 삭제 불일치 | commit 성공 후 Redis 장애 시 계정 생성 완료인데 요청이 실패처럼 보임 |
| 🟡 MEDIUM | `/logout` 무토큰 요청 시 401 대신 403 반환 | `HTTPBearer(auto_error=True)` 기본값이 FastAPI 레벨에서 403을 반환 |
| 🔴 HIGH (자체) | `redis.eval()` 예외 미처리 | Lua 스크립트 도입 후 기존 예외 처리 제거됨 |
| 🔴 HIGH (자체) | 롤백 파이프라인이 `except` 블록 안에서 실패 | Redis 장애 시 롤백도 실패하여 원래 예외가 덮어씌워짐 |

---

## 1. 팀원 코드리뷰 이슈

### 이슈 1 [HIGH]: 소셜 계정 로컬 로그인 시도 시 500 에러

#### 원인

`process_login()` 내부에서 유저 존재 여부와 비밀번호 검증을 한 조건문으로 묶어, provider 체크보다 먼저 실행했습니다.

```python
# Before (service.py)
if not user or not verify_password(payload.password, user.password):
    raise InvalidCredentialsException()

if user.provider != ProviderEnum.LOCAL:
    raise SocialLoginAttemptException()
```

소셜 유저는 DB에 `password = NULL`로 저장됩니다. `verify_password()` 내부에서 `user.password.encode("utf-8")`를 실행하는데, `None.encode()`는 `AttributeError`를 발생시키고 FastAPI는 이를 처리하지 못해 **500**을 반환합니다.

테스트에서도 이 문제가 드러나지 않았습니다. 단위/통합 테스트 헬퍼가 `ProviderEnum.GOOGLE`인 경우에도 항상 해시된 비밀번호를 넣고 있었기 때문입니다.

#### 해결

provider 체크를 `verify_password` 호출보다 먼저 수행하도록 조건문을 분리했습니다.

```python
# After (service.py)
if not user:
    raise InvalidCredentialsException()

if user.provider != ProviderEnum.LOCAL:
    raise SocialLoginAttemptException()

if not verify_password(payload.password, user.password):
    raise InvalidCredentialsException()
```

테스트 헬퍼도 소셜 계정 생성 시 `password=None`을 명시하도록 수정했습니다.

```python
# test_login.py - _FakeUser
self.password = get_password_hash("Password123!") if provider == ProviderEnum.LOCAL else None

# test_login_integration.py - _create_local_user
password=get_password_hash(password) if provider == ProviderEnum.LOCAL else None,
```


### 이슈 2 [MEDIUM]: Refresh Token Rotation 경쟁 상태

#### 원인

`reissue_access_token()`이 Redis 연산을 여러 단계의 분리된 `await`로 처리했습니다.

```python
# Before (service.py)
stored_token = await redis.get(f"auth:refresh_token:{user_id}")  # 1. GET
if not stored_token or stored_token != refresh_token:
    raise UnauthorizedException(...)

new_access_token = create_access_token(...)
new_refresh_token = create_refresh_token(...)

await redis.set(...)  # 2. SET
```

동시 요청 2개가 모두 `GET` 단계를 통과한 뒤 각자 새 토큰을 발급하고 `SET`을 실행할 수 있습니다. Refresh Token은 단일 사용 토큰(Single-Use)임에도 **두 요청 모두 유효한 응답을 받는** 경쟁 상태가 발생합니다.

```
요청 A: GET → (통과) ──────────────→ SET(new_token_A) → 200 OK
요청 B: GET → (통과) → SET(new_token_B) ─────────────→ 200 OK  ← 둘 다 통과
```

#### 해결: Lua 스크립트 원자적 연산

`redis.eval()`로 Lua 스크립트를 Redis 서버에 전송하여 실행합니다. Redis는 내부적으로 명령어를 단일 스레드로 처리하므로, Lua 스크립트가 실행되는 동안 다른 클라이언트의 요청이 끼어들 수 없습니다. "토큰 조회 → 비교 → 갱신"이라는 세 단계를 하나의 원자적 연산으로 묶은 것입니다.

```python
# After (service.py)
_ROTATE_TOKEN_SCRIPT = """
local stored = redis.call('GET', KEYS[1])
if stored == false then return 0 end   -- 키 없음 (로그아웃/만료)
if stored ~= ARGV[1] then return -1 end -- 토큰 불일치 (탈취 가능성)
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1  -- 성공
"""

result = await redis.eval(
    _ROTATE_TOKEN_SCRIPT, 1, key,
    refresh_token, new_refresh_token, str(REFRESH_TOKEN_TTL),
)
if result == 0 or result == -1:
    raise InvalidTokenException()
```

두 번째 요청이 도달할 시점에는 이미 첫 번째 요청이 토큰을 교체했으므로, `stored ~= ARGV[1]`(-1)로 차단됩니다.

> **참고: Redis Whitelist vs Blacklist**
>
> - **Whitelist (화이트리스트):** 승인된 토큰만 통과. 발급된 토큰을 Redis에 명시적으로 등록하고, 조회 시 존재하면 유효로 판단합니다. 로그아웃 시 키를 삭제해 즉시 무효화가 가능하며 보안에 유리합니다.
> - **Blacklist (블랙리스트):** 누구나 접근 가능하되, 문제가 생긴 토큰만 등록해 차단합니다. 토큰 자체의 서명만으로 유효성을 판단하기 때문에 즉시 무효화가 어렵습니다.
>
> 둥지에서는 Whitelist 방식을 채택해 `auth:refresh_token:{user_id}` 키로 관리합니다.


### 이슈 3 [MEDIUM]: 회원가입 DB commit ↔ Redis 삭제 불일치

#### 원인

`process_signup()`에서 DB commit 직후 Redis 삭제를 수행하는 구조였습니다.

```python
# Before (service.py)
db.add(new_user)
await db.commit()          # 1. DB에 유저 저장 완료

await redis.delete(verified_key)  # 2. Redis 인증 완료 마커 삭제
```

DB commit 성공 후 Redis 장애가 발생하면 `redis.delete()`가 예외를 던지고, **계정은 생성됐는데 가입 요청이 실패한 것처럼** 보이는 불일치 상태가 됩니다.

#### 해결

Redis 삭제를 `try/except`로 감싸 실패해도 계정 생성 성공으로 처리합니다. 인증 완료 마커(`auth:email_verified:{email}`)는 TTL(30분)이 설정되어 있으므로 삭제에 실패하더라도 시간이 지나면 자동으로 파기됩니다.

```python
# After (service.py)
db.add(new_user)
await db.commit()

try:
    await redis.delete(verified_key)
except Exception:
    # Redis 장애 시에도 계정 생성은 성공으로 처리
    # 인증 완료 마커는 TTL(30분) 만료 시 자동 파기됨
    pass
```

**설계 근거:** 계정 생성 완료가 더 중요한 불변 조건입니다. 인증 마커가 남아있어도 이미 이메일이 DB에 등록됐으므로, 다음 회원가입 시도 시 `EmailAlreadyExistsException`으로 차단됩니다.


### 이슈 4 [MEDIUM]: `/logout` 무토큰 요청 시 401 대신 403 반환

#### 원인

`HTTPBearer()`의 기본값은 `auto_error=True`입니다. `Authorization` 헤더가 없으면 FastAPI가 의존성 주입 단계에서 직접 **403 Forbidden**을 반환하고, `get_current_user_id()` 함수 본체에 도달하지 못합니다.

```python
# Before (dependencies.py)
_bearer = HTTPBearer()  # auto_error=True (기본값)

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    # 헤더 없으면 이 코드에 도달하지 못함 → FastAPI가 403 반환
    ...
```

HTTP 명세상 인증 정보 없는 요청은 **401 Unauthorized**여야 하는데, 테스트도 401을 기대하고 있어 코드·문서·테스트가 모두 맞지 않는 상태였습니다.

#### 해결

`auto_error=False`로 설정해 FastAPI의 자동 에러 반환을 막고, `credentials=None`을 직접 체크해 커스텀 401을 발생시킵니다.

```python
# After (dependencies.py)
_bearer = HTTPBearer(auto_error=False)

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None:
        raise MissingTokenException()  # 401
    ...
```


## 2. 추가 리팩토링: 인증 예외 클래스 세분화

이슈 1~4를 수정하는 과정에서 `UnauthorizedException("문자열 메시지")`로 여러 인증 실패 케이스를 구분하던 코드를 발견했습니다. 문자열로는 호출 의도가 코드에서 드러나지 않고, `isinstance()` 체크나 로깅 시 세분화가 불가능합니다.

### 계층 설계

토큰 관련 예외를 `auth/exceptions.py`에 추가하면 `core/security.py`와 `core/dependencies.py`가 `auth` 도메인을 임포트해야 합니다. 이는 `core → auth` 의존성 역전으로 아키텍처 원칙을 위반합니다. JWT 검증과 Bearer 추출은 인프라 레이어 관심사이므로 `core/exceptions.py`에 추가하는 것이 적절합니다.

```
core/exceptions.py   ← 인프라 예외 (JWT, Bearer)
auth/exceptions.py   ← 비즈니스 예외 (이메일, 비밀번호, 소셜 계정)
```

### 추가된 예외 클래스

```python
# core/exceptions.py — 모두 UnauthorizedException(401) 상속

class MissingTokenException     # Authorization 헤더 없음
class TokenExpiredException     # JWT 서명 만료 (jwt.ExpiredSignatureError)
class InvalidTokenException     # JWT 위변조 또는 Redis 화이트리스트 불일치
class WrongTokenTypeException   # 액세스 토큰 자리에 리프레시 토큰 사용
```

### 적용 위치

| 파일 | Before | After |
| --- | --- | --- |
| `core/security.py` | `UnauthorizedException("토큰이 만료되었습니다.")` | `TokenExpiredException()` |
| `core/security.py` | `UnauthorizedException("유효하지 않은 토큰입니다.")` | `InvalidTokenException()` |
| `core/dependencies.py` | `UnauthorizedException("인증이 필요합니다.")` | `MissingTokenException()` |
| `core/dependencies.py` | `UnauthorizedException("액세스 토큰이 필요합니다.")` | `WrongTokenTypeException()` |
| `auth/service.py` | `UnauthorizedException("유효하지 않은 토큰입니다.")` | `WrongTokenTypeException()` / `InvalidTokenException()` |


## 3. 자체 코드 분석 이슈

코드리뷰 반영 이후 자체 분석에서 추가로 발견된 예외 처리 허점입니다.

### 이슈 A [HIGH]: `redis.eval()` 예외 미처리

#### 원인

이슈 2에서 Lua 스크립트를 도입하면서 기존 `redis.get()` 구조의 예외 처리가 제거됐습니다.

```python
# 수정 전 (service.py) — redis.eval 예외 미처리
result = await redis.eval(...)    # Redis 장애 시 RedisError 발생
if result == 0 or result == -1:   # 이 줄에 도달하지 못해 500 반환
    raise InvalidTokenException()
```

초기 수정본에서 `except redis.exceptions.RedisError`로 작성했는데, `redis`가 모듈이 아니라 함수 파라미터(인스턴스)이므로 `redis.exceptions`가 `AttributeError`를 발생시키는 참조 오류도 있었습니다.

```python
# 잘못된 수정 (service.py)
except redis.exceptions.RedisError as e:  # redis는 모듈이 아닌 인스턴스
    raise InternalServerErrorException()
```

#### 해결

`from redis.exceptions import RedisError`로 직접 임포트하고, 인프라 예외(`RedisError`)와 비즈니스 예외(`InvalidTokenException`) 처리를 `try` 안팎으로 명확히 분리했습니다.

```python
# After (service.py)
try:
    result = await redis.eval(
        _ROTATE_TOKEN_SCRIPT, 1, key,
        refresh_token, new_refresh_token, str(REFRESH_TOKEN_TTL),
    )
except RedisError:
    raise InternalServerErrorException(
        detail="토큰 재발급 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    )

if result == 0 or result == -1:
    raise InvalidTokenException()
```


### 이슈 B [HIGH]: 롤백 파이프라인이 `except` 블록 안에서 실패

#### 원인

`process_email_sending()`의 `except` 블록 안에서 Redis 파이프라인으로 Rate Limit 키를 롤백하는 구조였습니다. 원래 예외가 Redis 장애인 경우 롤백 파이프라인도 같은 이유로 실패하며, 새로 발생한 예외가 원래 예외를 덮어씌웁니다.

```python
# Before (service.py)
except Exception as e:
    async with redis.pipeline() as pipe:  # Redis 장애 중이면 여기서도 예외 발생
        pipe.delete(rate_limit_key)
        ...
        await pipe.execute()              # 원래 예외가 이 예외로 덮어씌워짐

    if isinstance(e, (EmailAlreadyExistsException, ...)):
        raise e
    raise InternalServerErrorException(...)
```

추가로, `raise e`로 모든 예외를 그대로 올릴 경우 `ValueError` 같은 시스템 에러가 `AppBaseException` 전역 핸들러를 통과하지 못해 응답 포맷이 깨질 수 있었습니다.

#### 해결

롤백을 내부 `try/except`로 감싸 롤백 실패가 원래 예외를 덮어쓰지 못하게 하고, `isinstance(e, AppBaseException)` 체크로 비즈니스 예외와 시스템 에러 분기를 명확히 했습니다.

```python
# After (service.py)
except Exception as e:
    try:
        async with redis.pipeline() as pipe:
            pipe.delete(rate_limit_key)
            if "storage_key" in locals():
                pipe.delete(storage_key)
            await pipe.execute()
    except Exception:
        # Redis 장애로 롤백 자체가 실패해도 원래 예외를 우선 처리
        pass

    # 커스텀 비즈니스 예외는 그대로 re-raise (전역 핸들러가 적절한 상태코드로 처리)
    if isinstance(e, AppBaseException):
        raise e

    # 예측하지 못한 시스템/브로커 에러는 500으로 감싸 일관된 응답 포맷 보장
    raise InternalServerErrorException(
        detail="이메일 발송 대기열(Queue) 등록에 실패했습니다. 잠시 후 다시 시도해 주세요."
    )
```

---

## 마치며

코드리뷰 한 차례로 **단순 로직 버그(이슈 1)부터 동시성 보안 취약점(이슈 2), 분산 시스템 불일치(이슈 3), HTTP 명세 오용(이슈 4)**까지 넓은 범위의 문제가 드러났습니다.

특히 이슈 2 해결 과정에서 `redis.eval()` 예외 처리를 놓치는 이슈 A가 추가로 발생한 것처럼, 수정이 새로운 허점을 만들 수 있습니다. 리뷰 반영 후 자체 분석까지 이어가는 습관이 중요함을 다시 한번 확인했습니다.
