---
title: "[SAN] 자연어 통합 검색 API: AiEmbeddingClient 설계와 BindException 트러블슈팅"
date: 2026-05-04 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, pgvector, VectorSearch, API, Troubleshooting, CGLIB, Proxy, Validation]
toc: true
comments: true
description: "GET /api/search 구현 과정에서 결정한 사항들 — Scrap을 검색 풀에서 제외한 이유, AiEmbeddingClient 인터페이스 분리 전략, @ModelAttribute 검증 실패가 500을 던진 원인과 BindException 핸들러 통합, CGLIB 프록시 기동 실패까지 기록합니다."
---

pgvector 검색 엔진 설계가 끝난 뒤 첫 번째로 구현한 API는 자연어 통합 검색입니다. 사용자가 키워드를 입력하면 AI 서버에서 벡터로 변환하고, 해당 벡터로 지식 카드를 검색합니다.

## 검색 대상과 외부 의존성 설계

구현 전에 두 가지를 먼저 결정해야 했습니다. 어떤 데이터를 검색 풀에 포함할지, 그리고 외부 AI 서버 호출을 어떻게 구조화할지입니다.

### 검색 풀: KnowledgeCard만 포함

초기 설계에서는 KnowledgeCard, Scrap(원문), TIL 세 가지를 통합 검색하는 방안을 검토했습니다. 결론적으로 **KnowledgeCard만** 검색 풀에 포함하기로 했는데, 이유는 중복입니다.

KnowledgeCard는 Scrap 원문을 요약한 결과물이고, 임베딩도 카드 단위로 생성됩니다. Scrap을 검색 풀에 추가하면 같은 스크랩에서 나온 카드와 원문이 함께 노출되어 결과가 겹칩니다. 더불어 Scrap에는 현재 임베딩 컬럼 자체가 없어 당장 검색 풀에 넣을 수도 없습니다. TIL 역시 제외했습니다. 자연어 검색은 학습한 지식 카드를 찾는 목적에 집중하는 편이 UX상 명확하고, TIL 목록 조회는 별도 API가 이미 있습니다.

### AiEmbeddingClient: 인터페이스와 구현체 분리

자연어 검색에는 키워드를 벡터로 변환하는 외부 AI 서버 호출이 필요합니다. 이 역할을 `AiEmbeddingClient` 인터페이스로 추상화하고, 실제 HTTP 호출은 `AiEmbeddingClientImpl`에서 담당합니다.

```java
public interface AiEmbeddingClient {
    float[] embed(String text);
}
```

인터페이스를 두는 이유는 테스트입니다. `VectorSearchService`가 구현체를 직접 의존하면 AI 서버 없이는 단위 테스트가 불가능합니다. 인터페이스에 의존하면 `@Mock`으로 교체할 수 있습니다.

`AiEmbeddingClientImpl`은 AI 서버의 `POST /ai/search` 엔드포인트를 호출합니다. 장애 시에는 `CommonErrorCode.EXTERNAL_API_ERROR`를 던집니다. AI 서버 장애가 발생했을 때 빈 결과를 반환하는 방법도 있지만, "검색이 됐는데 결과가 없다"는 오해를 낳을 수 있어 명시적 오류 응답을 선택했습니다.

## GET /api/search 명세

검색 API는 키워드 외에 태그·날짜 필터와 페이지네이션을 함께 지원합니다.

### Query Parameter

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| keyword | string | 필수 | 검색어 |
| tag | string | 선택 | 태그명 필터 |
| fromDate | string | 선택 | 시작일 (yyyy-MM-dd) |
| toDate | string | 선택 | 종료일 (yyyy-MM-dd) |
| page | number | 선택 | 페이지 번호, 기본값 0 |
| size | number | 선택 | 페이지 크기, 기본값 10 |

태그·날짜 필터를 쿼리 레이어에서 처리하기 위해 `searchByVectorWithFilters`와 `countByVectorFilters` 두 개의 Native Query를 추가했습니다. 단순 `LIMIT` 기반 쿼리와 달리 `totalCount`를 별도로 조회해야 하기 때문에 COUNT 쿼리를 따로 두었습니다.

