---
title: "[둥지] 프론트엔드 HTTPS 구성: ALB 대신 certbot을 선택한 이유"
date: 2026-04-24 11:00:00 +0900
categories: [Project, 둥지]
tags: [Nginx, HTTPS, Certbot, LetsEncrypt, Docker, SSL, TLS, DevOps, Frontend, Infra]
toc: true
comments: true
image: /assets/img/posts/2026-04-24-doongzi-frontend-https-certbot/1.png
description: "ALB+ACM과 컨테이너 certbot 방식을 비교하고, webroot 인증과 standalone 선발급을 조합해 컨테이너 중단 없는 HTTPS 자동 갱신 구조를 설계한 과정을 정리합니다."
---

프론트엔드에 HTTPS를 붙이는 작업은 단순히 인증서를 발급하는 것이 아니었습니다. "어디서 SSL을 끊을 것인가", "어떻게 인증서를 갱신할 것인가", "컨테이너 기동 순서 문제를 어떻게 해결할 것인가" — 세 가지 결정이 연달아 필요했습니다.

---

## SSL을 어느 계층에서 끊을 것인가

HTTPS를 처리하는 방법은 크게 두 가지입니다.

### 1. L7 로드밸런서 계층 (ALB + ACM)

AWS ALB가 443 포트를 받아 ACM 인증서로 복호화한 뒤, EC2 컨테이너로는 HTTP로 전달하는 방식입니다.

```
클라이언트 → (HTTPS) → ALB (ACM 인증서) → (HTTP) → EC2 컨테이너
```

인증서 갱신을 ACM이 자동으로 처리하고, EC2 보안 그룹에서 443 포트를 열 필요도 없습니다. 암호화/복호화 부하도 ALB가 부담합니다. 현업에서 가장 많이 쓰는 표준 패턴입니다.

**그런데 ALB는 월 약 $20 + LCU 비용이 발생합니다.** 장기 운영 서비스라면 관리 편의성으로 충분히 상쇄되지만, 현재 프로젝트 규모에서는 부담이 됩니다.

### 2. 리버스 프록시 계층 (Nginx + certbot)

Nginx 컨테이너가 인증서를 직접 보유하고 443 포트를 처리하는 방식입니다.

```
클라이언트 → (HTTPS) → Nginx 컨테이너 (Let's Encrypt 인증서) → FastAPI
```

ALB 비용이 없고, nginx 설정에서 라우팅 규칙을 세밀하게 제어할 수 있습니다. 단점은 EC2가 인터넷에 직접 노출되고, 인증서 갱신을 직접 관리해야 한다는 점입니다.

### certbot으로 결정

비용이 결정적인 이유였습니다. 그리고 **인증서 갱신 자동화가 충분히 가능**하다면 관리 부담도 크지 않습니다. Dev/Prod 모두 컨테이너 certbot으로 통일하기로 했습니다.

| 항목 | ALB + ACM | 컨테이너 certbot |
|------|-----------|----------------|
| **비용** | 약 $20/월 + LCU | 무료 |
| **인증서 갱신** | 자동 (ACM) | 90일마다, deploy hook으로 자동화 |
| **nginx 변경** | 없음 (HTTP 그대로 유지) | 443 블록 추가 필요 |
| **EC2 직접 노출** | ALB 뒤에 숨음 | 인터넷에 직접 노출 |
| **DDoS 방어** | AWS Shield Standard 자동 적용 | 없음 |

---

## 인증서 갱신을 어떻게 자동화할 것인가

### certbot 인증 방식: standalone vs webroot

certbot이 인증서를 발급/갱신할 때 Let's Encrypt 서버에 도메인 소유권을 증명해야 합니다. 방식이 두 가지입니다.

**standalone 방식**은 certbot이 직접 80번 포트를 점유해 임시 HTTP 서버를 띄웁니다. 문제는 Nginx 컨테이너가 이미 80번 포트를 쓰고 있으면 충돌이 발생합니다. 갱신할 때마다 컨테이너를 내렸다 올려야 합니다.

**webroot 방식**은 certbot이 챌린지 파일을 디렉토리에 쓰고, 실행 중인 Nginx가 이를 서빙합니다. 컨테이너를 중단할 필요가 없습니다.

```
certbot → /var/www/certbot/.well-known/acme-challenge/{토큰} 파일 생성
Let's Encrypt → http://doongzi.site/.well-known/acme-challenge/{토큰} 요청
Nginx → /var/www/certbot 경로 서빙 (nginx-ssl.conf의 location 블록)
→ 파일 확인 완료 → 인증서 발급/갱신
```

**webroot를 선택**했습니다. `nginx-ssl.conf`에 ACME 챌린지 경로를 포함한 이유, compose 파일에 `/var/www/certbot` 볼륨 마운트가 들어간 이유가 여기에 있습니다.

