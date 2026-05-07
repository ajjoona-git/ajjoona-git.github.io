---
title: "[SAN] CGLIB 프록시: @Async + 인터페이스 구현 클래스에서 발생하는 기동 실패"
date: 2026-05-04 11:00:00 +0900
categories: [Project, SAN]
tags: [SpringBoot, Java, CGLIB, Proxy, Async, AOP, Spring, Troubleshooting]
toc: true
comments: true
description: "AsyncJobProcessor 인터페이스를 구현한 클래스에 @Async를 붙였을 때 @TransactionalEventListener handle() 메서드를 프록시에서 찾지 못해 기동이 실패한 원인과 해결 과정을 기록합니다."
---

`KnowledgeCardAnalysisJobProcessor` 빈 초기화 중 애플리케이션 기동이 실패했습니다. 에러 메시지는 다음과 같습니다.

```
Failed to process @EventListener annotation on bean with name 'knowledgeCardAnalysisJobProcessor':
Need to invoke method 'handle' declared on target class 'KnowledgeCardAnalysisJobProcessor',
but not found in any interface(s) of the exposed proxy type.
Either pull the method up to an interface or switch to CGLIB proxies
by enforcing proxy-target-class mode in your configuration.
```

## Spring AOP 프록시 방식: JDK vs CGLIB

원인을 이해하려면 Spring이 AOP 기반 기능(`@Async`, `@Transactional`, `@EventListener` 등)을 적용할 때 빈을 프록시 객체로 감싼다는 것을 먼저 알아야 합니다. 프록시 방식은 두 가지입니다.

| 방식 | 기반 | 적용 조건 | 노출 메서드 |
|------|------|----------|------------|
| **JDK 동적 프록시** | 인터페이스 | 빈이 인터페이스를 구현한 경우 기본값 | 인터페이스에 선언된 메서드만 |
| **CGLIB 프록시** | 클래스 상속 | `proxyTargetClass = true` 설정 시 | 클래스의 모든 메서드 |

JDK 프록시는 인터페이스를 기반으로 만들어지기 때문에, 인터페이스에 없는 메서드는 프록시 바깥에서 보이지 않습니다. CGLIB는 클래스 자체를 상속해 프록시를 생성하므로 클래스에 정의된 모든 메서드가 노출됩니다.

## `handle()`이 JDK 프록시에서 보이지 않는다

문제가 된 클래스 구조입니다.

```java
// 인터페이스: process() 메서드만 선언
public interface AsyncJobProcessor {
    void process(UUID jobId, UUID targetId);
}

// 구현체: handle() 메서드 추가 (인터페이스에 없음)
@Component
public class KnowledgeCardAnalysisJobProcessor implements AsyncJobProcessor {

    @Async("asyncJobExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(JobCreatedEvent event) { ... }  // ← 인터페이스에 없는 메서드

    @Override
    public void process(UUID jobId, UUID targetId) { ... }
}
```

`handle()` 메서드는 두 조건을 동시에 만족해야 합니다.

- `@Async` → 프록시를 통해 비동기로 호출돼야 함
- `@TransactionalEventListener` → Spring이 프록시에서 메서드를 탐색해야 함

그런데 `@Async`가 붙은 빈은 `AsyncJobProcessor` 인터페이스가 있으므로 JDK 동적 프록시로 생성됩니다. JDK 프록시는 `AsyncJobProcessor`에 선언된 `process()`만 노출하고, 인터페이스에 없는 `handle()`은 노출하지 않습니다. Spring이 `@TransactionalEventListener` 등록을 위해 프록시에서 `handle()`을 탐색하지만 찾지 못해 `BeanInitializationException`이 발생합니다.

```
1. Spring이 KnowledgeCardAnalysisJobProcessor 빈 생성
2. @Async 적용 대상 → 프록시 필요
3. AsyncJobProcessor 인터페이스 존재 → JDK 동적 프록시 선택
4. JDK 프록시는 AsyncJobProcessor 인터페이스 기준으로만 메서드 노출
5. @TransactionalEventListener 등록 시 handle() 탐색
6. 프록시에서 handle() 미노출 → BeanInitializationException 발생
```

## `proxyTargetClass = true`로 CGLIB 강제

`AsyncConfig`에서 CGLIB 프록시를 강제했습니다.

```java
@EnableAsync(proxyTargetClass = true)
@Configuration
public class AsyncConfig { ... }
```

CGLIB는 클래스 자체를 상속해 프록시를 생성하므로, 인터페이스에 없는 `handle()` 메서드도 프록시를 통해 정상 노출됩니다. 기존 `process()` 메서드는 인터페이스를 통해 동일하게 호출됩니다.

## 채택하지 않은 방법들

### `handle()`을 인터페이스에 추가

```java
public interface AsyncJobProcessor {
    void process(UUID jobId, UUID targetId);
    void handle(JobCreatedEvent event);  // 추가
}
```

모든 `AsyncJobProcessor` 구현체가 `handle()`을 구현해야 하는 강제 계약이 생깁니다. `JobCreatedEvent`라는 이벤트 시스템의 구현 세부사항이 인터페이스에 노출되는 설계 오염이 발생해 미채택했습니다.

### 인터페이스 제거

`@Mock AsyncJobProcessor`를 사용하는 테스트 코드 전체 변경이 필요하고 테스트 격리성이 저하되어 미채택했습니다.

## CGLIB 적용 시 주의할 점

- 프록시 대상 클래스는 `final`이면 안 됩니다. CGLIB는 클래스를 상속해 프록시를 만드는데, `final` 클래스는 상속이 불가능합니다.
- 프록시 대상 메서드도 `final`이면 안 됩니다. 상속 후 오버라이드가 불가능하기 때문입니다.
- `@RequiredArgsConstructor`(Lombok) 사용 시 기본 생성자가 없어도 Spring Boot 3.x에 포함된 objenesis 라이브러리가 처리해줍니다.
