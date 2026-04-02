---
title: "[허수아비] CI/CD 배포 트러블슈팅 모음"
date: 2026-03-20 09:00:00 +0900
categories: [Project, 허수아비]
tags: [Troubleshooting, CI/CD, GitLab, Docker, nginx, PostgreSQL, MinIO, Spark, EC2]
toc: true
comments: true
description: "GitLab CI 파이프라인 구성부터 nginx 설정 오류, 환경변수 불일치, Spark Master URL까지 — 배포 과정에서 마주친 실전 트러블슈팅 기록입니다."
---

배포 파이프라인을 처음 구성하면서 크고 작은 트러블이 연속으로 터졌습니다. 오류 메시지만 보고 바로 고치기보다, 왜 그 오류가 나는지를 먼저 짚고 선택지를 비교한 뒤 해결하는 방식으로 접근했습니다. 그 과정을 항목별로 정리했습니다.

---

## deploy 잡이 build 잡을 찾지 못해 파이프라인이 실패했다

### 증상

dev 브랜치에 머지 후 파이프라인 실행 시 아래 오류가 발생했습니다.

```
'deploy-frontend' job needs 'build-frontend' job,
but 'build-frontend' does not exist in the pipeline.
```

### 왜 이런 일이 생겼나

`build-*` 잡은 `rules: changes:` 조건으로 해당 컴포넌트에 변경이 있을 때만 실행되도록 설계되어 있었습니다. 반면 `deploy-*` 잡은 `if: branch == dev/main` 조건만 있어서, 파일 변경 여부와 관계없이 항상 실행을 시도했습니다.

변경이 없는 컴포넌트의 `build-*` 잡은 파이프라인에 아예 존재하지 않기 때문에, `needs:`로 그 잡을 참조하는 `deploy-*`가 실패하는 구조였습니다.

### 어떤 선택지를 고려했나

두 가지 방향을 검토했습니다.

- **`optional: true` 추가:** build 잡이 없어도 deploy 잡이 실패하지 않도록 의존성을 느슨하게 만드는 방법. 단, build가 실제로 실패한 경우에도 deploy가 실행될 수 있다는 위험이 있습니다.
- **`changes:` 조건 추가:** build 잡과 동일한 파일 변경 시에만 deploy 잡도 실행되도록 맞추는 방법. 아예 파이프라인에 올라오지 않으니 `needs:` 참조 문제 자체가 사라집니다.

두 방법을 함께 적용했습니다. `optional: true`는 예외 상황에 대한 안전망이고, `changes:` 조건은 애초에 잡이 불필요하게 실행되는 것을 막아줍니다.

### 해결

```yaml
deploy-frontend:
  needs:
    - job: build-frontend
      optional: true
  rules:
    - if: '$CI_COMMIT_BRANCH == "dev" || $CI_COMMIT_BRANCH == "main"'
      changes:
        - frontend/**/*
        - .gitlab-ci.yml
```

---

## nginx가 `server` 블록을 최상위에서 거부했다

### 증상

`birdybuddy-frontend` 컨테이너가 재시작을 반복하며 아래 로그를 출력했습니다.

```
2026/03/20 07:28:18 [emerg] 1#1: "server" directive is not allowed here
in /etc/nginx/nginx.conf:1
nginx: [emerg] "server" directive is not allowed here in /etc/nginx/nginx.conf:1
```

### 왜 이런 일이 생겼나

nginx 공식 이미지의 설정 구조는 `http {}` 블록 안에 `server {}` 블록이 위치해야 합니다. 작성한 `nginx.conf`는 `server {}`를 최상위에 바로 선언한 상태였기 때문에, nginx가 컨텍스트 오류로 시작을 거부했습니다.

### 해결

`nginx.conf`에 `events {}`와 `http {}` 블록을 추가하고, `server {}` 블록을 그 안으로 이동했습니다.

```nginx
events {}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    server {
        listen 80;
        ...
    }

    server {
        listen 443 ssl;
        ...
    }
}
```

---

## nginx.conf 마운트 경로가 파일이 아닌 디렉토리로 생성되어 있었다

### 증상

`deploy-frontend` CI 잡 실행 중 아래 오류가 발생했습니다.

