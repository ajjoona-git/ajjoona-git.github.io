---
title: "[모아톤] AWS HTTPS 배포 가이드 (CloudFront + Nginx + Certbot)"
date: 2026-01-02 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [AWS, Https, CloudFront, Nginx, Certbot, SSL, Deployment, Nip.io, Network]
toc: true 
comments: true
image: /assets/img/posts/2026-01-02-moathon-aws-https-deploy/6.png
description: "도메인 구매 없이 무료로 HTTPS 환경을 구축합니다. 프론트엔드는 CloudFront CDN을 통해, 백엔드는 nip.io와 Certbot(Let's Encrypt)을 통해 SSL 인증서를 적용하고 보안 그룹 및 CORS 설정을 최적화하는 과정을 정리했습니다."
---

{% linkpreview "https://ajjoona-git.github.io/posts/moathon-aws-deployment" %}

지난 포스트에서 EC2와 S3를 이용해 배포에 성공했지만, 주소창의 '주의 요함(Not Secure)' 문구가 눈에 밟혔다.
이번에는 **CloudFront**와 **Nginx + Certbot** 조합을 통해 프론트엔드와 백엔드 모두에 **HTTPS(보안 접속)**를 적용하여 아키텍처를 완성해 본다.

---

## 아키텍처 구조

**CloudFront**가 앞단에서 화면을 안전하게(HTTPS) 보여주고, 사용자가 API를 요청하면 **Nginx**가 이를 받아 내부의 Django에게 전달하는 구조다.

![아키텍처](/assets/img/posts/2026-01-02-moathon-aws-https-deploy/6.png)
*아키텍처*

### 프론트엔드 영역 (화면 보여주기)

사용자가 브라우저 주소창에 `https://d3xxxx.cloudfront.net`을 입력했을 때의 흐름이다.

- **CloudFront (AWS CDN):**
    - **역할:** 사용자와 가장 가까운 곳에서 웹사이트 파일(`html`, `css`, `js`)을 빠르게 전달한다.
    - **HTTPS 역할:** S3는 HTTPS를 못 쓰지만, CloudFront가 대신 HTTPS 암호화를 처리해서 사용자에게 안전한 자물쇠(🔒)를 보여준다.
    - **캐싱:** 한 번 가져온 파일은 기억해 뒀다가, 다음 요청 때 S3까지 안 가고 바로 준다.
- **S3 (Simple Storage Service):**
    - **역할:** 우리가 만든 Vue.js 빌드 결과물(`dist` 폴더 내용)이 저장된 원본 창고.
    - **특징:** 정적 웹 사이트 호스팅 기능을 켜서 웹 서버처럼 동작하지만, 보안 기능(HTTPS)이 약해서 CloudFront 뒤에 숨겨두었다.

### 백엔드 영역 (데이터 처리하기)

사용자가 로그인 버튼을 누르거나 상품 목록을 조회할 때의 흐름이다.

- **nip.io (Magic Domain):**
    - **역할:** `54.180.xx.xx`라는 숫자 주소(IP)는 SSL 인증서를 못 받는다. `nip.io`는 이 IP를 마치 `domain.com` 같은 도메인 이름처럼 보이게 해준다. 덕분에 무료로 HTTPS 인증서를 받을 수 있었다.
- **Nginx (Web Server):**
    - **역할:** EC2 서버의 문지기.
    - **HTTPS 처리:** 사용자의 암호화된 요청을 받아서 해독(SSL Termination)한 뒤, 내부의 Gunicorn에게 넘겨준다.
    - **정적 파일 처리:** Django가 처리할 필요 없는 단순 파일(CSS, 이미지 등)은 직접 빠르게 준다.
