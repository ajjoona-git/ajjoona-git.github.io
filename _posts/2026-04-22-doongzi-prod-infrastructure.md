---
title: "[둥지] Keyless Prod 서버 구축기: SSH 없이 EC2를 운영하는 법"
date: 2026-04-22 10:00:00 +0900
categories: [Project, 둥지]
tags: [AWS, EC2, SSM, Nginx, Certbot, Docker, HTTPS, Infra, Backend, DevOps]
toc: true
comments: true
image: 
description: "SSH 키 없이 AWS SSM으로만 접근하는 Prod EC2를 구축한 과정을 공유합니다. 개발(Dev)과 운영(Prod) 리소스를 완전히 분리한 이유, Nginx 리버스 프록시와 Let's Encrypt HTTPS 설정, 그리고 Docker Compose 기반 컨테이너 운영 구조까지 다룹니다."
---

개발 환경과 운영 환경을 하나의 서버와 하나의 Redis DB 안에서 DB 번호만 달리해 함께 쓰는 구조는 개발 초기엔 빠르지만, 배포 시점이 다가오면 여러 문제를 일으킵니다. 둥지 백엔드의 운영 서버를 처음부터 별도로 구성하며 내린 결정들을 기록합니다.

---

## 1. 왜 리소스를 완전히 분리했나

처음에는 Dev EC2에서 개발용 Redis DB 0번, 운영용 Redis DB 10번으로 나눠 쓰는, 논리적 분리 방식을 검토했습니다. 하지만 이 구조에는 근본적인 문제가 있었습니다.

### DB 번호 분리의 한계

- Celery 큐와 세션 캐시가 같은 인스턴스 안에 공존하므로 부하가 섞입니다.
- Dev 배포 중 Redis 재시작이 필요하면 Prod에도 영향이 미칩니다.
- Tailscale ACL에서 Dev와 Prod 트래픽을 논리적으로 구분하기 어렵습니다.

### EC2, RDS, ElastiCache 독립 인스턴스

그래서 **EC2, RDS, ElastiCache 각각 독립된 인스턴스**를 생성해 dev용 1세트, prod용 1세트로 나누기로 결정했습니다.

- Prod EC2에는 `doongzi.site` 도메인을 연결합니다.
- Prod RDS(PostgreSQL)와 Prod ElastiCache(Redis)는 운영 트래픽만 전담합니다.
- `.env.prod`에는 완전히 새로운 Prod 엔드포인트들만 담겨 있어 환경 변수 혼입 가능성이 없습니다.
- Tailscale ACL에서 `tag:dev` ↔ `tag:prod` 간 통신을 100% 차단하여 완벽한 망 분리를 구현합니다.

### 로컬 워커 운용

Windows 로컬 노트북에서 Celery 워커를 돌려야 하는 상황이 있습니다. 분리된 인스턴스 덕분에 `.env.worker.prod`만 주입하면 이 워커 프로세스는 물리적으로 떨어진 Prod Redis의 `issuance` 큐만 바라보고 작업합니다. Dev 큐와 섞일 위험이 사라집니다.

---

## 2. 왜 SSH 키 대신 SSM인가

EC2에 접근하는 전통적인 방법은 `.pem` 키 파일로 22번 포트에 SSH 접속하는 것입니다. Prod 서버에는 이 방식을 채택하지 않았습니다.

### SSH의 단점

- 22번 포트를 열어두면 인터넷에 공격 표면이 노출됩니다.
- `.pem` 키 파일을 분실하거나 유출하면 서버 접근 자체가 위협받습니다.
- GitHub Actions에서 EC2에 배포 명령을 내리려면 CI 서버에 키를 저장해야 합니다.

### AWS SSM Session Manager

- EC2 보안 그룹에서 22번 포트를 완전히 닫습니다.
- SSM Agent가 설치된 인스턴스에 IAM 권한으로만 접근합니다.
- GitHub Actions는 `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`로 SSM `send-command`를 호출하여 EC2에 명령을 내립니다. EC2 자체에는 어떤 비밀 키도 남지 않습니다.

