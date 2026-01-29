---
title: "[LIVErary] Spring Scheduler를 활용한 예약 방 수명주기 관리 (자동 시작/종료)"
date: 2026-01-29 09:00:00 +0900
categories: [Projects, LIVErary]
tags: [SpringBoot, Scheduler, JPA, Cron, Automation, Refactoring]
toc: true
comments: true
image: /assets/img/posts/2026-01-29-liverary-room-scheduler-logic/2.png
description: "Spring Scheduler를 도입하여 예약된 방의 상태(자동 시작, 노쇼 종료, 정상 종료)를 자동으로 관리하는 로직을 구현했습니다. Cron 표현식을 활용한 주기적 실행 흐름과 JPA 쿼리 메서드를 이용한 상태 변경 과정을 상세히 정리합니다."
---

**LIVErary**는 실시간 소통 플랫폼이기에 시간의 흐름에 따라 방의 상태가 자동으로 변해야 한다.
사용자가 예약한 시간이 되면 방이 열려야 하고, 아무도 오지 않으면 닫혀야 하며, 약속된 시간이 끝나면 종료되어야 한다.

이를 관리자가 수동으로 처리할 수 없으므로, **Spring Scheduler**를 도입하여 1분마다 전수 검사를 수행하고 상태를 업데이트하는 자동화 로직을 구현했다.

---

## 독서 모임방의 User Flow

독서 모임방 (`TALK`)이 생기고 사라지기까지의 생애주기 관점에서 다음과 같은 Flow Diagram으로 정리해보았다.

![독서 모임방 입퇴장 설계](/assets/img/posts/2026-01-29-liverary-room-scheduler-logic/2.png)
*독서 모임방 입퇴장 설계*

## 스케줄러의 동작 흐름

스케줄러는 **주기적인 실행(Trigger) → 대상 조회(Query) → 상태 변경(Update) → 트랜잭션 커밋(Commit)**의 4단계 순서로 동작한다.

알림 발송 기능을 제외하고, 핵심적인 3가지 상태 변경 로직(자동 시작, 노쇼 종료, 정상 종료)에 집중하여 설계했다.

![스케줄러 동작 흐름](/assets/img/posts/2026-01-29-liverary-room-scheduler-logic/1.png)
*스케줄러 동작 흐름*

### Step 1. 트리거 발생 (Trigger)

Spring Framework의 스케줄링 모듈이 설정된 **Cron Expression**(`0 * * * * *`, 매 분 0초)에 맞춰 `runRoomSchedules()` 메서드를 호출한다. 이때 `@Transactional`에 의해 하나의 트랜잭션이 시작된다.

### Step 2. 자동 시작 (Auto-Start)

예약된 시간 10분 전부터 방 입장이 가능하도록 상태를 변경한다.

* **조건:** 상태가 `SCHEDULED`(예약됨)이고, 시작 시간이 `현재 + 10분`보다 작거나 같은 방.
* **동작:** 상태를 `LIVE`로 변경.

### Step 3. 노쇼 자동 종료 (No-Show Close)

방이 시작되었으나 일정 시간 동안 아무도 들어오지 않으면 방을 종료한다.

* **조건:** 상태가 `LIVE`이고, 시작한 지 `10분`이 지났으며, 현재 인원(`currentCount`)이 `0명`인 방.
* **동작:** 상태를 `FINISHED`로 변경.

### Step 4. 정상 종료 (Auto-Close)

예약된 종료 시간이 되면 방을 닫는다.

* **조건:** 상태가 `LIVE`이고, 종료 시간이 `현재`보다 지난 방.
* **동작:** 상태를 `FINISHED`로 변경.

### Step 5. 트랜잭션 커밋 (Commit)

메서드가 종료되면 트랜잭션이 커밋되면서, **Dirty Checking(변경 감지)**에 의해 변경된 상태 값들이 DB에 `UPDATE` 쿼리로 반영된다.


## 코드 구현

### A. Repository (RoomRepository)

JPA의 쿼리 메서드를 활용하여 조건에 맞는 방을 조회한다.

등호(`=`)가 아닌 범위 연산자(`LessThanEqual`)를 사용하여, 스케줄러가 잠시 중단되었다가 다시 실행되더라도 누락되는 데이터가 없도록 했다.

