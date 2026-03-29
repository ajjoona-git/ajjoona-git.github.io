---
title: "[허수아비] WebRTC CCTV 스트리밍 트러블슈팅: nginx 프록시부터 ICE 연결 실패까지"
date: 2026-03-24 10:00:00 +0900
categories: [Project, 허수아비]
tags: [WebRTC, WHEP, MediaMTX, nginx, Docker, ICE, RTSP, FFmpeg, CI/CD]
toc: true
comments: true
description: "허수아비 프로젝트에서 CCTV 영상을 WebRTC로 브라우저에 스트리밍하는 과정에서 마주친 트러블슈팅을 기록합니다. nginx 호스트명 해석 실패, Mixed Content 오류, ERR_CONNECTION_TIMED_OUT, ICE 연결 실패까지 원인 분석과 해결 과정을 단계별로 공유합니다."
---

허수아비 프로젝트에서 CCTV 영상을 실시간으로 브라우저에 보여주기 위해 WebRTC 스트리밍 파이프라인을 구축했습니다. RTSP로 들어오는 영상을 MediaMTX가 WebRTC(WHEP)로 변환하고, nginx가 이를 브라우저까지 프록시하는 구조입니다.

이 글은 해당 파이프라인을 EC2에 배포하면서 마주쳤던 트러블슈팅들을 기록한 것입니다.

---

## 전체 구조

```
브라우저 (React)
  → HTTPS 443 (nginx, EC2 #2)
      → /<cam_id>/whep  →  MediaMTX (EC2 #1, :8889)  ← RTSP (mock-cctv)
      → /api/*          →  backend (Spring Boot, :8080)
```

- **mock-cctv**: FFmpeg로 영상을 RTSP 스트림으로 송출 → MediaMTX에 푸시
- **MediaMTX**: RTSP를 WebRTC(WHEP)로 변환하여 브라우저에 제공
- **nginx**: 브라우저의 WHEP 요청을 EC2 #1의 MediaMTX로 프록시

두 EC2의 네트워크 구조는 다음과 같습니다.

```
EC2 #1 (data-net)          EC2 #2 (app-net)
┌──────────────────┐        ┌──────────────────┐
│ media-proxy:8889 │ ←───── │ frontend (nginx)  │
│ kafka:9092       │ ←───── │ backend:8080      │
│ (외부: :9094)    │        │ postgres          │
└──────────────────┘        └──────────────────┘
```

EC2 #2에서 EC2 #1에 접근할 때 Docker 내부 호스트명(`media-proxy`, `kafka`)은 사용할 수 없고, 반드시 EC2 #1의 외부 IP와 외부 포트를 사용해야 합니다.

## 트러블슈팅 로그

### 이슈 1. nginx: `media-proxy` 호스트명 해석 실패

### 증상

```
host not found in upstream "media-proxy" in /etc/nginx/nginx.conf:41
```

#### 원인

`media-proxy` 컨테이너는 EC2 #1(`data-net`)에 있고, frontend nginx는 EC2 #2(`app-net`)에 있습니다. 서로 다른 서버에 있기 때문에 Docker 내부 DNS로는 호스트명을 해석할 수 없습니다.

#### 해결

`nginx.conf`에 `$EC2_DATA_HOST` 플레이스홀더를 사용하고, CI의 `deploy-frontend` 잡에서 `envsubst`로 실제 IP를 치환한 후 EC2로 전송했습니다.

```nginx
# nginx.conf
location ~ ^/[^/]+/whep$ {
    proxy_pass http://$EC2_DATA_HOST:8889;
}
```

```yaml
# .gitlab-ci.yml
- envsubst '${EC2_DATA_HOST}' < infra/ec2-app/nginx/nginx.conf > /tmp/nginx.conf
- scp /tmp/nginx.conf $EC2_USER@$EC2_APP_HOST:.../nginx/nginx.conf
```

이로써 브라우저 → `https://<도메인>/<cam_id>/whep` 요청이 nginx를 통해 `http://<EC2_DATA_IP>:8889/<cam_id>/whep`로 올바르게 프록시됩니다.


### 이슈 2. WHEP POST 요청 404

#### 증상

브라우저에서 WHEP 요청 시 404 응답.

#### 원인

DB의 `camera` 테이블이 비어 있어 backend가 카메라 정보를 찾지 못했습니다.

#### 해결

DB에 카메라 데이터를 삽입한 후 정상 동작을 확인했습니다. 배포 초기 시딩 스크립트에서 누락된 항목이었습니다.


### 이슈 3. Mixed Content 오류

#### 증상

```
Mixed Content: The page at 'https://...' was loaded over HTTPS,
but requested an insecure resource 'http://...'.
This request has been blocked; the content must be served over HTTPS.
```

#### 원인

GitLab Variables의 `MEDIA_PROXY_PUBLIC_WHEP_BASE_URL`이 `http://`로 설정되어 있었습니다. HTTPS 페이지에서 HTTP 리소스를 요청하면 브라우저가 차단합니다.

