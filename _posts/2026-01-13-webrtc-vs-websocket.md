---
title: "WebRTC와 WebSocket"
date: 2026-01-13 09:00:00 +0900
categories: [Tech, Web]
tags: [WebRTC, P2P, Signaling, Kurento, WebSocket, Streaming, Architecture, Network]
toc: true 
comments: true
image: /assets/img/posts/2026-01-13-webrtc-vs-websocket/2.png
description: "WebRTC의 기본 개념과 P2P 통신의 한계를 극복하기 위한 미디어 서버(Kurento) 도입 배경을 정리했습니다. 또한 WebRTC와 WebSocket의 역할 차이, 그리고 시그널링 과정에서의 데이터 흐름을 상세히 설명합니다."
---

## WebRTC란?

**WebRTC(Web Real-Time Communication)**는 이름 그대로 **웹 브라우저 간에 플러그인 없이 실시간으로 영상, 음성, 데이터를 주고받게 해주는 기술 표준**이다.

기술적으로는 **미디어 엔진**이 브라우저에 내장되어 있어, 개발자는 HTML5 API만으로 카메라와 마이크에 접근하고 **P2P(Peer-to-Peer)** 통신을 구현할 수 있다. 줌(Zoom)이나 구글 미트(Google Meet) 같은 화상 회의 서비스의 기반이 되는 기술이기도 하다.


## 비유하자면,

WebRTC의 핵심은 **서버를 거치지 않는 P2P 직접 통신**이다. 하지만 여기엔 모순이 있다. 

*서로 "누군지, 어디 사는지(IP)" 모르는 상태에서 어떻게 직접 연결할까?* 

그래서 **시그널링 서버(Signaling Server)**가 필요하다. 이를 '소개팅'에 비유하면 이해가 쉽다.

1.  **주선자 (Signaling Server):** 철수(A)와 영희(B)는 서로 연락처를 모른다. 철수가 주선자에게 "영희랑 통화하고 싶어, 내 번호는 010-XXXX야"라고 쪽지를 준다.
2.  **정보 교환 (Exchange):** 주선자는 영희에게 쪽지를 전해주고, 영희의 번호도 받아서 철수에게 전해준다.
3.  **직접 연결 (P2P):** 연락처를 교환한 철수와 영희는 이제 주선자 없이 **둘이서 직접** 영상 통화를 한다.

즉, WebRTC는 **"서버를 통해 연락처만 교환하고, 실제 무거운 영상 데이터는 둘이서 직접 주고받는 기술"**이다.


## 3단계 Flow

![WebRTC Architecture](/assets/img/posts/2026-01-13-webrtc-vs-websocket/1.png)
*WebRTC Architecture*

### Step 1. 시그널링 (Signaling)
서로의 미디어 스펙과 네트워크 정보를 교환하는 단계다. WebRTC 표준에는 "어떻게 교환하라"는 규정이 없어, 개발자가 편한 방식(WebSocket, MQTT 등)을 사용한다.

* **SDP (Session Description Protocol):** "나는 H.264 코덱을 지원해" 같은 미디어 사양 정보.
* **ICE Candidate:** "내 IP는 192.168.0.1이고 포트는 5000번이야" 같은 네트워크 경로 정보.

### Step 2. 연결 수립 (Connection)
정보 교환이 끝나면 브라우저 내부 엔진이 NAT(공유기 환경) 방화벽을 뚫고 최적의 경로를 찾아 연결을 수립한다. STUN/TURN 서버를 활용한다.

### Step 3. 미디어 송수신 (Streaming)
연결된 파이프를 통해 실제 영상과 음성 데이터(RTP 패킷)가 실시간으로 스트리밍된다.


## 왜 미디어 서버(Kurento)가 필요한가?

WebRTC는 기본적으로 **1:1 직거래(P2P)** 기술이다. 하지만 **N:M (다자간 소통)**이 필요한 경우 문제가 발생한다.

### P2P Mesh 구조의 한계
만약 5명이 대화한다면, 내 컴퓨터는 나머지 4명에게 각각 영상을 보내야 한다. 즉, 업로드에 4배 부하가 걸린다. 인원이 늘어날수록 클라이언트 PC와 네트워크가 버티지 못한다.

