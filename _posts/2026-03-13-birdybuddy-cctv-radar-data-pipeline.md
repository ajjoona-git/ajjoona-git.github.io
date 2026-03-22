---
title: "[허수아비] CCTV 영상과 레이더 시계열 데이터 파이프라인"
date: 2026-03-13 10:00:00 +0900
categories: [Projects, 허수아비]
tags: [DataPipeline, CCTV, Radar, Kafka, Spark, WebRTC, SSE, Architecture]
toc: true
comments: true
image: /assets/img/posts/2026-03-13-birdybuddy-cctv-radar-data-pipeline/1.png
description: "허수아비 프로젝트의 핵심인 이기종 데이터 처리 파이프라인을 소개합니다. 무거운 CCTV 비정형 데이터의 동기화 처리와 레이더 시계열 데이터의 Spark Streaming 최적화 흐름을 단계별로 정리합니다."
---


'허수아비' 프로젝트는 성격이 완전히 다른 두 가지 형태의 데이터를 실시간으로 다루어야 합니다. 바로 **무거운 비정형 데이터인 CCTV 영상**과 **초당 수만 건이 쏟아지는 시계열 데이터인 레이더 좌표**입니다. 

이번 포스트에서는 시스템 부하를 최소화하면서도 실시간성과 데이터 정합성을 모두 잡아낸 두 데이터 파이프라인의 전체 흐름을 상세히 소개합니다.

---

## 📷 CCTV 영상 데이터 흐름 (비정형 데이터)

CCTV 흐름의 핵심은 무거운 영상 프레임에서 유의미한 정보(객체)를 추출하고, 이를 안전하게 분리하여 저장하는 것입니다.

### 프록시 경유(Relay) 구조의 도입
우리 시스템은 엣지 디바이스의 부하를 최소화하기 위해 `media-proxy`를 스트림 분배기(Distributor)로 활용하는 구조를 채택했습니다. Mock CCTV(엣지)가 `media-proxy`로 단일 RTSP 스트림을 쏘면(Push), 프록시가 이를 받아 AI 워커와 프론트엔드로 각각 중계(Relay)합니다.

| 구분 | 설명 |
| :--- | :--- |
| **장점 (엣지 부하 감소)** | 엣지 디바이스(`mock-cctv`)는 단 하나의 목적지(`media-proxy`)로만 영상을 송출하면 되므로, 네트워크 업로드 대역폭(Bandwidth)과 패킷 생성에 드는 CPU 부하가 대폭 감소하여 엣지 환경을 안정적으로 운영할 수 있습니다. |
| **단점 (단일 장애점, SPOF)** | `media-proxy` 컨테이너가 스트림 분배의 중심이 됩니다. 프록시에 장애가 발생하면 프론트엔드 영상 송출과 AI 객체 탐지가 동시에 중단되는 단일 장애점(SPOF, Single Point of Failure) 위험이 존재합니다. |

### 단계별 데이터 파이프라인

![CCTV 데이터 흐름](/assets/img/posts/2026-03-13-birdybuddy-cctv-radar-data-pipeline/2.png)
*CCTV 데이터 흐름*

**Step 1: 영상 스트리밍 및 분배 (생산)**

`mock-cctv` 컨테이너가 가상의 CCTV 영상 스트림을 생성하여 `media-proxy`로 단일 전송합니다.

`media-proxy`는 이 스트림을 받아 프론트엔드용 WebRTC 프로토콜로 변환하고, AI 컨테이너가 읽어갈 수 있도록 RTSP 스트림을 중계(Relay)합니다.

**Step 2: AI 추론 및 동기화 처리 (단기 / 실시간)**

`AI` 워커(YOLO/FastAPI)가 프록시가 중계해 준 스트림을 읽어 객체(새)를 실시간으로 탐지합니다.

데이터 정합성을 위해 캡처된 이미지 원본을 App Node의 `minio` (오브젝트 스토리지)에 업로드하는 작업이 동기(Sync) 방식으로 실행됩니다.

