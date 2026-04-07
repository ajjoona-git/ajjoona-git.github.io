---
title: "[허수아비] Spark 컨테이너 구성과 역할 정리"
date: 2026-03-20 10:00:00 +0900
categories: [Project, 허수아비]
tags: [Infra, Docker, KappaArchitecture, DataPipeline, StructuredStreaming, HDFS, EC2, Kafka, Spark]
toc: true
comments: true
description: "배포 후 컨테이너 재시작 오류를 계기로 Spark 관련 컨테이너들의 역할과 구성을 전반적으로 점검했습니다. spark-master/worker의 연산 인프라 역할, 4개 Spark job 컨테이너의 책임 분리, Kappa 아키텍처 관점에서의 전체 데이터 흐름을 정리합니다."
---

배포 직후 예상치 못한 컨테이너 재시작 오류를 마주하면서, Spark 관련 컨테이너들이 실제로 어떤 역할을 맡고 있는지 체계적으로 다시 점검할 기회가 생겼습니다. 이 포스트는 그 점검 과정에서 정리한 컨테이너 구성, 데이터 흐름, 그리고 주요 설계 결정을 공유합니다.

---

## 왜 Spark 컨테이너 구성을 점검하게 되었나요?

배포 후 `birdybuddy-data-pipeline` 컨테이너가 재시작을 반복하는 문제가 발생했습니다.
로그를 확인하던 중 `Master must either be yarn or start with spark, k8s, or local` 오류가 발견되었고,
이를 계기로 Spark 관련 컨테이너들의 역할과 구성을 전반적으로 점검하게 되었습니다.

> 이 오류는 Spark Session을 생성할 때 Master URL이 올바르게 설정되지 않았을 경우 발생합니다. 예를 들어 환경 변수가 비어 있거나, `spark://spark-master:7077` 대신 빈 문자열이 전달되는 상황이 이에 해당합니다.

점검 과정에서 다음 사항들이 확인되었습니다:

1. **Spark job 컨테이너가 역할에 맞게 분리되지 않았습니다**
`cctv-ingest`와 `data-pipeline` 두 컨테이너가 스트리밍과 배치를 모두 담당하고 있어, 역할 경계가 불명확하고 장애 격리가 어려웠습니다.

2. **레이더 데이터 파이프라인이 정의되지 않았습니다**
CCTV 파이프라인은 구현되어 있었으나, 레이더 데이터의 실시간 변환과 HDFS 적재를 담당하는 컨테이너가 없었습니다.

3. **단기 집계(1분 주기)를 어느 컨테이너에서 처리할지 결정이 필요했습니다.**


## Kappa 아키텍처

Lambda 아키텍처는 배치 레이어와 스트리밍 레이어를 이중으로 운영합니다.
이 프로젝트는 외형상 배치/스트리밍이 분리된 것처럼 보이지만, 실질적으로는 **Kappa 아키텍처**에 해당합니다.

| 컨테이너 | 방식 | 설명 |
|---|---|---|
| `spark-stream-cctv` | Structured Streaming | Kafka(`bird.detection`)를 consume하여 PostgreSQL에 탐지 결과 저장 |
| `spark-radar-stream` | Structured Streaming | 레이더 원시 좌표를 Kafka에서 consume하여 변환 후 `radar.transformed` 토픽으로 재발행 |
| `spark-radar-archiver` | Triggered Batch | 레이더 데이터를 Kafka에서 읽어 HDFS(`/data/radar`)에 적재 |
| `spark-batch` | Scheduled Batch | HDFS에 쌓인 레이더 데이터를 읽어 히트맵·시계열 통계를 PostgreSQL에 집계 |

중요한 건 **모든 원시 데이터가 Kafka를 통해 한 번만 수집**된다는 점입니다.
`spark-batch`가 배치처럼 동작하더라도, 처리 대상 데이터는 스트리밍(`spark-radar-archiver`)으로 HDFS에 쌓입니다.
별도의 배치 수집 레이어 없이 **단일 수집 파이프라인(Kafka)** 으로 통일된 구조가 Kappa 아키텍처입니다.

### **Lambda vs Kappa**

**Lambda 아키텍처**는 배치 레이어(Batch Layer)와 스피드 레이어(Speed Layer)를 각각 따로 구현하여 동일한 데이터를 두 번 처리합니다. 운영 복잡도가 높지만 배치와 스트리밍 각각의 장점을 살릴 수 있습니다.

**Kappa 아키텍처**는 스트리밍 레이어 하나만 두고, 재처리가 필요할 때는 스트림을 다시 재생(replay)하는 방식으로 시스템을 단순화합니다. 이 프로젝트처럼 한정된 자원 안에서 운영 복잡도를 낮춰야 할 때 적합한 선택입니다.


## 각 컨테이너는 어떤 역할을 담당하나요?

모든 Spark 관련 컨테이너는 **EC2 #2(데이터 처리 서버)** 에서 실행됩니다.

### 연산 인프라: Spark 클러스터

| 컨테이너 | 역할 |
|---|---|
| `spark-master` | 작업 스케줄링. Spark job으로부터 작업을 받아 Worker에 분배 |
| `spark-worker` | 실제 데이터 연산 수행 (Executor). 3GB 메모리 할당, 1개 운영 |

`spark-master`와 `spark-worker`는 **연산 인프라**입니다. 이 둘만으로는 아무 일도 하지 않습니다.
Spark job 컨테이너가 `spark://spark-master:7077`로 작업을 제출해야 비로소 동작합니다.


### 작업을 지시하는 Spark job 컨테이너

