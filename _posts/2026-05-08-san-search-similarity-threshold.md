---
title: "[SAN] 자연어 검색에 유사도 threshold 적용하기"
date: 2026-05-08 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, pgvector, VectorSearch, JPA, Threshold, API, Mockito]
toc: true
comments: true
description: "자연어 통합 검색 API에서 코사인 유사도 70% 미만 카드를 결과에서 제외하도록 수정한 과정을 기록합니다. 시그니처 변경, count 쿼리 분리, Mockito eq(0.3d) 타입 불일치 해결까지 다룹니다."
---

자연어 통합 검색(`GET /api/search`)은 기존에 유사도와 무관하게 상위 `size`개를 반환했습니다. 이 방식은 관련 없는 카드까지 결과에 포함시킬 수 있어, TIL 리콜 카드와 같은 기준(코사인 거리 < 0.3, 유사도 > 70%)을 검색에도 적용하기로 했습니다.

---

## 1. `KnowledgeCardRepository` 변경

### `searchByVectorWithFilters` 시그니처 변경

`threshold` 파라미터를 추가하고, `WHERE` 절에 거리 조건을 추가했습니다.

```java
// 변경 전
List<KnowledgeCard> searchByVectorWithFilters(
    String queryVector, UUID userId, String tag,
    LocalDate fromDate, LocalDate toDate,
    int limit, int offset
);

// 변경 후 — threshold 파라미터 추가
List<KnowledgeCard> searchByVectorWithFilters(
    String queryVector, UUID userId, String tag,
    LocalDate fromDate, LocalDate toDate,
    double threshold,
    int limit, int offset
);
```

추가된 SQL 조건:

```sql
AND kc.embedding <=> CAST(:queryVector AS vector) < :threshold
```

### `countByVectorFiltersWithThreshold` 신규 메서드

기존 `countByVectorFilters`는 벡터 없이 태그·날짜만으로 카운트합니다. threshold를 반영한 `totalCount`를 구하려면 `queryVector`도 함께 넘겨야 하므로 신규 메서드로 분리했습니다. 기존 메서드는 그대로 유지합니다.

```java
long countByVectorFiltersWithThreshold(
    String queryVector, UUID userId, String tag,
    LocalDate fromDate, LocalDate toDate,
    double threshold
);
```

```sql
SELECT COUNT(*)
FROM knowledge_cards kc
JOIN scraps s ON kc.scrap_id = s.scrap_id
WHERE s.user_id = :userId
  AND kc.is_deleted = false
  AND kc.embedding IS NOT NULL
  AND (:tag IS NULL OR EXISTS (
      SELECT 1 FROM card_tags ct JOIN tags t ON ct.tag_id = t.tag_id
      WHERE ct.card_id = kc.card_id AND t.tag_name = :tag
  ))
  AND (:fromDate IS NULL OR CAST(kc.created_at AS date) >= CAST(:fromDate AS date))
  AND (:toDate IS NULL OR CAST(kc.created_at AS date) <= CAST(:toDate AS date))
  AND kc.embedding <=> CAST(:queryVector AS vector) < :threshold
```

---

## 2. `VectorSearchService` 변경

`search()` 내부에서 두 곳을 수정했습니다.

```java
// 변경 전
List<KnowledgeCard> cards = knowledgeCardRepository.searchByVectorWithFilters(
    queryVector, userId, tag, fromDate, toDate, size, offset);
long totalCount = knowledgeCardRepository.countByVectorFilters(userId, tag, fromDate, toDate);

// 변경 후
List<KnowledgeCard> cards = knowledgeCardRepository.searchByVectorWithFilters(
    queryVector, userId, tag, fromDate, toDate, RECALL_THRESHOLD, size, offset);
long totalCount = knowledgeCardRepository.countByVectorFiltersWithThreshold(
    queryVector, userId, tag, fromDate, toDate, RECALL_THRESHOLD);
```

`RECALL_THRESHOLD = 0.3`은 TIL 리콜 카드에서 이미 사용 중인 상수를 재사용합니다. 두 유즈케이스 모두 "유사도 70% 이상"을 기준으로 삼으므로 공유가 자연스럽습니다. 기준이 유즈케이스별로 달라지면 그때 분리합니다.

`totalCount`의 의미도 바뀝니다. 기존에는 "필터 조건에 맞는 전체 카드 수"였지만, 이제는 "threshold를 넘은 카드 수"입니다. `hasNext` 계산이 실제 반환 가능한 카드 수를 기반으로 해야 정확하므로 count 쿼리에 threshold를 포함시키는 것이 맞습니다.

---

## 3. `VectorSearchServiceTest` 업데이트

### 기존 테스트 — mock 시그니처 수정

아래 세 테스트는 `searchByVectorWithFilters` mock 호출부에 `threshold` 인자를 추가했습니다.

- `search_필터없음_결과반환`
- `search_태그필터_적용`
- `search_hasNext_페이지계산`

### 신규 테스트

```
search_threshold_미달_카드없으면_빈결과반환
  — threshold 미달 시 빈 리스트·totalCount 0 반환 검증

search_threshold_이상_카드만_포함
  — threshold 초과 카드만 결과에 포함되는지 검증
```

---

## 트러블슈팅

### Mockito `eq(0.3)` 타입 불일치

mock 매처로 `eq(0.3)`을 사용했더니 일부 케이스에서 매칭 실패가 발생했습니다. `eq(0.3)`은 `Double` 객체로 박싱되어 primitive `double` 파라미터와 타입이 맞지 않는 경우가 있습니다. 전체 11곳을 `eq(0.3d)`로 수정해 primitive 타입을 명시함으로써 해결했습니다.

### 고려해 볼 점

threshold 조건이 포함된 count 쿼리는 `queryVector`를 한 번 더 전달해야 해 쿼리 비용이 소폭 증가합니다. 캐싱이 필요한 수준의 트래픽이 되면 애플리케이션 레벨에서 `LIMIT`로 추정하는 방식을 고려할 수 있습니다.
