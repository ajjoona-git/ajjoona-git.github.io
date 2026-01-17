---
title: "[LIVErary] 로컬 개발 환경 구축: Docker Compose로 MySQL, Redis, Media Server 통합하기"
date: 2026-01-17 09:00:00 +0900
categories: [Projects, LIVErary]
tags: [Docker, DockerCompose, Infrastructure, MySQL, Redis, Kurento, Coturn, WebRTC]
toc: true
comments: true
image: /assets/img/posts/2026-01-17-liverary-local-dev-environment-docker/1.png
description: "LIVErary 프로젝트의 로컬 개발 환경을 Docker Compose로 구축한 과정입니다. 각 컨테이너(MySQL, Redis, Kurento, Coturn)의 역할과 네트워크 구성, 그리고 docker-compose.yml 파일의 상세 설정을 분석합니다."
---

프로젝트 **LIVErary**는 단순한 웹 애플리케이션이 아니라, 실시간 화상 소통(WebRTC)을 위한 미디어 서버와 고성능 캐시 서버 등 다양한 인프라를 필요로 한다.
이 모든 것을 로컬 개발자의 PC에 하나하나 설치하는 것은 비효율적이다. 따라서 우리는 **Docker Compose**를 활용해 명령어 한 줄(`docker compose up -d`)로 개발 환경을 구축하기로 했다.

이번 포스트에서는 Docker 컨테이너의 개념과 우리 프로젝트의 인프라 아키텍처, 그리고 `docker-compose.yml` 설정 파일의 상세 내용을 정리한다.

---

## Docker 컨테이너란?

**Docker 컨테이너**는 애플리케이션과 그 실행에 필요한 모든 의존성(라이브러리, 설정 파일, 런타임 등)을 하나로 패키징한 논리적 단위다.
가상 머신(VM)과 달리 독자적인 운영체제(Guest OS)를 포함하지 않고, 호스트 운영체제(Host OS)의 커널을 공유하며 프로세스 수준에서 격리되므로 훨씬 가볍고 빠르다.

### 주요 기술 요소

- **Namespaces (격리):** 프로세스 ID, 네트워크, 파일 시스템 등을 호스트와 분리하여 독립된 공간처럼 보이게 한다.
- **Cgroups (제어):** CPU, 메모리, 디스크 I/O 등 시스템 리소스 사용량을 제한한다.
- **Union File System (계층화):** 이미지를 읽기 전용(Read-Only) 레이어로 쌓고, 실행 시 쓰기(Writable) 레이어를 얹어 효율적으로 관리한다.

## 개발 환경 아키텍처 (Infrastructure Architecture)

현재 로컬 PC(Windows + WSL2)에서 실행되는 구조다. Spring Boot 서버는 IDE에서 네이티브로 실행하고, 나머지 인프라는 Docker 컨테이너로 띄워 관리한다.

![Infrastructure Architecture](/assets/img/posts/2026-01-17-liverary-local-dev-environment-docker/1.png)
*Infrastructure Architecture*


## 각 컨테이너의 역할 (Components)

### **① MySQL 컨테이너 (RDBMS)**

- **역할:** 영속성 데이터(Persistent Data) 저장소.
- **저장 데이터:** 회원 정보(`User`), 방 정보(`Room`), 입퇴장 로그(`RoomHistory`), 도서 정보(`Book`) 등.
- **Spring 연동:** Spring Data JPA를 통해 3306 포트로 JDBC 커넥션을 맺는다.

### **② Redis 컨테이너 (In-Memory Data Store)**

- **역할:** 고성능 임시 데이터 저장 및 캐싱.
- **저장 데이터 (휘발성):**
    - `JWT Refresh Token`: 로그인 유지 및 보안 토큰 관리
    - `Session State`: 실시간 채팅방의 마이크 On/Off 상태, 현재 접속자 목록 등 빈번하게 변하는 데이터
    - `Cache`: 자주 조회되는 도서 랭킹 등
- **Spring 연동:** `RedisTemplate`을 사용해 Key-Value 형태로 통신한다.

### **③ Kurento / Coturn 컨테이너 (Media Server)**

