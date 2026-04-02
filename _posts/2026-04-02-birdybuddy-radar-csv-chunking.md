---
title: "[허수아비] mock-radar CSV 청킹으로 메모리 98% 절감"
date: 2026-04-02 09:00:00 +0900
categories: [Project, 허수아비]
tags: [Troubleshooting, Python, Pandas, Docker, Memory, Kafka, CSV, EC2]
toc: true
comments: true
description: "EC2 메모리 고갈의 원인이었던 mock-radar 컨테이너를 CSV 청킹 방식으로 전환해 메모리 사용량을 3.93GiB에서 72MiB로 줄인 트러블슈팅 기록입니다."
---

프론트엔드 페이지 렌더링이 갑자기 느려졌습니다. EC2를 확인해보니 메모리가 거의 꽉 차 있었고, 범인은 예상치 못한 곳에 있었습니다. 레이더 데이터를 Kafka로 흘려주는 mock 서비스 `birdybuddy-mock-radar`가 혼자 3.93GiB를 점유하고 있었습니다. `mock_radar.py`의 CSV 읽기 방식을 청킹 구조로 전환해 해결했습니다.

---

## [문제] EC2 메모리가 꽉 찼다

프론트엔드 페이지 렌더링이 느려 EC2 #1 서버 상태를 확인한 결과, 전체 메모리(15.6GiB)가 거의 소진된 상태였습니다.

```
$ free -h
               total        used        free      shared  buff/cache   available
Mem:            15Gi        15Gi       212Mi        25Mi       712Mi       548Mi
```

`docker stats`로 컨테이너별 메모리 사용량을 확인했습니다.

```
birdybuddy-mock-radar             3.932GiB / 15.62GiB   25.18%   ← 주범
birdybuddy-spark-worker           2.467GiB / 3GiB       82.23%
birdybuddy-kafka                  1.448GiB / 2GiB       72.39%
birdybuddy-datanode               1.381GiB / 15.62GiB    8.85%
birdybuddy-namenode               1.233GiB / 15.62GiB    7.90%
birdybuddy-spark-stream           871.6MiB / 15.62GiB    5.45%
birdybuddy-spark-radar-stream     831.5MiB / 15.62GiB    5.20%
birdybuddy-spark-radar-archiver   743.2MiB / 15.62GiB    4.65%
...
```

mock 서비스임에도 불구하고 `birdybuddy-mock-radar`가 **3.93GiB**를 점유하고 있었으며, 메모리 limit도 설정되어 있지 않았습니다.

`docker logs`로 컨테이너 상태를 확인했습니다.

```
2026-04-02 10:42:54,520 [INFO] 진행: 6,630,000 / 8,213,608  (25.9 msg/s)
```

총 8,213,608행 CSV를 1배속(1.0x)으로 순회 중이었으며, 약 80% 진행 상태였습니다.
남은 행(약 1.58M행) 기준으로 완료까지 약 17시간 소요 예상 → 그때까지 4GB 점유 지속.


## [원인] mock-radar가 4GB를 잡아먹고 있었던 이유

### CSV 8백만 행을 한 번에 통째로 올려놓고 있었다

`mock_radar.py`의 `load_csv()` 함수:

```python
def load_csv(csv_path):
    usecols = list(COLUMN_RENAME.keys())
    df = pd.read_csv(csv_path, usecols=usecols, dtype="float64")  # ← 8.2M행 전체 로드
    df.rename(columns=COLUMN_RENAME, inplace=True)

    # 정수 필드 변환
    for col in int_cols:
        df[col] = df[col].astype(int)

    # absolute_sec 계산 후 정렬
    df["absolute_sec"] = (df["day"] - base_day) * 86400 + df["corrected_sec"]
    df.sort_values("absolute_sec", inplace=True)   # ← 정렬 중 내부 복사본 생성
    df.reset_index(drop=True, inplace=True)        # ← 또 복사

    return df  # 이후 run()에서 df.iterrows()로 순회하는 동안 계속 메모리 점유
```

메모리 점유 계산:
- raw 데이터: 8,213,608행 × 20컬럼 × 8bytes(float64) ≈ **1.3GB**
- `sort_values()` 내부 복사: ≈ **+1.3GB**
- pandas 인덱스, 오버헤드 등: ≈ **+수백MB**
- **합계 ~4GB**, 전체 순회가 끝날 때까지 메모리에 상주

### 메모리 상한도 걸려 있지 않았다

`docker-compose.yml`의 `mock-radar` 서비스에 `deploy.resources.limits.memory`가 없어 호스트 전체 메모리를 무제한으로 사용 가능한 상태였습니다.


