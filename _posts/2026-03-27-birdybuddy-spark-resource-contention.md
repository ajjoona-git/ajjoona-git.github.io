---
title: "[허수아비] Spark 자원 분배로 인한 메모리 부족 문제 해결"
date: 2026-03-27 12:00:00 +0900
categories: [Project, 허수아비]
tags: [Troubleshooting, Docker, DataPipeline, Kafka, Memory, Infra, EC2, Spark]
toc: true
comments: true
description: "spark-radar-stream이 리소스를 할당받지 못해 15초 간격으로 경고를 반복하는 문제가 발생했습니다. 코어 독식과 메모리 고갈 두 원인을 분석하고, spark.cores.max 설정과 잡별 메모리 할당으로 4개 Spark job이 워커 3GB 내에서 공존하도록 해결한 과정을 정리합니다."
---

4개의 Spark job이 워커 1개에서 동시에 실행되는 환경에서, 자원 설정 없이 배포하면 잡 하나가 모든 코어와 메모리를 독점합니다. 이 포스트는 `spark-radar-stream`이 리소스를 할당받지 못해 경고를 반복하는 문제의 원인을 단계적으로 추적하고 해결한 과정을 정리합니다.

---

## spark-radar-stream 재시도 반복

`spark-radar-stream` 로그에서 아래 경고가 15초 간격으로 무한 반복되었습니다:

```
WARN TaskSchedulerImpl: Initial job has not accepted any resources;
check your cluster UI to ensure that workers are registered and have sufficient resources
```

`radar.transformed` 토픽에 메시지가 발행되지 않아, 레이더 실시간 파이프라인 전체가 멈춘 상태였습니다.


## 1. 코어 독점 문제

### cctv-ingest가 코어 4개 전부를 점유하고 있었다

Spark Standalone 클러스터에서 먼저 제출된 잡이 워커의 모든 코어를 독점하고 있었습니다.

```
# Spark Master API 확인 결과
birdybuddy-cctv-ingest    | cores: 4   ← 전부 독점
RadarCoordinateTransformer | cores: 0   ← 대기
RadarHDFSArchiver          | cores: 0   ← 대기
```

### spark.cores.max가 없을 때 벌어지는 일

`spark.cores.max` 설정이 없으면 잡 하나가 워커의 모든 코어를 가져갑니다.

> Spark Standalone 클러스터는 기본적으로 **Greedy Allocation** 방식으로 동작합니다. 먼저 제출된 잡이 가용한 코어를 최대한 차지하고, 이후 제출된 잡은 남은 자원만 사용할 수 있습니다. 여러 잡이 공존하는 환경에서는 반드시 `spark.cores.max`로 잡당 코어 수를 제한해야 합니다.

### 잡당 코어 상한 설정

`data-pipeline/.env`에 코어 제한을 추가했습니다:

```
SPARK_MAX_CORES=1
```

`data-pipeline/common/config/spark.py`:

```python
MAX_CORES: str = os.getenv("SPARK_MAX_CORES", "1")
```

`data-pipeline/common/spark_session.py`:

```python
.config("spark.cores.max", spark_config.MAX_CORES)
.config("spark.executor.cores", spark_config.MAX_CORES)
```


## 2. 메모리 부족 문제

### 메모리도 꽉 찼습니다

코어 제한 적용 후에도 동일한 경고가 지속되었습니다.

```
# Spark Worker 메모리 확인
워커 총 메모리: 2048 MB
워커 사용 메모리: 2048 MB  ← 꽉 참
```

### SPARK_EXECUTOR_MEMORY=2g 기본값

`SPARK_EXECUTOR_MEMORY=2g` 기본값으로 인해 executor 하나가 워커 메모리 2GB 전체를 점유했습니다.
나머지 잡들은 코어가 남아있어도 메모리 부족으로 실행이 불가능했습니다.

> `SPARK_WORKER_MEMORY`는 워커가 제공할 수 있는 **총 가용 메모리**이고, `SPARK_EXECUTOR_MEMORY`는 잡 하나의 executor가 요청하는 **메모리 양**입니다. 가용 메모리보다 executor 메모리 합계가 크면 잡이 대기 상태에 빠집니다.

### 워커 메모리 확장과 잡별 분배

**1. Spark Worker 가용 메모리 명시** (`infra/ec2-data/docker-compose.yml`):

```yaml
spark-worker:
  environment:
    - SPARK_WORKER_MEMORY=3g
  deploy:
    resources:
      limits:
        memory: 3G
```

**2. 잡별 메모리 개별 설정** (`infra/ec2-data/docker-compose.yml`):

| 잡 | Driver | Executor | 비고 |
|---|---|---|---|
| spark-batch | 1g | 1g | 배치 집계 잡 |
| spark-stream-cctv | 512m | 512m | CCTV 인제스트 |
| spark-radar-archiver | 512m | 512m | 레이더 HDFS 아카이빙 |
| spark-radar-stream | 1g | 1g | 레이더 좌표 변환 |
| **합계** | | **3g** | 워커 3g 이내 |

각 서비스에 `environment` 블록으로 개별 적용했습니다:

```yaml
spark-stream-cctv:
  environment:
    - SPARK_DRIVER_MEMORY=512m
    - SPARK_EXECUTOR_MEMORY=512m
```

**3. `.env` 기본값 조정**:

```
SPARK_DRIVER_MEMORY=512m
SPARK_EXECUTOR_MEMORY=512m
```


## 검증

아래 명령어로 자원 할당 상태와 토픽 메시지 수신을 확인했습니다.

```bash
# 잡별 코어 할당 확인
curl -s http://localhost:8080/json/ | python3 -c "
import json,sys
d=json.load(sys.stdin)
for a in d.get('activeapps',[]): print(a['name'], '| cores:', a['cores'])
"

# 워커 메모리 사용량 확인
curl -s http://localhost:8080/json/ | python3 -c "
import json,sys
d=json.load(sys.stdin)
for w in d.get('workers',[]): print(w['host'], '| memory:', w['memory'], 'MB | used:', w['memoryused'], 'MB')
"

# 잡별 executor 메모리 할당량 확인
# memoryperexecutor가 2048이면 컨테이너 미재시작, 512/1024면 새 설정 적용됨
curl -s http://localhost:8080/json/ | python3 -c "
import json, sys
d = json.load(sys.stdin)
total = 0
for a in d.get('activeapps', []):
    mem = a['memoryperexecutor']
    cores = a['cores']
    total += mem
    print(f\"{a['name']:<35} | memory: {mem} MB | cores: {cores}\")
print(f\"{'TOTAL':<35} | memory: {total} MB\")
"

# radar.transformed 토픽 메시지 수신 확인
docker exec birdybuddy-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic radar.transformed \
  --max-messages 3 \
  --timeout-ms 10000
```

정상 시 모든 잡이 `cores: 1` 이상으로 표시되고, `radar.transformed` 토픽에 메시지가 수신됩니다.
