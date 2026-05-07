---
title: "[SAN] pgvector 기반 벡터 검색 엔진 설계"
date: 2026-04-30 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, pgvector, VectorSearch, PostgreSQL, JPA, NativeQuery, Architecture, Database, AI]
toc: true
comments: true
description: "pgvector 기반 유사도 검색 엔진을 설계하면서 마주친 ERD 제약 — knowledge_cards의 user_id 부재, float[] 직렬화 문제, NOT IN 빈 리스트 SQL 오류 — 을 어떻게 풀었는지 의사결정 과정을 기록합니다."
---

SAN 프로젝트는 지식 카드(`KnowledgeCard`)와 TIL(`daily_summaries`)에 1536차원 임베딩 벡터를 저장하고, 사용자 질의나 기존 카드의 임베딩을 기준으로 유사한 카드를 찾는 벡터 검색 기능을 제공합니다.

벡터 DB로는 기존 PostgreSQL 인프라에 pgvector 확장을 추가하는 방식을 선택했습니다. Pinecone이나 Weaviate 같은 전용 벡터 DB는 대규모 서비스에서 강점이 있지만, 별도 인프라 구성과 데이터 동기화 부담이 따릅니다. 지금 단계에서는 PostgreSQL 한 곳에서 관계형 데이터와 벡터를 함께 다루는 쪽이 복잡도를 낮출 수 있었습니다.

## ERD 제약: `knowledge_cards`에 `user_id`가 없다

벡터 쿼리를 짜기 전에 ERD 구조부터 확인했습니다. SAN은 기본적으로 로그인한 사용자 본인이 스크랩한 데이터만 제공합니다. 검색 결과를 사용자 범위로 좁히려면 사용자 식별자가 쿼리 어딘가에 있어야 하는데, `knowledge_cards` 테이블에는 `user_id` 컬럼이 없습니다.

```
users
  └── scraps (user_id FK)
        └── knowledge_cards (scrap_id FK)
              └── card_tags → tags

users
  └── daily_summaries (user_id FK)  ← TIL, embedding vector(1536)
```

카드는 스크랩에 종속되고, 스크랩이 사용자에 종속되는 구조입니다. 결국 **모든 벡터 쿼리에 `scraps JOIN`이 필수**입니다. 자연어 검색이든 연관 추천이든, 특정 사용자의 카드만 대상으로 하려면 항상 `JOIN scraps s ON kc.scrap_id = s.scrap_id WHERE s.user_id = :userId` 조건이 따라붙어야 합니다. 이 제약을 먼저 인식하지 않으면 쿼리를 짤 때마다 JOIN을 빠뜨리는 실수가 생깁니다.

## Native Query와 벡터 파라미터

ERD 구조를 파악했으니 실제 쿼리 방식을 결정해야 했습니다. 여기서 두 가지 문제를 연달아 마주쳤습니다.

### JPQL로는 `<=>` 연산자를 쓸 수 없다

pgvector의 코사인 거리 연산자 `<=>`는 JPQL이 인식하지 못합니다. Spring Data JPA의 `@Query`로 벡터 연산을 표현하려면 Native Query가 사실상 유일한 선택입니다. QueryDSL 확장이나 사용자 정의 함수 등록도 기술적으로 가능하지만, 그만큼의 설정 비용을 들일 이유가 없었습니다.

기본 쿼리 구조는 다음과 같습니다.

```sql
SELECT kc.*
FROM knowledge_cards kc
JOIN scraps s ON kc.scrap_id = s.scrap_id
WHERE s.user_id = :userId
  AND kc.is_deleted = false
  AND kc.embedding IS NOT NULL
ORDER BY kc.embedding <=> CAST(:queryVector AS vector)
LIMIT :limit
```

`embedding IS NOT NULL` 필터는 빠뜨리기 쉬운 조건입니다. 임베딩 생성이 비동기 파이프라인으로 처리되기 때문에 카드 생성 직후에는 임베딩이 없을 수 있고, 컬럼은 NULL을 허용합니다. NULL인 카드가 벡터 비교에 포함되면 예외가 발생하므로 검색 시 반드시 필터링해야 합니다.

### `float[]`을 파라미터로 직접 넘길 수 없다

쿼리를 실제로 실행하려면 임베딩 벡터를 파라미터로 넘겨야 합니다. JPA 엔티티에서 임베딩 컬럼은 `float[]`으로 선언합니다.

```java
@JdbcTypeCode(SqlTypes.VECTOR)
@Array(length = 1536)
private float[] embedding;
```

Native Query 파라미터로 `float[]`을 그대로 넘기면 PostgreSQL이 타입을 인식하지 못합니다. `"[0.1,0.2,...]"` 형식의 문자열로 변환한 뒤 `CAST(:queryVector AS vector)`로 캐스팅해야 합니다.