- **역할:** 실시간 멀티미디어 처리 및 네트워크 중계
- **Kurento Media Server (KMS):** N:M 화상 채팅 시, 클라이언트들의 영상/음성 스트림을 받아서 다른 사람에게 전달(Routing)하거나, 합성(Mixing), 녹화(Recording)하는 미디어 파이프라인 처리를 담당.
- **Coturn (TURN/STUN Server):** 클라이언트가 방화벽(NAT) 뒤에 있을 때, P2P 연결이 불가능한 경우 미디어 패킷을 중계(Relay).
- **Spring 연동:** Spring은 WebSocket을 통해 Kurento에게 "A와 B를 연결해"와 같은 제어 명령(Signaling)을 내린다.

## docker-compose.yml 분석

### **주요 설정 포인트**

- **MySQL 포트 포워딩 (`3307:3306`)**:
    - 개발자 PC에는 이미 로컬 MySQL이 3306 포트를 점유하고 있을 확률이 높다. 충돌을 피하기 위해 호스트의 **3307** 포트를 컨테이너의 3306 포트로 연결했다. Spring 설정에서도 포트를 3307로 맞춰야 한다.
- **Redis 영속성 (`appendonly yes`)**:
    - Redis는 기본적으로 메모리에만 저장하지만, 이 옵션을 켜면 디스크에 로그를 기록하여 컨테이너가 재시작되어도 데이터가 유지된다.
- **환경 변수 (`.env`) 사용**:
    - DB 비밀번호나 TURN 서버 인증 정보 같은 민감한 데이터는 코드에 직접 적지 않고 `${VAR}` 문법을 통해 `.env` 파일에서 주입받도록 했다.
- **Coturn 포트 범위**:
    - TURN 서버는 미디어 데이터를 중계할 때 많은 포트를 사용한다. `49160-49200` 범위를 명시적으로 열어주어야 영상이 정상적으로 전달된다.

```yaml
# docker-compose.yml
name: liverary
services:
  mysql:
    image: mysql:8.0
    container_name: mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      # ... (생략)
    ports:
      - "127.0.0.1:3307:3306" # Local 3307 -> Container 3306
    volumes:
      - mysql_data:/var/lib/mysql
    command: >
      --default-authentication-plugin=mysql_native_password
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
    networks:
      - appnet

  redis:
    image: redis:7-alpine
    container_name: redis
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    command: ["redis-server", "--appendonly", "yes"] # 데이터 영구 저장(AOF) 활성화
    networks:
      - appnet

  kms:
    image: kurento/kurento-media-server:latest
    container_name: kms
    restart: unless-stopped
    ports:
      - "127.0.0.1:8888:8888" # Spring 제어용 포트
    environment:
	    # STUN/TURN 서버 설정 주입
      TZ: ${TZ:-Asia/Seoul}
      KMS_STUN_IP: ${KMS_SERVER_NAME}
      KMS_STUN_PORT: ${KMS_SERVER_PORT}
      KMS_TURN_URL: ${KMS_TURN_USER}:${KMS_TURN_PASSWORD}@${KMS_SERVER_NAME}:${KMS_SERVER_PORT}?transport=udp
    networks:
      - appnet
    labels: # 스프링 시작할 때 준비될 필요 x
      org.springframework.boot.readiness-check.tcp.disable: "true"

  coturn:
    image: coturn/coturn:latest
    container_name: coturn
    restart: unless-stopped
    ports:
      - "127.0.0.1:3478:3478/tcp"
      - "127.0.0.1:3478:3478/udp"
      - "127.0.0.1:5349:5349/tcp"
      - "127.0.0.1:5349:5349/udp"
      - "49160-49200:49160-49200/udp"
    environment:
      TZ: ${TZ:-Asia/Seoul}
    volumes:
      - ./.coturn/turnserver.conf:/etc/turnserver.conf:ro
    command: ["-c", "/etc/turnserver.conf"]
    networks:
      - appnet
    labels: # 스프링 시작할 때 준비될 필요 x
      org.springframework.boot.readiness-check.tcp.disable: "true"

networks:
  appnet:
    driver: bridge

volumes:
  mysql_data:
  redis_data:

```

### **Global Settings (전역 설정)**

