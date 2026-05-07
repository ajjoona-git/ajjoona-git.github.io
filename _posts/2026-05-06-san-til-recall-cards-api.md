---
title: "[SAN] TIL 리콜 카드 API: threshold 기반 전체 반환과 LazyInitializationException"
date: 2026-05-06 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, pgvector, VectorSearch, JPA, LazyLoading, Transactional, Threshold, API, Troubleshooting]
toc: true
comments: true
description: "GET /api/til/{summaryId}/recall-cards 구현 과정에서 결정한 사항들 — LIMIT 대신 threshold 기반으로 전환한 이유, 코사인 거리 0.3의 의미, LazyInitializationException 원인과 @Transactional 해결까지 기록합니다."
---

TIL 페이지 하단에 표시되는 리콜 카드는 "오늘 학습한 내용을 요약한 TIL과 연관이 높은 카드"입니다. TIL 임베딩을 기준으로 유사한 카드를 찾되, 당일 TIL 생성의 원본이 된 카드들은 이미 알고 있는 내용이므로 결과에서 제외합니다.

## LIMIT에서 threshold로

### 고정 개수보다 유사도 기준이 목적에 맞다

초기 설계에서 `findRelatedByTil(UUID summaryId, UUID userId, int limit)`는 LIMIT 파라미터를 받아 상위 N개를 반환했습니다. 구현하면서 이 방식이 리콜 카드의 목적에 맞지 않는다는 생각이 들었습니다.

리콜 카드는 캐러셀(가로 스크롤) 컴포넌트로 표시됩니다. 카드가 3개든 10개든 표시 자체에는 문제가 없습니다. 그런데 LIMIT을 고정하면 유사도가 낮은 카드까지 채워서 보여줄 수 있습니다. 복습 효과를 위해서는 "N개"가 아니라 "유사도가 충분히 높은 카드만" 보여주는 것이 맞습니다. 그래서 메서드를 `findRelatedByTil(UUID summaryId, UUID userId)`로 바꾸고, 내부에서 `RECALL_THRESHOLD = 0.3` 상수를 기준으로 해당 임계값을 만족하는 카드 전체를 반환하도록 변경했습니다.

### threshold 0.3의 의미

pgvector의 `<=>` 연산자는 코사인 거리(cosine distance)를 반환합니다. 범위는 0~2이고, 값이 작을수록 두 벡터가 유사합니다. 코사인 거리와 유사도의 관계는 다음과 같습니다.

```
코사인 거리 = 1 - 코사인 유사도

distance < 0.3  →  유사도 > 0.7
```

유사도 0.7 이상이면 두 텍스트가 주제 면에서 실질적으로 겹친다고 볼 수 있습니다. 검색 엔진 분야에서 흔히 쓰이는 기준점이기도 합니다. 프로젝트 특성상 정밀한 튜닝 데이터를 확보하기 어려워 이 값을 초기 기준으로 삼았고, 추후 실사용 피드백으로 조정할 여지를 열어뒀습니다.

쿼리에서는 LIMIT 없이 threshold 조건만으로 결과를 제한합니다.

```sql
SELECT kc.*
FROM knowledge_cards kc
JOIN scraps s ON kc.scrap_id = s.scrap_id
WHERE s.user_id = :userId
  AND kc.is_deleted = false
  AND kc.embedding IS NOT NULL
  AND kc.card_id NOT IN (:excludeIds)
  AND kc.embedding <=> CAST(:queryVector AS vector) < :threshold
ORDER BY kc.embedding <=> CAST(:queryVector AS vector)
```

## Repository 메서드 구성 최종안

이 변경으로 이전에 설계했던 `searchByVectorExcluding`(LIMIT 기반)은 호출부가 없어졌습니다. TIL 리콜이 `searchByVectorExcludingWithThreshold`로 대체됐기 때문입니다. 최종 Repository 메서드 구성은 다음과 같습니다.

| 메서드 | 용도 | 특이사항 |
|--------|------|---------|
| `searchByVector` | 카드 기반 연관 추천 | limit+1 조회 후 Service에서 자기 자신 제거 |
| `searchByVectorWithFilters` | 자연어 통합 검색 | 태그·날짜 선택 필터, 페이지네이션 |
| `countByVectorFilters` | 통합 검색 totalCount | `searchByVectorWithFilters`와 동일 조건 |
| `searchByVectorExcludingWithThreshold` | TIL 리콜 카드 | threshold 기반 전체 반환, `NOT IN (:excludeIds)` |

TIL은 원본 스크랩이 없으면 생성될 수 없으므로 excludeIds는 항상 1개 이상 존재합니다. 빈 리스트로 `NOT IN ()`을 호출하는 문제가 원천적으로 발생하지 않아, threshold 버전 하나만으로 TIL 리콜 케이스가 완전히 커버됩니다.

---

## 트러블슈팅

### 트랜잭션 경계 밖에서 LAZY 로딩을 시도했다

코드리뷰에서 `TilService.getRecallCards()`에 `@Transactional`이 누락됐다는 지적이 들어왔습니다. 당시에는 `vectorSearchService.findRelatedByTil()` 내부에 트랜잭션이 있으니 괜찮다고 생각했는데, 문제는 그 트랜잭션의 범위였습니다.

`findRelatedByTil()` 내부 트랜잭션은 해당 메서드가 끝나면 종료됩니다. 반환된 `KnowledgeCard` 엔티티는 이미 트랜잭션 밖에 있는 상태입니다. 이후 `KnowledgeCardResponse.from(card)` 안에서 `card.getCategory()`처럼 LAZY 로딩 연관관계에 접근하면, 영속성 컨텍스트가 없어 Hibernate가 프록시를 초기화하지 못하고 `LazyInitializationException`을 던집니다.

```java
// 문제: getRecallCards()에 @Transactional 없음
public TilRecallCardsResponse getRecallCards(UUID summaryId, UUID userId) {
    List<KnowledgeCard> cards = vectorSearchService.findRelatedByTil(summaryId, userId);
    // findRelatedByTil()의 트랜잭션이 이미 종료된 상태
    return cards.stream()
        .map(card -> KnowledgeCardResponse.from(card)) // card.getCategory() → LazyInitializationException
        .collect(...);
}
```

### 호출자 트랜잭션으로 범위를 확장한다

`getRecallCards()`에 `@Transactional(readOnly = true)`를 추가하면 메서드 전체(벡터 검색 + DTO 변환)가 하나의 트랜잭션 안에서 실행됩니다. `findRelatedByTil()` 내부 트랜잭션은 부모 트랜잭션에 참여하고, DTO 변환 시점에도 영속성 컨텍스트가 살아 있어 LAZY 로딩이 정상 동작합니다.

```java
@Transactional(readOnly = true)
public TilRecallCardsResponse getRecallCards(UUID summaryId, UUID userId) {
    List<KnowledgeCard> cards = vectorSearchService.findRelatedByTil(summaryId, userId);
    return cards.stream()
        .map(KnowledgeCardResponse::from)
        .collect(...);
}
```

`readOnly = true`는 쓰기가 없는 조회 전용 트랜잭션임을 명시합니다. Hibernate의 dirty checking을 비활성화해 불필요한 변경 감지를 줄이는 효과도 있습니다.
