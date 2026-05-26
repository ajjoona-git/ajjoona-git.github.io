---
title: "[SAN] Hybrid 검색 설계: 자연어 검색에 키워드 검색 더하기"
date: 2026-05-14 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, pgvector, VectorSearch, ILIKE, HybridSearch, PostgreSQL, API, Design]
toc: true
comments: true
description: "벡터 검색만으로는 키워드 일치를 보장하기 어렵습니다. ILIKE 키워드 검색을 병합한 Hybrid 검색 구조를 도입한 과정과 함께, 벡터 검색 QA에서 발견한 빈 excludeIds 오류와 카테고리 필터 추가도 기록합니다."
---

자연어 통합 검색(`GET /api/search`)은 벡터 유사도만으로 결과를 반환했습니다. 사용자가 `AOP`처럼 정확한 키워드를 입력했을 때 해당 단어가 포함된 카드가 낮은 순위에 밀리거나 누락될 수 있는 구조였습니다. 키워드 검색을 병합한 Hybrid 검색으로 전환하고, QA 과정에서 발견한 문제들도 함께 수정했습니다.

---

## 벡터 검색 QA에서 발견한 문제들

### 빈 excludeIds의 SQL 오류

`findRelatedByTil`은 TIL 생성의 원본이 된 카드를 리콜 대상에서 제외하기 위해 `NOT IN (:excludeIds)` 조건을 사용합니다. 그런데 원본 카드가 없으면 `NOT IN ()` 구문이 되어 PostgreSQL 문법 오류가 발생합니다.

리포지토리 주석에 "excludeIds는 반드시 1개 이상이어야 함"이라고 명시되어 있었으나 실제 방어 로직은 없는 상태였습니다. 발생 조건은 사용자가 해당 날짜에 수집한 카드가 없는 경우 — 첫 TIL 생성 등 초기 상태에서 재현됩니다.

서비스 레이어에서 리포지토리 호출 전 조기 반환하는 방식으로 해결했습니다. 원본 카드가 없으면 리콜 대상도 없다는 도메인 로직에도 부합합니다.

### 카테고리 필터 추가

`knowledge_cards.category_id` 컬럼이 있었지만 검색 필터로 노출되지 않았습니다. `tag`, `fromDate`, `toDate`와 동일한 방식으로 `categoryId`(null 시 미적용) 파라미터를 컨트롤러부터 리포지토리 쿼리까지 전 계층에 추가했습니다. count 쿼리(`countByVectorFiltersWithThreshold`)에도 동일 조건을 추가해 `hasNext` 정확도를 유지합니다.

---

## Hybrid 검색 설계

### 키워드 검색 방식: ILIKE vs tsvector

키워드 검색 방식으로 ILIKE와 tsvector를 검토했습니다.

tsvector는 PostgreSQL의 전문 검색 자료형으로 텍스트를 토큰 단위로 분해해 GIN 인덱스를 지원합니다. 그러나 `simple` 딕셔너리는 공백 기준으로만 토큰을 나눕니다. `"AOP 개념"` 검색은 되지만 붙어있는 한국어는 제대로 분리하지 못합니다. 한국어 형태소 분석(`mecab` 등)을 별도 설치해야 동작하므로 현재 프로젝트에서는 도입 비용 대비 이점이 없다고 판단했습니다.

ILIKE는 스키마 변경 없이 즉시 적용 가능합니다. 현재 `knowledge_cards`에는 tsvector 컬럼이 없고, 사용자가 검색하는 키워드가 주로 짧은 기술 용어나 단어 단위라 ILIKE로 충분합니다. 추후 성능 이슈가 생기면 `pg_trgm` 익스텐션과 GIN 트라이그램 인덱스를 추가하는 방식으로 대응합니다. 쿼리 변경 없이 인덱스만 추가하면 되므로 전환 비용이 낮습니다.

### 항상 Hybrid로 통합

벡터 검색과 키워드 검색을 선택적으로 쓰는 방식 대신 **항상 동시에 실행하고 병합**하는 구조를 선택했습니다.

사용자 입장에서 검색 방식을 선택하게 하거나, 파라미터로 분기하면 인터페이스가 복잡해집니다. 벡터 검색은 의미적 유사도를, 키워드 검색은 정확한 단어 일치를 잡으므로 두 결과를 합치는 것이 항상 이득입니다. 기존 `GET /api/search` 엔드포인트를 그대로 유지하며 내부 구현만 `HybridSearchService`로 교체했습니다.

### 병합 우선순위

두 검색에서 모두 히트한 카드가 가장 관련도가 높습니다. 병합 순서는 다음과 같습니다.

| 순위 | 조건 | 정렬 |
|---|---|---|
| 1 | 벡터 + 키워드 모두 히트 | 벡터 유사도 순 (코사인 거리 오름차순) |
| 2 | 벡터 검색만 히트 | 벡터 유사도 순 |
| 3 | 키워드 검색만 히트 | `created_at DESC` |

키워드만 히트한 카드는 유사도 값이 없으므로 최신순으로 정렬합니다.

### 페이지네이션 처리

벡터 검색과 ILIKE 검색을 DB 레벨에서 UNION하면 쿼리가 복잡해지고 유사도 정렬과 최신순 정렬을 함께 다루기 어렵습니다. 서비스 레이어에서 병합 후 슬라이싱하는 방식을 택했습니다.

각 검색에서 최대 `HYBRID_FETCH_LIMIT = 200`개를 조회하고, `cardId` 기준 중복 제거 → 우선순위 정렬 → `page * size` ~ `(page+1) * size` 슬라이싱 순으로 처리합니다. `totalCount`는 병합 후 중복 제거된 전체 카드 수입니다.

상한을 완전히 제거하지 않은 이유는 threshold가 느슨해질 경우 전송량을 예측할 수 없기 때문입니다. 하루 10건 스크랩 기준 연간 약 3,650개 누적이며, threshold 0.3이 엄격하게 걸리므로 실제 통과 카드는 전체의 일부입니다. 카드 수가 크게 늘어나면 threshold를 조이거나 상한값을 재조정합니다.

---

## 검색 API 현황

| API | 엔드포인트 | 담당 서비스 | 변경 |
|---|---|---|---|
| 자연어 통합 검색 | `GET /api/search` | `HybridSearchService` | 벡터 + ILIKE 병합으로 교체 |
| 카드 기반 연관 추천 | `GET /api/cards/jobs/{jobId}/similar-cards` | `VectorSearchService.findRelatedByCard()` | 유지 |
| TIL 기반 리콜 카드 | `GET /api/til/{summaryId}/recall-cards` | `VectorSearchService.findRelatedByTil()` | 유지 (빈 excludeIds 가드 추가) |

연관 추천과 리콜 카드는 의미적 유사도가 핵심이므로 벡터 검색만 유지합니다. 사용자가 직접 입력하는 자연어 검색만 Hybrid로 전환했습니다.
