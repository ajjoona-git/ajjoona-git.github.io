---
title: "[둥지] n8n과 CODEF API로 등기부등본 자동 발급하기"
date: 2025-11-23 09:00:00 +0900
categories: [Projects, 둥지]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, API, Automation, Backend, CODEF]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-23-n8n-registry/4.png # (선택) 대표 이미지
description: n8n과 CODEF API를 활용하여 등기부등본 조회 및 발급 프로세스를 자동화하고, 수수료 결제 문제를 해결하기 위한 로직을 설계합니다.
---

체크리스트 액션 버튼 중 하나로 ‘등기부등본 발급하기’를 구현해보고자 한다.

사용자가 주소를 비롯해 필요한 정보만 입력하면, 외부 사이트 연결 없이 등기부등본을 자동 발급해준다.

마침 CODEF에서 등기부등본을 열람하고 발급해주는 API를 제공하고 있어서 활용해보기로 했다.

## CODEF API - 등기부등본 열람/발급

### 서버-클라이언트 흐름 (n8n 기반)

**사용자가 주소를 입력**하고 최종적으로 등기부등본(PDF 또는 데이터)을 받는 과정은 어떻게 될까?

**Step 1: 클라이언트 (사용자 입력)**

- 사용자가 '둥지' 웹 서비스에서 주소를 입력한다 (도로명 주소 권장).
- 클라이언트가 n8n의 **Webhook URL**로 주소 데이터를 전송한다 (POST 요청).

**Step 2: n8n (서버/로직 처리)**

- **데이터 전처리:** 사용자가 입력한 주소를 API 규격에 맞게 매핑한다.
- **RSA 암호화:** 명세서에 따라 비밀번호 등 민감 정보는 RSA 암호화가 필요하다. n8n의 **'Code' 노드(JavaScript)**를 사용하여 CODEF에서 발급받은 PublicKey로 비밀번호를 암호화해야 한다.
- **API 요청 (HTTP Request Node):**
    - **Endpoint:** `https://api.codef.io/v1/kr/public/ck/real-estate-register/status` (정식 버전)
    - **Body:** 입력 파라미터를 JSON으로 구성하여 전송한다.

**Step 3: CODEF & 대법원 (외부 연동)**

- CODEF가 대법원 등기소에 접속하여 데이터를 조회한다.
- **추가 인증(2Way) 처리:** 만약 검색된 주소가 여러 개이거나 추가 인증이 필요한 경우, CODEF는 `continue2Way: true`를 반환한다. 이 경우 n8n은 사용자에게 주소 목록(`resAddrList`)을 보여주고 사용자가 선택한 `uniqueNo`로 다시 API를 호출해야 하는 **재귀적 흐름**이 필요할 수 있다.

**Step 4: 결과 반환**

- 최종적으로 `resOriGinalData`(PDF Base64) 또는 `resRegisterEntriesList`(텍스트 데이터)를 받아 클라이언트에 전달한다.

---

### 필요한 데이터 (Input)

사용자에게 받아야 할 필수 데이터와 서버(n8n)에서 관리해야 할 데이터가 나뉜다. 가장 정확한 **'도로명 주소(inquiryType=3)'** 검색을 기준으로 정리했다.

**필수 입력 필드**

- 사용자 input: (비회원 로그인용) 전화번호, 비밀번호, 조회구분, 주소
- `registerSummaryYN=1`등기사항요약 출력

![부동산등기부등본 입력부 객체 (1/2)](/assets/img/posts/2025-11-23-n8n-registry/7.png)
*부동산등기부등본 입력부 객체 (1/2)*

![부동산등기부등본 입력부 객체 (2/2)](/assets/img/posts/2025-11-23-n8n-registry/6.png)
*부동산등기부등본 입력부 객체 (2/2)*

**사용자에게 받아야 하는 데이터 (Input Form)**

1. **주소_시군구 (`addr_sigungu`):** 예) 노원구
2. **주소_도로명 (`addr_roadName`):** 예) 한글비석로
3. **주소_건물번호 (`addr_buildingNumber`):** 예) 62
4. **동 (`dong`) & 호 (`ho`):** 아파트나 다세대 주택(집합건물, `realtyType=1`)인 경우 필수이다.
    - *Tip:* 사용자가 주소를 입력할 때 '다음 주소 API' 같은 서비스를 연동하여 위 데이터를 분리해서 받는 것이 정확도를 높이는 길이다.

**서버(n8n/CODEF)에서 고정/관리하는 데이터**

1. **organization:** `0002` (고정값)
2. **inquiryType:** `3` (도로명 주소로 찾기 권장)
3. **realtyType:** `1` (집합건물-아파트/빌라) 또는 `0` (토지+건물) 등 상황에 맞게 설정
4. **issueType:** `0`(발급), `1`(열람) 중 선택. (단순 확인용이면 '열람' 권장)
5. **ePrepayNo & ePrepayPass:** **(중요) 결제 관련 필수 정보**

---

### 결제는 어떻게 하나요?

CODEF API 비용과 별개로, **대법원 등기소 수수료(열람 700원, 발급 1,000원)는 API 호출 시 실시간으로 결제**되어야 한다.