```
Error response from daemon: failed to create task for container:
failed to create shim task: OCI runtime create failed: runc create failed:
unable to start container process: error during container init:
error mounting "/home/ubuntu/birdybuddy/infra/ec2-app/nginx/nginx.conf"
to rootfs at "/etc/nginx/nginx.conf":
mount src=..., flags=MS_BIND|MS_REC: not a directory:
Are you trying to mount a directory onto a file (or vice-versa)?
```

### 왜 이런 일이 생겼나

EC2에 `nginx/nginx.conf` 파일이 존재하지 않는 상태에서 `docker compose up`을 실행하면, Docker가 마운트 대상 경로를 **파일이 아닌 디렉토리**로 자동 생성합니다. 이후 파일로 마운트를 시도할 때 타입 불일치로 실패하는 구조입니다.

### 어떤 선택지를 고려했나

- **EC2에서 수동으로 디렉토리를 제거하고 재실행:** 즉시 해결되지만, 다음 배포에서도 같은 상황이 반복될 수 있습니다.
- **CI에서 `docker compose up` 전에 파일을 먼저 전송:** 파일이 미리 존재하면 Docker가 디렉토리를 만들 이유가 없습니다. 재현 가능한 구조로 해결할 수 있습니다.

CI 파이프라인 자체를 고치는 두 번째 방법을 선택했습니다. 수동 조치는 임시방편이고, 배포 순서를 올바르게 정의하는 것이 근본 해결이라고 판단했습니다.

### 해결

CI 파이프라인에서 `docker compose up` 전에 `scp`로 `nginx.conf`를 EC2에 먼저 전송하도록 수정했습니다.

```yaml
script:
  - ssh $EC2_USER@$EC2_APP_HOST "mkdir -p $DEPLOY_DIR/infra/ec2-app/nginx"
  - scp infra/ec2-app/nginx/nginx.conf $EC2_USER@$EC2_APP_HOST:$DEPLOY_DIR/infra/ec2-app/nginx/nginx.conf
  - ssh $EC2_USER@$EC2_APP_HOST "docker compose up -d --no-deps frontend"
```

이미 디렉토리로 생성되어 있는 경우, EC2에서 수동으로 제거 후 파이프라인을 재실행합니다.

```bash
rm -rf ~/birdybuddy/infra/ec2-app/nginx
```

---

## scp로 nginx.conf를 전송하려는데 Permission denied가 났다

### 증상

```
scp: dest open "birdybuddy/infra/ec2-app/nginx/nginx.conf/nginx.conf": Permission denied
scp: failed to upload file infra/ec2-app/nginx/nginx.conf
to ~/birdybuddy/infra/ec2-app/nginx/nginx.conf
```

### 왜 이런 일이 생겼나

이전 배포 실패로 EC2에 `nginx/nginx.conf`가 **디렉토리**로 남아있었습니다. `scp`가 그 안에 `nginx.conf`라는 이름의 파일을 새로 만들려 했지만, 해당 경로에 쓰기 권한이 없어 실패했습니다. 앞선 항목과 연결된 문제로, 디렉토리를 제거하지 않은 채 scp를 재시도해서 발생한 상황이었습니다.

### 해결

EC2에서 잘못 생성된 디렉토리를 제거하고 CI를 재실행했습니다.

```bash
rm -rf ~/birdybuddy/infra/ec2-app/nginx
```

---

## 백엔드가 DB에 접속하지 못하고 인증 실패를 반복했다

### 증상

`birdybuddy-backend` 컨테이너가 재시작을 반복하며 아래 로그를 출력했습니다.

```
Caused by: org.postgresql.util.PSQLException:
FATAL: password authentication failed for user "admin"
```

### 왜 이런 일이 생겼나

GitLab CI 변수 `ENV_BACKEND`에 설정된 `POSTGRES_PASSWORD`가 PostgreSQL 컨테이너 초기화 시 사용된 비밀번호와 달랐습니다.

PostgreSQL은 **최초 초기화 시 비밀번호를 볼륨에 저장**합니다. 이후 환경변수를 바꿔도 기존 볼륨이 남아있으면 변경 내용이 반영되지 않습니다. 즉, `ENV_BACKEND`와 `ENV_EC2_APP`의 비밀번호가 맞지 않는 상태에서 컨테이너를 재시작해봤자 볼륨에 저장된 원래 비밀번호로 계속 인증이 시도됩니다.

