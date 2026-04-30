---
title: "[둥지] 프론트엔드 Nginx 구조와 Prod 배포 전략"
date: 2026-04-24 10:00:00 +0900
categories: [Project, 둥지]
tags: [Nginx, Docker, DockerHub, GitHubActions, SSM, CD, DevOps, Frontend, Infra]
toc: true
comments: true
description: "React SPA를 서빙하는 Nginx 설정 파일을 환경별로 어떻게 나눴는지, 그리고 SSM 전용 Prod 서버에서 rsync 대신 Dockerfile 이미지 빌드를 선택한 이유를 정리합니다."
---

둥지 프론트엔드 배포를 설계하면서 두 가지 문제를 먼저 해결해야 했습니다. 하나는 **Nginx 설정 파일을 환경별로 어떻게 나눌 것인가**, 다른 하나는 **SSH 키가 없는 Prod 서버에 어떻게 배포할 것인가**입니다.

---

## 1. Nginx 파일을 왜 세 개로 나눴나

처음에는 `nginx.conf` 하나로 모든 환경을 커버하려 했습니다. 그런데 환경마다 필요한 기능이 달랐습니다.

- **로컬**: AWS VPC 내부의 RDS/ElastiCache에 직접 접속하려면 TCP 터널(`stream {}` 블록)이 필요합니다. 이 블록은 Nginx 메인 설정(`nginx.conf`)을 교체해야만 추가할 수 있고, Dev/Prod 서버에서는 전혀 필요 없습니다.
- **Dev/Prod**: Let's Encrypt 인증서를 마운트해 HTTPS를 처리해야 합니다. 인증서 경로만 다를 뿐 설정 내용은 동일합니다.

하나의 파일에 `if` 분기나 환경 변수를 넣어 처리하는 방법도 있었지만, Nginx는 `if` 지시어 사용을 권장하지 않습니다. 대신 **파일 자체를 목적별로 분리**하고 compose 파일에서 어떤 파일을 마운트할지 결정하는 방식을 택했습니다.

| 파일 | 사용 환경 | 마운트 경로 | 역할 |
|------|-----------|------------|------|
| `nginx.conf` | 로컬 전용 | `/etc/nginx/conf.d/default.conf` | HTTP SPA 서빙 + API 프록시 |
| `nginx-main.conf` | 로컬 전용 | `/etc/nginx/nginx.conf` | 메인 설정 교체 — TCP 터널 (`stream {}`) 포함 |
| `nginx-ssl.conf` | Dev/Prod 공통 | `/etc/nginx/conf.d/default.conf` | HTTPS SPA 서빙 + API 프록시 |

### `nginx.conf` (로컬)

```nginx
server {
    listen 80;
    resolver 127.0.0.11 valid=10s ipv6=off;
    set $backend http://doongzi-api:8000;

    location /api/v1/ { proxy_pass $backend; }
    location / { try_files $uri $uri/ /index.html; }
    location ~* \.(js|css|png|jpg|gif|ico|woff2)$ { expires 1y; }
}
```

`proxy_pass`에 URL을 직접 적지 않고 `$backend` 변수를 거치는 이유가 있습니다. Nginx는 시작 시점에 `proxy_pass` 호스트명을 DNS로 즉시 해석합니다. `doongzi-api` 컨테이너가 아직 없으면 Nginx 자체가 크래시합니다. 변수에 담으면 실제 요청이 들어올 때 Docker 내부 DNS(`127.0.0.11`)로 lazy resolve하므로 컨테이너 기동 순서와 무관하게 안전합니다.

### `nginx-main.conf` (로컬)

- `http {}` 블록: `conf.d/*.conf` include → `nginx.conf` 포함
- `stream {}` 블록: Tailscale VPN 경유 AWS VPC 서비스 TCP 터널

| 로컬 포트 | 대상 |
|-----------|------|
| `6379` | ElastiCache Redis (dev 클러스터) |
| `5432` | RDS PostgreSQL (dev 인스턴스) |

