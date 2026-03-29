---
title: "[둥지] utils에 있던 시세 조회 로직, 왜 독립 도메인으로 옮겼나"
date: 2026-03-20 09:00:00 +0900
categories: [Project, 둥지]
tags: [DDD, DomainService, Architecture, FastAPI, Redis, Caching, Python, Backend, Repository]
toc: true
comments: true
description: "utils/price에 묶여 있던 시세 조회 로직을 독립 도메인으로 승격하고, Repository 패턴 도입 여부 결정, 헤드리스 도메인 구조, DB 캐싱 전략까지 아키텍처 의사결정 전 과정을 정리합니다."
---

둥지 서비스에는 등기부등본 주소를 기반으로 주변 실거래가를 조회하는 시세 조회 기능이 있습니다. 이 시세 데이터는 깡통전세 위험도 분석과 보증보험 가입 가능 여부 판단, 두 곳에서 모두 필요합니다.

문제는 이 로직이 `utils/price/` 안에 있었다는 것입니다.

*"price/에 있는 각 API 클라이언트를 순차 호출하고 DB에 적재하는 함수를 모듈화해서, 깡통전세와 보증보험 서비스에서 호출하는 구조가 많이 이상한가요?"*

전혀 이상하지 않습니다. 오히려 이상적인 방향입니다. 다만 **위치가 `utils`라는 게 문제**였습니다.

## utils와 Domain Service는 다릅니다

보통 `utils` 디렉토리는 **상태를 가지지 않고(Stateless) DB에 접근하지 않는 순수 함수**를 두는 곳입니다. 날짜 포맷팅, 문자열 파싱, 단순 변환 로직 같은 것들입니다.

반면 시세 조회는 다릅니다.

- 여러 외부 API 클라이언트를 순차적으로 호출하고
- 실패하면 다음 클라이언트로 폴백하며
- 최종 결과를 `TradePrice` 테이블에 INSERT합니다

이건 단순 유틸리티가 아니라 **비즈니스 로직**입니다. `utils`에 두면 코드를 처음 보는 사람이 다른 유틸 함수들과 뒤섞여 책임 소재가 불분명해집니다.

기존 `utils/price/`의 구성 요소를 성격별로 분류하면 이렇습니다.

| 기존 위치 | 실제 성격 | 이동 위치 |
|---|---|---|
| `utils/price/clients/` | 외부 API 클라이언트, 부수효과 있음 | `domains/price/clients/` |
| `utils/price/enums.py` | 도메인 열거형 | `domains/price/enums.py` |
| `utils/price/schemas.py` | 데이터 클래스 | `domains/price/schemas.py` |

도메인을 나누는 기준은 **데이터의 소유권(Data Ownership)** 과 **비즈니스 관심사(Bounded Context)** 입니다. `TradePrice` 테이블에 데이터를 쓰고 읽는 주체, 그리고 그 행위가 어떤 비즈니스적 의미를 갖는지가 기준이 됩니다.

시세 데이터는 깡통전세와 보증보험 두 도메인이 **공통으로 필요로 하는 핵심 기반 데이터**입니다. `price`는 충분히 독립 도메인 자격이 있습니다.

## price를 독립 도메인으로 승격하기

`utils/price/`를 `domains/price/`로 옮기고, 서비스 계층을 명확히 정의합니다.

```
app/domains/
├── price/                         # [신규] 시세 애그리게이터 도메인
│   ├── services/
│   │   └── price_service.py       # DB 캐시 조회 + API 조율 + 적재
│   ├── clients/
│   │   ├── __init__.py            # ClientFactory
│   │   ├── base_client.py
│   │   ├── rtech_client.py
│   │   ├── safe_jeonse_client.py
│   │   ├── hometax_client.py
│   │   └── real_transaction_client.py
│   ├── schemas.py                 # PriceQuery, PriceResult
│   ├── enums.py                   # PriceSource, HousingType
│   ├── constants.py               # 타임아웃, 재시도 설정
│   └── exceptions.py              # PriceFetchException 등
│
├── checklist/
│   └── services/
│       ├── can_service.py         # price_service 사용 (깡통전세)
│       └── insurance_service.py   # price_service 사용 (보증보험)
```

`price` 도메인의 `price_service.py`가 모든 외부 API 호출과 DB 적재 책임을 단독으로 가집니다. 다른 도메인은 이 함수 하나만 호출하면 됩니다.

