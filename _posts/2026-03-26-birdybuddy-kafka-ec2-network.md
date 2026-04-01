---
title: "[허수아비] Kafka 멀티 EC2 네트워크 트러블슈팅: bootstrap 주소 해석 실패"
date: 2026-03-26 10:00:00 +0900
categories: [Project, 허수아비]
tags: [Kafka, Docker, EC2, Network, Troubleshooting, DockerCompose, Port, Infra]
toc: true
comments: true
image: /assets/img/posts/2026-03-26-birdybuddy-kafka-ec2-network/1.png
description: "허수아비 프로젝트에서 EC2 #2의 backend가 EC2 #1의 Kafka에 접속하지 못하는 문제를 분석하고 해결합니다. Docker 내부 호스트명과 외부 포트의 차이, Kafka 리스너 구성, 멀티 EC2 환경에서의 환경변수 관리 전략을 함께 정리합니다."
---

허수아비 프로젝트는 두 대의 EC2에 서비스를 분산 배포하는 구조입니다. EC2 #1에는 Kafka, AI, 데이터 파이프라인을 올리고, EC2 #2에는 Spring Boot backend, frontend, PostgreSQL, MinIO를 올렸습니다.

배포 과정에서 EC2 #2의 backend가 EC2 #1의 Kafka에 접속하지 못하는 문제가 발생했습니다. 원인을 분석하고 해결하는 과정, 그리고 관련 개념을 함께 정리합니다.

## 트러블슈팅: backend의 Kafka bootstrap 주소 해석 실패

### 증상

```
Caused by: org.apache.kafka.common.config.ConfigException:
No resolvable bootstrap urls given in bootstrap.servers
```

### 원인

`ENV_BACKEND`에 `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`로 설정되어 있었습니다.

`kafka`는 EC2 #1의 Docker 내부 네트워크 호스트명입니다. Docker Compose로 띄운 서비스들은 같은 `networks:` 안에 있을 때만 서비스명으로 DNS 해석이 가능합니다. EC2 #2는 EC2 #1의 Docker 네트워크에 속하지 않으므로 `kafka`라는 호스트명을 해석할 수 없습니다.

### 해결

`ENV_BACKEND`에서 EC2 #1의 외부 주소와 외부 포트로 변경했습니다.

```
KAFKA_BOOTSTRAP_SERVERS=j14A206B.p.ssafy.io:9094
```

`9092`는 Docker 내부 포트이고, `9094`는 외부에 노출된 포트입니다.



## 개념 정리: 포트와 네트워크

### Docker 네트워크와 호스트명

Docker Compose로 띄운 서비스들은 같은 `networks:` 블록 안에 있을 때만 서비스명으로 DNS 해석이 가능합니다. 프로젝트의 네트워크 구성은 다음과 같습니다.

```
EC2 #1 (data-net)          EC2 #2 (app-net)
┌──────────────────┐        ┌──────────────────┐
│ kafka            │        │ backend          │
│ ai               │        │ frontend         │
│ mock-radar       │        │ postgres         │
│ data-pipeline    │        │ minio            │
└──────────────────┘        └──────────────────┘
```

- `data-net` 내부 서비스끼리는 `kafka:9092`, `minio:9000` 등 서비스명으로 접근 가능합니다.
- **다른 EC2의 서비스**는 서비스명으로 접근할 수 없으며, 외부 IP + 외부 포트가 필요합니다.

### Kafka 포트: 9092 vs 9094

| 포트 | 리스너 | 용도 |
|---|---|---|
| `9092` | `INTERNAL` | Docker 내부 통신 (같은 data-net) |
| `9094` | `EXTERNAL` | 외부 접근 (EC2 #2 → EC2 #1, 로컬 호스트 등) |

- EC2 #1 내부 서비스(`ai`, `mock-radar`, `data-pipeline`) → `kafka:9092`
- EC2 #2의 `backend` → `<EC2_DATA_IP>:9094`
- 로컬 개발 환경 → 모든 서비스가 같은 네트워크이므로 `kafka:9092`

### 인바운드 vs 아웃바운드 포트

- **인바운드**: 외부에서 해당 서버로 **들어오는** 트래픽을 허용하는 규칙입니다.
- **아웃바운드**: 해당 서버에서 외부로 **나가는** 트래픽을 허용하는 규칙입니다.

`9094`를 EC2 #1 보안 그룹의 **인바운드**로 열어두면, EC2 #2의 backend가 EC2 #1:9094로 접속할 수 있습니다.

### 로컬과 EC2 환경의 포트 설정이 달라도 되는 이유

로컬은 모든 컨테이너가 같은 Docker 네트워크에 있어서 내부 포트(9092)로 통신이 가능합니다. EC2는 두 서버가 물리적으로 분리되어 있어 외부 포트(9094)가 필요합니다.

각 서비스의 `.env.example`은 로컬 기준으로 작성하고, EC2용 실제 값은 GitLab variables(`ENV_*`)로 관리하면 환경별로 올바른 설정이 주입됩니다.

![docker compose 실행 결과](/assets/img/posts/2026-03-26-birdybuddy-kafka-ec2-network/1.png)
*docker compose 실행 결과*