`stream {}` 블록은 `/etc/nginx/nginx.conf`(메인 설정) 안에 있어야 합니다. `conf.d/`에 include되는 파일에는 추가할 수 없습니다. 그래서 메인 설정 파일 자체를 교체하는 방식을 사용했습니다.

### `nginx-ssl.conf` (Dev/Prod)

```nginx
server {
    listen 80;
    server_name _;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl;
    server_name _;
    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    resolver 127.0.0.11 valid=10s ipv6=off;
    set $backend http://doongzi-api:8000;

    location /api/v1/ { proxy_pass $backend; }
    location / { try_files $uri $uri/ /index.html; }
    location ~* \.(js|css|png|jpg|gif|ico|woff2)$ { expires 1y; }
}
```

`server_name`에 도메인을 하드코딩하지 않고 `_`(catch-all)을 사용한 이유가 있습니다. 도메인을 명시하면 Dev(`dev.doongzi.site`)와 Prod(`doongzi.site`) 각각 다른 파일이 필요해집니다. catch-all을 쓰면 **동일한 파일 하나로 두 환경에 배포**할 수 있습니다.

인증서 경로도 `/etc/nginx/certs/`로 고정해 두고, compose 파일에서 도메인별 실제 경로를 해당 경로에 마운트하는 방식을 택했습니다.

- Dev: `/etc/letsencrypt/live/dev.doongzi.site` → `/etc/nginx/certs`
- Prod: `/etc/letsencrypt/live/doongzi.site` → `/etc/nginx/certs`

---

## 2. Docker Compose 파일 구조

Nginx 파일 분리와 같은 맥락으로, compose 파일도 환경별로 나눴습니다.

| 파일 | 사용 환경 | 역할 |
|------|-----------|------|
| `docker-compose.yml` | 로컬 | 기본 설정 — 빌드 볼륨, nginx.conf, nginx-main.conf, 포트 80/5432/6379 |
| `docker-compose.dev.yml` | Dev EC2 | override — nginx-ssl.conf, 443 포트, 인증서/certbot 볼륨 추가 |
| `docker-compose.prod.yml` | Prod EC2 | DockerHub 이미지 기반, 80/443, 인증서/certbot 볼륨, appnet |

Dev EC2는 `docker-compose.yml`을 base로 두고 `docker-compose.dev.yml`이 필요한 항목만 덮어쓰는 override 패턴을 씁니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d webserver
```

---

## 3. Dev 배포 구조 (SSH + rsync)

Dev EC2는 PEM 키로 SSH 직접 접근이 가능합니다. Dockerfile 없이 공식 `nginx:stable-alpine` 이미지에 파일을 볼륨 마운트하는 구조입니다.

```
dev 브랜치 push
    └→ GitHub Actions
          1. npm ci + npm run build  →  build/ 생성
          2. rsync → EC2 ~/doongzi-frontend/
               ├── build/            (정적 파일)
               ├── docker-compose.yml
               ├── docker-compose.dev.yml
               ├── nginx-ssl.conf
               └── nginx-main.conf
          3. SSH: docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d webserver