```python
# app/domains/price/services/price_service.py
CACHE_VALID_DAYS = 30


async def get_price(
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    query: PriceQuery,
) -> PriceResult | None:
    """시세 조회 통합 서비스.

    1. DB 캐시 확인 (최근 30일 이내)
    2. 캐시 없으면 → API 순차 조회 (waterfall)
    3. 결과 DB 저장
    """
    cached = await _get_cached_price(db, query)
    if cached:
        return cached

    result = await _fetch_from_api(http_client, query)
    if not result:
        return None

    await _save_to_cache(db, query, result)
    return result


async def _fetch_from_api(http_client, query):
    """외부 API에서 시세 조회 (waterfall 방식)."""
    sources = _get_source_priority(query.housing_type)
    clients = ClientFactory.create_clients(sources, http_client)

    for client in clients:
        try:
            result = await client.fetch_price(query.to_enriched())
            if result:
                return result
        except Exception as e:
            logger.warning("Client %s failed: %s", client.__class__.__name__, e)
            continue

    return None


def _get_source_priority(housing_type: HousingType) -> list[PriceSource]:
    """주택 유형별 시세 소스 우선순위."""
    if housing_type.is_group_a():  # 아파트, 오피스텔, 집합건물
        return [
            PriceSource.RTECH,
            PriceSource.HOMETAX,
            PriceSource.SAFE_JEONSE,
            PriceSource.REAL_TRANSACTION,
            PriceSource.PRESALE,
        ]
    else:  # 단독, 다가구
        return [
            PriceSource.REAL_TRANSACTION,
            PriceSource.SAFE_JEONSE,
        ]
```

주택 유형(집합건물 vs 단독)에 따라 시세 소스 우선순위가 다릅니다. 이 판단도 `price_service.py`가 담당하기 때문에 깡통전세 서비스는 이런 세부 사항을 알 필요가 없습니다.

```python
# app/domains/checklist/services/can_service.py
from app.domains.price.services import price_service

async def analyze_risk(db, http_client, nest_id, user_id, deposit):
    nest = await db.get(Nest, nest_id)

    # 시세 확보 — 내부적으로 캐시/API/폴백을 알아서 처리
    price_result = await price_service.get_price(db, http_client, PriceQuery.from_nest(nest))
    if not price_result:
        raise PriceNotFoundException()

    # 이 함수는 위험도 계산에만 집중
    gap_ratio = (price_result.price - deposit) / price_result.price * 100
    risk_level = _determine_risk_level(gap_ratio)

    report = UnderwaterRiskReport(
        nest_id=nest_id,
        estimated_price=price_result.price,
        price_source=price_result.source.value,
        deposit=deposit,
        gap_ratio=gap_ratio,
        risk_level=risk_level,
    )
    db.add(report)
    await db.commit()
    return report


def _determine_risk_level(gap_ratio: float) -> RiskLevelEnum:
    if gap_ratio >= 30:
        return RiskLevelEnum.SAFE
    elif gap_ratio >= 20:
        return RiskLevelEnum.CAUTION
    elif gap_ratio > 0:
        return RiskLevelEnum.DANGER
    else:
        return RiskLevelEnum.CRITICAL
```

깡통전세 서비스는 `(보증금 - 시세) / 시세` 계산과 등급 판정에만 집중할 수 있습니다.

## router.py는 필수가 아니다 — 헤드리스 도메인

*"price를 domains/로 올리면 다른 도메인들과 구조를 맞춰야 하나요? router.py를 만들어서 API화해야 하나요?"*

아닙니다. 도메인을 구성할 때 반드시 모든 도메인이 `router.py`를 가져야 하는 것은 아닙니다. 프론트엔드와 직접 통신하지 않고 시스템 내부에서만 사용되는 도메인을 **헤드리스 도메인(Headless Domain)** 이라고 부릅니다. DDD에서 자연스럽고 권장되는 구조입니다.

라우터는 외부 세계와의 인터페이스 역할을 할 뿐, 도메인의 본질이 아닙니다. 불필요한 API 엔드포인트 노출 없이, 파이썬 모듈 임포트를 통해 메모리 상에서 함수를 직접 호출합니다. HTTP 통신 오버헤드도 없고, 프론트엔드 통신용 API와 백엔드 내부 로직의 경계도 명확합니다.

## DB 접근 패턴 — Repository를 도입할까?

독립 도메인을 구성하면서 자연스럽게 따라오는 질문이 있습니다. *"Repository 패턴도 도입해야 할까?"*

현재 프로젝트는 Service에서 SQLAlchemy ORM을 직접 사용하는 패턴입니다.

```
현재:       Router → Service → DB (직접 접근)
Repository: Router → Service → Repository → DB
```

Repository 패턴은 데이터 접근 로직을 별도 클래스로 분리합니다. Model과는 다른 개념입니다.