- **`name: liverary`**: Docker Compose 프로젝트의 이름을 'liverary'로 지정. 컨테이너들이 생성될 때 `liverary-mysql-1` 같은 접두사로 붙는다.
- **`networks: appnet`**: 4개의 컨테이너가 서로 통신할 수 있는 `appnet`이라는 가상의 내부 네트워크(Bridge)를 만든다.
- **`volumes`**: `mysql_data`, `redis_data`라는 저장 공간을 만든다. 컨테이너를 삭제했다가 다시 켜도 데이터가 날아가지 않게 하기 위함.

### **Services (각 컨테이너 설정)**

**① `mysql` (메인 데이터베이스)**

- **`image: mysql:8.0`**: MySQL 8.0 버전 사용.
- **`restart: unless-stopped`**: 사용자가 명시적으로 끄지 않는 한, 오류로 죽거나 재부팅되어도 자동으로 다시 켜진다.
- **`environment`**: `${VAR}` 문법은 같은 폴더에 있는 `.env` 파일에서 값을 가져온다. DB 비밀번호 등의 민감 정보를 숨기기 위해 사용.
- **`ports`**:
    - 내 컴퓨터(Host)의 **3307** 포트를 컨테이너 내부의 **3306** 포트와 연결한다.
    - 개발자 PC에 이미 로컬 MySQL이 3306 포트를 쓰고 있을 확률이 높으므로, 충돌을 막기 위해 3307로 우회한 것.
- **`volumes`**: 데이터를 영구 저장하기 위해 내부 `/var/lib/mysql` 폴더를 호스트의 `mysql_data` 볼륨과 연결.
- **`command`**:
    - `-default-authentication-plugin=mysql_native_password`: 구형 클라이언트와의 호환성을 위해 구식 인증 방식을 사용.
    - `-character-set-server=utf8mb4`: 한글 및 이모지 저장을 위해 UTF-8 설정을 강제한다.

**② `redis` (캐시 및 세션 저장소)**

- **`image: redis:7-alpine`**: 가볍고 최적화된 Alpine 리눅스 기반의 Redis 7 버전을 사용.
- **`ports`**: `"127.0.0.1:6379:6379"`: 기본 포트 6379를 그대로 사용.
- **`command: ["redis-server", "--appendonly", "yes"]`**:
    - Redis는 원래 메모리에만 저장하지만, 이 옵션을 켜면 데이터를 디스크에 파일로도 기록한다. 서버가 꺼져도 데이터가 복구된다.

**③ `kms` (Kurento Media Server)**

- **`image: kurento/kurento-media-server:latest`**: WebRTC 미디어 처리를 담당하는 쿠렌토 서버.
- **`ports`**: `"127.0.0.1:8888:8888"`: Spring Boot 서버가 쿠렌토에게 명령(시그널링)을 내릴 때 사용하는 제어 포트.
- **`environment`**:
    - STUN/TURN 서버 정보를 환경변수로 주입받는다. WebRTC 연결 시 NAT(공유기 환경)를 넘어가기 위해 자신의 공인 IP 등을 알아내는 데 사용.
- **`labels`**:
    - `org.springframework.boot.readiness-check.tcp.disable: "true"`: Spring Boot의 Docker Compose 지원 기능을 사용할 때, "이 컨테이너가 켜졌는지 굳이 확인하지 말고 넘어가라"는 설정. 부팅이 오래 걸리거나 체크가 불필요할 때 사용.

**④ `coturn` (TURN/STUN Server)**

- **역할**: P2P 연결이 막힌 환경(방화벽 등)에서 미디어 데이터를 중계해주는 서버.
- **`ports`**:
    - `3478`: 기본적인 연결 요청 포트 (TCP/UDP).
    - `5349`: 보안 연결(TLS) 포트.
    - `49160-49200/udp`: **실제 미디어 데이터(영상/음성)가 중계될 때 사용하는 통로**. 이 범위는 방화벽에서 열려 있어야 한다.
- **`volumes`**:
    - `./.coturn/turnserver.conf:/etc/turnserver.conf:ro`: 프로젝트 폴더 내에 있는 설정 파일(`turnserver.conf`)을 컨테이너 안으로 집어넣는다. `:ro`는 Read-Only(읽기 전용).
- **`command`**: 위에서 마운트한 설정 파일을 사용하여 서버를 시작한다.