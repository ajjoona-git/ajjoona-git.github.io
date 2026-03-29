---
title: "[둥지] Supabase와 n8n 연결해서 메일로 보내봅시다"
date: 2025-11-19 09:00:00 +0900
categories: [Project, 둥지]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, Supabase, PostgreSQL, Automation]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-19-n8n-checklist/cover.png # (선택) 대표 이미지
description: "n8n 워크플로우를 통해 Supabase 데이터를 조회하고, HTML 리포트를 생성하여 Gmail로 발송하는 자동화 로직을 구현합니다."
---

Gemini 3 출시 기념, 나의 멘토 Gemini와 함께 n8n + Supabase + 프론트엔드 (React) 연결까지 테스트해봤다.

사용한 프롬프트는 다음과 같다. 프롬프트와 함께 우리의 기획서와 프론트엔드 코드를 함께 제공했다.

> 집 계약을 처음하는 사회초년생을 위한 임대차계약 체크리스트 및 챗봇 서비스, '둥지: 집 찾는 아기새'를 기획했어. 해당 서비스는 AI 노코드, MCP 해커톤에서 개발할거야. n8n, RAGFlow를 백엔드 메인으로 해서 개발할 거야. 데이터베이스가 필요하다면 Supabase를 활용할 계획이야. 기획서와 프론트코드를 참고해서, n8n 워크 플로우를 어떻게 설계해야 할 지 조언해줘. 모든 기능을 구현하기에 앞서, 다음 기능을 구현해보면서 n8n의 노드 설계와 supabase, 프론트 연결 등을 테스트해보려고 해. 테스트해볼 기능은 DB(SUPABASE)의 체크리스트 테이블에서 해당 사용자의 체크 여부를 받아오고, 체크리스트 내용을 PDF로 내보내기 및 해당 PDF를 메일로 보내는 기능이야. n8n을 중심으로 어떻게 설계해야 하는지 단계별로 상세히 알려줘
> 

# **"체크리스트 데이터 조회 -> PDF 생성 -> 이메일 발송"**

## Step 1. Supabase 데이터베이스 설계

### 1-1 테이블 만들기

**체크리스트 진행 상황(`checklist_progress`)** 테이블을 만든다.

Supabase 프로젝트 대시보드에 접속, 사이드바 메뉴 중 **SQL Editor** 아이콘(터미널 모양 `>_`)을 클릭한다.

사용자의 이메일과 체크리스트 항목 ID, 체크 여부를 저장하는 테이블 `checklist_progress`을 만들기 위해, SQL 코드를 작성하고 우측 하단의 RUN 버튼을 클릭한다.

![SQL Editor 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/29.png)
*SQL Editor 실행 결과*

### 1-2 RLS 설정

외부(프론트엔드, n8n)에서 접근할 수 있도록 RLS(Row Level Security, 행 수준 보안)를 설정

해커톤 초기 단계이고 n8n과 프론트엔드 연결 테스트가 목적이므로, 복잡한 인증 정책보다는 **"일단 모든 요청을 허용"**하는 정책을 설정하여 통신 오류를 방지하는 것이 좋습니다.

> ⚠️ 주의: 이 설정은 누구나 데이터를 읽고 쓸 수 있게 하므로, 실제 배포 시에는 반드시 Supabase Auth(auth.uid())를 연동한 보안 정책으로 수정해야 합니다.
> 

새 쿼리 창에 RLS 활성화 코드를 입력하고 **RUN**을 클릭한다.

![RLS 활성화 코드 실행 화면](/assets/img/posts/2025-11-19-n8n-checklist/28.png)
*RLS 활성화 코드 실행 화면*

## Step 2. n8n 워크플로우 설계

<aside>
💡

[Webhook] -> [Supabase] -> [Code] -> [HTML to PDF] -> [Gmail] -> [Respond to Webhook]

</aside>

### 2-1 Webhook Node (시작점)

