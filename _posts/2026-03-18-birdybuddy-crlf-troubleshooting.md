---
title: "[허수아비] Windows에서 작성한 쉘 스크립트가 Docker 컨테이너에서 죽는 이유 — CRLF 트러블슈팅"
date: 2026-03-18 09:00:00 +0900
categories: [Project, 허수아비]
tags: [Docker, CRLF, Linux, Windows, Shell, Troubleshooting, RTSP, FFmpeg]
toc: true
comments: true
description: "Windows에서 편집한 stream.sh의 CRLF 줄바꿈이 Docker 컨테이너 내부에서 오류를 일으키는 원인을 분석하고, 볼륨 마운트 환경에서도 동작하는 해결 방법을 정리합니다."
---

`docker compose up`을 실행했는데 특정 컨테이너만 계속 재시작을 반복합니다. 로그를 보면 `command not found` 오류가 쏟아지는데, 내가 작성한 명령어가 분명히 맞는데도 실행이 안 됩니다. 허수아비 프로젝트의 `mock-cctv` 컨테이너에서 이 현상이 발생했고, 원인은 예상 밖에 있었습니다.

## 어떤 증상이었나

`birdybuddy-mock-cctv` 컨테이너가 시작되자마자 종료되고, 계속 재시작을 반복했습니다. 로그에서 확인한 오류는 이렇습니다.

```
birdybuddy-mock-cctv    | ./stream.sh: line 2: $'\r': command not found
birdybuddy-mock-cctv    | ./stream.sh: line 8: $'\r': command not found
birdybuddy-mock-cctv    | ./stream.sh: line 10: $'\r': command not found
birdybuddy-mock-cctv    | ========================================
birdybuddy-mock-cctv    | [mock-cctv] 스트리밍 시작
birdybuddy-mock-cctv    |  - 원본 영상: cctv.mp4
birdybuddy-mock-cctv    |  - 타겟 URL: rtsp://media-proxy:8554/1
birdybuddy-mock-cctv    |  - 송출 FPS: 10
birdybuddy-mock-cctv    | ========================================
birdybuddy-mock-cctv    | ./stream.sh: line 17: $'\r': command not found
birdybuddy-mock-cctv    | [in#0 @ 0x7f4b2ddc48c0] Error opening input: No such file or directory
birdybuddy-mock-cctv    | Error opening input file cctv.mp4.
birdybuddy-mock-cctv    | Error opening input files: No such file or directory
birdybuddy-mock-cctv    | ./stream.sh: line 27: -c:v: command not found
birdybuddy-mock-cctv    | ./stream.sh: line 28: -r: command not found
birdybuddy-mock-cctv    | ./stream.sh: line 29: -c:a: command not found
birdybuddy-mock-cctv    | ./stream.sh: line 30: -f: command not found
birdybuddy-mock-cctv exited with code 127
```

`$'\r': command not found` 라는 오류가 여러 줄에 걸쳐 나타나고 있습니다. 스크립트 문법도 맞고, 파일도 존재하는데 왜 실행이 안 되는 걸까요?

## Windows가 줄바꿈을 다르게 저장한다

문제의 원인은 **줄바꿈 문자**입니다.

운영체제마다 텍스트 파일의 줄바꿈을 표현하는 방식이 다릅니다.

| OS | 줄바꿈 방식 | 표현 |
|---|---|---|
| Linux / macOS | LF | `\n` |
| Windows | CRLF | `\r\n` |

Windows 환경에서 VSCode나 메모장으로 `stream.sh`를 편집하면, 자동으로 줄바꿈이 `\r\n`으로 저장됩니다. Linux 컨테이너(bash)는 `\n`만 줄바꿈으로 인식하기 때문에, `\r`을 문자 그대로 명령어의 일부로 읽어버립니다.

이로 인해 두 가지 문제가 동시에 발생했습니다.

### 1. 변수값 오염

