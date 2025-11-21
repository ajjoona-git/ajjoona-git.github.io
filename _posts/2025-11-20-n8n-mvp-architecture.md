---
title: "[n8n] MVP 선정하고 아키텍처 설계하기"
date: 2025-11-20 09:00:00 +0900
categories: [해커톤, n8n]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, nc/lc, ai, api, supabase, db, supabase]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-20-n8n-mvp-architecture/3.png # (선택) 대표 이미지
---

앞서 피그마로 디자인한 프로토타입을 실제 동작하는 서비스로 구현하기 위해 고민했던 MVP 선정 과정과 n8n 기반의 백엔드 아키텍처 설계 전략을 공유합니다.

## 1. MVP 선정: "선택과 집중"

사용자가 가장 불안해하는 순간은 **"계약서를 받아들고 도장을 찍기 직전"**이다. 매물을 확정했다는 가정 하에, 계약을 하려면 필요한 서류와 확인해야 할 사항들을 위주로 체크리스트를 구성했다. 그중에서도 자동화가 가능한 기능을 우선적으로 n8n 워크플로우 구현 테스트를 해보기로 했다. 따라서 다음 3가지 기능을 MVP(Minimum Viable Product)로 확정했다.

1. 📄 **계약서 꼼꼼히 살펴보기**: 사용자가 계약서 사진을 찍어 올리면, AI가 내용을 분석하고 분석 결과 리포트를 PDF나 메일로 발송해주는 기능.

2. 🚨 **깡통전세 위험도 분석**: 매매가와 전세가를 입력하면, 주변 시세와의 비교를 통해 위험도를 계산하여 직관적인 점수와 경고를 보여주는 기능.

3. **체크리스트 리포트**: 체크리스트 목록과 진행 상황을 깔끔한 리포트로 정리해 PDF나 메일로 발송해주는 기능.

여기에 RAGFlow를 활용한 **'어미새 챗봇'**을 더해, 사용자가 언제든 궁금한 법률 용어를 물어볼 수 있도록 구성했습니다.


## 2. 아키텍처 설계
각자 기능을 하나씩 맡아서 n8n 워크플로우를 테스트해보았다. 성공한 기능도, 보완이 필요한 기능도 있었다. 
성공한 기능과 위에서 선정한 MVP 기능을 중심으로 *트리거 역할을 할 Webhook URL을 어떻게 나눌 것인지*, *세부적인 분기 처리는 어떻게 할 것인지*에 대해 고민해봤다.

각자 테스트한 워크플로우는 Webhook Node에서 URL에 POST 요청을 보내는 방식으로 트리거가 설정되어 있었다. 이것들을 하나로 합치는 과정에서 기능별 워크플로우를 병렬로 나열하는 방법도 고려해보았고, 하나의 master Webhook URL을 설정하고 Switch Node를 활용해 분기처리하는 방법도 고려해봤다.

우리는 데이터의 성격과 처리 방식에 따라 워크플로우를 3개의 마이크로 서비스(Micro-service) 형태로 통합/재편하는 **'3-Service Architecture'**를 설계했다.


| **서비스 명칭**         | **Webhook URL (Endpoint)** | **역할**                                  | **데이터 통신 방식**  |
| ----------------------- | -------------------------- | ----------------------------------------- | --------------------- |
| **① Checklist Service** | `/checklist-service`       | 체크리스트 관리, 위험도 계산, 리포트 발송 | `JSON`                |
| **② Document Service**  | `/document-service`        | 계약서 파일 업로드 및 AI 분석             | `Multipart/Form-Data` |
| **③ Chat Service**      | `/chat-service`            | RAGFlow 챗봇 대화                         | `JSON`                |

### 🛠️ 3-Service Architecture 상세

#### ① Checklist Service (논리 & 계산 담당)
가장 빈번하게 호출되는 가벼운 로직들을 모았다. Switch 노드를 라우터(Router)로 활용하여, 프론트엔드에서 보내는 action 값에 따라 분기 처리하도록 설계했다.

- Webhook URL: `/checklist-service`

- 주요 기능 (Switch 분기):
  - `analyze_jeonse` 깡통전세 위험도 분석: 전세가율 계산 로직 및 위험도 판별.
  - `export_report` 리포트 발송: Supabase에서 데이터 조회 → HTML 생성 → PDF 변환 → 이메일 발송.
  - `toggle_check`: 체크리스트 진행 상황 저장.

#### ② Document Service (파일 & AI 분석 담당)
파일 업로드와 Vision AI 처리는 리소스를 많이 소모하고 시간이 걸린다. 이를 별도 서비스로 분리하여 안정성을 확보했다.

- Webhook URL: `/document-service`

- 입력 데이터: Multipart/Form-Data (파일 포함)

- 주요 기능 (Switch 분기):
  - DB 저장: 사용자가 입력한 파일을 S3에 업로드 및 DB 적재.
  - 계약서 정밀 분석: 사용자가 입력한 파일을 OCR, LLM으로 분석하여 결과 리포트를 생성.
  - 둥지 스캔하기: 사용자가 입력한 파일을 스캔하고 관련 체크리스트에 자동 체크.
  - 프론트엔드 Respond: 진행 상황 (예: 처리 중입니다.)

#### ③ Chat Service (대화형 AI 담당)
RAGFlow와의 통신을 전담한다.

- Webhook URL: `/chat-service`

- 프로세스: 사용자 질문 수신 → RAGFlow API 호출 (검색 및 답변 생성) → 답변 반환.

- 주요 기능: 어미새 챗봇, 판례/법률 검색


## 3. n8n 워크플로우 구현 패턴: "Router Pattern"
n8n 워크플로우의 기본 뼈대에 **단일 웹훅 진입점 + Switch 분기** 방식을 도입했다.

```JavaScript

// 프론트엔드 요청 예시
axios.post('/checklist-service', {
  action: 'analyze_jeonse', // 이 action 값에 따라 n8n이 길을 찾습니다.
  salePrice: 300000000,
  deposit: 250000000
});
```

n8n 내부에서는 Switch 노드가 `body.action` 값을 확인하여, '위험도 분석 로직'으로 보낼지, '이메일 발송 로직'으로 보낼지를 결정한다. 이 구조 덕분에 API 엔드포인트 관리가 수월해졌다.

### Base Workflow
3-Service Architecture와 Router Pattern을 토대로 Base Workflow를 생성했다.
각자 개발한 기능을 이곳 base workflow에 합칠 예정인데, 우리 서비스는 하나의 기능의 볼륨이 큰 경우도 있기 때문에 너무 뚱뚱해진다 싶으면 3가지 Webhook을 각각의 Workflow로 독립시키기로 했다.

![base workflow](/assets/img/posts/2025-11-20-n8n-mvp-architecture/3.png)
*base workflow*

![체크리스트](/assets/img/posts/2025-11-20-n8n-mvp-architecture/4.png)
*체크리스트*

![문서 관련 기능](/assets/img/posts/2025-11-20-n8n-mvp-architecture/2.png)
*문서 관련 기능*

![챗봇](/assets/img/posts/2025-11-20-n8n-mvp-architecture/1.png)
*챗봇*

---

### 마치며
MVP 범위를 명확히 하고, 이를 지원하기 위한 아키텍처를 '데이터 성격'에 맞춰 3가지로 구조화하니 개발의 방향이 명확해졌다. 이제 남은 해커톤 기간 동안 이 설계도를 바탕으로 **"아기새를 위한 튼튼한 둥지"**를 완성해 보겠다.

팀 ASGI 화이팅! 🐣