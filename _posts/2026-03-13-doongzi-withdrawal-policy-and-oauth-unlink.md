---
title: "[둥지] 결제 시스템 도입에 따른 회원 탈퇴 정책 고도화 및 OAuth 연동 해제 전략"
date: 2026-03-13 10:00:00 +0900
categories: [Projects, 둥지]
tags: [Backend, Architecture, SoftDelete, OAuth, Privacy, Database]
toc: true
comments: true
image: /assets/img/posts/2026-03-13-doongzi-withdrawal-policy-and-oauth-unlink/1.png
description: "결제 시스템 도입으로 인해 변경된 둥지 서비스의 회원 탈퇴 정책을 소개합니다. Hard Delete에서 Soft Delete로의 전환 이유, 데이터 마스킹 전략, 그리고 Google, Kakao, Naver 등 각 소셜 프로바이더별 맞춤형 연동 해제(Unlink) 플로우를 상세히 공유합니다."
---

서비스에 '결제 시스템'이 도입된다는 것은 백엔드 아키텍처, 특히 **회원 탈퇴 정책**에 변화를 요구합니다. 기존에는 유저가 탈퇴하면 데이터를 깔끔하게 지워주면 그만이었지만, 이제는 법적 의무와 데이터 정합성 사이에서 균형을 찾아야 합니다.

이번 포스트에서는 '둥지' 프로젝트가 결제 시스템을 도입하며 겪은 탈퇴 정책의 변화와, 복잡한 소셜 로그인(OAuth) 연동 해제 과정을 어떻게 풀어냈는지 공유합니다.

---

## 결제 시스템이 바꿔놓은 것: Hard Delete에서 Soft Delete로

결제 시스템이 없는 기존 환경에서는 **개인정보보호법(제21조)의 파기 원칙**에 따라, 탈퇴 후 30일의 유예 기간을 거쳐 유저 데이터를 영구 삭제(Hard Delete)했습니다.

하지만 결제 시스템이 도입되면 **전자상거래법**에 따라 대금결제 등의 거래 기록을 5년 동안 의무적으로 보존해야 합니다. 여기서 딜레마가 발생합니다. 결제 내역(`Payment`)은 유저(`User`)를 외래키(FK)로 참조하고 있는데, 유저를 물리적으로 지워버리면 참조 무결성이 깨져 분쟁 발생 시 결제 이력을 추적할 수 없게 됩니다.

따라서 정책을 다음과 같이 전면 개편했습니다.

* **영구 보존 (Soft Delete):** User 레코드를 삭제하지 않고 `deleted_at` 필드에 현재 시간을 기록하여 논리적으로만 삭제 처리합니다.
* **외래키 보호:** Payment 테이블의 외래키는 `ondelete="RESTRICT"`로 설정하여, 시스템이나 개발자가 실수로 User를 Hard Delete 하려 할 때 DB 단에서 강력하게 차단하도록 설계했습니다.
* **개인정보 즉시 파기 (Masking):** 데이터는 남기되 식별은 불가능하도록, 탈퇴 즉시 이메일은 `None`으로 덮어씌우고 닉네임은 `"탈퇴한유저#<uuid 앞 8자리>"` 형태로 마스킹 처리합니다.


## 탈퇴 정책: 두 가지 케이스

회원 탈퇴는 결제 시스템 도입 여부에 따라 법적 의무와 데이터 처리 방식이 달라집니다. 먼저 두 케이스의 차이를 한눈에 비교해봅니다.

| 항목 | Case 1 (결제 없음) | Case 2 (결제 있음) |
|---|---|---|
| 법적 보존 의무 | 없음 (즉시 파기 원칙) | 거래 기록 최대 5년 |
| email 마스킹 | 선택 (재가입 허용 여부에 따라) | 즉시 None |
| nickname 마스킹 | 불필요 | `"탈퇴한유저#<uuid>"` |
| User hard delete | 30일 후 | 없음 (영구 보존) |
| Nest cascade 삭제 | User hard delete 시 자동 | 별도 정책 필요 |
| Payment FK | 해당 없음 | `RESTRICT` |
| 스케줄러 대상 | User (30일 후) | Payment (5년 후) |
| 탈퇴 전 확인 API | 불필요 | 불필요 (이용 시점 단건 결제, 미완료 상태 없음) |


### Case 1. 결제 시스템 없음

**법적 근거**
- **개인정보보호법 제21조**: 처리 목적 달성 시 지체 없이 파기 원칙
- 전자상거래법상 거래 기록 보존 의무 **해당 없음** (무료 서비스)

**탈퇴 시점 처리**

| 항목 | 처리 방법 |
|---|---|
| `User.deleted_at` | `now()` 설정 (soft delete) |
| `User.email` | 즉시 재가입 허용 여부에 따라 선택 (아래 참고) |
| `User.nickname` | 그대로 보존 (랜덤 생성값이라 개인 식별 정보 아님) |
| Redis refresh_token | 즉시 삭제 (로그아웃 처리) |
| 로그인 차단 | `deleted_at IS NOT NULL` 체크로 즉시 차단 |