```bash
INPUT_FILE="cctv.mp4"
```

이 줄이 `INPUT_FILE="cctv.mp4\r"`로 읽힙니다. `\r`이 붙은 파일명은 실제 파일 시스템에 존재하지 않으므로, ffmpeg는 파일을 찾지 못하고 `No such file or directory`를 뱉습니다.

### 2. 줄 연결 깨짐

ffmpeg 명령어처럼 옵션이 많을 때는 `\`로 줄을 이어 쓰는 경우가 많습니다.

```bash
ffmpeg \
  -i cctv.mp4 \
  -c:v copy \
  ...
```

그런데 `\` 바로 뒤에 `\r`이 붙으면 `\\\r`이 되어 줄 연결이 무효화됩니다. bash는 이어진 명령어 하나로 보지 않고 각 줄을 독립된 명령어로 실행하려 합니다. `-c:v`, `-r`, `-f` 같은 ffmpeg 플래그들이 단독 명령어로 해석되니 당연히 `command not found`가 납니다.

## 왜 Dockerfile에 COPY가 있는데도 문제가 됐을까

*"Dockerfile에서 `COPY stream.sh /app/`을 하는데, 이미지 빌드 시 정상 파일이 들어가지 않나요?"*

맞는 말이지만, 로컬 개발 환경에서는 볼륨 마운트가 이를 덮어씁니다.

`docker-compose.local.yml`에서 `./mock-cctv:/app` 볼륨 마운트를 사용하고 있기 때문에, 컨테이너가 실행될 때 이미지에 COPY된 파일이 아닌 **호스트의 실제 파일**이 `/app`에 마운트됩니다. 호스트가 Windows라면 CRLF가 그대로 컨테이너 안으로 들어오게 됩니다.

```yaml
# docker-compose.local.yml
services:
  mock-cctv:
    volumes:
      - ./mock-cctv:/app   # 호스트의 CRLF 파일이 그대로 사용됨
```

운영 환경에서는 볼륨 마운트 없이 이미지의 COPY된 파일을 쓰기 때문에 문제가 없을 수도 있지만, 로컬과 운영의 동작이 달라지는 것 자체가 문제입니다.

## 해결 — 실행 시점에 변환하기

`.gitattributes`로 줄바꿈을 강제하거나, `dos2unix`를 설치하는 방법도 있지만, 가장 확실한 방법은 **컨테이너 실행 시점에 `\r`을 제거하는 것**입니다. 빌드 이미지 안에 COPY된 파일이든 볼륨 마운트로 들어온 호스트 파일이든, 실행 직전에 한번 정리하므로 어떤 경로로 파일이 들어와도 동일하게 동작합니다.

```dockerfile
# 변경 전
CMD ["/bin/bash", "./stream.sh"]

# 변경 후
CMD ["/bin/bash", "-c", "sed -i 's/\r//' /app/stream.sh && /bin/bash /app/stream.sh"]
```

`sed -i 's/\r//'`는 파일 내의 `\r`을 모두 제거합니다. 이미 LF인 파일에 실행해도 아무 영향이 없으므로, 로컬(볼륨 마운트)과 운영(COPY) 환경 모두 동일하게 적용할 수 있습니다.

## 검증 — 스트림이 제대로 오나?

수정 후 컨테이너가 정상적으로 뜨는 것을 확인했고, 실제 RTSP 스트림도 수신되는지 ffmpeg로 검증했습니다.

```bash
docker run --rm --network host linuxserver/ffmpeg \
  -rtsp_transport tcp -i rtsp://localhost:8554/1
```

```
Input #0, rtsp, from 'rtsp://localhost:8554/1':
  Stream #0:0: Video: h264, 1280x720, 10 fps
  Stream #0:1: Audio: aac, 44100 Hz, stereo
```

1280×720 해상도의 h264 비디오와 aac 오디오 스트림이 정상적으로 수신됩니다.