```bash
# 로컬에서 SSM 접속 확인
aws sts get-caller-identity
aws ssm start-session --target <인스턴스 ID>
```

인스턴스 생성 시 pem 키 없이 SSM 전용으로 설정하고, VPC와 EIP를 연결한 뒤 위 명령어로 접속을 검증했습니다.

---

## 3. EC2 인스턴스 설정하기

### Docker CE + Compose 설치

ubuntu 22.04 버전에서 Docker CE와 Compose를 설치하는 명령어입니다.

```bash
# Docker 공식 GPG 키 및 저장소 추가
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

설치가 잘 되었는지 version을 찍어 확인해봅니다.

```bash
$ docker --version
Docker version 29.4.1, build 055a478
$ docker compose version
Docker Compose version v5.1.3
```

### Nginx 리버스 프록시 + Let's Encrypt HTTPS

컨테이너는 `127.0.0.1:8000`에 바인딩하고, 외부 트래픽은 Nginx가 받아 전달합니다. 이 구조에서 컨테이너 포트를 외부에 직접 노출하지 않아도 됩니다.

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo nano /etc/nginx/sites-available/doongzi
```

nginx는 다음과 같이 작성합니다.

```nginx
server {
    listen 80;
    server_name doongzi.site www.doongzi.site;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Certbot은 Nginx 설정을 직접 수정하여 443 포트 블록을 추가하고 80→443 리다이렉트를 자동으로 처리합니다.

```bash
# 설정 활성화 및 적용
sudo ln -s /etc/nginx/sites-available/doongzi /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# HTTPS 인증서 발급 (Let's Encrypt)
sudo certbot --nginx -d doongzi.site -d www.doongzi.site
```

![인증서 발급 완료](/assets/img/posts/2026-04-22-doongzi-prod-infrastructure/1.png)
*인증서 발급 완료*

성공 시 syntax is ok, test is successful 이라는 메시지가 뜹니다.

---

## 4. 운영 환경 변수 전략

### docker-compose.cloud.yml의 역할

로컬 개발용 `docker-compose.yml`과 별도로 `docker-compose.cloud.yml`을 오버레이로 관리합니다.

- **로컬호스트 바인딩**: `127.0.0.1:8000:8000`으로 외부 직접 접근 차단
- **로그 로테이션**: EC2 디스크 보호를 위한 `x-logging` 설정
- **리소스 분배**: Celery 워커와 Beat에 합리적인 CPU/메모리 제한

### IMAGE_TAG 변수를 쓰는 이유

`latest` 태그만 사용하면 두 가지 문제가 생깁니다.

1. **롤백 불가**: `latest`는 '마지막에 푸시된 상태'를 가리키는 임시 꼬리표입니다. 특정 시점으로 정확히 롤백할 수 없습니다.
2. **캐싱 오류**: EC2에 이미 `latest` 이미지가 있으면 `docker compose up`이 새 이미지를 내려받지 않고 예전 버전을 그대로 올립니다.

```yaml
# .env.prod
IMAGE_TAG=a1b2c3d  # GitHub Actions에서 SHORT_SHA로 주입
```

Git 커밋의 앞 7자리(SHORT_SHA)를 태그로 사용하면 배포된 이미지가 정확히 어떤 커밋인지 추적할 수 있습니다.

---

## 정리

| 결정 | 선택 | 이유 |
|---|---|---|
| 인프라 분리 | EC2/RDS/Redis 각각 독립 인스턴스 | 부하 격리, 망 분리, 설정 혼입 방지 |
| 서버 접근 | SSM (SSH 없음) | 공격 표면 최소화, 키 관리 부담 제거 |
| 포트 구조 | Nginx 리버스 프록시 | 컨테이너 포트 미노출, HTTPS 처리 일원화 |
| 이미지 태그 | SHORT_SHA | 롤백 기준 확보, 캐싱 오류 방지 |

다음 포스트에서는 GitHub Actions CD 파이프라인 구성과 배포 과정에서 발생한 트러블슈팅을 다룹니다.
