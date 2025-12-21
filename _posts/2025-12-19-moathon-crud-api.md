---
title: "[모아톤] Django 앱 분리 리팩토링과 API 문서화 도구(Swagger) 교체기"
date: 2025-12-19 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Django, DRF, Refactoring, DrfSpectacular, Swagger, Architecture, Backend]
toc: true 
comments: true
image: /assets/img/posts/2025-12-19-moathon-crud-api/6.png
description: "기존 accounts 앱에 종속되어 있던 모델을 독립적인 challenges 앱으로 분리하고, 유지보수가 중단된 drf-yasg 대신 drf-spectacular를 도입하여 API 문서를 고도화한 과정을 정리했습니다."
---

금융 목표 달성 챌린지인 **'모아톤(Moathon)'**의 핵심 CRUD 기능을 구현하면서 진행한 **아키텍처 리팩토링** 과정과, API 문서 자동화를 위해 **라이브러리를 교체했던 트러블슈팅** 에 대한 기록이다.


## 1. 아키텍처 리팩토링 (Architecture Refactoring)

### 앱 분리를 통한 의존성 낮추기
초기 설계 단계에서는 유저 정보가 있는 `accounts` 앱에 `Moathon` 모델을 함께 두었다. 하지만 챌린지 기능이 고도화되고 로직이 복잡해짐에 따라, `accounts` 앱이 너무 비대해지는 문제가 발생했다.

결합도를 낮추고 응집도를 높이기 위해 **`challenges`라는 별도 앱을 신규 생성하고 모델을 이관**했다.

- **Migration:** 모델 위치가 변경되었으므로, 기존 DB와의 충돌을 방지하기 위해 마이그레이션 전략을 다시 수립하여 스키마를 재정의했다.
생성된 DB와 마이그레이션을 삭제하고 마이그레이트를 재진행했다.

```bash
$ python manage.py makemigrations
$ python manage.py migrate
```

### 데이터 무결성 확보 (save 메서드 오버라이딩)
프론트엔드에서 종료일(`end_date`)을 일일이 계산해서 보내주는 것은 비효율적이다. 백엔드에서 데이터 무결성을 보장하기 위해 모델의 `save()` 메서드를 오버라이딩했다.

시작일(`start_date`)과 기간(`term_months`)만 입력받으면, 저장 시점에 자동으로 종료일이 계산되도록 로직을 구현했다.
이를 기반으로 현재 진행률(`profress_rate`)을 계산했다. serializer에서 종료일 대비 오늘까지의 비율을 계산하는 필드를 생성했다.

```python
# challenges/serializers.py

class MoathonDetailSerializer(serializers.ModelSerializer):
  # ...
  def get_progress_rate(self, obj):
      # 공식: (오늘 - 시작일) / (종료일 - 시작일) * 100
      total_days = (obj.end_date - obj.start_date).days
      elapsed_days = (date.today() - obj.start_date).days

      if total_days <= 0: return 100
      if elapsed_days <= 0: return 0

      rate = (elapsed_days / total_days) * 100
      return min(int(rate), 100)
```

---

## 2. API 구현 전략 (Implementation)

### Serializer 분리 전략: UX 개선
API를 설계하며 **"입력받는 데이터(Request)"**와 **"보여주는 데이터(Response)"**의 형태가 달라야 한다는 점에 주목했다. 이를 위해 Serializer를 용도에 맞게 분리했다.

1.  **`MoathonCreateSerializer` (입력용)**: 
    - 유저 입력을 최소화하기 위해 목표 금액, 기간, 상품 등 필수 정보만 받는다.
    - 유저 정보나 날짜 계산 등은 백엔드에서 자동 주입한다.
2.  **`MoathonDetailSerializer` (응답용)**: 
    - 생성 직후나 조회 시에는 계산된 `end_date`, 가입된 은행 정보 등 풍부한 데이터를 내려준다.

### 권한 제어 (Permission)
타인의 챌린지 내역을 함부로 수정하거나 삭제하면 안 된다.
- **조회(GET)**: 누구나 가능 (Read-Only)
- **수정/삭제(PATCH/DELETE)**: 작성자 본인만 가능

이를 위해 `IsOwnerOrReadOnly` 커스텀 권한 클래스를 적용하고, 수정 시에는 수정 가능한 필드를 제한하는 `UpdateSerializer`를 별도로 구현하여 보안을 강화했다.

---

## 3. 트러블슈팅: API 문서화 도구 교체

### 문제 상황: drf-yasg의 한계
API 문서화를 위해 익숙한 `drf-yasg` 라이브러리를 설치하고 설정을 마쳤다. 하지만 곧 두 가지 문제에 봉착했다.
1. 최신 Django/DRF 버전과의 호환성 경고 발생
2. 해당 라이브러리가 더 이상 적극적으로 유지보수되지 않는 구형 라이브러리임

