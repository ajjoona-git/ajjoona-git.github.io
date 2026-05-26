---
title: "[SAN] Vite 프록시부터 nginx까지, API 연결 트러블슈팅"
date: 2026-05-06 09:00:00 +0900
categories: [Project, SAN]
tags: [Vite, CORS, SpringSecurity, nginx, Proxy, Troubleshooting, Frontend]
toc: true
comments: true
description: "로컬 개발 환경에서 배포 환경까지, 프론트엔드 API 연결 과정에서 마주친 404, 401, CORS 403 오류의 원인과 해결 과정을 단계별로 정리합니다."
---

`san-frontend` 로컬 개발 서버에서 로그인 요청을 보냈는데 404가 떴습니다. 단순 설정 누락처럼 보였지만, 고치면 고칠수록 다른 오류가 발생했습니다. 로컬 개발 환경부터 배포 환경까지, API 요청이 통과해야 하는 레이어를 하나씩 짚어 가며 해결한 과정을 정리합니다.

## 요약

```
POST http://localhost:5173/api/auth/login → 404 Not Found
```

단계별로 다음 오류들이 순서대로 등장했습니다.

| 단계 | 오류 | 원인 |
|------|------|------|
| 1 | 404 | Vite 프록시 미설정 |
| 2 | 401 | 프록시 경로 rewrite 누락 |
| 3 | CORS 403 | Spring Security가 OPTIONS preflight 차단 |
| 4 | 401 | nginx `proxy_pass` trailing slash 누락 |

---

## 1단계: (404) Vite 프록시가 없었다

`packages/dashboard/vite.config.ts`에 프록시 설정이 없었습니다. Vite dev server는 `/api/*` 경로를 모르기 때문에 자기 자신(5173 포트)에서 처리하려다 404를 반환했습니다.

**해결 — `vite.config.ts`에 프록시 추가**

```ts
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://localhost:8081',
      changeOrigin: true,
    },
  },
},
```


## 2단계: (401) 로컬 백엔드와 경로가 맞지 않았다

프록시를 추가하자 404는 사라졌지만 이번엔 401 Unauthorized가 발생했습니다.

요청 흐름을 추적해 보면 문제가 명확해집니다.

```
프론트: POST /api/auth/login
  → Vite proxy → localhost:8081/api/auth/login  ← 백엔드 실제 경로와 다름
백엔드 실제 경로: /auth/login  (context path에 /api 없음)
```

배포 환경의 nginx는 `/api/` prefix를 유지한 채 백엔드로 전달하지만, 로컬 백엔드(`localhost:8081`)는 `/api` prefix 없이 라우팅됩니다. 이 환경별 차이를 프록시의 `rewrite`로 흡수해야 했습니다.

**해결 — 프록시에 `rewrite` 옵션 추가**

```ts
proxy: {
  '/api': {
    target: 'http://localhost:8081',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
},
```

이후 흐름:

```
프론트: POST /api/auth/login
  → Vite proxy rewrite → localhost:8081/auth/login  ✓
```


## 3단계: (CORS 403) Spring Security가 OPTIONS preflight를 차단했다

`.env.prod-api`를 사용해 로컬 프론트(`localhost:5173`)에서 배포 백엔드(`https://k14a309.p.ssafy.io/api`)를 직접 호출하는 경우에 발생한 문제입니다.

```
OPTIONS https://k14a309.p.ssafy.io/api/auth/login → 403 Forbidden
```

브라우저는 cross-origin 요청 전에 OPTIONS preflight를 먼저 보냅니다. 이때 Spring Security 필터 체인이 이 OPTIONS 요청을 가로채 403을 반환했습니다.

기존 CORS 설정은 `WebConfig.java`에서 `WebMvcConfigurer.addCorsMappings()`를 사용하고 있었습니다.

```java
// WebConfig.java — MVC 레이어에서만 동작
registry.addMapping("/auth/**")
    .allowedOriginPatterns("*")
    ...
```

`SecurityConfig`의 `.cors(withDefaults())`는 `CorsConfigurationSource` 타입의 빈을 찾아 참조하는데, `WebMvcConfigurer` 방식은 이 빈을 등록하지 않습니다. 결과적으로 Spring Security 필터 단계에서 CORS 처리가 되지 않아 OPTIONS 요청이 403으로 차단됩니다.

**해결 — `SecurityConfig`에 `CorsConfigurationSource` 빈을 명시적으로 등록**

```java
// SecurityConfig.java
.cors(cors -> cors.configurationSource(corsConfigurationSource()))

@Bean
public CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOriginPatterns(List.of("*"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("*"));
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}
```