- **Certbot (Let's Encrypt):**
    - **역할:** "이 서버는 안전한 서버입니다"라고 증명하는 **SSL 인증서**를 무료로 발급해주고, Nginx 설정을 자동으로 고쳐주는 도구.
- **Gunicorn (WSGI Server):**
    - **역할:** 웹 서버인 Nginx와 파이썬 프로그램인 Django 사이에서 말을 전달해준다. Nginx는 파이썬 코드를 이해 못 하기 때문.
- **Django (Web Framework):**
    - **역할:** 실제 로직을 처리한다. DB에서 데이터를 꺼내고, 계산하고, JSON 형태로 가공해서 프론트엔드에 응답을 준다.
    - **Settings:** `ALLOWED_HOSTS`(우리 집 주소 허용), `CORS`(프론트엔드 친구 허용) 설정을 통해 보안 검사를 수행한다.
- **AWS Security Group (Firewall):**
    - **역할:** AWS 클라우드 차원에서 포트(문)를 열고 닫는다.
    - **HTTPS(443):** 암호화된 편지가 들어오는 전용 출입구. 이걸 안 열어주면 Nginx가 아무리 기다려도 요청이 도착하지 않는다.

---

## 1. 백엔드 HTTPS 적용 (Nginx + Certbot)

보통 SSL 인증서를 받으려면 유료 도메인이 필요하다. 하지만 우리는 **`nip.io` (매직 도메인 서비스)**를 활용해 IP 주소를 도메인처럼 사용하여 무료 인증서(Let's Encrypt)를 발급받을 것이다.

### 1-1. Nginx 설정 수정 (`nip.io` 적용)

EC2 서버의 Nginx 설정에서 server_name을 IP 주소 기반의 도메인 형식으로 변경한다.

```bash
# /etc/nginx/sites-available/moathon

server {
    listen 80;
    # IP가 54.180.xx.xx 라면 아래와 같이 작성
    server_name 54.180.xx.xx.nip.io; 

    # ... 기존 설정 ...
}

```


### 1-2. Certbot 설치 및 인증서 발급

무료 인증서 발급 도구인 Certbot을 설치하고 실행한다. Nginx 플러그인을 사용하면 설정 파일까지 자동으로 수정해 준다.

```bash
# 1. Certbot 설치
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot

# 2. 인증서 발급 (이메일 입력 -> 약관 동의 Y -> 마케팅 N)
sudo certbot --nginx
```

명령어가 완료되면 백엔드는 이제 `https://54.180.xx.xx.nip.io` 주소를 갖게 된다.

![Certbot 인증서 발급](/assets/img/posts/2026-01-02-moathon-aws-https-deploy/5.png)
*Certbot 인증서 발급*

### 1-3. Django 설정 업데이트

도메인이 변경되었고 프로토콜이 HTTPS로 바뀌었으므로 Django의 보안 설정을 업데이트해야 한다.

```python
# settings.py

ALLOWED_HOSTS = [
    '52.180.xx.xx', 
    '52.180.xx.xx.nip.io' # [추가] nip.io 도메인 허용
]

# [추가] HTTPS 요청의 CSRF 검증을 위한 신뢰 도메인 설정
CSRF_TRUSTED_ORIGINS = ['https://52.180.xx.xx.nip.io']
```


## 2. 프론트엔드 HTTPS 적용 (CloudFront)

S3 정적 웹 호스팅은 기본적으로 HTTP만 지원한다. AWS의 CDN 서비스인 CloudFront를 앞단에 두어 HTTPS를 처리하도록 구성한다.

### 2-1. CloudFront 배포 생성

1. **Origin domain:** S3의 '정적 웹 사이트 호스팅 엔드포인트' URL 입력.
2. **Viewer protocol policy: Redirect HTTP to HTTPS** 선택 (보안 강제).
    - (예: `http://moathon-client-dist.s3-website.ap-northeast-2.amazonaws.com`)
3. 나머지 기본값으로 생성.

![배포 생성](/assets/img/posts/2026-01-02-moathon-aws-https-deploy/4.png)
*배포 생성*

### 2-2. 배포 완료

생성이 완료되면 `d3xxxxxx.cloudfront.net `형태의 도메인이 발급된다. 이제 이 주소로 접속하면 안전한 자물쇠 아이콘(🔒)을 볼 수 있다.

## 3. 프론트엔드 & 백엔드 연결 (Integration)

양쪽 모두 HTTPS로 전환되었으므로, 서로를 바라보는 주소를 수정하고 재배포해야 한다.

### 3-1. 프론트엔드 환경 변수 수정 (Local)

API 요청을 보내는 백엔드 주소를 https와 nip.io가 포함된 주소로 변경한다.

```python
# .env.production
VITE_API_URL=https://52.180.xx.xx.nip.io
```

### 3-2. 백엔드 CORS 설정 수정 (EC2)

Django가 허용할 프론트엔드 도메인(CloudFront 주소)을 추가한다.

```python
# settings.py

CORS_ALLOWED_ORIGINS = [
    # ... 기존 주소들 ...
    'https://d1xxxxxx.cloudfront.net', # [추가] CloudFront 도메인
]

CSRF_TRUSTED_ORIGINS = [
    'https://52.180.xx.xx.nip.io', # 백엔드 주소
    'https://d1xxxxxx.cloudfront.net', # 프론트엔드 주소
]
```
설정 후 `sudo systemctl restart gunicorn`으로 서버를 재시작한다.

### 3-3. 재빌드 및 배포

프론트엔드 코드를 다시 빌드(`npm run build`)하고, S3 버킷의 내용을 덮어씌운다.


## 4. 최종 보안 및 캐시 설정

### 4-1. AWS 보안 그룹 (Security Group) 설정

EC2 인스턴스의 방화벽 설정에서 **HTTPS(443) 포트**를 열어줘야 한다. 이를 놓치면 Nginx까지 요청이 도달하지 못한다.

- **유형:** HTTPS (443)

- **소스:** Anywhere-IPv4 (0.0.0.0/0)

![인바운드 규칙 편집](/assets/img/posts/2026-01-02-moathon-aws-https-deploy/3.png)
*인바운드 규칙 편집*

### 4-2. CloudFront 캐시 무효화 (Invalidation)

S3에 새 파일을 올렸더라도 CloudFront는 캐시된 구버전 파일을 계속 보여줄 수 있다. 변경 사항을 즉시 반영하기 위해 캐시를 날려준다.

- **경로:** CloudFront 콘솔 > 배포 선택 > 무효화 탭

- **객체 경로:** `/*` (모든 파일 무효화)

![무효화 생성](/assets/img/posts/2026-01-02-moathon-aws-https-deploy/2.png)
*무효화 생성*


## 최종 접속

이제 브라우저 주소창에 CloudFront 도메인(`https://...`)을 입력하면 **자물쇠 아이콘**과 함께 안전하게 접속된다. 개발자 도구의 Network 탭을 확인해 보면, 백엔드 API 요청 또한 HTTPS로 암호화되어 전송되는 것을 확인할 수 있다.

[배포 사이트 바로가기](https://d314hr75zv7jjv.cloudfront.net)

![https 접속 확인](/assets/img/posts/2026-01-02-moathon-aws-https-deploy/1.png)
*https 접속 확인*

이로써 **보안성(Security)**과 **성능(CDN)**을 모두 잡은 배포 아키텍처가 완성되었다.

---

### 레퍼런스

[[Deploy] nip.io, Nginx, certbot을 이용한 https 적용](https://innovation123.tistory.com/241)