변환 로직을 작성할 때 `Arrays.stream(float[])`을 쓰려 했는데, 이 메서드는 Java에서 지원하지 않습니다. `IntStream`, `LongStream`, `DoubleStream`은 있지만 `FloatStream`은 없기 때문입니다. 결국 `StringBuilder`로 직접 조합하는 방법을 택했습니다.

```java
private String toVectorString(float[] vector) {
    StringBuilder sb = new StringBuilder("[");
    for (int i = 0; i < vector.length; i++) {
        if (i > 0) sb.append(",");
        sb.append(vector[i]);
    }
    sb.append("]");
    return sb.toString();
}
```

## Repository 메서드 분리

쿼리 파라미터 문제를 해결하고 나니 다음 문제가 나타났습니다. 검색 용도가 세 가지인데, 용도마다 "특정 카드를 결과에서 제외해야 하는지" 여부가 다릅니다.

### NOT IN 빈 리스트 오류

TIL 리콜은 당일 TIL의 원본이 된 카드들을 결과에서 빼야 합니다. 처음에는 하나의 쿼리에 `NOT IN (:excludeIds)` 조건을 달고, excludeIds가 비어 있으면 빈 리스트를 넘기면 된다고 생각했습니다. 그런데 `NOT IN ()`에 빈 리스트를 전달하면 PostgreSQL에서 SQL 오류가 발생합니다. 빈 리스트를 방어하는 조건(`CASE WHEN ... THEN ... END`)을 쿼리 안에 넣으면 Native Query가 복잡해집니다.

대신 메서드를 두 개로 분리하고 Service에서 분기하는 방식을 선택했습니다.

| 메서드 | 용도 | 제외 조건 |
|--------|------|---------|
| `searchByVector` | 자연어 검색, 카드 기반 연관 추천 | 없음 |
| `searchByVectorExcluding` | TIL 리콜 (원본 카드 제외) | `NOT IN (:excludeIds)` |

각 메서드가 하는 일이 명확해지고, excluding 버전은 "excludeIds가 반드시 1개 이상"이라는 전제를 그대로 유지할 수 있습니다.

### 카드 기반 연관 추천: 자기 자신 제외

Repository 메서드 구조가 잡히고 나서 연관 추천에서 자잘한 문제가 하나 더 있었습니다. 카드의 임베딩으로 유사 카드를 검색하면 당연히 자기 자신이 1위로 나옵니다. 처리 방법으로 쿼리에 `WHERE kc.card_id != :cardId`를 추가하는 것도 가능하지만, 그렇게 하면 `searchByVector`와 `searchByVectorExcluding` 사이에 또 다른 변형이 생깁니다.

대신 `searchByVector`로 `limit + 1`개를 조회한 뒤 Service에서 자기 자신을 걸러내는 방식을 택했습니다. 쿼리는 그대로 두고 Service 레이어에서 한 줄 필터링으로 해결합니다.

## TIL 리콜 원본 카드 추출 흐름

Repository 메서드 분기의 키가 되는 `excludeIds`는 어떻게 수집할까요? 

TIL과 원본 카드를 직접 연결하는 외래키가 없기 때문에 날짜를 기준으로 추론합니다.

```
summaryId
  → daily_summaries 조회 → target_date + embedding + 소유자 검증
  → scraps WHERE DATE(created_at) = target_date AND user_id = ?
  → 해당 scrap의 knowledge_cards.card_id 목록 = excludeIds
  → excludeIds 있으면 searchByVectorExcluding, 없으면 searchByVector
```

`daily_summaries.target_date`와 `scraps.created_at::date`가 일치하는 스크랩을 찾아 원본 카드 ID를 수집합니다. 이 ID들이 excludeIds가 되어 리콜 결과에서 제외됩니다. TIL은 반드시 당일 스크랩이 있어야 생성되므로 일반적으로 excludeIds는 1개 이상 존재하지만, 방어를 위해 빈 경우에는 `searchByVector`로 분기합니다.

## 권한 검증 위치

마지막으로 권한 검증 위치를 결정했습니다. 세 가지 API 유형마다 검증 방식이 조금씩 다릅니다.

- **자연어 검색**: 쿼리의 `WHERE s.user_id = :userId`로 자동 처리
- **카드 기반 연관 추천**: Service에서 `card.scrap.user.userId == userId` 비교 후 검색 실행
- **TIL 리콜**: Service에서 `summary.user.userId == userId` 비교 후 검색 실행

권한 검증을 Controller에 두면 Service를 다른 곳에서 호출할 때 누락될 위험이 있습니다. 검색을 실행하기 직전, Service에서 소유권을 확인하는 것이 더 안전합니다.