## [해결] 조금씩 나눠 읽도록 하자

### CSV 청킹(chunked reading)으로 전환

`load_csv()`를 제거하고, `pd.read_csv(..., chunksize=50_000)`으로 5만 행씩만 메모리에 올려 처리하는 방식으로 변경했습니다.
CSV가 `absolute_sec` 기준 시간순 정렬되어 있다는 전제 하에 `sort_values()`도 제거했습니다.

핵심 변경 내용:

```python
CHUNK_SIZE = 50_000

def _read_first_row(csv_path: str) -> tuple[float, int]:
    """base_original(첫 행의 absolute_sec) 계산을 위해 첫 행만 읽음."""
    first = pd.read_csv(
        csv_path,
        nrows=1,
        usecols=list(COLUMN_RENAME.keys()),  # 필요한 컬럼만 선택 (문자열 컬럼 제외)
        dtype="float64",
    )
    first.rename(columns=COLUMN_RENAME, inplace=True)
    base_day = int(first.iloc[0]["day"])
    absolute_sec = float(first.iloc[0]["corrected_sec"])  # base_day 기준이므로 day 차이 = 0
    return absolute_sec, base_day


def _preprocess_chunk(chunk: pd.DataFrame, base_day: int) -> pd.DataFrame:
    """청크 단위 전처리: 컬럼 rename, 타입 변환, absolute_sec 계산."""
    chunk = chunk[[c for c in COLUMN_RENAME.keys() if c in chunk.columns]].copy()
    chunk.rename(columns=COLUMN_RENAME, inplace=True)
    for col in int_cols:
        chunk[col] = chunk[col].astype(int)
    chunk["absolute_sec"] = (chunk["day"] - base_day) * 86400 + chunk["corrected_sec"]
    return chunk


def run(csv_path, bootstrap, topic, sensor_id, speed):
    base_original, base_day = _read_first_row(csv_path)
    producer = build_producer(bootstrap)

    reader = pd.read_csv(
        csv_path,
        usecols=list(COLUMN_RENAME.keys()),
        dtype="float64",
        chunksize=CHUNK_SIZE,   # ← 5만 행씩만 메모리에 올림
    )
    for chunk in reader:
        chunk = _preprocess_chunk(chunk, base_day)
        for _, row in chunk.iterrows():
            # 타이밍 재현 + Kafka 발행 (기존과 동일)
            ...
```

### `usecols`를 빠뜨렸더니 문자열 컬럼에서 ValueError가 터졌다

청킹 수정 후 첫 배포 시 컨테이너가 재시작을 반복하는 증상이 발생했습니다.

```
ValueError: could not convert string to float: '2021-10-08-09-57-07tracks.txt'
```

**원인:** `_read_first_row`에서 `usecols`를 지정하지 않아, CSV에 존재하는 파일명 형태의 문자열 컬럼(`2021-10-08-09-57-07tracks.txt`)까지 읽으려다 `dtype="float64"` 변환에서 실패했습니다.

**수정:**
```python
# 수정 전
first = pd.read_csv(csv_path, nrows=1, dtype="float64")

# 수정 후
first = pd.read_csv(csv_path, nrows=1, usecols=list(COLUMN_RENAME.keys()), dtype="float64")
```

---

## [결과] 메모리 사용량이 98% 줄었다

수정 후 `docker stats`:

```
birdybuddy-spark-worker           2.475GiB / 3GiB       82.50%
birdybuddy-datanode               1.658GiB / 15.62GiB   10.62%
birdybuddy-kafka                  1.485GiB / 2GiB       74.23%
birdybuddy-namenode               1.234GiB / 15.62GiB    7.90%
...
birdybuddy-mock-radar              72.18MiB / 15.62GiB    0.45%   ← 해결
```

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| mock-radar 메모리 | 3.93 GiB | **72 MiB** |
| 전체 메모리 사용 | ~15 GiB (100%) | ~12 GiB (~77%) |
| 메모리 감소량 | — | **약 3.86 GiB (98% 감소)** |

정상 동작 로그:
```
2026-04-02 11:35:09,442 [INFO] CSV 스트리밍 모드 시작 (chunk=50,000): /data/radar.csv
2026-04-02 11:35:09,499 [INFO] 발행 시작 — topic=radar.events, speed=1.0x
2026-04-02 11:43:00,115 [INFO] 진행: 10,000 건 발행  (21.2 msg/s)
2026-04-02 11:53:30,404 [INFO] 진행: 20,000 건 발행  (18.2 msg/s)
```

