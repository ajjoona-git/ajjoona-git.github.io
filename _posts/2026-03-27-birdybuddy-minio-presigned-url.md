---
title: "[허수아비] MinIO Presigned URL 서명 불일치 트러블슈팅"
date: 2026-03-27 10:00:00 +0900
categories: [Project, 허수아비]
tags: [Troubleshooting, MinIO, S3, PresignedURL, HTTPS, Nginx, Docker, SpringBoot]
toc: true
comments: true
description: "CCTV 이미지가 브라우저에서 로드되지 않는 문제를 추적했습니다. s3:// 스킴 오류, Mixed Content 차단, 내부 hostname 접근 불가 세 가지 원인을 분석하고, MINIO_SERVER_URL과 nginx 프록시를 조합해 presigned URL 서명 불일치를 해결한 과정을 정리합니다."
---

CCTV 이벤트 로그 화면에서 이미지가 전혀 표시되지 않는 문제가 발생했습니다. 원인을 추적하다 보니 presigned URL 생성, Mixed Content 차단, 서명 불일치라는 세 가지 문제가 중첩되어 있었고, 이를 해결하는 과정에서 MinIO의 서명 검증 구조를 깊이 이해하게 되었습니다.

---

## CCTV 이미지가 로드되지 않는다?!

CCTV 이벤트 로그 화면에서 이미지가 로드되지 않았습니다.

브라우저 콘솔 오류:
```
GET s3://birdybuddy/20260327/cam1_112017.jpg net::ERR_UNKNOWN_URL_SCHEME
```

브라우저가 `s3://`라는 스킴을 알 수 없어 요청 자체를 거부한 것입니다. 이미지 URL이 HTTP(S) 주소가 아닌 내부 S3 경로 그대로 프론트엔드에 전달된 상태였습니다.


## 세 가지 원인

### 전체 이미지 URL 흐름

```
AI worker
  → MinIO에 이미지 업로드 (http://minio:9000)
  → Kafka bird.detection 토픽에 s3://birdybuddy/YYYYMMDD/camN_HHMMSS.jpg 발행

spark-stream-cctv
  → Kafka 구독 → PostgreSQL cctv_frame_ingest 테이블에 s3_path 저장

backend VideoEventConsumer
  → Kafka 구독 → DB에서 CctvFrameIngest 조회
  → StorageService.resolveUrl()로 s3:// 경로를 presigned URL로 변환
  → SSE cctv-alert 이벤트로 프론트엔드에 전송

frontend
  → <img src={s3Path} /> 로 이미지 렌더링
```

> **Presigned URL이란?**
> MinIO(S3)에 저장된 비공개 객체를 인증 없이 일정 시간 동안 접근할 수 있도록 서버에서 서명(HMAC-SHA256)을 포함해 발급하는 임시 URL입니다. 서명에는 요청 시각, 버킷, 경로, **Host 헤더**가 포함되어, 변조 방지를 위해 MinIO가 요청 수신 시 재검증합니다.

### 1. presigned URL이 생성되지 않아 s3:// 경로가 그대로 전달되었다

`StorageService.resolveUrl()`이 실패하면 원본 `s3://` 경로를 fallback으로 반환하는데,
브라우저는 `s3://` 스킴을 알 수 없어 `ERR_UNKNOWN_URL_SCHEME` 오류가 발생했습니다.

### 2. HTTPS 페이지에서 HTTP presigned URL을 불러오면 브라우저가 차단한다

프론트엔드가 `https://`로 서빙되는데 presigned URL이 `http://minio:9000/...`으로 생성되어
브라우저가 Mixed Content로 차단했습니다:

```
Unsafe attempt to load URL http://minio:9000/... from frame with URL https://...
```

### 3. minio:9000은 Docker 내부 호스트명이라 외부 브라우저가 접근할 수 없다

`http://minio:9000`은 Docker 내부 네트워크 호스트명이라 외부 브라우저에서 직접 접근이 불가능합니다.


## 시도한 방법들

### 1. 생성된 URL의 호스트를 공개 주소로 replace

```java
URI internal = URI.create(url);
String internalBase = internal.getScheme() + "://" + internal.getHost() + ":" + internal.getPort();
url = url.replace(internalBase, publicEndpoint);
```

서명이 `minio:9000` 기준으로 생성된 상태에서 호스트만 교체하면
`X-Amz-SignedHeaders=host` 서명 검증 실패가 우려되어 다음 방법으로 전환했습니다.

> 실제로는 `MINIO_SERVER_URL` 설정 시 이 방식이 동작합니다. 최종 해결에서 다시 채택한 방법입니다.

### 시도 2: presigned 전용 MinioClient를 공개 주소로 생성

```java
// MinioConfig.java
@Bean
public MinioClient presignedMinioClient() {
    String presignEndpoint = (publicEndpoint != null && !publicEndpoint.isBlank())
            ? publicEndpoint : endpoint;
    return MinioClient.builder()
            .endpoint(presignEndpoint)
            .credentials(accessKey, secretKey)
            .build();
}
```

```java
// StorageService.java
public StorageService(@Qualifier("presignedMinioClient") MinioClient presignedMinioClient) {
    this.presignedMinioClient = presignedMinioClient;
}
```

`MINIO_PUBLIC_ENDPOINT=https://xxxxxxx.p.ssafy.io`로 설정했는데,
MinIO SDK가 presigned URL 생성 시 내부적으로 해당 엔드포인트에 실제 HTTP 요청을 보냈습니다.
MinIO는 HTTP만 지원하는데 `https://`로 연결을 시도하여 SSL handshake가 실패했습니다.

