---
title: "[모아톤] 뱃지 시스템 구현: 기획부터 트러블슈팅까지"
date: 2025-12-23 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Django, Vue.js, Troubleshooting, Serializer, Frontend, Gamification, Refactoring, Async]
toc: true 
comments: true
image: /assets/img/posts/2025-12-23-moathon-badge-system/14.png
description: "저축의 지루함을 덜어줄 게이미피케이션 요소인 '뱃지 리워드 시스템'을 기획하고, 이를 구현하는 과정에서 발생한 데이터 누락 및 비동기 렌더링 문제를 해결한 트러블슈팅 로그입니다."
---

이번 포스팅에서는 '모아톤(Moathon)' 프로젝트의 핵심 게이미피케이션 요소인 **뱃지 시스템**을 소개하고, **"모아톤 상세 페이지에서 유저의 뱃지 도감(전체 뱃지 현황)을 불러오고 렌더링하는 과정"**에서 발생한 연쇄적인 문제들과 해결 과정을 정리해 본다.

단순히 "뱃지를 획득했다"는 사실을 넘어, **"아직 획득하지 못한 뱃지"를 보여줌으로써 수집 욕구를 자극**하는 것이 이번 구현의 주요 과제였다.

---

## 뱃지 리워드 시스템

'저축'이라는 행위는 자칫 지루해지기 쉽다. 이를 보완하기 위해 **마라톤(Marathon)** 컨셉을 차용하여, 사용자의 활동에 따라 보상을 제공하는 **뱃지 시스템**을 설계했다.

뱃지는 크게 **진행률(Track)**, **성취(Achieve)**, **소셜(Social)** 세 가지 카테고리로 분류된다.

### 카테고리별 획득 조건

**진행률 보상 (Track)**

모아톤의 진행 상황에 따라 자동으로 지급되는 뱃지다. 마라톤 코스를 완주하는 여정을 시각화했다.

| 뱃지 이름 | 설명 | 획득 조건 | 뱃지 이미지 |
| --- | --- | --- | --- |
| **첫 번째 숨 고르기** | 순조로운 출발입니다. | 목표 25% 달성 | ![badge_track_25.png](/assets/img/posts/2025-12-23-moathon-badge-system/13.png)|
| **반환점 터치** | 이제 돌아갈 수 없어요. | 목표 50% 달성 | ![badge_track_50.png](/assets/img/posts/2025-12-23-moathon-badge-system/12.png)|
| **막판 스퍼트!** | 고지가 코앞입니다. | 목표 75% 달성 |![badge_track_75.png](/assets/img/posts/2025-12-23-moathon-badge-system/11.png)|
| **완주 트로피** | 축하합니다! | 목표 100% 달성 |![badge_track_100.png](/assets/img/posts/2025-12-23-moathon-badge-system/10.png)|

**성취 보상 (Achieve)**

저축 습관 형성을 독려하기 위해 저축에 성공했을 때 지급되는 뱃지다.

| 뱃지 이름 | 획득 조건 | 뱃지 이미지 |
| --- | --- | --- |
| **시작이 반** | 모아톤 서비스 가입 | ![badge_achieve_start.png](/assets/img/posts/2025-12-23-moathon-badge-system/9.png)|
| **티끌 모아 태산** | 첫 번째 모아톤 생성 | ![badge_achieve_deposit.png](/assets/img/posts/2025-12-23-moathon-badge-system/8.png)|
| **작심삼일 탈출** | 모아톤 3일 이상 유지 | ![badge_achieve_3days.png](/assets/img/posts/2025-12-23-moathon-badge-system/7.png)|
| **프로 완주러** | 모아톤 3회 이상 완주 | ![badge_achieve_3moathons.png](/assets/img/posts/2025-12-23-moathon-badge-system/6.png)|
| **억만장자의 꿈** | 36개월 이상 장기 모아톤 시작 | ![badge_achieve_billionaire.png](/assets/img/posts/2025-12-23-moathon-badge-system/5.png)|


**소셜 보상 (Social)**

유저 간의 상호작용을 활성화하기 위한 소셜 뱃지다.

| 뱃지 이름 | 획득 조건 | 뱃지 이미지 |
| --- | --- | --- |
| **응원 단장** | 좋아요 10회 누름 | ![badge_social_cheerleader.png](/assets/img/posts/2025-12-23-moathon-badge-system/4.png) |
| **소통 요정** | 응원 댓글 5회 작성 | ![badge_social_comments.png](/assets/img/posts/2025-12-23-moathon-badge-system/3.png) |
| **인기 스타** | 내 모아톤이 좋아요 20개 받음 | ![badge_social_beloved.png](/assets/img/posts/2025-12-23-moathon-badge-system/2.png) |
| **팔로팔로미** | 팔로워 10명 달성 | ![badge_social_followers.png](/assets/img/posts/2025-12-23-moathon-badge-system/1.png) |

