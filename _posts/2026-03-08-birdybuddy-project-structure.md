---
title: "[허수아비] 모노레포 프로젝트 구조"
date: 2026-03-08 10:00:00 +0900
categories: [Project, 허수아비]
tags: [Monorepo, Docker, Architecture, CI/CD, DevOps, Kafka, Spark, Backend, EC2, Infra]
toc: true
comments: true
description: "EC2 2대·단일 레포지토리 제약 속에서 '허수아비' 프로젝트의 디렉토리 구조와 컨테이너 배치를 결정한 근거, 그리고 모노레포 환경에 맞게 설계한 브랜치 전략과 커밋 컨벤션을 정리합니다."
---

허수아비 프로젝트의 구조를 결정짓는 강력한 두 가지 전제 조건이 있었습니다.

- **물리적 인프라 한계:** 가용 서버가 **EC2 인스턴스 2대**로 제한
- **형상 관리 정책:** 모든 코드를 하나의 저장소에서 관리하는 **단일 레포지토리(Monorepo)**

이 두 제약 아래에서 의존성 충돌을 막고, CI/CD를 최적화하고, 인프라 장애를 격리하기 위한 구조를 어떻게 설계했는지 정리합니다.

---

## 미리보기

- **디렉토리 구조:** 언어/기술 스택이 아닌 '논리적 도메인' 기준으로 5+1 최상위 디렉토리 분리
- **EC2 배치:** App 서빙(#2)과 AI·데이터 연산(#1)을 물리적으로 격리하여 장애 전파 차단
- **브랜치 전략:** `main ← dev ← feat/*` 3단계 구조 + Jira 이슈 키 연동
- **커밋 컨벤션:** `type(scope): subject #이슈키` 포맷으로 모노레포에서 변경 도메인 즉시 식별

---

## 1. 모노레포 디렉토리 구조

초기에는 배포 서버(Node)를 기준으로 `node_1/`, `node_2/` 폴더로 나누는 방안과 `frontend/`, `backend/`, `ai/`로 단순 분리하는 방안이 후보에 올랐습니다. 그러나 유지보수성과 패키지 충돌 방지를 위해 **논리적 도메인 기반의 5+1 최상위 디렉토리 구조**로 확정했습니다.

```
S14P21A206/
├── frontend/              # React + TypeScript (관제 UI)
├── backend/               # Spring Boot (핵심 API, Kafka 구독, SSE 푸시)
├── ai/                    # FastAPI + YOLO (실시간 조류 탐지 워커)
├── mock_edge/             # Python (가상 엣지 센서 - CCTV·레이더 시뮬레이터)
├── data_pipeline/         # PySpark (장기 통계 집계 배치, HDFS 아카이빙)
└── infra/                 # 글로벌 인프라 배포 설정 (EC2별 docker-compose)
    ├── ec2-data/
    │   └── docker-compose.yml   # EC2 #1 통합 실행 파일
    └── ec2-app/
        └── docker-compose.yml   # EC2 #2 통합 실행 파일
```

### 결정 근거

**1. 의존성 충돌(Dependency Hell) 원천 차단**

`mock_edge`(영상/RTSP 송출), `ai`(PyTorch/OpenCV), `data_pipeline`(PySpark/Hadoop)은 사용하는 패키지 생태계가 완전히 다릅니다. 이를 하나의 폴더나 컨테이너에 묶으면 버전 충돌 해결에 막대한 시간을 낭비하게 되므로, 최상위 디렉토리로 엄격히 격리했습니다.

**2. CI/CD 파이프라인 최적화**

디렉토리가 명확히 분리되어 있어, GitLab CI에서 변경된 경로(Path)만 추적해 해당 컨테이너만 선택적으로 빌드할 수 있습니다. 프론트엔드 버튼 색상을 변경했다면 프론트엔드 이미지만 새로 빌드됩니다.


## 2. EC2 컨테이너 배치

단일 레포지토리에서 관리되는 코드들은 배포 시점에 `infra/` 폴더의 `docker-compose.yml`을 통해 2대의 EC2 서버로 분산 배치됩니다.

| **EC2** | **역할** | **구동 컨테이너** |
| --- | --- | --- |
| **EC2 #1** (AI & Data) | 데이터 수집 및 무거운 연산 | `mock_edge`, `ai(YOLO)`, `media_proxy(MediaMTX)`, `kafka`, `spark`, `hadoop`, `data_pipeline` |
| **EC2 #2** (App & DB) | 애플리케이션 서빙 및 저장 | `frontend(nginx)`, `backend(Spring Boot)`, `minio`, `postgresql` |

### 결정 근거

**1. JVM OOM으로 인한 연쇄 장애 차단 (Fault Isolation)**

EC2 #1에 배치된 Kafka, Spark, Hadoop은 모두 JVM 위에서 동작하는 메모리 다소비 프로세스들입니다. 이들을 Spring Boot와 같은 서버에 두었다가 OOM(Out Of Memory) 에러로 컨테이너가 멈추면, 메인 웹 서비스까지 동반 다운되는 대참사가 발생합니다. EC2 #1로 완전히 격리함으로써 데이터 파이프라인이 붕괴하더라도 **EC2 #2의 관제 UI와 핵심 API는 무중단 서비스를 유지**합니다.

**2. 실제 물리적 엣지 환경의 모사**

현실의 관제 시스템에서 CCTV와 레이더 센서(Edge)는 중앙 서버(App)와 수십 킬로미터 떨어져 있습니다. `mock_edge` 컨테이너를 EC2 #1에 의도적으로 배치함으로써 컨테이너 간 로컬 파일 시스템 공유 같은 꼼수를 원천 차단하고, 오직 네트워크 프로토콜(RTSP, Kafka)을 통해서만 데이터를 주고받도록 강제했습니다. 추후 실제 하드웨어 센서를 도입하더라도 **IP 주소만 변경하면 즉시 호환**됩니다.

**3. 영상 트래픽의 메인 서버 완전 우회 (Bypass)**

무거운 CCTV 영상 스트리밍(WebRTC)은 EC2 #1의 `media_proxy(MediaMTX)`가 전담합니다. EC2 #2의 Spring Boot는 영상 중계에 단 1%의 자원도 소모하지 않으며, 오직 가벼운 레이더 좌표와 위험 알림 텍스트(SSE)만 처리합니다.

**4. CPU 집중 부하의 물리적 격리 (Workload Isolation)**

EC2 #1은 영상 프레임 분석(YOLO)과 대용량 데이터 처리(Spark)로 CPU 점유율이 극단적으로 치솟는 환경입니다. 이를 물리적으로 분리하여 **EC2 #2의 UI 렌더링 및 API 응답 가용성을 100% 보장**합니다.


## 3. 전체 디렉토리 상세 구조

```
S14P21A206/
├── .gitlab/
│   └── merge_request_templates/
│       └── Default.md             # 확정된 MR 템플릿
├── .gitlab-ci.yml                 # CI/CD 파이프라인 (경로 기반 필터링)
├── .gitignore
├── .editorconfig                  # IDE 포맷팅 통일 규약
├── .env.example                   # 전체 시스템 환경변수 명세
├── README.md
│
├── frontend/                      # [Client Layer] React + TypeScript
│   ├── src/
│   │   ├── components/            # 공통 UI 컴포넌트
│   │   ├── pages/                 # 라우팅 페이지 (관제 대시보드 등)
│   │   └── services/              # API 통신 및 SSE 구독 로직
│   ├── Dockerfile                 # Nginx 기반 멀티 스테이지 빌드
│   └── .dockerignore
│
├── backend/                       # [EC2 #2] Spring Boot
│   └── src/main/java/com/heoswabi/
│       ├── kafka/                 # Kafka Consumer (레이더 좌표, 위험 알림)
│       └── sse/                   # SSE Emitter 관리 로직
│
├── ai/                            # [EC2 #1] FastAPI + YOLO
│   ├── app/
│   │   ├── core/                  # YOLO 모델 로드 및 추론 엔진 (PyTorch)
│   │   └── kafka_producer.py      # 탐지 결과(JSON)를 Kafka로 발행
│   └── weights/                   # YOLO 가중치 파일 (.pt) -> gitignore 처리
│
├── mock_edge/                     # [EC2 #1] 가상 센서 송출기
│   ├── cctv_simulator/
│   │   └── stream.py              # FFmpeg로 RTSP 영상 송출
│   └── radar_collector/
│       └── mock_radar.py          # CSV 리더 및 Kafka 1초 단위 발행
│
├── data_pipeline/                 # [EC2 #1] PySpark 데이터 처리
│   ├── streaming/
│   │   └── hdfs_archiver.py       # Kafka 메시지를 HDFS 원시 로그로 저장
│   └── batch/
│       └── daily_aggregator.py    # 자정 통계 연산 후 PostgreSQL 적재
│
└── infra/
    ├── ec2-data/                  # EC2 #1 환경
    │   ├── docker-compose.yml     # kafka, ai, mock_edge, spark, hadoop, media_proxy
    │   ├── media_proxy/
    │   │   └── mediamtx.yml       # WebRTC 영상 중계기 설정
    │   └── hadoop/                # HDFS 코어 설정 (core-site.xml 등)
    └── ec2-app/                   # EC2 #2 환경
        ├── docker-compose.yml     # frontend, backend, postgresql, minio
        ├── nginx/
        │   └── default.conf       # 리버스 프록시 라우팅
        └── postgresql/
            └── init.sql           # DB 초기 스키마 생성 스크립트
```

---

## 마치며

모노레포는 코드를 한곳에서 관리하는 편리함이 있지만, 구조 설계를 잘못하면 의존성 지옥과 CI 병목이라는 역풍을 맞습니다. 허수아비에서는 **도메인별 최상위 디렉토리 분리**로 패키지 생태계를 격리하고, **scope 기반 커밋 컨벤션**으로 변경 도메인을 즉시 식별할 수 있는 구조를 갖췄습니다.