```
Caused by: io.minio.errors.ErrorResponseException:
The request signature we calculated does not match the signature you provided.
```

백엔드 기동 자체가 실패하여 502 Bad Gateway가 발생했습니다.


## 어떻게 해결했나?

### MinIO는 서명을 공개 도메인 기준으로 재검증한다

MinIO는 `MINIO_SERVER_URL`이 설정되면 presigned URL 검증 시 해당 URL 기준으로 서명을 재계산합니다.
즉 내부 주소(`http://minio:9000`)로 서명을 생성한 뒤 호스트만 공개 주소로 교체해도,
MinIO가 `MINIO_SERVER_URL` 기준으로 서명을 재검증하므로 일치합니다.

이는 MinIO 공식 문서에서 리버스 프록시 환경에서 권장하는 방식입니다.

### 1. nginx가 /birdybuddy/ 요청을 내부 MinIO로 프록시합니다

`infra/ec2-app/nginx/nginx.conf`

```nginx
location /birdybuddy/ {
    proxy_http_version 1.1;
    proxy_pass         http://minio:9000/birdybuddy/;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

- `proxy_set_header Host $host`: 브라우저가 보낸 `xxxxxxx.p.ssafy.io`를 MinIO까지 그대로 전달합니다.
- Mixed Content 해소: `https://xxxxxxx.p.ssafy.io/birdybuddy/...` 경로로 HTTPS 접근이 가능해집니다.

### 2. MinIO에 MINIO_SERVER_URL을 설정합니다

`infra/ec2-app/docker-compose.yml`

```yaml
minio:
  environment:
    - MINIO_SERVER_URL=${MINIO_SERVER_URL}
```

GitLab CI/CD variables(`ENV_EC2_APP`)에 추가합니다:
```
MINIO_SERVER_URL=https://xxxxxxx.p.ssafy.io
```

MinIO가 외부 도메인으로 오는 요청의 Host 헤더를 신뢰하고 서명을 재검증합니다.

### 3. 백엔드가 내부 주소로 서명한 뒤 호스트만 공개 주소로 바꿔 내려줍니다

`backend/config/StorageService.java`

```java
@Value("${MINIO_PUBLIC_ENDPOINT:}")
private String publicEndpoint;

private String getPresignedUrl(String bucketName, String objectPath) {
    String url = minioClient.getPresignedObjectUrl(
            GetPresignedObjectUrlArgs.builder()
                    .bucket(bucketName)
                    .object(objectPath)
                    .method(Method.GET)
                    .expiry(1, TimeUnit.HOURS)
                    .build()
    );
    if (publicEndpoint != null && !publicEndpoint.isBlank()) {
        URI internal = URI.create(url);
        String internalBase = internal.getScheme() + "://" + internal.getHost()
                + (internal.getPort() != -1 ? ":" + internal.getPort() : "");
        url = url.replace(internalBase, publicEndpoint);
    }
    return url;
}
```

backend variables에 추가합니다:
```
MINIO_PUBLIC_ENDPOINT=https://xxxxxxx.p.ssafy.io
```
- `MINIO_PUBLIC_ENDPOINT`는 경로 없이 호스트만 설정해야 합니다.
  - ✅ `https://xxxxxxx.p.ssafy.io`
  - ❌ `https://xxxxxxx.p.ssafy.io/minio-storage` (MinioClient가 경로 포함 endpoint를 거부)


## 해결 후 서명이 일치하는 전체 요청 흐름

```
backend StorageService
  → minioClient (http://minio:9000 기준으로 서명 생성)
  → URL 호스트 교체: http://minio:9000 → https://xxxxxxx.p.ssafy.io
  → presigned URL: https://xxxxxxx.p.ssafy.io/birdybuddy/YYYYMMDD/camN_HHMMSS.jpg?X-Amz-...

브라우저
  → GET https://xxxxxxx.p.ssafy.io/birdybuddy/... (Host: xxxxxxx.p.ssafy.io)

nginx
  → /birdybuddy/ 프록시 (Host 헤더 유지)
  → http://minio:9000/birdybuddy/...

MinIO
  → MINIO_SERVER_URL=https://xxxxxxx.p.ssafy.io 기준으로 서명 재검증 → 일치 → 200 OK
```


## (대안) nginx Host 헤더 스푸핑 방식

`MINIO_SERVER_URL` 없이도 해결할 수 있는 방법이 있습니다.

서명은 `minio:9000` 기준으로 생성되므로, nginx가 MinIO로 전달할 때 Host 헤더를 `minio:9000`으로 강제 변경하면 MinIO 입장에서 서명 생성 시와 동일한 Host를 받게 되어 검증이 통과됩니다.

```nginx
location /birdybuddy/ {
    proxy_pass       http://minio:9000/birdybuddy/;
    proxy_set_header Host minio:9000;  # 공개 도메인이 아닌 내부 주소로 고정
}
```

Host 스푸핑 방식 사용 시, nginx에서 `Host $host`로 설정하면 공개 도메인이 MinIO에 전달되어 서명 검증이 실패합니다.

| | MINIO_SERVER_URL 방식 | Host 스푸핑 방식 |
|---|---|---|
| MinIO 환경 변수 | `MINIO_SERVER_URL` 설정 필요 | 불필요 |
| nginx Host 헤더 | `$host` (공개 도메인 유지) | `minio:9000` (내부 주소로 변조) |
| MinIO 공식 지원 | 리버스 프록시 권장 방식 | 비공식 우회 방법 |