### Kurento 도입
중간에 중계소 역할을 하는 **미디어 서버(Kurento)**를 두어 부하를 줄일 수 있다.

* **Client:** 서버에게 영상을 **한 번만** 보낸다.
* **Server (Kurento):** 받은 영상을 복제하여 나머지 4명에게 뿌려준다.

실제 개발 시에는 크게 **시그널링(Signaling)**과 **미디어(Media)** 두 단계로 나뉜다.
1.  **세션 서버 (Spring Boot)**가 "연결해!"라고 명령(Signaling)만 내린다.
2.  **미디어 서버 (Kurento)**가 실제 무거운 데이터를 받아서 중계한다.


## 챗봇(텍스트 채팅)에도 WebRTC가 사용되나?

**아니요, 일반적으로는 사용하지 않습니다.**

WebRTC에도 `DataChannel`이라는 기능이 있어 텍스트나 파일을 보낼 수 있지만, 단순한 텍스트 채팅(Chatbot 포함)은 **WebSocket**이나 **HTTP**만으로도 충분히 빠르고 효율적이다.

WebRTC는 연결 수립 과정이 복잡하고 무겁기 때문에, **"실시간성"이 극도로 중요한 대용량 미디어(영상/음성/화면공유)** 전송에 특화되어 있다. 따라서 보통 **채팅은 WebSocket**으로, **화상 통화는 WebRTC**로 기술을 분리하여 구현한다.


## WebSocket이랑 뭐가 다른가?

| **비교 항목** | **WebSocket** | **WebRTC** |
| --- | --- | --- |
| **아키텍처** | **Client-Server** (양방향 데이터 통신) | **P2P** (브라우저 간 직접 연결) |
| **주요 용도** | 채팅, 실시간 데이터(주식 등), 협업 도구 | 화상 회의, 오디오/비디오 스트리밍 |
| **지연 시간** | 낮음 (데이터 교환에 최적화) | 매우 낮음 (미디어 스트리밍에 최적화) |
| **확장성** | 서버 기반이라 **대규모 확장이 용이**함 | P2P 특성상 소규모에 적합 (대규모 시 미디어 서버 필요) |
| **보안** | SSL/TLS(WSS) 지원 (추가 보안 조치 필요) | **기본적으로 암호화 및 인증 강제** (DTLS/SRTP) |

![WebRTC vs WebSocket](/assets/img/posts/2026-01-13-webrtc-vs-websocket/3.png)
*WebRTC vs WebSocket*

WebSocket은 **신뢰성 있는 데이터(텍스트, 알림)**를 서버와 주고받을 때 사용하고,

WebRTC는 **지연 없는 미디어(영상, 음성)**를 사용자끼리 주고받을 때 사용한다.


## WebSocket과의 관계 및 역할 구분

**"WebRTC를 쓰는데 왜 WebSocket이 또 필요한가?"** WebSocket은 두 가지 서로 다른 목적으로 사용된다.

### 사용자용 WebSocket (Signaling & Chat)
* **연결:** 브라우저 ↔ Spring Boot 서버
* **역할:** P2P 연결을 위한 정보 교환(시그널링) 및 일반 채팅.
    * "나 1번 방 입장할래."
    * "내 SDP(명함) 받아줘."
    * "안녕하세요! (채팅)"

### 미디어 서버용 WebSocket (Control)
* **연결:** Spring Boot 서버 ↔ Kurento 미디어 서버
* **역할:** 미디어 서버 원격 제어 (JSON-RPC).
    * "Kurento야, A유저 마이크랑 B유저 스피커 연결해(Connect)."
    * "A유저 영상 녹화 시작해(Record)."


---

## 레퍼런스

[호기심 많은 이를 위한 WebRTC](https://webrtcforthecurious.com/ko/docs/01-what-why-and-how/)

[WebRTC Demos, Examples, Samples, and Applications: Your Comprehensive Guide](https://www.videosdk.live/developer-hub/webrtc/webrtc-demos-examples-samples-applications-guide)

[WebRTC API - MDN Web Docs - Mozilla](https://developer.mozilla.org/ko/docs/Web/API/WebRTC_API)

[WebSocket vs WebRTC: A Comprehensive Comparison](https://www.apizee.com/websocket-vs-webrtc.php)