### 어떤 선택지를 고려했나

- **비밀번호만 맞추고 컨테이너 재시작:** 볼륨이 남아있으면 변경이 반영되지 않으므로 효과가 없습니다.
- **볼륨을 삭제하고 재초기화:** 데이터가 날아가지만 개발 환경에서는 허용 가능하고, 비밀번호를 올바르게 맞춘 상태로 처음부터 초기화할 수 있습니다.

볼륨 삭제 후 재초기화 방법을 선택했습니다. 환경변수 불일치 + 기존 볼륨 잔존이라는 두 조건이 겹친 문제이므로, 두 조건을 동시에 해소해야 했습니다.

### 해결

`ENV_BACKEND`의 `POSTGRES_PASSWORD`를 `ENV_EC2_APP`의 값과 일치시킨 뒤, 기존 볼륨을 삭제하고 재시작했습니다.

```bash
cd ~/birdybuddy/infra/ec2-app
docker compose down -v   # 볼륨까지 삭제 (데이터 초기화 주의)
docker compose up -d
```

---

## AI 컨테이너가 MinIO 호스트명을 해석하지 못했다

### 증상

```
urllib3.exceptions.NameResolutionError:
HTTPConnection(host='minio', port=9000): Failed to resolve 'minio'
([Errno -3] Temporary failure in name resolution)
```

### 왜 이런 일이 생겼나

`ENV_AI`에 `MINIO_ENDPOINT=http://minio:9000`으로 설정되어 있었습니다. `minio`는 EC2 #2의 Docker 내부 호스트명입니다. EC2 #1에서 동작하는 AI 컨테이너는 다른 호스트의 Docker 네트워크를 알 수 없으므로, 이 이름을 해석하지 못합니다.

단일 EC2 환경이었다면 docker network를 통해 접근할 수 있었겠지만, 멀티 EC2 구성에서는 내부 호스트명이 아닌 외부 주소로 통신해야 합니다.

### 해결

`ENV_AI`에서 EC2 #2의 외부 주소로 변경했습니다.

```
MINIO_ENDPOINT=http://j14A206A.p.ssafy.io:9000
```

---

## MinIO Access Key가 맞지 않아 업로드가 실패했다

### 증상

```
[ERROR] MinIO 업로드 실패: S3 operation failed;
code: InvalidAccessKeyId,
message: The Access Key Id you provided does not exist in our records.
```

### 왜 이런 일이 생겼나

`ENV_AI`의 `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`가 MinIO 컨테이너에 설정된 `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`와 달랐습니다.

MinIO에서 `MINIO_ROOT_USER`가 Access Key, `MINIO_ROOT_PASSWORD`가 Secret Key에 해당합니다. 환경변수 이름이 달라 헷갈리기 쉬운 부분인데, 각 서비스의 `.env` 파일이 독립적으로 관리되다 보니 한쪽만 수정된 채로 배포된 상황이었습니다.

### 해결

`ENV_AI`의 값을 `ENV_EC2_APP`의 MinIO 설정과 일치시켰습니다.

```
MINIO_ACCESS_KEY={MINIO_ROOT_USER 값}
MINIO_SECRET_KEY={MINIO_ROOT_PASSWORD 값}
```

---

## Spark Master URL 형식이 잘못되어 있었다

### 증상

`birdybuddy-data-pipeline` 컨테이너가 재시작을 반복하며 아래 로그를 출력했습니다.

```
Exception in thread "main" org.apache.spark.SparkException:
Master must either be yarn or start with spark, k8s, or local
```

### 왜 이런 일이 생겼나

`ENV_DATA_PIPELINE`의 `SPARK_MASTER` 값이 Spark가 인식하지 못하는 형식으로 설정되어 있었습니다. Spark가 허용하는 Master URL 형식은 다음과 같습니다.

- `spark://host:port` — Standalone 클러스터
- `local[*]` — 로컬 실행
- `yarn` — YARN 클러스터
- `k8s://...` — Kubernetes

오류 메시지 자체가 허용 형식을 명확히 알려주고 있었고, 이 프로젝트는 Spark Standalone 구성이므로 `spark://` 형식을 사용해야 했습니다.

### 해결

`ENV_DATA_PIPELINE`에서 올바른 형식으로 수정했습니다.

```
SPARK_MASTER=spark://spark-master:7077
```