이렇게 하면 Spring Security 필터가 OPTIONS preflight를 가로채기 전에 CORS 헤더를 붙여 200으로 응답합니다.


## 4단계: (배포 환경 401) nginx가 `/api` prefix를 그대로 넘겼다

배포 백엔드(`https://k14a309.p.ssafy.io`)에서 PUBLIC_URLS에 속한 경로(`/auth/check-username`, `/auth/login` 등)도 401을 반환하는 문제입니다.

서버 nginx의 `location /api/` 블록에 `proxy_pass` trailing slash가 없었습니다.

```nginx
# 변경 전 — /api/auth/login이 백엔드에 그대로 전달됨
location /api/ {
    proxy_pass http://localhost:8080;
}
```

nginx에서 `proxy_pass` 뒤에 trailing slash가 없으면 요청 URI 전체(`/api/auth/login`)를 백엔드로 전달합니다. 백엔드 컨트롤러는 `/auth`로 매핑되어 있어 Spring Security의 PUBLIC_URLS(`/auth/login`)와 불일치하고, `anyRequest().authenticated()`가 적용되어 401이 반환됩니다.

**해결 — `proxy_pass`에 trailing slash 추가**

```nginx
# 변경 후 — /api/ prefix가 제거되어 /auth/login으로 전달됨
location /api/ {
    proxy_pass http://localhost:8080/;
}
```

`/api/auth/login` → 백엔드에 `/auth/login`으로 전달 → PUBLIC_URLS 매칭 → 정상 동작.

```bash
sudo nginx -s reload
```

---

## 환경별 API 요청 흐름 정리

세 환경 모두 프론트엔드 코드는 `/api/auth/login`으로 요청을 보냅니다. 차이는 그 요청이 백엔드에 닿기 전에 누가 `/api` prefix를 제거하느냐에 있습니다.

### 로컬 개발 (`pnpm dev`)

`VITE_API_BASE_URL`을 `/api`로 설정하고 Vite dev server를 띄웁니다.

```
브라우저 → POST /api/auth/login
  → Vite dev server (localhost:5173)
  → proxy rewrite: /api/auth/login → /auth/login
  → 로컬 백엔드 localhost:8081/auth/login
```

Vite proxy의 `rewrite` 옵션이 `/api` prefix를 제거합니다. 브라우저 입장에서는 같은 origin(5173)으로 요청하기 때문에 CORS가 발생하지 않습니다.

### 로컬 프론트 + 배포 백엔드 (`pnpm dev --mode prod-api`)

`.env.prod-api`에 `VITE_API_BASE_URL=https://k14a309.p.ssafy.io/api`를 설정하고 로컬 Vite를 띄웁니다.

```
브라우저 → POST https://k14a309.p.ssafy.io/api/auth/login
  → (OPTIONS preflight 먼저 전송)
  → 배포 서버 nginx
  → Spring Security CORS 필터 → 200 OK (preflight 통과)
  → nginx /api/ → 백엔드 localhost:8080/auth/login
```

`localhost:5173`에서 `k14a309.p.ssafy.io`로 보내는 cross-origin 요청이기 때문에 브라우저가 본 요청 전에 OPTIONS preflight를 먼저 보냅니다. 3단계에서 `SecurityConfig`에 `CorsConfigurationSource`를 명시적으로 등록해야 이 preflight가 통과됩니다. prefix 제거는 배포 서버의 nginx가 담당합니다.

### 배포 환경 (빌드 후 nginx)

빌드된 정적 파일을 nginx가 서빙하고, API 요청도 같은 nginx가 받습니다.

```
브라우저 → POST https://k14a309.p.ssafy.io/api/auth/login
  → nginx (same origin, CORS 없음)
  → location /api/ { proxy_pass http://localhost:8080/; }
  → prefix 제거: /api/auth/login → /auth/login
  → 백엔드 localhost:8080/auth/login
```

프론트와 백엔드가 같은 도메인에 있어 CORS가 발생하지 않습니다. nginx의 `proxy_pass` trailing slash가 `/api` prefix를 제거하는 역할을 합니다. trailing slash가 없으면 URI 전체가 백엔드로 전달되어 Spring Security PUBLIC_URLS와 불일치하고 401이 반환됩니다.

---

결국 세 환경에서 `/api` prefix를 제거하는 주체가 각각 다릅니다.

- **로컬 개발**: Vite proxy `rewrite`
- **로컬 + 배포 백엔드**: nginx trailing slash (배포 서버에서 처리)
- **배포**: nginx trailing slash