프론트엔드에서 "이메일 보내기" 버튼을 눌렀을 때 신호를 받는 문입니다.

- **HTTP Method:** `POST`
- **Path:** `send-checklist-pdf` (원하는 이름으로 설정)
- **Authentication:** 테스트 단계이므로 `None`으로 설정 (보안이 필요하면 나중에 Header Auth 추가)
- **Respond:** `Using 'Respond to Webhook' Node` (마지막에 응답을 직접 제어하기 위함)
- **Test:** 노드를 활성화하고, `Test URL`을 복사해둡니다.

![webhook node 설정](/assets/img/posts/2025-11-19-n8n-checklist/27.png)
*webhook node 설정*

### 2-2 Supabase Node (데이터 조회)

사용자가 어떤 항목을 체크했는지 DB에서 가져옵니다. Supabase의 Get many rows 노드를 선택했다.

- **Credential:** 앞서 확인한 `Project URL`과 `service_role` 키로 새 자격 증명(Credential)을 생성하여 연결합니다.

Supabase에서 설정 > Data API에서 `Project URL`를, API Keys의 Legacy API Keys 탭에서 `service_role` 키를 확인할 수 있다. `service_role`키가 막혀있는 경우, RLS 무시 설정(Step 1-2)을 했는지 확인하고, Reveal 버튼을 눌러 복사한다.

![Supabase Settings > Data API](/assets/img/posts/2025-11-19-n8n-checklist/26.png)
*Supabase Settings > Data API*

![Supabase Settings > API Keys > Legacy API Keys](/assets/img/posts/2025-11-19-n8n-checklist/25.png)
*Supabase Settings > API Keys > Legacy API Keys*

두 값을 Create New Credential 페이지에 붙여넣고 Save한다. 아래 사진처럼 초록색 “Connection tested successfully”가 뜨면 잘 연결된 거다.

![Supabase Credential 설정](/assets/img/posts/2025-11-19-n8n-checklist/24.png)
*Supabase Credential 설정*

나머지 파라미터들을 설정한다.

- **Resource:** `Database`
- **Operation:** `Get Many` (여러 행 가져오기)
- **Table:** `checklist_progress`
- **Return All:** `True` (또는 Limit을 100 정도로 넉넉히 설정)
- **Filters:**
    - `user_email` **Equal** `{{ $json.body.userEmail }}`
    - (Webhook으로 들어오는 Body에 `userEmail`이 있다고 가정합니다)

![Supabase Node 설정](/assets/img/posts/2025-11-19-n8n-checklist/23.png)
*Supabase Node 설정*

### 2-3 Code Node (데이터 병합 및 HTML 생성)

DB에는 단순히 `item_id`와 `is_checked` 상태만 저장되어 있습니다. 이를 사람이 읽을 수 있는 **제목(Title)과 설명(Description)**으로 바꾸려면, 프론트엔드 코드(`ChecklistSection.tsx`)에 있는 데이터를 n8n 안에도 가지고 있어야 합니다.

아래 코드를 복사해서 Code 노드의 JavaScript(또는 TypeScript) 창에 붙여넣으세요. `ChecklistSection.tsx`의 데이터를 기반으로 작성했습니다.