업로드된 MinIO의 이미지 URL, Bounding Box 좌표, 신뢰도(Confidence) 점수를 JSON 형태로 `kafka` 토픽에 발행합니다.

**Step 3: 실시간 알림 서비스 (단기 / 실시간)**

`backend` (Spring Boot)가 해당 `Kafka` 토픽을 구독하고 있다가, 이벤트가 들어오는 즉시 프론트엔드에 **SSE(Server-Sent Events)**로 알림을 푸시합니다.

사용자는 브라우저에서 알림과 함께 MinIO URL을 통해 실시간 객체 탐지 이미지를 확인합니다.

**Step 4: 영구 보존 및 통계 (장기 / 배치)**

이미지 원본은 `minio` 버킷에 장기 보관되며, AI가 발행했던 탐지 메타데이터(발생 시간, 객체 종류 등)는 `postgres` DB에 적재됩니다.

이후 월간 보고서나 특정 시간대 조류 출몰 빈도 통계 조회 시 이 DB 데이터를 활용합니다.



## 📡 레이더 데이터 흐름 (시계열 스트리밍 데이터)

레이더 흐름의 핵심은 초당 쏟아지는 방대한 좌표 데이터를 실시간 DB 부하 없이 화면에 뿌려주고, 연산의 결과물만 효율적으로 압축하여 장기 보관하는 것입니다.

### 단계별 데이터 파이프라인

![Radar 데이터 흐름](/assets/img/posts/2026-03-13-birdybuddy-cctv-radar-data-pipeline/1.png)
*Radar 데이터 흐름*

**Step 1: 원시 좌표 수집 (생산)**

`mock-radar` 컨테이너가 모의 레이더 좌표 데이터(x, y, v 등)를 쉴 새 없이 생성하여 `kafka`의 `raw-radar-events` 토픽으로 직접 쏘아 올립니다.

**Step 2: 실시간 윈도우 연산 (단기 / 실시간)**

`data-pipeline`의 Spark Streaming이 해당 토픽을 읽어 들여 1초 단위로 윈도우(Window)를 묶어 연산합니다.

지연된 데이터(Late Data)로 인한 메모리 누수를 막기 위해 **워터마크(Watermark)**가 적용됩니다.

컨테이너 재시작 시 꼬임을 막기 위해 최신 데이터(latest offset)부터 읽도록 처리됩니다.

**Step 3: 데이터 분기 - 실시간 대시보드와 아카이빙 (단기 / 실시간)**

- **실시간용:** 즉시 사용 가능한 집계 데이터를 새로운 `kafka` 토픽(`agg-radar-1sec`)에 발행하며, `backend`가 이를 구독하여 SSE를 통해 프론트엔드 관제 화면에 뿌려줍니다. (RDBMS 저장은 철저히 배제됩니다).
- **보관용:** 동시에 Spark는 원시 데이터와 1초 집계 데이터를 Data Node의 `namenode` 및 `datanode` (HDFS)에 Parquet 포맷으로 영구 아카이빙합니다.

**Step 4: 일간 배치 집계 연산 (장기 / 배치)**

매일 자정, 무거운 통계 연산을 담당하는 Spark Batch 작업이 실행됩니다.
별도의 메타 DB(Hive)를 거치지 않고, HDFS에 저장된 Parquet 파일들의 내부 스키마를 직접 읽어 들여 일간/주간/월간 통계를 고속으로 집계합니다.
최종적으로 계산된 깔끔한 통계 데이터만 App Node의 `postgres` 테이블에 적재됩니다.


**Step 5: 통계 대시보드 제공 (장기 / 서비스)**

사용자가 프론트엔드에서 통계를 조회하면, `backend`는 무거운 HDFS가 아닌 최적화된 `postgres` DB만 가볍게 조회하여 장기 트렌드 그래프를 제공합니다.
