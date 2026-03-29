---
title: "[허수아비] WebRTC에서 HLS로 전환하다"
date: 2026-03-24 11:00:00 +0900
categories: [Project, 허수아비]
tags: [HLS, MediaMTX, nginx, Docker, RTSP, WebRTC, SPA]
toc: true
comments: true
image: /assets/img/posts/2026-03-24-birdybuddy-webrtc-to-hls/1.png
description: "허수아비 프로젝트에서 WebRTC WHEP 방식을 HLS로 전환하는 과정에서 마주친 두 가지 트러블슈팅을 기록합니다. mediamtx.yml 볼륨 마운트 후 RTSP 스트림이 차단된 문제와, nginx SPA fallback이 HLS 세그먼트 요청을 가로채는 문제를 다룹니다."
---

이전 포스트에서 WebRTC(WHEP) 방식으로 CCTV 스트리밍 파이프라인을 구축하며 겪은 트러블슈팅을 정리했습니다. 이번에는 해당 방식에서 **HLS**로 전환하는 과정에서 추가로 마주친 이슈 두 가지를 기록합니다.

> 이전 글: [WebRTC CCTV 스트리밍 트러블슈팅: nginx 프록시부터 ICE 연결 실패까지]({% post_url 2026-03-24-birdybuddy-webrtc-troubleshooting %})

---

## 왜 HLS로 변경해야 했나?

![허수아비 시스템 아키텍처](/assets/img/posts/2026-03-24-birdybuddy-webrtc-to-hls/2.png)
*허수아비 시스템 아키텍처*

허수아비는 EC2 2대를 사용하며, app-node와 data-node를 분리하고 있습니다. WebRTC 연결이 필요했던 이유는 CCTV 영상을 스트리밍해 프론트엔드에서 보여줘야 했기 때문입니다.

시스템 아키텍처에서 확인할 수 있듯이, CCTV 영상을 스트리밍하고 있는 media-proxy 컨테이너는 EC2-DATA 서버에 있고, nginx(프론트엔드) 컨테이너는 EC2-APP 서버에 있습니다. 여기서 **AWS 보안 그룹**에서 ICE 연결에 필요한 포트가 차단되어 있었습니다. AWS 보안 그룹 설정이 필요한데, 보안 그룹 설정 권한이 없어서 문제가 생겼습니다. 


WebRTC 연결 흐름:

1. 브라우저 → nginx(443) → MediaMTX(8889): WHEP POST **✅ 성공**
2. 브라우저 ↔ MediaMTX: ICE/UDP or ICE/TCP 직접 연결 **❌ 차단됨**

시도한 포트:

| 포트 | 프로토콜 | 결과 |
| --- | --- | --- |
| 8189 | UDP | 차단 |
| 9001 | UDP | 차단 |
| 9001 | TCP | 차단 |

ufw는 모두 열려있으나 **AWS 보안 그룹이 우선**하므로 ufw로는 해결할 수 없었습니다.

### 대안 1. HLS 스트리밍 (즉시 적용 가능)

포트 추가 없이 기존 8889(HTTP)만으로 영상을 제공할 수 있습니다.

| 항목 | 내용 |
| --- | --- |
| 난이도 | 낮음 |
| 지연시간 | 2~5초 |
| 추가 인프라 | 불필요 |
| 보안 그룹 변경 | 불필요 |

HLS URL 형식:

```
<https://j14a206a.p.ssafy.io/1/index.m3u8>
```

nginx에 HLS 프록시를 추가해야 합니다.

```
location ~ ^/[^/]+/index\\.m3u8$ {
    proxy_pass http://$EC2_DATA_HOST:8888;
}
```

프론트엔드에서는 hls.js 라이브러리로 재생합니다.

---

### 대안 2. STUN/TURN 서버 사용

공개 TURN 서버를 통해 ICE 연결을 중계합니다. 브라우저와 MediaMTX가 직접 연결하지 않고 TURN 서버를 경유하므로 보안 그룹 포트 차단을 우회할 수 있습니다.

| 항목 | 내용 |
| --- | --- |
| 난이도 | 중간 |
| 지연시간 | WebRTC 수준 (< 1초) |
| 추가 인프라 | TURN 서버 필요 (유료 또는 자체 구축) |
| 보안 그룹 변경 | 불필요 |

mediamtx.yml 설정:

```yaml
webrtcICEServers2:
  - url: turn:<TURN서버주소>:3478
    username: <username>
    password: <password>
```

프론트엔드 RTCPeerConnection 설정에도 동일한 TURN 서버를 추가해야 합니다.

공개 TURN 서버(Twilio, Metered 등)는 유료이며, 자체 구축 시 coturn을 사용합니다.

---

### 대안 3. nginx(frontend)를 EC2 DATA로 이동

media-proxy를 EC2 APP으로 옮기려면 mock-cctv, AI 워커도 함께 옮겨야 하므로, 오히려 **nginx와 frontend를 EC2 DATA로 이동**하는 것이 더 합리적입니다.

**현재 구조:**

```
EC2 APP: frontend(nginx), backend, postgres, minio
EC2 DATA: media-proxy, mock-cctv, ai, kafka, spark, hadoop
```

**변경 후 구조:**

