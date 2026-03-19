---
title: "[허수아비] Docker Compose 설계 전략 및 트러블슈팅"
date: 2026-03-12 00:00:00 +0900
categories: [Project, 허수아비]
tags: [Docker, DockerCompose, Kafka, Spark, CI/CD, DevOps, Backend, Infra, Hadoop, EC2]
toc: true
comments: true
description: "허수아비 프로젝트의 Docker Compose 설계 철학과 Kafka 리스너 분리, 헬스체크, 포트 충돌 등 실제 트러블슈팅 기록을 정리합니다."
---

EC2 두 대에 걸친 멀티 노드 Docker Compose 구성에서 겪은 설계 결정과 트러블슈팅을 정리합니다.

---

## 핵심 설계 결정 요약

### 1. 아키텍처 분리 및 컨테이너 설계 철학

- **노드 분리 전략:** 사용자 접점 및 최종 저장소 역할을 하는 `EC2 #1 (App & DB)`와 무거운 연산 및 스트리밍을 전담하는 `EC2 #2 (Data & AI Infra)`로 역할을 완벽하게 분리했습니다.
- **스케줄러의 독립성 (`data-pipeline`):** 단순한 크론(Cron) 작업이라도 Spark Master 컨테이너에 섞지 않고 독립된 컨테이너로 분리했습니다. 이는 도커의 '1 컨테이너 1 프로세스' 철학을 지키고, 무중단 배포 및 향후 Airflow 도입을 위한 설계 기반이 되었습니다.
- **Mock 데이터의 분리와 통합:**
  - **분리:** 목적과 실행 환경이 완전히 다른 `mock-cctv`(FFmpeg)와 `mock-radar`(Python)는 각각 독립된 컨테이너로 분리하여 디버깅과 이미지 경량화를 도모했습니다.
  - **통합:** 4개의 CCTV 영상을 쏠 때는 불필요한 OS 오버헤드를 막기 위해 1개의 `mock-cctv` 컨테이너 안에서 백그라운드 스크립트로 병렬 송출하도록 최적화했습니다.

### 2. 빅데이터 생태계의 이해와 최적화

- **하둡용 DB의 진실:** HDFS는 단순한 분산 파일 시스템이므로 원시 데이터를 적재할 때 별도의 DB가 필요하지 않습니다. 이미 세팅한 `PostgreSQL`이 분석 결과를 담을 'DB' 역할을 충실히 수행합니다.
- **Spark 이미지 트러블슈팅:** `bitnami/spark:4.1.1` 이미지가 Docker Hub 정책 변경으로 내려간 상황을 맞닥뜨렸고, 공식 `apache/spark:4.1.1` 이미지로 즉각 선회하여 Master/Worker 실행 명령어를 직접 세팅했습니다.
- **PySpark 직렬화 함정 회피:** Spark 클러스터(Worker) 내부의 Python 마이너 버전과 작업을 지시하는 `data-pipeline`의 베이스 이미지 Python 버전을 완벽하게 일치시켜야 한다는 중요한 의존성 규칙을 짚었습니다.

### 3. 도커 네트워크 및 헬스체크 고도화

- **Kafka 리스너 분리:** 로컬 및 외부 EC2 접속용 `EXTERNAL`(9094) 포트와 컨테이너 간 내부 통신용 `INTERNAL`(9092) 포트를 명확히 분리하여, 백엔드와 워커들이 브로커를 찾지 못하는 Connection Refused 에러를 해결했습니다.
- **우아한 기동 순서 제어:** 외부 스크립트(`wait-for-it.sh`)를 억지로 설치하는 대신, 도커의 최신 권장 방식인 컨테이너 자체 `healthcheck`와 `condition: service_healthy`를 조합하여 DB와 Kafka가 완전히 준비된 후 앱이 켜지도록 구성했습니다.
- **네이밍 컨벤션:** 서비스명과 컨테이너명을 `kebab-case`로 전면 통일하여, 코드의 가독성과 DNS 호스트 네임의 일관성을 확보했습니다.

### 4. 한정된 자원(8GB RAM/CPU)에서의 생존 전략

- **OOM(Out of Memory) 방어선:** 무거운 컨테이너들(Kafka, Spark, AI)에 `deploy.resources.limits` 옵션을 부여하여 한 컨테이너가 서버 전체 자원을 독식하는 것을 막았습니다.
- **AI 및 Java 튜닝:** GPU가 없는 가혹한 환경에서 서버가 뻗는 것을 막기 위해, 스왑 메모리(Swap Space) 설정, YOLO 모델 최소화(Nano) 및 FPS 제한, Hadoop/Spark의 JVM Heap 메모리를 쥐어짜는 경량화 전략을 세웠습니다.

