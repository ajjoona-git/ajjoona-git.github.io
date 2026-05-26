---
title: "[SAN] 비동기 스레드 풀 분리: 잡 타입별 Executor 격리"
date: 2026-05-19 10:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, AsyncJob, ThreadPool, Executor, Async, Architecture, Design]
toc: true
comments: true
description: "단일 스레드 풀을 공유하던 5개 비동기 컴포넌트를 AI 호출·GitHub·알림 세 풀로 분리한 설계를 기록합니다. 메시지 큐 없이 @Async Bean 분리만으로 잡 타입 간 간섭을 제거했습니다."
---

`asyncJobExecutor` 단일 풀을 AI 호출, GitHub 커밋, 피드백 알림 등 성격이 다른 5개 컴포넌트가 공유하고 있었습니다. AI 호출(수초~수십초)이 몰리면 corePoolSize 2가 즉시 포화되어, 상대적으로 빠른 GitHub 커밋이나 알림 발송도 큐에서 대기하게 됩니다. 잡 타입 간 처리 속도 차이가 큰 구조에서 단일 풀은 서로 간섭합니다.

---

## Executor 분리 vs 메시지 큐

풀 간섭 문제를 해결하는 방법으로 Executor 분리와 메시지 큐(Kafka/RabbitMQ) 도입 두 가지를 검토했습니다.

메시지 큐는 잡 타입별로 토픽/큐를 나눠 소비자를 독립적으로 운영할 수 있고, 다중 인스턴스 스케일아웃까지 지원합니다. 그러나 브로커 인프라를 추가로 운영해야 하고, 현재 `async_jobs` 상태 기계와 `@TransactionalEventListener` 기반 흐름을 컨슈머 구조로 재설계해야 합니다. 재시도와 데드레터 처리도 큐 레벨로 이관해야 합니다.

Executor 분리는 `AsyncConfig.java` 설정과 `@Async` 어노테이션 값만 바꾸면 됩니다. 기존 이벤트 흐름, `async_jobs` 상태 기계, 재시도 로직은 그대로 유지됩니다. 현재 문제의 원인인 잡 타입 간 간섭은 풀 분리만으로 제거됩니다.

현재는 단일 서버 운영 구조이고 수평 확장 요구가 없습니다. 지금 해결해야 할 문제에 비해 메시지 큐 도입 비용이 과도합니다. Executor 분리로 간섭을 제거하고, 수평 확장이 필요해지는 시점에 메시지 큐 전환을 재검토합니다.

| | Executor 분리 | 메시지 큐 도입 |
|---|---|---|
| 변경 범위 | 설정 파일 + `@Async` 값 | 인프라 추가 + 컨슈머 재설계 |
| 격리 효과 | 잡 타입 간 간섭 제거 | 동일 + 다중 인스턴스 스케일아웃 |
| 재시도/상태 관리 | 기존 `async_jobs` 상태 기계 유지 | 큐 레벨로 이관 필요 |
| 적합 시점 | 현재 단일 서버 구조 | 수평 확장이 필요해질 때 |

### 풀을 분리하면 뭐가 좋지?

풀을 분리하면 각 잡 타입이 독립된 스레드 자원을 가집니다.

- **간섭 제거**: AI 호출이 몰려 `aiJobExecutor`가 포화되어도 `githubJobExecutor`와 `notificationExecutor`는 영향을 받지 않습니다. GitHub 커밋과 피드백 알림은 AI 작업 부하와 무관하게 즉시 처리됩니다.
- **튜닝 독립성**: 잡 타입별로 corePoolSize, maxPoolSize, queueCapacity를 독립적으로 조정할 수 있습니다. AI 서버 응답이 느려지는 상황에서 `aiJobExecutor`의 풀 크기만 늘리면 됩니다.
- **장애 격리**: 특정 외부 서비스가 느려져 스레드가 묶히더라도 다른 풀의 잡 처리는 계속됩니다.

---

## 풀 설계

| Bean | 대상 | 특성 | core / max / queue |
|---|---|---|---|
| `aiJobExecutor` | `KnowledgeCardAnalysisJobProcessor`<br>`TilGenerationJobProcessor`<br>`ScrapRefineJobProcessor` | AI HTTP, 느린 I/O bound | 4 / 10 / 50 |
| `githubJobExecutor` | `TilGithubCommitJobProcessor` | GitHub API, 중간 속도 | 2 / 6 / 30 |
| `notificationExecutor` | `MattermostFeedbackNotifier` | 단순 HTTP, 빠름 | 1 / 3 / 20 |

AI 호출은 응답 대기 시간이 길어 I/O bound 특성을 가지므로 corePoolSize를 넉넉하게 잡았습니다. GitHub API는 중간 속도, 알림은 단순 HTTP로 빠르므로 각각 더 작은 풀로 충분합니다.

`ScrapRefineJobProcessor`는 초안에서 `githubJobExecutor`로 분류했으나, `ScrapRefineService`가 AI 정제 호출을 수행하므로 `aiJobExecutor`로 변경했습니다. 코드리뷰에서 지적된 부분입니다.