### 도감 시각화 전략 (Visual Logic)

단순히 목록을 나열하는 것이 아니라, 수집 욕구를 자극하기 위해 다음과 같은 시각화 규칙을 적용했다.

1.  **미획득 상태 (Locked):** 아직 얻지 못한 뱃지는 **흑백(Grayscale)** 처리하여 실루엣만 보여준다.
2.  **중복 획득 (Counter):** 같은 뱃지를 여러 번 획득한 경우(예: 완주 트로피 3회), 우측 하단에 **`x 3`** 카운트 칩을 표시한다.

---

## 트러블슈팅: 도감 데이터 연동 및 렌더링

모아톤 상세 페이지(`MoathonDetailView`)에서 개최자(Owner)의 프로필과 뱃지 목록을 보여주려 했으나 다음과 같은 문제들이 단계적으로 발생했다.

1. **데이터 누락:** 초기에는 `moathonDetail.user` 안에 뱃지 정보가 포함되지 않음.
2. **로직 오류:** `UserBadge` 테이블만 조회하다 보니, 획득하지 못한 뱃지(Gray 처리 대상)는 아예 목록에 뜨지 않음.
3. **렌더링 에러:** 페이지 진입 시 `Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'user')` 발생하며 화면이 하얗게 변함.

### Issue 1: 백엔드 데이터 구조 문제 (미획득 뱃지 누락)

- **현상:** `UserBadge` 테이블(획득 이력)만 조회하니 사용자가 **이미 획득한 뱃지**만 리스트로 반환되었다. 하지만 도감의 요구사항은 **"획득하지 못한 뱃지도 흐리게(Gray) 표시"**하는 것이었다.
- **원인:** 획득 이력 테이블에는 당연히 미획득 정보가 없다.
- **해결:** 기준을 `UserBadge`가 아닌 `Badge`(전체 마스터 데이터)로 변경했다. `Badge.objects.all()`로 전체 틀을 잡고, 유저가 가진 뱃지 개수를 매핑하는 방식으로 로직을 전면 수정했다.

```python
# backend/accounts/serializers.py

from collections import Counter
from .models import Badge, UserBadge

# ... (생략)

def get_badge_collection(self, obj):
    # 1. 시스템의 모든 뱃지 가져오기 (기본 틀)
    all_badges = Badge.objects.all().order_by('id')

    # 2. 해당 유저가 획득한 뱃지 ID 리스트 추출
    user_acquired_badge_ids = UserBadge.objects.filter(user=obj).values_list('badge_id', flat=True)

    # 3. 뱃지별 획득 수량 계산 (Counter 활용)
    # 예: {1: 2, 3: 1} -> 1번 뱃지 2개, 3번 뱃지 1개
    badge_counts = Counter(user_acquired_badge_ids)

    results = []
    for badge in all_badges:
        # 4. 전체 뱃지를 순회하며 수량(quantity) 매핑
        quantity = badge_counts.get(badge.id, 0)
        
        results.append({
            "id": badge.id,
            "name": badge.name,
            "image": badge.image.url if badge.image else None,
            "description": badge.description,
            "quantity": quantity,  # 0이면 미획득, 2이상이면 중복 획득
            "is_obtained": quantity > 0
        })
        
    return results
```

### Issue 2: 프론트엔드 비동기 렌더링 에러

- **현상**: 페이지 진입 직후 콘솔에 `TypeError: Cannot read properties of undefined` 에러가 뜨면서 화면 렌더링이 중단됨.
- **원인**: Vue 컴포넌트는 `setup()`이 실행되자마자 HTML 템플릿을 그리기 시작한다. 하지만 API 응답(`fetchMoathonDetail`)은 비동기로 도착하므로, 데이터가 도착하기 전 찰나의 순간에 빈 객체(`moathonDetail`)의 `user` 속성에 접근하려다 에러가 발생한 것이다.
- **해결**: 데이터가 로드되기 전에는 해당 DOM을 그리지 않도록 `v-if` 가드를 설치하고, 로딩 상태를 명확히 분기 처리했다.

```html
<template>
  <div class="container py-5">
    <div v-if="moathonDetail" class="row">

      <div class="col-lg-4">
        <h5>{{ moathonDetail.user?.nickname }}</h5>
        
        <BadgeLibrary 
          v-if="moathonDetail.user?.badge_collection"
          :badges="moathonDetail.user.badge_collection" 
        />
      </div>
    </div>

    <div v-else class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
      <p>로딩 중...</p>
    </div>
  </div>
</template>
```