### 해결: drf-spectacular 도입
당장은 작동하더라도 장기적인 프로젝트 관리 관점에서 보안 이슈나 추후 업그레이드 시 발목을 잡을 수 있다고 판단했다. 과감하게 `drf-yasg` 관련 코드를 모두 삭제하고, **최신 표준인 OpenAPI 3.0을 지원하는 `drf-spectacular`로 전격 교체**했다.

#### 주요 설정 내용
1.  **Schema Customization**: `@extend_schema` 데코레이터를 사용하여 Request Body와 Response 예시를 명확하게 정의했다.
2.  **Security Scheme**: JWT 인증 헤더 설정을 추가하여 Swagger UI에서 바로 토큰 인증 테스트가 가능하도록 설정했다.
3.  **환경 분리**: 보안을 위해 `DEBUG=True`인 개발 환경에서만 문서 URL에 접근할 수 있도록 라우팅을 분기 처리했다.

```python
# settings.py

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication', # 개발자 테스트용 (Swagger)
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Moathon API',
    'DESCRIPTION': '모아톤 서비스 API 문서',
    'VERSION': '1.0.0',
    'COMPONENT_SPLIT_REQUEST': True,
    'SERVE_INCLUDE_SCHEMA': False,
    'SECURITY': [{'tokenAuth': []}], 
}
```

#### 테스트용 입력 필드 추가
swagger에서 API 호출 테스트를 해보기 위해 입력을 위한 필드가 필요했다. @extend_schema를 적용하여 Request Body 및 Response 스키마 명세를 구체화했다.

```python
# challenges/views.py

@extend_schema(
    methods=['GET'],
    responses=MoathonDetailSerializer,
    summary="모아톤 상세 조회"
)
@extend_schema(
    methods=['PATCH'],
    request=MoathonUpdateSerializer,
    responses=MoathonDetailSerializer,
    summary="모아톤 수정"
)
@extend_schema(
    methods=['DELETE'],
    summary="모아톤 삭제"
)
@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def moathon_detail(request, moathon_pk):
    """
    특정 모아톤의 상세 조회, 수정, 삭제 API
    - GET: 누구나 조회 가능 (로그인 유저)
    - PATCH/DELETE: 본인만 가능 
    GET/PATCH/DELETE /moathon/<int:moathon_pk>/
    """
    pass


@extend_schema(
    request=MoathonCreateSerializer,
    responses=MoathonDetailSerializer,
    summary="모아톤 생성"
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def moathon_create(request):
    """
    모아톤 생성 API
    POST /moathons/create/
    """
    pass
```

---

## 4. 구현 결과 (Screenshots)

**모아톤 생성 (POST)**
입력은 최소화하고, 응답은 상세하게 반환된다.
![모아톤 생성 요청](/assets/img/posts/2025-12-19-moathon-crud-api/7.png)
*모아톤 생성 요청*
![모아톤 생성 응답](/assets/img/posts/2025-12-19-moathon-crud-api/6.png)
*모아톤 생성 응답*

**모아톤 수정 (PATCH)**
![모아톤 수정 요청](/assets/img/posts/2025-12-19-moathon-crud-api/5.png)
*모아톤 수정 요청*
![모아톤 수정 응답](/assets/img/posts/2025-12-19-moathon-crud-api/4.png)
*모아톤 수정 응답*

**모아톤 삭제 (DELETE)**
![모아톤 삭제](/assets/img/posts/2025-12-19-moathon-crud-api/3.png)
*모아톤 삭제*

**권한 제어 테스트 (403 Forbidden)**
작성자와 로그인한 유저가 다른 경우, 수정/삭제 요청 시 403 에러를 반환한다.
![권한 제어](/assets/img/posts/2025-12-19-moathon-crud-api/2.png)
*권한 제어*

**모아톤 전체 조회 (GET)**
![모아톤 전체 조회](/assets/img/posts/2025-12-19-moathon-crud-api/1.png)
*모아톤 전체 조회*

---

## 마치며

이번 작업을 통해 `challenges` 앱 분리로 코드의 구조적 안정성을 확보했고, `drf-spectacular` 도입으로 더 현대적이고 관리가 용이한 API 문서를 갖추게 되었다. 특히 Serializer 분리와 Permission 적용을 통해 실제 서비스 가능한 수준의 견고한 CRUD API를 완성했다는 점에서 의미가 있다.

---

### 레퍼런스

[drf-yasg docs](https://drf-yasg.readthedocs.io/en/stable/readme.html)

[drf-spectacular documentation](https://drf-spectacular.readthedocs.io/en/latest/readme.html)