### 5. 개발 및 배포 환경 최적화

- **버전 태그의 늪:** MediaMTX 이미지 태그에서 알파벳 `v` 하나 때문에 빌드가 실패하는 도커 허브의 태그 관례를 경험하고 수정했습니다.
- **초고속 패키지 매니저 (`uv`):** 파이썬 환경의 빌드 속도를 높이기 위해 `uv` 도입을 검토했습니다. 도커 캐시로 인해 일상적인 빌드에서는 극적인 차이가 없지만, 의존성 해결 시에는 큰 이점이 있음을 확인했습니다.
- **철저한 방화벽(포트) 명세:** UFW나 AWS Security Group에 적용할 인바운드 허용 리스트를 작성하며, 컨테이너 내부 통신은 닫아두고 상호 참조가 필요한 최소한의 포트(5430, 9000, 9094, 8889)만 열어두는 보안 원칙을 세웠습니다.

---

## 트러블슈팅 상세

### 1. Kafka ADVERTISED_LISTENERS — 컨테이너 간 통신 불가

**문제**

```yaml
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
```

`backend`, `mock-radar` 등 다른 컨테이너가 Kafka 브로커에 접속할 때 `localhost` 주소를 안내받아 **자기 자신의 9092 포트**를 찾으려다 Connection Refused로 죽음.

**원인**

Docker 네트워크에서 `localhost`는 각 컨테이너 자신을 가리킵니다. Advertised Listener는 클라이언트가 **재접속할 주소**로 사용되므로, 컨테이너 간 통신에는 서비스 이름(hostname)이 필요합니다.

**해결**

리스너를 INTERNAL / EXTERNAL 두 가지로 분리합니다.

```yaml
KAFKA_LISTENERS: INTERNAL://:9092,EXTERNAL://:9094,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:9092,EXTERNAL://localhost:9094
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
```

| 리스너 | 포트 | 용도 |
| --- | --- | --- |
| INTERNAL | 9092 | 컨테이너 간 통신 (서비스명 `kafka` 사용) |
| EXTERNAL | 9094 | 호스트/외부 접근 (`localhost` 또는 EC2 IP 사용) |
| CONTROLLER | 9093 | KRaft 내부 전용 (노출 불필요) |

### 2. Healthcheck 및 기동 순서 제어 누락

**문제**

`depends_on`에 서비스 이름만 나열하면 **컨테이너 시작** 순서만 보장되고, 실제 서비스 준비 완료(DB accept, Broker ready)는 보장되지 않습니다. Backend/AI가 Postgres·Kafka 부팅 중에 연결을 시도하다 실패하고 종료됩니다.

**해결**

각 서비스에 healthcheck 추가 + `condition: service_healthy` 사용:

```yaml
# postgres
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U admin -d birdybuddy"]
  interval: 10s
  timeout: 5s
  retries: 5

# minio
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
  interval: 10s
  timeout: 5s
  retries: 5

# kafka
healthcheck:
  test: ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s   # KRaft 초기화 시간 확보 필수

# 의존 서비스
depends_on:
  postgres:
    condition: service_healthy
  kafka:
    condition: service_healthy
```

> **Kafka `start_period` 주의**
> Kafka KRaft 모드는 초기화에 시간이 걸립니다. `start_period` 없이 `interval: 10s`만 설정하면 부팅 중 healthcheck가 실패로 카운트되어 `retries` 소진 후 `unhealthy` 판정을 받을 수 있습니다. **`start_period: 30s` 필수.**


### 3. 포트 충돌 — 기존 컨테이너와 중복 바인딩

**문제**

`infra/ec2-data/`, `infra/ec2-app/` docker-compose로 올라온 `birdybuddy-*` 컨테이너가 이미 9000, 9001, 5430, 8554 포트를 점유한 상태에서 `docker-compose.local.yml`을 실행하면 포트 바인딩 실패:

```
Bind for 0.0.0.0:9000 failed: port is already allocated
```

**해결**

로컬 실행 전 기존 compose 스택을 먼저 내려야 합니다.

```bash
cd infra/ec2-data && docker compose down -v
cd infra/ec2-app  && docker compose down -v
```


### 4. mock-edge → mock-cctv / mock-radar 분리

**배경**

`mock-edge` 단일 컨테이너가 CCTV 스트리밍(RTSP → MediaMTX)과 레이더 데이터 송출(Kafka) 두 가지 역할을 함께 담당하고 있었습니다.