### 갱신 후 Nginx reload 자동화: deploy hook

webroot로 갱신에 성공해도 Nginx가 새 인증서를 읽으려면 reload가 필요합니다. crontab에 `certbot renew && docker exec ...`를 붙이는 방법도 있지만, 갱신이 실패하면 reload가 실행되지 않아야 하는 조건 처리가 지저분해집니다.

certbot은 갱신 성공 시 `/etc/letsencrypt/renewal-hooks/deploy/` 내 스크립트를 **자동으로 실행**합니다. 여기에 Nginx reload를 등록하면 조건 처리 없이 깔끔합니다.

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null <<'EOF'
#!/bin/bash
docker exec doongzi-app nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

갱신 흐름은 이렇게 됩니다.

```
certbot renew (systemd timer 또는 crontab — 일 2회)
    └→ 인증서 갱신 성공 시에만 deploy hook 자동 실행
          └→ docker exec doongzi-app nginx -s reload
```

certbot timer 상태를 확인합니다.

```bash
sudo systemctl status certbot.timer
```

`inactive`이면 crontab을 수동 등록합니다.

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * certbot renew --quiet"; echo "0 14 * * * certbot renew --quiet") | sudo crontab -
```

---

## 컨테이너 기동 전에 인증서가 있어야 한다는 문제

여기서 닭과 달걀 문제가 생겼습니다.

`nginx-ssl.conf`는 컨테이너에 항상 마운트됩니다. 이 파일은 443 블록에 `ssl_certificate` 경로를 명시하고 있어서 **인증서 파일이 없으면 Nginx가 시작 자체를 거부**합니다.

그런데 webroot 방식으로 인증서를 발급하려면 Nginx가 먼저 떠서 챌린지 파일을 서빙해야 합니다.

> Nginx가 뜨려면 인증서가 있어야 하고, 인증서를 받으려면 Nginx가 떠 있어야 한다.

### 해결: PR 머지 전 standalone으로 선발급

컨테이너가 아직 없는 상태, 즉 80번 포트가 비어있을 때 standalone 방식으로 **최초 1회만 발급**합니다. PR 머지 전에 서버에서 직접 실행합니다.

```bash
# Dev EC2
sudo certbot certonly --standalone -d dev.doongzi.site

# Prod EC2
sudo certbot certonly --standalone -d doongzi.site -d www.doongzi.site
```

이후 컨테이너가 기동될 때는 인증서가 이미 존재하므로 Nginx가 정상 시작됩니다. 그 다음부터의 갱신은 webroot로 처리합니다.

renewal 설정 파일에서 인증 방식을 전환합니다.

```ini
# /etc/letsencrypt/renewal/doongzi.site.conf
authenticator = webroot
webroot_path = /var/www/certbot
```

standalone(최초 발급) → webroot(이후 갱신)를 조합하는 이유입니다.

---

## 전체 작업 순서

세 가지 결정을 정리하면 아래 순서가 됩니다.

### 1단계 — Dev/Prod EC2 인증서 선발급 (PR 머지 전)

컨테이너가 없는 상태에서 standalone으로 발급합니다.

![dev 배포 전 인증서 선발급 (standalone)](/assets/img/posts/2026-04-24-doongzi-frontend-https-certbot/2.png)
*dev 배포 전 인증서 선발급 (standalone)*

### 2단계 — PR 머지 → CD 자동 실행

`cicd-prod.yml` 트리거 → Prod 프론트엔드 첫 배포. 인증서가 이미 있으므로 컨테이너 정상 기동됩니다.

```
main 머지
→ 이미지 빌드 (nginx-ssl.conf 내장)
→ docker-compose.prod.yml → S3 업로드
→ SSM: S3에서 compose 파일 다운로드 → docker compose up -d
→ 컨테이너 HTTP(80) 기동 성공

이후 Prod EC2에서:
sudo certbot certonly --webroot -w /var/www/certbot -d doongzi.site -d www.doongzi.site
docker compose -f docker-compose.prod.yml up -d --force-recreate
→ nginx-ssl.conf 볼륨 + 인증서 볼륨 모두 있음 → HTTPS 적용
```

### 3단계 — deploy hook 등록 (Dev/Prod EC2 각각)

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null <<'EOF'
#!/bin/bash
docker exec doongzi-app nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

### 4단계 — certbot timer 확인

```bash
sudo systemctl status certbot.timer
```

### 5단계 — 컨테이너 재시작으로 HTTPS 적용

```bash
# Dev EC2
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate webserver

# Prod EC2
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

---

## 배포 결과

![배포 성공](/assets/img/posts/2026-04-24-doongzi-frontend-https-certbot/1.png)
*HTTPS 배포 성공*

`server_name _` 하나로 Dev와 Prod에 동일한 이미지를 배포하고, 인증서 경로만 볼륨으로 교체하는 구조가 의도대로 동작했습니다.