```jsx
// 1. Webhook에서 받은 사용자 이메일
const userEmail = $node["Webhook"].json.body.userEmail;

// 2. Supabase에서 가져온 체크된 항목들 (checkedItems)
// Supabase 노드에서 데이터가 없으면 빈 배열 처리
const dbItems = items.length > 0 ? items.map(item => item.json) : [];
const checkedIds = new Set(dbItems.filter(i => i.is_checked).map(i => i.item_id));

// 3. 체크리스트 정적 데이터 (ChecklistSection.tsx 내용 복사)
// 실제로는 더 많은 항목이 있지만, 테스트를 위해 일부만 예시로 넣었습니다.
// 필요하면 전체 데이터를 여기에 붙여넣으세요.
const checklistData = {
  before: [
    { id: 'b1', title: '매매가격 확인하기', desc: '국토교통부 실거래가 조회로 깡통전세 예방' },
    { id: 'b2', title: '보증보험 가입 가능 여부 확인하기', desc: 'HUG/SGI 가입 가능 여부 확인' },
    { id: 'b3', title: '선순위 권리관계 확인하기', desc: '등기부등본 갑구/을구 확인' }
  ],
  during: [
    { id: 'd1', title: '임대인 확인하기', desc: '신분증 진위 여부 및 소유자 일치 확인' },
    { id: 'd4', title: '계약 내용 꼼꼼히 확인 및 작성하기', desc: '표준 임대차 계약서 사용 및 필수 항목 확인' }
  ],
  after: [
    { id: 'a3', title: '전입신고하여 대항력 확보하기', desc: '잔금 지급 즉시 주민센터 방문 또는 정부24 신고' },
    { id: 'a8', title: '임대차 신고하기', desc: '보증금 6천만원 초과 또는 월세 30만원 초과 시 의무' }
  ]
};

// 4. HTML 생성 (CSS 스타일 포함)
const date = new Date().toLocaleDateString('ko-KR');
let html = `
<html>
<head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
  body { font-family: 'Noto Sans KR', sans-serif; padding: 40px; color: #333; }
  h1 { color: #83AF3B; text-align: center; margin-bottom: 10px; }
  .subtitle { text-align: center; color: #666; margin-bottom: 40px; }
  .section-title { color: #22909D; border-bottom: 2px solid #22909D; padding-bottom: 10px; margin-top: 30px; }
  .item { padding: 12px 0; border-bottom: 1px solid #eee; }
  .checkbox { display: inline-block; width: 20px; font-size: 18px; color: #ccc; }
  .checkbox.checked { color: #83AF3B; font-weight: bold; }
  .title { font-size: 16px; font-weight: bold; }
  .desc { font-size: 12px; color: #888; display: block; margin-top: 4px; margin-left: 25px; }
  .footer { margin-top: 50px; text-align: center; font-size: 12px; color: #aaa; }
</style>
</head>
<body>
  <h1>둥지: 집 찾는 아기새</h1>
  <p class="subtitle">임대차 계약 안전 점검 리포트 (${date})</p>
  <p><strong>사용자:</strong> ${userEmail}</p>
`;

const phaseNames = { before: '계약 전', during: '계약 중', after: '계약 후' };

for (const [phase, list] of Object.entries(checklistData)) {
  html += `<h2 class="section-title">${phaseNames[phase]} 단계</h2>`;
  
  list.forEach(item => {
    const isChecked = checkedIds.has(item.id);
    const checkMark = isChecked ? "☑" : "☐";
    const checkClass = isChecked ? "checked" : "";
    
    html += `
      <div class="item">
        <span class="checkbox ${checkClass}">${checkMark}</span>
        <span class="title">${item.title}</span>
        <span class="desc">${item.desc}</span>
      </div>
    `;
  });
}

html += `
  <div class="footer">
    본 리포트는 '둥지' 서비스를 통해 생성되었습니다.<br>
    안전한 계약 되세요!
  </div>
</body>
</html>
`;

// 5. 다음 노드로 HTML 전달
return [{ json: { html: html, email: userEmail } }];
```

![Code Node 설정](/assets/img/posts/2025-11-19-n8n-checklist/22.png)
*Code Node 설정*

### 2-4 HTML to PDF Node (또는 대체재)

생성된 HTML을 PDF 파일로 변환합니다. `HTML to PDF` 노드를 연결하고 `Content` 속성에 `{{ $json.html }}`을 매핑하세요.

Create New Credential 에서 API Key를 추가해야 한다. API Docs 링크를 타고 들어가 로그인/회원가입 후 API Key 발급을 받으면 확인할 수 있다.

![PDF Munk > API Keys](/assets/img/posts/2025-11-19-n8n-checklist/21.png)
*PDF Munk > API Keys*

![HTML to PDF Credential 설정](/assets/img/posts/2025-11-19-n8n-checklist/20.png)
*HTML to PDF Credential 설정*

- **HTML Content**: `{{ $json.html }}`

![HTML to PDF Node 설정](/assets/img/posts/2025-11-19-n8n-checklist/19.png)
*HTML to PDF Node 설정*

**💡 추천:** 해커톤 환경에서는 서버 세팅 문제로 기본 `HTML to PDF` 노드가 실패할 확률이 높습니다.
가장 빠르고 확실한 방법은 **[Gmail 노드]**에서 **이메일 본문(Body) 타입을 'HTML'로 설정**하고, PDF 첨부 대신 **HTML을 메일 본문에 바로 넣어서 보내는 것**입니다. 이 방법은 Credential 고민도 없고 한글 폰트 깨짐 문제도 피할 수 있어 가장 추천합니다.

**💡 PDF 한글 폰트:** n8n의 `HTML to PDF` 노드 사용 시 한글이 깨질 수 있습니다. HTML `<head>` 태그 안에 Google Fonts(예: Noto Sans KR) CDN 링크를 넣거나, 시스템 폰트 설정이 필요할 수 있습니다. 만약 한글이 계속 깨진다면, 해커톤에서는 PDF 대신 **이메일 본문(HTML Body)**에 체크리스트 표를 예쁘게 그려서 보내는 것으로 우회하는 것도 전략입니다.

### 2-5 Gmail Node (이메일 발송)

- **Credential:** Google OAuth2 연결 (미리 Google Cloud Console에서 설정 필요).

Create New Credential 버튼을 누르고, Sign in with Google에서 동의하면 바로 연결된다.

![Gmail Credential 설정](/assets/img/posts/2025-11-19-n8n-checklist/18.png)
*Gmail Credential 설정*

- **Resource:** `Message`
- **Operation:** `Send`
- **To:** `{{ $json.email }}` (Code 노드에서 넘겨준 이메일)
- **Subject:** `[둥지] ${new Date().toLocaleDateString()} 체크리스트 리포트`
- **HTML / Body:**
    - PDF를 만들었다면: "첨부파일을 확인해주세요."
    - PDF가 없다면: `{{ $json.html }}` (HTML 본문 직접 삽입)
- **Attachments:** PDF 생성 노드의 Output Binary Property 이름 (보통 `data`)을 입력.

![Gmail Node 설정](/assets/img/posts/2025-11-19-n8n-checklist/17.png)
*Gmail Node 설정*

### 2-6 Respond to Webhook Node (응답)

프론트엔드가 무한 대기하지 않도록 성공 신호를 보냅니다.

- **Respond With:** `JSON`
- **Response Body:** `{ "success": true, "message": "이메일이 성공적으로 발송되었습니다." }`

![Respond to Webhook Node 설정](/assets/img/posts/2025-11-19-n8n-checklist/16.png)
*Respond to Webhook Node 설정*

### n8n 워크플로우 테스트

이제 실제로 데이터가 흐르는지 확인하기 위해 **Supabase에 가짜 데이터(Mock Data)를 넣고, n8n을 작동시켜 이메일을 받아보는 테스트**를 진행해 보겠습니다.

![Supabase에 mock data 생성](/assets/img/posts/2025-11-19-n8n-checklist/15.png)
*Supabase에 mock data 생성*

만약 Gmail 노드 설정 시 받는 사람(`To`)을 `{{ $json.email }}` 변수로 설정했다면, 실제 테스트할 때는 1단계 SQL에서 `test@example.com` 대신 **본인이 확인 가능한 실제 이메일 주소**로 데이터를 넣어야 메일을 받을 수 있습니다.

```sql
-- 본인 이메일로 테스트 데이터를 다시 넣고 싶다면:
UPDATE checklist_progress 
SET user_email = 'my_real_email@gmail.com' 
WHERE user_email = 'test@example.com';
```

화면 하단의 **Test Workflow** (또는 `Execute Workflow`) 버튼을 클릭하여 **'Waiting for Webhook call'** 상태(대기 상태)로 만듭니다. **Webhook Node**를 더블 클릭하여 엽니다. 노드 설정 창 상단(또는 왼쪽)의 **Test** 탭을 찾거나, 단순히 이 상태에서 **cURL** 요청을 보냅니다. 

```sql
curl -X POST https://ajjoona.app.n8n.cloud/webhook-test/send-checklist-pdf -H "Content-Type: application/json" -d "{\"userEmail\": \"ajjoona@gmail.com\"}"
```

![Webhook Node 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/14.png)
*Webhook Node 실행 결과*

![Supabase Node 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/13.png)
*Supabase Node 실행 결과*

Code Node 에서 **'Error: Referenced node doesn't exist'** 에러 발생했다.

**코드에서는 `Webhook`이라는 이름의 노드를 찾고 있는데, 실제 워크플로우 상의 노드 이름은 `"이메일 보내기" 버튼 클릭 시` 로 변경되어 있어서** 발생하는 문제입니다.

n8n의 Code 노드에서 `$node["노드이름"]`을 사용할 때는 **노드의 이름이 정확히 일치**해야 합니다.

![Error: Referenced node doesn't exist](/assets/img/posts/2025-11-19-n8n-checklist/12.png)
*Error: Referenced node doesn't exist*

![Code Node 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/11.png)
*Code Node 실행 결과*

![HTML to PDF 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/10.png)
*HTML to PDF 실행 결과*

Gmail Node에서 이메일 주소 변수가 잘못 입력되어 에러가 발생했다. `{{ $('Code in JavaScript').item.json.email }}`로 변경해 올바른 이메일 주소를 받아오도록 변경했다.

![Error: **Cannot read properties of undefined (reading 'split')**](/assets/img/posts/2025-11-19-n8n-checklist/9.png)
*Error: *Cannot read properties of undefined (reading 'split')*

이번에는 data가 없다는 에러가 발생했다.

![**Error: This operation expects the node's input data to contain a binary file 'data', but none was found**](/assets/img/posts/2025-11-19-n8n-checklist/8.png)
*Error: This operation expects the node's input data to contain a binary file 'data', but none was found*

**INPUT** 데이터를 보면 `HTML to PDF` 노드가 파일 자체(Binary Data)가 아닌 **다운로드 링크(`pdf_url`)**를 반환하고 있기 때문입니다.

Gmail 노드는 "첨부파일을 보내줘"라고 설정되어 있어 `data`라는 이름의 파일을 찾고 있는데, 현재 데이터에는 링크 주소(텍스트)만 있고 실제 파일이 없어서 에러가 난 것입니다.

**해결 방법: 중간에 파일을 다운로드하는 HTTP Request 노드를 하나 추가하면 됩니다.**

- 연결 순서: `[HTML to PDF]` ➔ `[HTTP Request]` ➔ `[Gmail]`

![HTTP Request Node 설정](/assets/img/posts/2025-11-19-n8n-checklist/7.png)
*HTTP Request Node 설정*

![HTTP Request Node 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/6.png)
*HTTP Request Node 실행 결과*

![Gmail Node 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/5.png)
*Gmail Node 실행 결과*

![Respond to Webhook 실행 결과](/assets/img/posts/2025-11-19-n8n-checklist/4.png)
*Respond to Webhook 실행 결과*

### 테스트 결과

![생성된 PDF 파일](/assets/img/posts/2025-11-19-n8n-checklist/3.png)
*생성된 PDF 파일*

![메일 보내기](/assets/img/posts/2025-11-19-n8n-checklist/2.png)
*메일 보내기*

![n8n 워크플로우](/assets/img/posts/2025-11-19-n8n-checklist/1.png)
*n8n 워크플로우*