#### 해결

```
MEDIA_PROXY_PUBLIC_WHEP_BASE_URL=https://<APP 서버 도메인>
```

`setup-env-app` 잡을 수동 실행하고 backend를 재시작해 환경변수를 반영했습니다.


### 이슈 4. WHEP POST ERR_CONNECTION_TIMED_OUT

#### 증상

```
POST https://<도메인>/1/whep net::ERR_CONNECTION_TIMED_OUT
WebRTC 연결 오류: TypeError: Failed to fetch
```

#### 원인 1: MEDIA_PROXY_PUBLIC_WHEP_BASE_URL에 EC2 DATA 주소 설정

`MEDIA_PROXY_PUBLIC_WHEP_BASE_URL`에 EC2 DATA 서버 주소가 직접 설정되어 있었습니다. 브라우저가 HTTPS로 EC2 DATA에 직접 접근을 시도하지만, EC2 DATA에는 SSL을 처리하는 nginx가 없어서 타임아웃이 발생했습니다.

올바른 요청 흐름은 다음과 같습니다.

```
브라우저 → https://<EC2 APP>/1/whep → nginx → http://<EC2 DATA>:8889/1/whep → MediaMTX
```

#### 해결

`MEDIA_PROXY_PUBLIC_WHEP_BASE_URL`을 nginx가 있는 EC2 APP 주소로 설정합니다.

```
MEDIA_PROXY_PUBLIC_WHEP_BASE_URL=https://<EC2 APP 도메인>
```

#### 원인 2: nginx.conf의 EC2_DATA_HOST 환경변수 미치환

CI의 `deploy-frontend` 잡이 `envsubst`로 `nginx.conf`를 치환한 뒤 `scp`로 파일을 전송했지만, **컨테이너를 재생성하지 않아** 컨테이너 내부에는 이전 파일이 그대로 남아 있었습니다.

#### 해결

파일 전송 후 컨테이너를 재생성했습니다.

```bash
docker compose up -d --no-deps frontend
```

컨테이너 내부의 nginx.conf가 올바르게 치환됐는지 확인하는 방법:

```bash
docker exec birdybuddy-frontend cat /etc/nginx/nginx.conf | grep proxy_pass
```


### 이슈 5. ICE 연결 실패 (TimeoutError)

#### 증상

WHEP POST(시그널링)는 성공하지만 WebRTC 영상이 재생되지 않고 타임아웃이 발생합니다.

#### 원인 1: media-proxy 컨테이너 ICE/UDP 포트 미노출

EC2 docker-compose에서 media-proxy의 포트 매핑이 잘못 설정되어 있었습니다.

```yaml
# 잘못된 설정 (SRT 포트, ICE와 무관)
- "8890:8890/udp"

# 올바른 설정 (WebRTC ICE/UDP)
- "8189:8189/udp"
```

MediaMTX 로그에서 실제로 사용하는 포트를 확인할 수 있습니다.

```
[WebRTC] listener opened on :8889 (HTTP), :8189 (ICE/UDP)
```

#### 해결
docker-compose에서 `8189:8189/udp`로 수정하고 media-proxy를 재시작했습니다.

#### 원인 2: MediaMTX ICE candidate에 Docker 내부 IP 포함

MediaMTX가 SDP 응답에 Docker 내부 IP(`172.18.0.x`)를 ICE candidate로 포함했습니다. 브라우저는 해당 IP에 접근할 수 없어 ICE 연결에 실패했습니다.

#### 해결
`mediamtx.yml`에 외부 호스트를 명시해 올바른 ICE candidate가 포함되도록 설정했습니다.

```yaml
webrtcAdditionalHosts:
  - <EC2 DATA 도메인 또는 IP>
```

---

## 정리

이번 트러블슈팅에서 반복적으로 등장한 핵심 원인은 **두 EC2 간 네트워크 격리**였습니다. 같은 Docker 네트워크가 아니기 때문에 내부 호스트명이 통하지 않고, SSL 종료도 각 EC2별로 처리됩니다. 이를 기준으로 설정을 검토하면 대부분의 문제를 빠르게 추적할 수 있습니다.

| 이슈 | 핵심 원인 | 해결 키워드 |
|------|----------|------------|
| nginx 호스트명 해석 실패 | Docker 네트워크 격리 | `envsubst` + 외부 IP |
| WHEP 404 | DB 시딩 누락 | 카메라 데이터 삽입 |
| Mixed Content | HTTP URL 설정 오류 | `https://` 로 변경 |
| ERR_CONNECTION_TIMED_OUT | nginx 미경유 / 컨테이너 미재생성 | APP 도메인 사용 + 컨테이너 재생성 |
| ICE 연결 실패 | 포트 오설정 / 내부 IP 노출 | UDP 포트 수정 + `webrtcAdditionalHosts` |