### 응답

```json
{
  "keyword": "AOP",
  "page": 0,
  "size": 10,
  "totalCount": 12,
  "hasNext": true,
  "results": [
    { "cardId": "uuid", "title": "AOP 개념 정리", "summary": "..." }
  ]
}
```

`hasNext`는 `(page + 1) * size < totalCount`로 계산합니다.

---

## 트러블슈팅

### BindException: `@ModelAttribute` 검증 실패가 500을 반환한다

`SearchController`에 `@Valid @ModelAttribute SearchRequest`를 적용한 뒤 검증 실패 시 400이 아닌 500 응답이 발생했습니다. 기존 `GlobalExceptionHandler`는 `MethodArgumentNotValidException`만 처리하고 있었는데, 문제는 예외 타입이 달랐습니다.

```
BindException
  └── MethodArgumentNotValidException  (@RequestBody 검증 실패)
```

`@RequestBody`는 `MethodArgumentNotValidException`을 던지지만, `@ModelAttribute` 검증 실패는 부모 타입인 `BindException`을 던집니다. 핸들러가 자식 타입만 잡으니 `@ModelAttribute` 실패는 처리되지 않은 채 500으로 올라간 것입니다.

`MethodArgumentNotValidException` 핸들러를 제거하고 `BindException` 단일 핸들러로 통합했습니다. `@RequestBody`와 `@ModelAttribute` 검증 실패 모두 400으로 처리됩니다.

```java
@ExceptionHandler(BindException.class)
public ResponseEntity<ErrorResponse> handleBindException(BindException e) {
    // ...
}
```

### CGLIB 프록시: 인터페이스 구현 클래스에 `@Async`를 붙이면 생기는 문제

같은 날 별개 이슈로 서버 기동 실패가 발생했습니다. `KnowledgeCardAnalysisJobProcessor`의 `@TransactionalEventListener handle()` 메서드를 프록시에서 찾지 못하는 오류입니다.

`KnowledgeCardAnalysisJobProcessor`는 `AsyncJobProcessor` 인터페이스를 구현하고 `@Async`가 붙어 있습니다. Spring이 `@Async` 대상을 프록싱할 때, 인터페이스가 있으면 기본적으로 **JDK 동적 프록시**를 생성합니다. JDK 프록시는 인터페이스에 선언된 메서드만 노출합니다. `@TransactionalEventListener`가 붙은 `handle()` 메서드는 `AsyncJobProcessor` 인터페이스에 없어 프록시에서 보이지 않았고, 기동 시점에 오류가 발생했습니다.

```
No such method: handle() on proxy KnowledgeCardAnalysisJobProcessor
```

`AsyncConfig`에서 CGLIB 프록시를 강제하는 옵션으로 해결했습니다.

```java
@Configuration
@EnableAsync(proxyTargetClass = true)
public class AsyncConfig { ... }
```

`proxyTargetClass = true`를 설정하면 인터페이스 유무와 관계없이 항상 CGLIB 프록시(클래스 기반 서브클래싱)를 사용합니다. 클래스의 모든 메서드가 프록시에 노출되므로 `handle()`도 정상 동작합니다.

## Scrap 임베딩 논의

검색 API를 구현하면서 나온 부가 논의입니다. 현재 `Scrap` 엔티티에는 `embedding` 컬럼이 없지만, AI API를 통해 스크랩 원문의 임베딩을 얻는 것은 기술적으로 가능합니다. 당장 구현하지 않기로 결정했는데, KnowledgeCard 임베딩으로 검색 품질이 충분하고, Scrap 전용 임베딩 생성 파이프라인을 새로 만드는 비용 대비 이득이 크지 않아서입니다.

추후 카드가 없는 스크랩도 검색 풀에 포함해야 한다면, 스크랩 생성 직후 비동기 임베딩 생성(AsyncJob) 방식이 적합합니다.