이메일 처리는 재가입 허용 여부에 따라 선택합니다.
- **즉시 재가입 불가 (단순)**: `email` 그대로 보존, unique constraint 유지
- **즉시 재가입 허용**: `email = None` (PostgreSQL에서 NULL은 unique constraint 통과)

**보관 및 파기**

| 대상 | 처리 |
|---|---|
| `User` 레코드 | soft delete 후 **30일 유예, 이후 hard delete** |
| `Nest` 및 하위 데이터 | `cascade="all, delete-orphan"` → User hard delete 시 자동 연쇄 삭제 |
| `Issue.user_id` | `ondelete="SET NULL"` → User hard delete 시 NULL로 변경, 이슈 기록은 익명으로 보존 |

> **30일 유예 이유**: 실수 탈퇴 복구를 위한 UX 안전망 (업계 표준)

Celery beat 스케줄러가 매일 새벽 3시에 `deleted_at <= now() - INTERVAL '30 days'` 조건을 만족하는 유저를 Hard Delete합니다.


### Case 2. 결제 시스템 있음

**법적 근거**
- **개인정보보호법 제21조**: 개인정보 파기 원칙
- **전자상거래법 제6조**: 거래 기록 보존 의무

| 보존 대상 | 보존 기간 |
|---|---|
| 계약·청약철회 기록 | 5년 |
| 대금결제·재화 공급 기록 | 5년 |
| 소비자 불만·분쟁 기록 | 3년 |
| 표시·광고 기록 | 6개월 |

**탈퇴 시점 처리**

| 항목 | 처리 방법 |
|---|---|
| `User.deleted_at` | `now()` 설정 (soft delete) |
| `User.email` | `None` 으로 마스킹 (개인정보 즉시 파기 원칙 준수) |
| `User.nickname` | `"탈퇴한유저#<user.id 앞 8자>"` 로 마스킹 (unique constraint 충돌 방지) |
| Redis refresh_token | 즉시 삭제 (로그아웃 처리) |
| 로그인 차단 | `deleted_at IS NOT NULL` 체크로 즉시 차단 |

**보관 및 파기**

| 대상 | 처리 |
|---|---|
| `User` 레코드 | soft delete 후 **hard delete 없이 영구 보존** |
| `Nest` 및 하위 데이터 | User soft delete와 무관하게 보존 (cascade 미적용) or 별도 정책 수립 |
| `Payment` 레코드 | **5년 보존 후 파기** (Celery beat 스케줄러) |
| `Issue.user_id` | `ondelete="SET NULL"` → 이슈 기록은 익명으로 보존 |

> **User를 hard delete하지 않는 이유**: Payment FK가 User UUID를 참조하므로, User를 지우면 FK가 깨져 분쟁 시 결제 이력 추적 불가. Soft delete된 User 레코드를 영구 보존하면 FK가 항상 유효합니다.

Payment 테이블의 FK는 실수에 의한 Hard Delete도 DB 레벨에서 막도록 `RESTRICT`로 설정합니다.

```python
class Payment(Base):
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT")
    )
```

Celery beat 스케줄러가 매일 새벽 3시에 `Payment.created_at <= now() - INTERVAL '5 years'` 조건을 만족하는 결제 기록만 Hard Delete합니다. User 레코드는 유지됩니다.


### 탈퇴 의사 재확인

탈퇴 의사 재확인 모달은 프론트엔드 책임입니다. API가 호출된 시점 자체가 이미 확인이 완료된 것이므로 `{"confirm": true}` body는 불필요합니다. 마찬가지로 탈퇴 후 어디로 이동할지는 프론트가 결정할 일이므로, 백엔드가 `/login`을 하드코딩해서 내려주는 `redirect_url`도 책임 분리 위반입니다.

`deleted_at IS NOT NULL` 로그인 차단 체크는 아래 모든 인증 경로에 동일하게 적용되어야 합니다.
- `process_login` (로컬)
- `_register_or_login_social_user` (구글, 카카오, 네이버 공통)

#### `DELETE /api/v1/users/me`

```
[Request]
Authorization: Bearer {access_token}
body: 없음

[Response 200 OK]
{
  "status": 200,
  "message": "OK",
  "data": {
    "is_deleted": true
  }
}

[Response 401 Unauthorized]
액세스 토큰이 없거나 유효하지 않은 경우

[Response 400 Bad Request]
이미 탈퇴 처리된 계정인 경우 (deleted_at IS NOT NULL)

[Response 409 Conflict]  ← 결제 시스템 있는 경우에만
미결제 구독이 존재하여 탈퇴 불가한 경우 (has_unpaid = true)
```

> 결제는 이용 시점 단건 거래이므로 미완료 상태가 없습니다. 환불은 탈퇴와 별개로 처리되므로 탈퇴 전 별도의 확인 API는 필요하지 않습니다.


## 프로바이더별 맞춤형 소셜 연동 해제(Unlink) 플로우