```
EC2 APP: backend, postgres, minio
EC2 DATA: frontend(nginx), media-proxy, mock-cctv, ai, kafka, spark, hadoop
```

| 항목 | 내용 |
| --- | --- |
| 난이도 | 중간 |
| 지연시간 | WebRTC 수준 (< 1초) |
| 추가 인프라 | 없음 |
| 보안 그룹 변경 | EC2 DATA에 443, 80, ICE 포트(8189/UDP) 추가 필요 |

변경 사항:

- `infra/ec2-data/docker-compose.yml`에 frontend(nginx) 서비스 추가
- `infra/ec2-app/docker-compose.yml`에서 frontend 제거
- nginx의 backend 프록시 주소를 EC2 APP 외부 주소로 변경
- SSL 인증서를 EC2 DATA에 마운트
- CI `deploy-frontend` 잡을 EC2 DATA로 변경

EC2 APP의 리소스 부담이 줄어드는 부수적인 이점도 있습니다. 단, EC2 DATA에 443/80 포트 개방 및 SSL 인증서 설정이 필요합니다.

---

## HLS로 전환하는 과정에서 발생한 트러블슈팅

대안 중 가장 즉각적이고 변경 비용이 적은 **HLS** 방법을 선택했습니다. 전환하는 과정에서도 순탄치 않았는데, 그 과정을 공유합니다.

| 이슈 | 핵심 원인 | 해결 키워드 |
|------|----------|------------|
| RTSP 스트림 차단 | `paths:` 섹션 누락으로 기본값 무효화 | `paths: all_others:` 추가 |
| HLS 세그먼트 → index.html 반환 | SPA fallback이 `.mp4` 요청을 가로챔 | location 패턴에 `.mp4` 추가 |


### 이슈 1. mediamtx.yml 마운트 시 RTSP 스트림 차단

#### 증상

`mediamtx.yml`을 docker-compose에 볼륨 마운트한 직후, mock-cctv(FFmpeg)가 MediaMTX에 스트림을 올리지 못했습니다.

```
[out#0/rtsp @ ...] Could not write header: Server returned 400 Bad Request
```

MediaMTX 로그에서는 다음 메시지가 출력됐습니다.

```
[RTSP] [conn ...] closed: path '1' is not configured
```

#### 원인

`mediamtx.yml`에 `paths:` 섹션이 없으면 기본 path 허용 설정이 적용되지 않아, 모든 path가 차단됩니다. 마운트 전에는 MediaMTX 내부 기본값으로 동작하지만, 빈 설정 파일을 마운트하는 순간 기본값이 무시됩니다.

#### 해결

`mediamtx.yml`에 `paths: all_others:` 를 추가해 명시적으로 모든 path를 허용합니다.

```yaml
webrtcAdditionalHosts:
  - <EC2 DATA 도메인>

paths:
  all_others:
```

`all_others`는 MediaMTX에서 미리 정의되지 않은 모든 path에 기본 설정을 적용하는 와일드카드 키입니다. 아무 값 없이 키만 선언해도 허용 상태가 됩니다.


### 이슈 2. nginx SPA fallback이 HLS 세그먼트를 가로챔

#### 증상

HLS 재생 시 `.m3u8`, `.mp4` 파일 요청이 HTTP 200 응답을 받는데, 응답 본문이 영상 데이터가 아닌 `index.html`이어서 영상이 재생되지 않았습니다.

#### 원인

nginx의 SPA fallback 설정이 문제였습니다.

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

`try_files`는 파일이 존재하지 않으면 `/index.html`을 반환합니다. HLS 세그먼트 파일은 nginx 로컬에 없기 때문에, MediaMTX로 프록시되어야 할 요청이 SPA fallback에 걸려 `index.html`이 반환됐습니다.

추가로, nginx HLS location 패턴에 `.mp4`가 누락되어 있었습니다. MediaMTX의 **Low-Latency HLS(기본값)** 는 세그먼트 형식으로 `.mp4`를 사용합니다.

| 변형 | 세그먼트 형식 |
|---|---|
| `mpegts` | `.ts` |
| `fmp4` | `.mp4` |
| `lowLatency` (기본값) | `.mp4` |

#### 해결

nginx.conf의 HLS location 패턴에 `.mp4`를 추가해 SPA fallback보다 먼저 매칭되도록 했습니다.

```nginx
location ~ ^/[^/]+/.*\.(m3u8|ts|mp4)$ {
    proxy_http_version 1.1;
    proxy_pass         http://$EC2_DATA_HOST:8888;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;

    add_header Access-Control-Allow-Origin * always;
}
```

nginx는 `location ~` (정규식)이 `location /` (prefix)보다 우선순위가 높으므로, HLS 세그먼트 요청은 SPA fallback에 도달하기 전에 MediaMTX로 프록시됩니다.


## 성공했어요ㅜㅜㅜ

![CCTV 스트리밍 화면](/assets/img/posts/2026-03-24-birdybuddy-webrtc-to-hls/1.png)
*CCTV 스트리밍 화면*

---

## 레퍼런스

- [WebRTC CCTV 스트리밍 트러블슈팅: nginx 프록시부터 ICE 연결 실패까지]({% post_url 2026-03-24-birdybuddy-webrtc-troubleshooting %})
- [MediaMTX 공식 문서](https://github.com/bluenviron/mediamtx)