| 컨테이너 | 유형 | 역할 |
|---|---|---|
| `spark-stream-cctv` | Structured Streaming | CCTV 탐지 결과 수신·저장 (Kafka → PostgreSQL) |
| `spark-radar-stream` | Structured Streaming | 레이더 좌표 변환 및 재발행 (Kafka → Kafka) |
| `spark-radar-archiver` | Triggered Batch | 레이더 데이터 HDFS 적재 (Kafka → HDFS) |
| `spark-batch` | Scheduled Batch | 장기 통계 집계 (HDFS → PostgreSQL) |

각 컨테이너는 담당하는 데이터 흐름과 실행 방식이 명확히 구분됩니다.
스트리밍 job(`spark-stream-cctv`, `spark-radar-stream`)은 상시 실행되고,
배치 job(`spark-radar-archiver`, `spark-batch`)은 스케줄 또는 트리거에 따라 실행됩니다.


## 데이터의 흐름

### CCTV 실시간 파이프라인

```
Mock CCTV ──▶ MediaMTX (RTSP → HLS) ──▶ AI Worker (YOLO 탐지)
                                               └──▶ Kafka (bird.detection)
                                                          ├──▶ spark-stream-cctv
                                                          │          └──▶ PostgreSQL
                                                          │               (cctv_frame_ingest, cctv_detection)
                                                          └──▶ Backend SSE ──▶ 프론트엔드
```

`spark-stream-cctv`는 상시 실행되며 Kafka 메시지가 들어올 때마다 처리합니다.
`foreachBatch` 콜백 안에서 Spark DataFrame을 PostgreSQL에 upsert하는 방식으로, 스트리밍 수신과 저장을 하나의 흐름으로 처리합니다.

### 레이더 실시간 파이프라인

```
Mock Radar ──▶ Kafka ──▶ spark-radar-stream (좌표 변환)
                               └──▶ Kafka (radar.transformed)
                                          └──▶ Backend SSE ──▶ 프론트엔드
```

레이더 엣지에서 들어온 원시 좌표를 `spark-radar-stream`이 실시간으로 변환하여 새로운 토픽(`radar.transformed`)으로 재발행합니다.
Backend는 이 토픽을 구독하여 SSE로 프론트엔드에 즉시 전달합니다.

### 레이더 배치 파이프라인

```
Mock Radar ──▶ Kafka ──▶ spark-radar-archiver ──▶ HDFS (/data/radar)
                                                          └──▶ spark-batch
                                                                    └──▶ PostgreSQL
                                                                         (long_term_radar_heatmap,
                                                                          line_chart_year/month/day/hour)
```

`spark-radar-archiver`가 Kafka의 레이더 데이터를 HDFS에 적재하면,
`spark-batch`가 이를 읽어 히트맵과 시계열 통계를 집계합니다.

| 작업 | 주기 | 출력 테이블 |
|---|---|---|
| 히트맵 집계 | 매일 02:00 | `long_term_radar_heatmap` |
| 시계열 통계 | 매일 02:00 | `line_chart_year/month/day/hour` |
| 카메라 각도 분석 | 매일 02:00 | `angle_insight` |
| 단기 CCTV 집계 | 1분 | `cctv_short_agg` |


## 어떤 설계 결정을 내렸나요?

### 1. Spark job을 역할별로 독립 컨테이너로 분리합니다

초기에는 `cctv-ingest`와 `data-pipeline` 두 컨테이너가 스트리밍·배치를 모두 담당했습니다.
역할이 혼재되다 보니 한 job의 장애가 다른 job에 영향을 미칠 수 있었고, 배포 단위도 불명확했습니다.

**결정: 역할에 따라 4개 컨테이너로 분리합니다**

- 장애 격리: 레이더 archiver가 실패해도 CCTV 스트리밍은 영향을 받지 않습니다.
- 배포 독립성: job별로 이미지를 독립적으로 빌드하고 배포할 수 있습니다.
- 책임 명확화: 컨테이너 이름만 보고 어떤 데이터를 어떻게 처리하는지 파악할 수 있습니다.

### 2. spark-worker는 1개로 운영합니다

EC2 #2에서 kafka, hadoop(namenode+datanode), spark-master/worker, ai(YOLO), mock-cctv, mock-radar, 그리고 4개의 Spark job 컨테이너가 함께 실행됩니다.
워커를 늘리면 메모리 부족(OOM) 위험이 있으므로 현재는 3GB 할당 워커 1개로 운영하고, 실제 부하를 확인하며 판단합니다.

> 단일 워커 환경에서는 Spark의 분산 연산 이점이 제한적입니다. 그러나 이 프로젝트의 목표는 "운영 가능한 시스템을 먼저 구축하고, 이후 필요에 따라 스케일 아웃"하는 것이므로 현 단계에서는 안정성을 우선시합니다.

### 3. 단기 집계는 spark-batch에서 통합 처리합니다

단기 집계를 `spark-stream-cctv`의 `foreachBatch` 안에서 처리할지, `spark-batch` 스케줄로 처리할지 검토했습니다.

`foreachBatch` 안에서 처리하면 스트리밍 흐름과 자연스럽게 연결되는 것처럼 보이지만,
어느 쪽에서 처리하든 **PostgreSQL 읽기/쓰기 IO는 동일하게 발생**합니다.

**결정: `spark-batch` 스케줄로 처리합니다**

- 작업 성격이 "주기적으로 집계 테이블 덮어쓰기"로 배치에 해당합니다.
- 모든 집계 스케줄을 `spark-batch` 한 곳에서 관리하면 운영이 단순해집니다.
- `spark-stream-cctv`는 수신/저장에만 집중하고 집계는 분리하여 관심사를 분리할 수 있습니다.