원래는 사용자가 직접 대법원 등기소 사이트에 접속해서 신청 과정을 거쳐 700원 혹은 1000원을 결제해야 발급을 받을 수 있다. 하지만 이렇게 되면 우리 서비스에서 등기부등본을 발급받아야 하는 당위성이 떨어진다. 서비스의 이유가 사라지는 것이다.

대신, 우리가 결제를 미리 해두고 사용자는 둥지 사이트에 결제를 하는 식으로 운영하면 해결할 수 있다. API가 호출될 때마다 충전해 둔 캐시에서 700원(열람) 또는 1,000원(발급)이 자동으로 차감된다. 즉, 700원을 건별로 카드 결제하는 것이 아니라, 개발자(서비스 운영자)가 대법원 등기소 사이트에서 미리 **전자민원캐시**를 충전해 두어야 한다.

*"선불전자지급수단은 전자민원캐시를 사용합니다."*

![전자민원캐시 구입 화면](/assets/img/posts/2025-11-23-n8n-registry/5.png)
*전자민원캐시 구입 화면*

1. **사전 준비:**
    - 대법원 인터넷등기소 회원가입 및 로그인.
    - **전자민원캐시** 메뉴에서 금액을 미리 충전 (예: 10만 원).
    - 해당 캐시의 **번호(12자리)**와 **비밀번호**를 확보한다.
2. **API 요청 시 입력:**
    - `ePrepayNo`: 확보한 전자민원캐시 번호 (12자리)
    - `ePrepayPass`: 전자민원캐시 비밀번호

---

## n8n 워크플로우

![n8n Workflow](/assets/img/posts/2025-11-23-n8n-registry/4.png)
*n8n Workflow*

### n8n 워크플로우 전체 구조

`Webhook (수신)` → `AI Agent (주소 파싱)` → `Code Node (RSA 암호화)` → `HTTP Request (CODEF API)` → `Database (저장)`

1. Webhook (사용자 입력): 주소(도로명), 전화번호, 비밀번호를 입력받는다.
2. AI Agent (주소 파싱): 입력받은 도로명 주소를 CODE API 규격에 맞는 필드로 분리한다.
3. Code (RSA 암호화): CODEF API 명세에 따라 password를 RSA 암호화한다.
4. HTTP Request (CODEF API 호출): 미리 충전해둔 '전자민원캐시' 정보, 파싱된 주소, 암호화된 비밀번호를 조합하여 요청을 보낸다.
5. Database (결과 저장): API 응답 중에서 추후 분석에 필요한 데이터를 DB에 저장한다.

### AI Agent? Basic LLM Chain?

AI Agent Node에서도 Model만 지정하기 때문에 Basic LLM Chain Node 사용해도 된다.

![Basic LLM Chain Node의 Prompt 설정](/assets/img/posts/2025-11-23-n8n-registry/3.png)
*Basic LLM Chain Node의 Prompt 설정*

**1. Memory가 필요 없는 이유**

**Memory**는 "대화의 맥락(Context)"을 기억해야 할 때 쓴다. (예: 챗봇이 이전 질문을 기억해야 할 때)

사용자가 주소를 던지면, AI가 그걸 분석해서 JSON으로 뱉어내고 끝나는 단발성 작업(One-shot task). 이전 주소를 기억할 필요가 전혀 없기 때문에 Memory는 필요 없다.

**2. Tool이 필요 없는 이유**

**Tool**은 AI가 모르는 정보를 검색하거나(Google Search), 계산을 하거나, 특정 코드를 실행해야 할 때 쓴다.

주소 텍스트를 분석하는 언어 능력만 있으면 된다. "서울특별시 노원구..." 같은 텍스트 패턴은 AI(Model)가 이미 학습한 지식만으로 충분히 분석할 수 있다.

### CODEF API Credential

OAuth2 API 를 선택하고 아래와 같이 값을 입력한다.

| **설정 항목** | **입력값 / 설명** |
| --- | --- |
| **Grant Type** | `Client Credentials` 선택 |
| **Token URL** | `https://oauth.codef.io/oauth/token` (CODEF 표준 토큰 발급 주소) |
| **Client ID** | CODEF 홈페이지에서 발급받은 ID (환경변수 권장: `{{$env.CODEF_CLIENT_ID}}`) |
| **Client Secret** | CODEF 홈페이지에서 발급받은 Secret (환경변수 권장: `{{$env.CODEF_CLIENT_SECRET}}`) |
| **Scope** | `read` (보통 read 입력, 비워둬도 작동할 수 있음) |
| **Auth** | `Body` (Client ID/Secret을 Body로 전송) |

![CODEF Credential 설정 (1/2)](/assets/img/posts/2025-11-23-n8n-registry/2.png)
*CODEF Credential 설정 (1/2)*

![CODEF Credential 설정 (2/2)](/assets/img/posts/2025-11-23-n8n-registry/1.png)
*CODEF Credential 설정 (2/2)*

---

아뿔싸, 로직은 다 짰는데 CODEF API 서비스가 운영하지 않아서 테스트는 하지 못했다.

---

### 레퍼런스

[CODEF API 개발가이드](https://developer.codef.io/products/public/each/ck/real-estate-register)

[전자민원캐시](https://minwon.cashgate.co.kr/myCash.do)

[인터넷 등기소](https://www.iros.go.kr/index.jsp)