**분리 기준**

| 서비스 | 역할 | 의존성 |
| --- | --- | --- |
| `mock-cctv` | RTSP 영상 스트림 → media-proxy | `media-proxy` |
| `mock-radar` | 레이더 좌표 데이터 → Kafka | `kafka` (healthy) |

**환경변수 분리**

`mock-cctv/.env`

```
MEDIA_PROXY_URL=rtsp://media-proxy:8554
AIRPORT_ID=
CCTV_FPS=10
TZ=Asia/Seoul
```

`mock-radar/.env`

```
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_RADAR_TOPIC=radar-raw
AIRPORT_ID=
RADAR_INTERVAL_MS=1000
TZ=Asia/Seoul
```

> **네이밍 주의:** Docker 서비스명 및 디렉토리명은 **kebab-case** (`mock-cctv`, `mock-radar`)로 통일. 환경변수의 URL에서도 underscore(`media_proxy`) 대신 kebab-case(`media-proxy`) 사용.


### 5. 로컬 환경에서 Spark 클러스터 부재

`infra/ec2-data/docker-compose.yml`에는 `spark-master`, `spark-worker`, `namenode`, `datanode`가 있지만 `docker-compose.local.yml`에는 포함되지 않습니다.

`data-pipeline` 코드가 Spark 실행 모드를 어떻게 설정하는지에 따라 대응이 달라집니다.

- **로컬 모드** (`SparkSession.builder.master("local[*]")`) → 클러스터 없이 동작 가능, 로컬 compose 그대로 사용
- **클러스터 모드** (`spark://spark-master:7077` 하드코딩) → 로컬 compose에 spark-master/worker 추가 필요


### 6. 프론트엔드 포트 매핑 확인 필요

현재 설정: `"3000:80"`

컨테이너 내부에서 **Nginx**를 띄우는 프로덕션 빌드라면 80이 맞습니다. **Vite / CRA 개발 서버**를 그대로 띄운다면 내부 포트가 5173(Vite) 또는 3000(CRA)이므로 매핑 수정이 필요합니다. Dockerfile 완성 시점에 재확인.

---

## EC2 포트 정리

### EC2 #1 — App & DB (`ec2-app/`) 인바운드 허용 리스트

| 포트 | 프로토콜 | 목적 | 허용 대상 | 서비스 |
| --- | --- | --- | --- | --- |
| **22** | TCP | SSH 서버 원격 접속 | 관리자 (내 PC) IP | - |
| **80** | TCP | 웹 UI HTTP 접속 | Anywhere (0.0.0.0/0) | frontend (nginx) |
| **443** | TCP | 웹 UI HTTPS 접속 | Anywhere (0.0.0.0/0) | frontend (nginx) |
| **5430** | TCP | PostgreSQL 데이터 적재 | EC2 #2의 Private IP | postgres |
| **9000** | TCP | MinIO API 이미지 저장 | EC2 #2의 Private IP | minio |
| **9001** | TCP | MinIO Web Console 모니터링 | 관리자 (내 PC) IP | minio |

> `backend`, `frontend`는 `app-net` 내부 통신 외에 nginx를 통해서만 외부 노출

### EC2 #2 — AI & Data Infra (`ec2-data/`) 인바운드 허용 리스트

| 포트 | 프로토콜 | 목적 | 허용 대상 | 서비스 |
| --- | --- | --- | --- | --- |
| **22** | TCP | SSH 서버 원격 접속 | 관리자 (내 PC) IP | - |
| **9094** | TCP | Kafka 메시지 구독 | EC2 #1의 Private IP | kafka |
| **8889** | TCP | WebRTC 영상 스트리밍 (HTTP) | Anywhere (0.0.0.0/0) | media-proxy |
| **8890** | UDP | WebRTC 영상 스트리밍 (UDP) | Anywhere (0.0.0.0/0) | media-proxy |
| **8989** | TCP | Kafka UI 모니터링 | 관리자 (내 PC) IP | kafka-ui |
| **9870** | TCP | HDFS NameNode Web UI | 관리자 (내 PC) IP | namenode |
| **9864** | TCP | HDFS DataNode Web UI | 관리자 (내 PC) IP | datanode |
| **8080** | TCP | Spark Master Web UI | 관리자 (내 PC) IP | spark-master |

> HDFS RPC(9000)는 `data-net` 내부 전용 — 호스트 미노출
> `spark-worker` Web UI(8081), `ai`, `mock-cctv`, `mock-radar`, `data-pipeline`은 포트 미노출 (외부 접근 불필요)
