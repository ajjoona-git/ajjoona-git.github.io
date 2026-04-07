---
title: "[허수아비] SSL 인증서 확인과 Nginx 프록시 구성 결정"
date: 2026-03-20 11:00:00 +0900
categories: [Project, 허수아비]
tags: [Infra, SSL, Nginx, HTTPS, Docker, EC2, LetsEncrypt, Apache, Proxy]
toc: true
comments: true
description: "배포 준비 중 EC2에 SSAFY 발급 SSL 인증서가 사전 설치되어 있음을 확인했습니다. Apache httpd 실행 현황과 외부 네트워크 레이어를 점검한 뒤, EC2 #1의 frontend nginx가 80/443을 직접 점유하는 프록시 구성 방향을 결정한 과정을 정리합니다."
---

배포 환경을 준비하면서 HTTPS 설정 작업에 앞서 EC2의 현재 상태를 점검했습니다. 예상하지 못했던 사전 설치 인증서와 Apache 프로세스를 발견했고, 이를 바탕으로 Nginx 프록시 구성 방향을 결정했습니다.

---

## SSL 인증서가 이미 설치되어 있었습니다

EC2에 배포된 컨테이너들을 점검하던 중, HTTPS 설정을 논의하면서 SSL 인증서가 이미 존재하는 걸 확인했습니다.

```bash
ls /etc/letsencrypt/live/
# 결과: README  p.ssafy.io
```

EC2 #1, EC2 #2 모두 `/etc/letsencrypt/live/p.ssafy.io/` 경로에 인증서가 존재했습니다.

### 왜 미리 설치되어 있을까요?

`.p.ssafy.io` 와일드카드 인증서는 SSAFY가 직접 발급해서 EC2에 넣어준 것입니다. `p.ssafy.io` 도메인은 SSAFY가 소유하고 있어 수강생이 직접 Let's Encrypt DNS 인증을 받을 수 없기 때문입니다.

> Let's Encrypt는 도메인 소유를 증명하는 방식으로 HTTP 인증(HTTP-01)과 DNS 인증(DNS-01)을 지원합니다. `p.ssafy.io`처럼 서브도메인을 SSAFY가 소유·관리하는 경우, 수강생은 DNS 레코드를 직접 추가할 수 없어 DNS-01 챌린지를 통한 인증이 불가능합니다. SSAFY가 대신 와일드카드 인증서(`*.p.ssafy.io`)를 발급해 EC2에 배치한 것입니다.

certbot으로 발급한 표준 Let's Encrypt TLS 인증서이며, 경로도 certbot 표준 경로(`/etc/letsencrypt/live/`)를 따릅니다.


## Apache가 8989 포트에서 실행 중이었습니다

인증서가 있다면 이미 어딘가에서 쓰이고 있을 수 있다고 판단해 실행 중인 웹 서버를 확인했습니다.

```bash
systemctl status httpd
```

결과: Apache(`httpd`)가 `/opt/httpd/bin/httpd`로 실행 중이었습니다. 이전에 `8989` 포트 충돌이 있었던 것도 이 Apache가 원인이었습니다.

### Apache 설정은 어떻게 되어 있나요?

설정 파일: `/opt/httpd/conf/httpd.conf`

```
Listen 8989
Include conf/extra/httpd-vhosts.conf
```

- Apache는 **8989 포트만** 리스닝하고 있습니다.
- **80/443 포트는 점유하지 않습니다.**
- `mod_proxy`, `mod_proxy_http`, `mod_ssl`이 로드되어 있으나 실제 리버스 프록시 설정은 없습니다.
- `httpd-ssl.conf`도 주석 처리되어 있습니다.

즉 Apache는 리버스 프록시 역할을 하지 않으며, SSAFY가 관리 목적으로 8989에 올려둔 것으로 추정됩니다.

### EC2별 Apache 운영 현황

| EC2 | Apache 상태 |
|---|---|
| EC2 #1 (app) | Apache 없음. 80/443 완전히 비어있음 |
| EC2 #2 (data) | 8989에서 실행 중 |


## 외부 네트워크 레이어가 있을까요?

EC2 앞에 ALB나 로드밸런서가 있어서 80/443 → 8989로 포워딩할 가능성을 검토했습니다.

> ALB(Application Load Balancer)는 AWS에서 제공하는 L7 로드밸런서입니다. EC2 앞에 ALB가 있을 경우 외부에서 443으로 접속해도 실제 EC2로는 다른 포트로 전달될 수 있으며, 이 경우 EC2 내 nginx가 443을 직접 점유하지 않아도 HTTPS가 동작합니다.

```bash
curl -I http://xxxxxx.p.ssafy.io
```

확인 결과, EC2 #1에는 프록시 설정 자체가 없고 Apache도 없습니다. EC2 #2에만 Apache가 설정되어 있으며, 외부 네트워크 레이어의 프록시는 없는 것으로 확인됐습니다.

따라서 **EC2 #1의 nginx가 80/443을 직접 점유**해야 합니다.


## EC2별 프록시 구성 방향을 결정했습니다

### EC2 #1 (app): frontend nginx가 80/443을 직접 점유합니다

80/443이 비어있고 인증서도 있으므로, frontend 컨테이너(nginx)가 직접 80:80, 443:443을 점유합니다.
별도의 리버스 프록시 레이어 없이 frontend 컨테이너 자체가 nginx로 동작합니다.

트래픽 흐름:

```
클라이언트
  → 443 (HTTPS)
  → frontend 컨테이너 (nginx)
      → 정적 파일 서빙 (React 빌드 결과물)
      → /api/* → backend 컨테이너 (Spring Boot, 8080)
```

### EC2 #2 (data): 외부 노출 없이 내부 통신만 사용합니다

외부에 노출할 서비스가 없고 내부 통신만 사용합니다. 모니터링 UI(Kafka UI, Spark UI, Hadoop UI)는 포트 직접 오픈으로 충분하며, nginx 프록시는 불필요합니다.


## 어떤 작업이 남아 있나요?

### nginx.conf 작성 (`infra/ec2-app/nginx/nginx.conf`)

- HTTPS (443) 설정
- HTTP → HTTPS 리다이렉트 (80 → 443)
- React 정적 파일 서빙 (`/`)
- backend API 프록시 (`/api` → `http://backend:8080`)
- SPA용 fallback (`try_files $uri /index.html`)

### docker-compose 수정 (`infra/ec2-app/docker-compose.yml`)

frontend 서비스에 `/etc/letsencrypt` 마운트를 추가합니다:

```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  - /etc/letsencrypt:/etc/letsencrypt:ro
```