```

빌드 결과물이 EC2 디스크에 직접 올라가므로 nginx 설정을 rsync만으로 즉시 반영할 수 있습니다. 단, 이미지 태그로 롤백하는 것은 불가능합니다.

---

## 4. Prod 배포 전략: 왜 이미지 빌드를 선택했나

### Prod EC2에는 SSH 키가 없다

처음에는 Dev와 동일한 rsync 방식을 Prod에도 적용하려 했습니다. 그런데 Prod EC2는 보안상의 이유로 **PEM 키 없이 SSM(AWS Systems Manager)으로만 접근**합니다. rsync는 SSH 연결을 전제로 하므로 SSM 환경에서는 동작하지 않습니다.

### 선택지 비교

SSM 환경에서 파일을 EC2로 전달하는 방법을 따져봤습니다.

**S3 경유 rsync 대체**: GitHub Actions에서 S3에 빌드 결과물을 올리고, SSM으로 EC2에서 `aws s3 sync`로 받는 방법입니다. 가능하지만 빌드 결과물(수백 개의 정적 파일)을 매번 S3에 올리고 EC2에서 받는 과정이 번거롭고, 이미지 태그 기반 롤백도 불가능합니다.

**Dockerfile 이미지 빌드**: GitHub Actions에서 `docker build`로 빌드 결과물과 `nginx-ssl.conf`를 이미지 안에 내장하고 DockerHub에 push합니다. EC2에서는 `docker pull`만 실행하면 됩니다. 백엔드 CD와 구조가 동일하고, 이미지 태그로 롤백도 가능합니다.

| 기준 | rsync + S3 경유 | Dockerfile 이미지 빌드 |
|------|----------------|----------------------|
| Prod 적용 가능 여부 | ✅ (복잡) | ✅ |
| 백엔드 CD와 일관성 | ❌ | ✅ 동일 패턴 |
| 롤백 | ❌ 불가 | ✅ 이미지 태그 |
| nginx 설정 핫픽스 | ✅ S3 업로드 후 재시작 | ❌ 재빌드 필요 |
| S3 비용/복잡도 | 빌드 결과물 전체 업로드 | compose 파일만 업로드 |

nginx 설정 핫픽스가 불가능한 점은 단점이지만, nginx 설정 변경이 잦지 않고 이미지 빌드 시간도 캐시를 활용하면 크지 않습니다. **이미지 빌드 방식**을 선택했습니다.

### Prod 배포 흐름

```
main 브랜치 push
    └→ GitHub Actions
          1. npm ci + npm run build
          2. docker build (nginx-ssl.conf 이미지에 내장) → DockerHub push
               srogsrogi/doongzi-frontend:{SHORT_SHA}
               srogsrogi/doongzi-frontend:latest-prod
          3. docker-compose.prod.yml → S3 업로드
          4. SSM → EC2 (/home/ubuntu/doongzi-frontend/)
               S3에서 docker-compose.prod.yml 다운로드
               IMAGE_TAG={SHORT_SHA} docker compose pull
               docker compose up -d
          5. SSM command 완료 polling
```

S3에는 compose 파일(텍스트 파일 하나)만 올립니다. 빌드 결과물은 모두 이미지 안에 있으므로 EC2는 `docker pull` 한 번으로 최신 상태가 됩니다.

---

## 5. Prod 사전 작업: 호스트 Nginx 제거

Prod EC2에는 호스트 Nginx가 설치되어 80번 포트를 선점하고 있었습니다. 프론트엔드 컨테이너도 80번 포트가 필요하므로 충돌이 발생합니다.

호스트 Nginx를 유지한 채 컨테이너를 다른 포트에 올리고 프록시하는 방법도 있었지만, 그러면 Nginx가 두 겹으로 쌓입니다. 불필요한 레이어를 제거하고 **컨테이너가 80번 포트를 직접 점유**하는 구조로 정리했습니다.

```bash
# 호스트 nginx 제거 (80번 포트 반환, /etc/nginx/ 전체 삭제됨)
sudo systemctl stop nginx && sudo apt purge nginx nginx-common -y
sudo apt autoremove -y

# Docker 네트워크 생성 (백엔드와 공유)
docker network create appnet

# 배포 디렉토리 생성
mkdir -p ~/doongzi-frontend
```

기존 `/etc/nginx/sites-available/doongzi`에 있던 설정(백엔드 직접 프록시)은 별도 수정 불필요합니다. `apt purge`로 디렉토리 전체가 삭제되고, 이후 `/api/v1/` 프록시는 컨테이너 내부 `nginx-ssl.conf`가 담당합니다.