| 구분 | Model (ORM) | Repository |
|---|---|---|
| 역할 | 테이블 구조 정의 | 데이터 접근 로직 캡슐화 |
| 질문 | "무엇을 저장하나?" | "어떻게 저장/조회하나?" |
| 내용 | 컬럼, 타입, 관계, 제약조건 | 쿼리 메서드 (get, create, find_by_x) |

도입하면 얻는 것들이 있습니다. 비즈니스 로직과 쿼리 로직이 분리되고, Repository를 Mock으로 대체하면 DB 없이 단위 테스트가 가능합니다. 동일한 쿼리가 여러 Service에서 반복될 때 한 곳에서 관리할 수 있습니다.

**결정: 현재는 도입하지 않습니다.**

| 근거 | 설명 |
|---|---|
| 일관성 | auth, user, issuance 등 기존 서비스가 모두 Service 직접 접근 패턴 사용 중 |
| 단순성 | 추가 레이어 없이 직관적인 코드 유지 |
| 규모 | 현재 프로젝트 규모에서 충분히 관리 가능 |

다음 상황이 되면 재검토합니다.

- 동일한 쿼리 패턴이 3개 이상의 Service에서 반복될 때
- 단위 테스트 커버리지 요구사항이 생길 때
- 팀 규모가 커져서 역할 분담이 필요할 때

도입 시에는 **전체 프로젝트에 일괄 적용**해서 일관성을 유지합니다. 일부 도메인만 Repository를 쓰고 나머지는 직접 접근하는 혼재 상태가 되면, 오히려 코드 이해 비용이 늘어납니다.

## DB 캐싱 전략 — 시세는 자주 바뀌지 않는다

외부 API를 매번 호출하면 응답 시간도 길고 API 사용량도 낭비됩니다. 시세 데이터는 실시간으로 초 단위 변동이 일어나는 성격이 아닙니다. **30일 유효 기간의 DB 캐싱**을 적용합니다.

```python
async def _get_cached_price(db, query):
    threshold = datetime.now(timezone.utc) - timedelta(days=CACHE_VALID_DAYS)  # 30일

    result = await db.execute(
        select(TradePrice)
        .where(
            TradePrice.pnu_code == query.pnu_code,
            TradePrice.exclusive_area == query.exclusive_area,
            TradePrice.trade_date >= threshold.date(),
        )
        .order_by(TradePrice.trade_date.desc())
        .limit(1)
    )
    trade_price = result.scalar_one_or_none()
    if not trade_price:
        return None

    return PriceResult(price=trade_price.trade_price, source=..., cached=True)
```

캐시 키로 `nest_id`를 쓰지 않는 이유가 있습니다. 서로 다른 유저 A와 B가 같은 오피스텔에 대해 각자의 둥지를 생성할 수 있습니다. `pnu_code`(법정동 고유 식별자) + 전용면적 기준으로 캐시를 구성하면, A가 조회해서 적재한 데이터를 B가 외부 API 호출 없이 바로 재사용할 수 있어 캐시 히트율이 높아집니다.

전체 조회 흐름은 이렇습니다.

```
1. DB 캐시 조회 (30일 이내 데이터 있는지)
   → 있으면: 즉시 반환 (cached=True)

2. 외부 API 순차 호출 (주택 유형별 우선순위 적용)
   → 성공하면: DB INSERT 후 반환

3. 모든 소스 실패
   → None 반환 (호출한 쪽에서 예외 처리)
```

## 최종 아키텍처 흐름

```
┌──────────────────────────────────────────────────────┐
│                      Routers                          │
│    (checklist_router, can_router, insurance_router)   │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│               Checklist Services                      │
│   ┌─────────────────┐   ┌──────────────────────┐     │
│   │  can_service    │   │  insurance_service   │     │
│   │  (깡통전세)      │   │  (보증보험)           │     │
│   └────────┬────────┘   └──────────┬───────────┘     │
└────────────┼────────────────────────┼────────────────┘
             └──────────┬─────────────┘
                        │ import
                        ▼
┌──────────────────────────────────────────────────────┐
│                   Price Domain                        │
│   price_service.py                                    │
│   ├─ DB 캐시 조회 (30일 이내)                          │
│   ├─ API 조회 (ClientFactory, 주택 유형별 우선순위)     │
│   └─ 결과 DB 저장                                     │
│                                                       │
│   clients/                                            │
│   └─ RtechClient, SafeJeonseClient, HometaxClient ... │
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│              Database (PostgreSQL)                    │
│   TradePrice (시세 캐시)                              │
│   UnderwaterRiskReport (깡통전세 리포트)               │
└──────────────────────────────────────────────────────┘
```

`checklist` → `price` 단방향 의존입니다. `price`는 `checklist`를 모릅니다. 나중에 `price` 도메인을 분리하거나 교체하더라도 `checklist`에는 영향이 없습니다.