단순히 우리 DB에서만 유저를 지운다고 끝나는 것이 아닙니다. 유저가 다시 로그인 창을 열었을 때 소셜 계정이 자동으로 연결되는 것을 막으려면, 각 프로바이더(Google, Kakao, Naver)의 정책에 맞춘 **연동 해제(Unlink)** 작업이 필수적입니다.

### ① 카카오 (Kakao): 가장 깔끔한 백엔드 주도 플로우

![카카오 탈퇴 플로우](/assets/img/posts/2026-03-13-doongzi-withdrawal-policy-and-oauth-unlink/1.png)
*카카오 탈퇴 플로우*

카카오는 서버 사이드에서 Admin Key를 이용해 제어할 수 있습니다. 유저의 `access_token`이 없어도 DB에 저장된 `social_id`만으로 강제 연동 해제가 가능하여, 세 프로바이더 중 가장 깔끔한 플로우를 가집니다.

1. 클라이언트가 `DELETE /api/v1/users/me` 호출
2. 백엔드에서 Admin API(`POST /v1/user/unlink`)를 호출하여 카카오 연동 강제 해제
3. 내부 DB Soft Delete 및 Redis 토큰 파기

### ② 구글 (Google): 프론트엔드 주도 플로우

우리 백엔드는 구글의 토큰을 보관하지 않습니다. 구글은 OIDC 기반 웹 서비스를 위해 프론트엔드에서 직접 연동을 끊을 수 있는 직관적인 JS SDK를 제공합니다. 덕분에 백엔드는 외부 API 호출 없이 내부 처리만 담당합니다.

1. 프론트엔드 탈퇴 모달에서 `google.accounts.id.revoke` 함수를 호출하여 브라우저 단에서 연동 즉시 해제
2. 해제 성공 콜백을 받으면 백엔드로 `DELETE` API 호출
3. 백엔드는 외부 연동 로직 없이 내부 DB Soft Delete만 수행

### ③ 네이버 (Naver): 프론트와 백엔드의 릴레이 플로우

네이버는 연동 해제를 위해 **반드시 유효한 소셜 `access_token`을 요구**하는 엄격한 보안 정책을 가집니다. 백엔드에 토큰을 저장해두지 않으므로, 프론트가 토큰을 확보해 백엔드로 넘겨주는 릴레이 방식으로 처리합니다.

1. 프론트엔드가 네이버 SDK를 통해 유효한 토큰 확보
2. 백엔드 `DELETE` 호출 시 Body에 네이버 토큰 포함하여 전달
3. 백엔드는 전달받은 토큰으로 네이버 해제 API(`grant_type=delete`) 호출
4. 1회용으로 사용된 토큰은 즉시 메모리에서 폐기 후 내부 DB Soft Delete 수행

*(참고: 로컬 가입 유저는 소셜 연동이 없으므로 외부 API 호출 없이 내부 DB만 처리합니다.)*

---

## 완벽한 익명화와 데이터 무결성을 위한 과제

정책을 세우고 나니 백엔드 개발자로서 두 가지 치명적인 사이드 이펙트(Side Effect)가 눈에 밟혔습니다. 이를 해결하기 위한 추가적인 방어 로직을 도입했습니다.

### 1. 텍스트 필드 데이터 클렌징 (Scrubbing)

이메일과 닉네임을 마스킹하더라도, 유저가 자유롭게 입력할 수 있는 `memo` 컬럼이나 사진(`image_url`)에 "집주인 김철수(010-1234-5678)" 같은 잠재적인 개인정보가 숨어있을 위험이 큽니다. 진정한 의미의 익명화(Anonymization)를 달성하기 위해, 탈퇴 트랜잭션 내에서 이러한 자유 입력 필드들을 일괄적으로 빈값(`""`)으로 초기화해 버리는 **데이터 스크러빙(Scrubbing)** 로직을 추가 적용했습니다.

### 2. 전역 필터링(Global Filter)을 통한 고스트 데이터 차단

가장 놓치기 쉬운 부분입니다. Soft Delete는 `DELETE` 쿼리가 아닌 `UPDATE` 쿼리를 발생시키므로, 기존 DB 모델에 설정해 둔 `ondelete="CASCADE"`나 `SET NULL` 옵션이 **전혀 동작하지 않습니다.** 즉, 탈퇴한 유저가 올린 방 매물이나 이슈 데이터가 DB에 온전히 남아있게 됩니다.

이를 방지하기 위해 전체 매물 검색 API나 통계 기능 등 데이터를 조회하는 모든 Repository 레이어에 **`User.deleted_at.is_(None)` 조건을 전역 필터링(Global Filter)으로 강제 적용**하여 고스트 데이터의 노출을 원천 차단했습니다.

---

## 마치며

회원 탈퇴는 사용자가 우리 서비스를 떠나는 마지막 순간입니다. 이 순간을 법적 기준에 맞춰 투명하게 처리하고, 보이지 않는 곳의 찌꺼기 데이터까지 완벽하게 정돈하는 것이 백엔드 시스템의 신뢰도를 결정짓는다고 생각합니다.