### Issue 3: 뷰(View) 재사용을 위한 컴포넌트 분리

- **현상**: 상세 페이지(`MoathonDetailView`)뿐만 아니라 마이 페이지(`MyPageView`)에서도 똑같은 3x3 뱃지 그리드가 필요했다. 로직(흑백 처리, xN 표시 등)을 중복해서 작성하는 것은 비효율적이었다.
- **해결**: `BadgeLibrary.vue`라는 공통 컴포넌트를 분리했다. "데이터(뱃지 리스트)만 던져주면 알아서 그리는" 구조로 리팩토링하여 유지보수성을 높였다.

```js
// frontend/src/components/common/BadgeLibrary.vue

<script setup>
// Props로 뱃지 리스트만 심플하게 받음
const props = defineProps({
  badges: Array
})
</script>

<template>
  <div 
    class="badge-item" 
    :class="{ 'is-inactive': badge.quantity === 0 }"
  >
    </div>
</template>

<style scoped>
/* 상태에 따른 시각화 로직은 CSS로 위임 */
.badge-item.is-inactive img {
  filter: grayscale(100%); /* 흑백 처리 */
  opacity: 0.5;            /* 흐리게 */
}
</style>
```

### Issue 4: 모아톤 삭제 시 UNIQUE constraint failed

![모아톤 삭제 시 500 Error](/assets/img/posts/2025-12-23-moathon-badge-system/15.png)
*모아톤 삭제 시 500 Error*

- **현상**: 모아톤 삭제 API 요청 시 `500 Internal Server Error` 에러가 발생함.
    ```bash
    # Django 터미널 로그
    django.db.utils.IntegrityError: UNIQUE constraint failed: accounts_userbadge.user_id, accounts_userbadge.badge_id
    ```
- **원인**(충돌 시나리오): 
    1. **상황:**
        - 사용자가 '모아톤 A'를 진행하며 **'반환점(50%)' 뱃지**를 받는다. (DB: `user=나`, `badge=50%`, `moathon=A`)
        - 사용자가 이전에 '모아톤 B'를 삭제해서, 이미 **'반환점(50%)' 뱃지(Orphan)**를 하나 가지고 있다. (DB: `user=나`, `badge=50%`, `moathon=NULL`)
    2. **삭제 시도:**
        - '모아톤 A'를 삭제한다.
        - `on_delete=models.SET_NULL` 설정에 의해, `moathon=A`였던 뱃지가 **`moathon=NULL`로 변경**되려고 시도한다.
    3. **충돌 발생 (IntegrityError):**
        - 변경하려는 순간, DB는 `unique_user_badge_when_moathon_null` 제약 조건을 체크한다.
        - **"잠깐! 너 이미 `moathon=NULL`인 50% 뱃지 가지고 있잖아?"**
        - 결국 유일성 제약 위반으로 **삭제 트랜잭션 전체가 롤백되고 500 에러**가 터진다.
- **해결**: 모아톤 삭제 시 해당 모아톤으로 받은 뱃지도 함께 삭제하도록 CASCADE 조건을 설정했다.

```python
# accounts/models.py

class UserBadge(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)

    # [수정 전] SET_NULL -> 모아톤 삭제 시 뱃지가 '주인 없는 뱃지'가 되어 충돌 유발
    # moathon = models.ForeignKey(Moathon, on_delete=models.SET_NULL, null=True, blank=True)

    # [수정 후] CASCADE -> 모아톤 삭제 시, 해당 모아톤으로 받은 뱃지도 함께 삭제
    moathon = models.ForeignKey(
        Moathon, 
        on_delete=models.CASCADE,  # <-- 여기를 수정!
        null=True, 
        blank=True
    )

    # ... 나머지 코드는 그대로 유지 ...
```


---

## 마치며 (Insights)

이번 트러블슈팅을 통해 프론트엔드와 백엔드 양쪽에서 **"안정적인 데이터 처리 패턴"**을 확립할 수 있었다.

- **Backend Strategy**: "없는 데이터(미획득)"를 표현해야 할 때는 유저 테이블 기준이 아니라 **Master Data(전체 목록)**를 기준으로 Loop를 돌리거나 `Left Join`을 해야 한다.

- **Frontend Defensive Programming**: API 데이터는 언제나 네트워크 지연으로 늦게 도착한다. `v-if` 분기 처리나 Optional Chaining(`?.`)을 습관화하여 데이터가 없을 때의 UI(Loading, Empty State)를 반드시 고려해야 한다.

- **Refactoring**: UI 로직이 조금이라도 복잡하거나 반복될 조짐이 보이면, 초기 단계부터 컴포넌트 분리를 계획하는 것이 정신 건강에 이롭다.