```java
public interface RoomRepository extends JpaRepository<Room, UUID> {
    // [자동 시작 대상] 시작 시간까지 10분 이하로 남은 예약 방 조회
    List<Room> findAllByStatusAndStartAtLessThanEqual(RoomStatus status, LocalDateTime time);

    // [노쇼 종료 대상] 시작 후 10분 경과했고, 인원이 0명인 라이브 방 조회
    List<Room> findAllByStatusAndStartAtLessThanEqualAndCurrentCount(RoomStatus status, LocalDateTime time, int currentCount);

    // [자동 종료 대상] 종료 시간이 지난 라이브 방 조회
    List<Room> findAllByStatusAndEndAtLessThanEqual(RoomStatus status, LocalDateTime time);
}

```

### B. Service (RoomService)

실제 비즈니스 로직을 수행하는 계층이다. 기준 시간(`threshold`)을 계산하고 상태를 업데이트한다.

```java
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RoomService {
    private final RoomRepository roomRepository;

    /**
     * 1. [자동 시작] 예약 시간 10분 전 오픈
     */
    @Transactional
    public void autoStartScheduledRooms() {
        LocalDateTime threshold = LocalDateTime.now().plusMinutes(10);
        List<Room> rooms = roomRepository.findAllByStatusAndStartAtLessThanEqual(RoomStatus.SCHEDULED, threshold);

        for (Room room : rooms) {
            room.updateStatus(RoomStatus.LIVE);
        }
    }

    /**
     * 2. [노쇼 종료] 시작 10분 후에 참여자 0명이면 종료
     */
    @Transactional
    public void autoCloseNoShowRooms() {
        LocalDateTime threshold = LocalDateTime.now().minusMinutes(10);
        List<Room> rooms = roomRepository.findAllByStatusAndStartAtLessThanEqualAndCurrentCount(RoomStatus.LIVE, threshold, 0);

        for (Room room : rooms) {
            room.updateStatus(RoomStatus.FINISHED);
        }
    }

    /**
     * 3. [자동 종료] 종료 시간이 지나면 종료 및 참여자 퇴장 처리
     */
    @Transactional
    public void autoCloseFinishedRooms() {
        LocalDateTime now = LocalDateTime.now();
        List<Room> rooms = roomRepository.findAllByStatusAndEndAtLessThanEqual(RoomStatus.LIVE, now);

        for (Room room : rooms) {
            room.updateStatus(RoomStatus.FINISHED);
            roomHistoryRepository.exitAllUsersByRoom(
                    room,
                    HistoryStatus.LEFT,
                    now,
                    HistoryStatus.JOINED
            );
        }
    }
}

```

### C. Scheduler (RoomScheduler)

실제 크론잡을 실행하는 **트리거** 역할을 한다.

```java
@Component
@RequiredArgsConstructor
public class RoomScheduler {
    public final RoomService roomService;

    @Scheduled(cron = "0 * * * * *")
    public void runRoomSchedules() {
        // 시작 임박 예약 방을 LIVE로 전환
        roomService.autoStartScheduledRooms();

        // 시작 후 10분 동안 참여자가 없으면 종료
        roomService.autoCloseNoShowRooms();

        // 종료 시간이 지난 방 종료 및 유저 퇴장
        roomService.autoCloseFinishedRooms();
    }
}

```


### 개발 시 유의사항

1. **`@EnableScheduling` 필수:** 메인 애플리케이션 클래스(`BackendApplication`)에 이 어노테이션이 붙어 있어야 스케줄러가 작동한다.
2. **범위 조건(`<=`) 사용:** 서버 재시작이나 배포로 인해 특정 시간(분)의 스케줄러가 실행되지 못할 수 있다. 따라서 정확히 일치하는 시간(`Equals`)을 찾으면 안 되고, **"이미 지났지만 처리되지 않은"** 데이터까지 포함하기 위해 `LessThanEqual`을 사용해야 데이터 정합성이 유지된다.
3. **대량 데이터 처리 (Optimization):** 현재는 객체를 하나씩 조회해서 수정하는 방식(Dirty Checking)이다. 서비스 초기에는 문제가 없으나, 동시 접속 방이 수천 개가 되면 성능 이슈가 발생할 수 있다. 추후에는 `@Modifying`을 사용한 **벌크 연산(Bulk Update)**으로 리팩토링하여 쿼리 한 방으로 상태를 변경하는 최적화를 고려할 수 있다.

