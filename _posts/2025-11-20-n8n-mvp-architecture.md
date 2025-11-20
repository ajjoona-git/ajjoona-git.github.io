---
title: "[n8n] MVP 선정하고 아키텍처 설계하기"
date: 2025-11-20 09:00:00 +0900
categories: [해커톤, n8n]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, nc/lc, ai, api, supabase, db, supabase]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
# image: /assets/img/posts/2025-11-20-n8n-checklist/cover.png # (선택) 대표 이미지
---

해커톤 기간 동안 아이디어를 실제 동작하는 서비스로 구현하기 위해 고민했던 MVP 선정 과정과 n8n 기반의 백엔드 아키텍처 설계 전략을 공유합니다.

## 1. MVP 선정: "선택과 집중"
처음 아이디어 회의에서는 회원가입부터 계약, 입주, 퇴거까지 모든 과정을 다루고 싶었습니다. 하지만 2박 3일이라는 시간 제약 속에서 모든 기능을 완성하는 것은 불가능했습니다. 우리는 **"사용자에게 가장 핵심적인 가치를 주는 시나리오 하나만 완벽하게 구현하자"**는 전략을 세웠습니다.

우리가 집중한 핵심 시나리오
사용자가 가장 불안해하는 순간은 **"계약서를 받아들고 도장을 찍기 직전"**입니다. 따라서 다음 3가지 기능을 MVP(Minimum Viable Product)로 확정했습니다.

📄 계약서 꼼꼼히 살펴보기 (Document Analysis): 사용자가 계약서 사진을 찍어 올리면, AI가 내용을 분석하고 체크리스트를 자동으로 채워주는 기능.

🚨 깡통전세 위험도 분석 (Risk Analysis): 매매가와 전세가를 입력하면, 위험도를 계산하여 직관적인 점수와 경고를 보여주는 기능.

e-mail 체크리스트 리포트 (Export): 분석된 결과를 깔끔한 리포트로 정리해 PDF나 메일로 발송해주는 기능.

여기에 RAGFlow를 활용한 **'어미새 챗봇'**을 더해, 사용자가 언제든 궁금한 법률 용어를 물어볼 수 있도록 구성했습니다.

## 2. 아키텍처 설계: 복잡함에서 단순함으로
기능이 정해진 후, 백엔드 로직을 어떻게 구성할지 고민했습니다. 초기에는 기능별로 웹훅을 7개나 만들려고 했지만, 이는 관리가 어렵고 비효율적이었습니다.

우리는 데이터의 성격과 처리 방식에 따라 워크플로우를 3개의 마이크로 서비스(Micro-service) 형태로 통합/재편하는 **'3-Service Architecture'**를 설계했습니다.


| **서비스 명칭**         | **Webhook URL (Endpoint)** | **역할**                                  | **데이터 통신 방식**  |
| ----------------------- | -------------------------- | ----------------------------------------- | --------------------- |
| **① Checklist Service** | `/checklist-service`       | 체크리스트 관리, 위험도 계산, 리포트 발송 | `JSON`                |
| **② Document Service**  | `/document-service`        | 계약서 파일 업로드 및 AI 분석             | `Multipart/Form-Data` |
| **③ Chat Service**      | `/chat-service`            | RAGFlow 챗봇 대화                         | `JSON`                |

🛠️ 3-Service Architecture 상세
### ① Checklist Service (논리 & 계산 담당)
가장 빈번하게 호출되는 가벼운 로직들을 모았습니다. Switch 노드를 라우터(Router)로 활용하여, 프론트엔드에서 보내는 action 값에 따라 분기 처리하도록 설계했습니다.

Webhook URL: /checklist-service

주요 기능 (Switch 분기):

analyze_jeonse: 전세가율 계산 로직 (전세가/매매가 * 100) 및 위험도 판별.

export_report: Supabase에서 데이터 조회 → HTML 생성 → PDF 변환 → 이메일 발송.

toggle_check: 체크리스트 진행 상황 저장.

### ② Document Service (파일 & AI 분석 담당)
파일 업로드와 Vision AI 처리는 리소스를 많이 소모하고 시간이 걸립니다. 이를 별도 서비스로 분리하여 안정성을 확보했습니다.

Webhook URL: /document-service

입력 데이터: Multipart/Form-Data (파일 포함)

프로세스:

AWS S3 노드: Supabase Storage(S3 호환)에 파일 업로드.

Supabase: 파일 메타데이터 저장.

AI Agent (Vision): 계약서 이미지를 읽고 독소조항 및 중요 정보 추출.

Code & DB: 추출된 정보를 바탕으로 체크리스트 상태 자동 업데이트(Upsert).

### ③ Chat Service (대화형 AI 담당)
RAGFlow와의 통신을 전담합니다. 구조는 가장 단순하지만, 서비스의 '지능'을 담당하는 핵심 파트입니다.

Webhook URL: /chat-service

프로세스: 사용자 질문 수신 → RAGFlow API 호출 (검색 및 답변 생성) → 답변 반환.

## 3. n8n 워크플로우 구현 패턴: "Router Pattern"
저희가 사용한 핵심 패턴은 단일 웹훅 진입점 + Switch 분기입니다.

JavaScript

// 프론트엔드 요청 예시
axios.post('/checklist-service', {
  action: 'analyze_jeonse', // 이 action 값에 따라 n8n이 길을 찾습니다.
  salePrice: 300000000,
  deposit: 250000000
});
n8n 내부에서는 Switch 노드가 body.action 값을 확인하여, '위험도 분석 로직'으로 보낼지, '이메일 발송 로직'으로 보낼지를 결정합니다. 이 구조 덕분에 API 엔드포인트 관리가 매우 수월해졌습니다.

## 4. 프론트엔드-백엔드 역할 분담
n8n이 만능은 아닙니다. 보안이 중요하거나 단순한 CRUD는 프론트엔드에서 직접 처리하여 효율을 높였습니다.

로그인/회원가입: n8n을 거치지 않고, React에서 Supabase Auth SDK를 직접 호출하여 보안성 강화.

단순 데이터 조회: 마이페이지의 프로필 조회 등은 프론트에서 DB 직접 조회.

복잡한 로직/외부 연동: 문서 분석, PDF 생성, 메일 발송 등은 n8n Webhook 호출.


### Base Workflow

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
MVP 범위를 명확히 하고, 이를 지원하기 위한 아키텍처를 **'데이터 성격'**에 맞춰 3가지로 구조화하니 개발의 방향이 명확해졌습니다. 이제 남은 해커톤 기간 동안 이 설계도를 바탕으로 **"아기새를 위한 튼튼한 둥지"**를 완성해 보겠습니다.

팀 ASGI 화이팅! 🐣