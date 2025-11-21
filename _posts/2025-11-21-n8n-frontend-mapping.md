---
title: "[n8n] 프론트엔드와 n8n 매핑 테스트"
date: 2025-11-21 09:00:00 +0900
categories: [해커톤, n8n]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, nc/lc, ai, react, backend, frontend]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-21-n8n-frontend-mapping/1.png # (선택) 대표 이미지
---

프론트엔드의 버튼 클릭과 n8n의 로직을 매핑하는 것을 테스트해봤다.

n8n 워크플로우의 논리적 모순(Switch 노드와 If 노드의 충돌)을 해결하고, 프론트엔드에서 'PDF 다운로드'와 '이메일 발송' 버튼을 정확하게 동작시키기 위한 상세 코드 수정했다.

### 1. If 노드 설정 변경

**Switch 노드**는 `action`이 `export_report`일 때만 통과시킨다. 하지만 뒤에 있는 **If 노드**는 `action`이 `email`인지 확인한다. 따라서 `action`을 `export_report`로 보내면 **If 노드**에서 무조건 `False`(PDF 다운로드)로 빠지게 된다.

`*action`이 'email'인가?* 라는 질문은 애초에 Switch 노드 때문에 불가능하다. 그래서 `*export_type`이 'email'인가?* 를 물음으로써 예/아니오로 확실하게 답할 수 있도록 수정했다.

- **노드:** `If` 노드 (PDF 파일 가져오기 뒤에 있는 노드)
- **수정할 설정:**
    - **Value 1 (Left Value):** `{{ $json.body.action }}` → **`{{ $json.body.export_type }}`**
    - **Value 2 (Right Value):** `email` (그대로 유지)

![If Node 재설정](/assets/img/posts/2025-11-21-n8n-frontend-mapping/5.png)
*If Node 재설정*

### 2. `src/components/ChecklistSection.tsx` 수정

버튼 클릭 시 `onAction` 함수에 각각 다른 타입(`export_pdf`, `send_email`)을 전달하도록 핸들러를 수정한다. 즉, 사용자가 누른 버튼이 'PDF'인지 '메일'인지 구분하여 상위 컴포넌트(`App.tsx`)에 알리도록 한다.

```tsx
// src/components/ChecklistSection.tsx

// ... existing imports

// [수정] onAction 타입 정의에 맞게 핸들러 수정
export function ChecklistSection({ onAction, isLoading }: ChecklistSectionProps) {
  // ... existing state

  // 1. PDF 내보내기 버튼 핸들러
  const handleExportPDF = () => {
    // 'export_pdf' 액션으로 호출 -> App.tsx에서 처리
    onAction('export_pdf', { 
      // 필요한 경우 현재 체크리스트 상태 등을 payload로 전달 가능
      phase: activeTab 
    });
  };

  // 2. 이메일 발송 버튼 핸들러
  const handleSendEmail = () => {
    // 'send_email' 액션으로 호출
    onAction('send_email', {
      phase: activeTab
    });
  };

  // ... handleExecuteAction 등 기존 코드

  return (
    <div className="bg-white rounded-xl shadow-md border border-gray-200 p-4 md:p-6">
      <div className="flex flex-col gap-4 mb-6 md:flex-row md:items-center md:justify-between">
        <h2 className="text-foreground">전월세 계약 체크리스트</h2>
        <div className="flex gap-2">
          {/* 3. PDF 버튼에 핸들러 및 로딩 상태 연결 */}
          <Button 
            variant="outline" 
            size="sm" 
            onClick={handleExportPDF} 
            disabled={isLoading['export_pdf']} // 로딩 중 비활성화
            className="rounded-full border-primary/30 text-primary hover:bg-primary/10 flex-1 md:flex-initial"
          >
            <Download className="size-4 md:mr-2" />
            <span className="hidden sm:inline">PDF</span>
          </Button>
          
          {/* 4. 메일 버튼에 핸들러 및 로딩 상태 연결 */}
          <Button 
            variant="outline" 
            size="sm" 
            onClick={handleSendEmail} 
            disabled={isLoading['send_email']} // 로딩 중 비활성화
            className="rounded-full border-primary/30 text-primary hover:bg-primary/10 flex-1 md:flex-initial"
          >
            <Mail className="size-4 md:mr-2" />
            <span className="hidden sm:inline">메일</span>
          </Button>
        </div>
      </div>

      {/* ... Tabs 및 나머지 코드 ... */}
    </div>
  );
}
```

### 3. `src/App.tsx` 수정

n8n으로 보낼 데이터 구조를 구성하고, PDF 파일(Binary) 응답을 처리하는 로직을 추가한다.

```tsx
// src/App.tsx

// [필수] axios import 확인 (없으면 추가)
import axios from "axios"; 

// ... existing imports

export default function App() {
  // ... existing state
  
  // .env에서 Webhook URL 가져오기
  const CHECKLIST_WEBHOOK_URL = import.meta.env.VITE_CHECKLIST_SERVICE_URL;

  const handleAction = useCallback(
    async (actionType: ActionType, payload: any = {}) => {
      // 로딩 상태 시작 (버튼 비활성화용)
      setIsLoading((prev) => ({ ...prev, [actionType]: true }));

      try {
        // ============================================================
        // [수정] 체크리스트 리포트 내보내기 (PDF / Email) 통합 처리
        // ============================================================
        if (actionType === 'export_pdf' || actionType === 'send_email') {
          
          // 1. n8n 'If' 노드 분기를 위한 타입 결정 ('email' vs 'download')
          const exportType = actionType === 'send_email' ? 'email' : 'download';
          
          // 2. 사용자 정보 가져오기 (없으면 테스트용 이메일 사용)
          const userEmail = userProfile?.email || 'test@example.com';

          // 3. n8n Webhook 호출
          const response = await axios.post(
            CHECKLIST_WEBHOOK_URL, 
            {
              // [중요] n8n 'Switch' 노드 통과를 위한 고정 값
              action: 'export_report', 
              
              // [중요] n8n 'If' 노드 분기를 위한 값
              export_type: exportType, 
              
              userEmail: userEmail,
              ...payload
            },
            {
              // PDF 다운로드('download')일 경우 파일(blob)로 받고, 
              // 이메일 전송('email')일 경우 JSON으로 받음
              responseType: exportType === 'download' ? 'blob' : 'json'
            }
          );

          // 4. 응답 결과 처리
          if (exportType === 'download') {
            // [PDF 다운로드 처리]
            // Blob 데이터를 가상 URL로 변환
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            // 파일명 설정 (예: checklist_report_2024-11-21.pdf)
            link.setAttribute('download', `checklist_report_${new Date().toISOString().slice(0,10)}.pdf`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            
            toast.success('리포트가 다운로드되었습니다.');
          } else {
            // [이메일 발송 처리]
            if (response.data && response.data.success) {
              toast.success(`'${userEmail}'로 이메일이 발송되었습니다.`);
            } else {
              toast.error('이메일 발송에 실패했습니다.');
            }
          }
        }
        
        // ... (기존의 다른 action 처리 로직들 유지: login, get_profile 등) ...

      } catch (error) {
        console.error('Action Error:', error);
        toast.error('요청을 처리하는 중 오류가 발생했습니다.');
      } finally {
        // 로딩 상태 종료
        setIsLoading((prev) => ({ ...prev, [actionType]: false }));
      }
    },
    [userProfile] // userProfile 의존성 확인
  );

  // ... renderPageContent 및 return ...
}
```

### 데이터 흐름은 이렇습니다

![workflow](/assets/img/posts/2025-11-21-n8n-frontend-mapping/4.png)
*workflow*

1. **사용자 클릭:** 'PDF' 버튼 클릭
2. **ChecklistSection:** `onAction('export_pdf')` 호출
3. **App.tsx:**
    - Payload 생성: `{ action: 'export_report', export_type: 'download', ... }`
    - n8n Webhook 호출 (responseType: 'blob')
4. **n8n:**
    - **Switch 노드:** `action == 'export_report'` 이므로 **[계약서 분석 보고서 내보내기]** 경로로 진입 (JSON의 outputKey 이름 기준)
    - ... PDF 생성 ...
    - **If 노드:** `export_type == 'email'` 체크 → False (download이므로)
    - **Respond to Webhook (Binary):** 파일 반환
5. **App.tsx:** Blob 응답을 받아 브라우저 다운로드 트리거

### 1차 테스트 결과

![1차 테스트 결과](/assets/img/posts/2025-11-21-n8n-frontend-mapping/3.png)
*1차 테스트 결과*

메인 화면은 잘 떴는데, ‘둥지 짓기 플랜’ 버튼을 누르면 세부 페이지가 하얀 빈 화면으로 떴다. 그리고 Console을 확인하니 이런 오류 메시지가 있었다.

```markdown
`ReferenceError: Download is not defined` 에러는 컴포넌트 내에서 `<Download />` 아이콘을 사용했지만, 상단에서 `import` 하지 않았기 때문에 발생합니다.

빈 화면이 뜨는 이유는 이 에러 때문에 React 렌더링이 중단되었기 때문입니다.

방금 수정한 `src/components/ChecklistSection.tsx` 파일에서 `lucide-react` import 부분을 수정해야 합니다.
```

`src/components/ChecklistSection.tsx` 파일 상단의 import 구문을 다음과 같이 수정해서 해결했다.

```tsx
// 변경 전
// import { MessageSquare } from 'lucide-react';

// 변경 후 
import { MessageSquare, Download, Mail } from 'lucide-react';
```

### 2차 테스트 결과

workflow Executions 탭에서 확인하길, Webhook Trigger Node에서 오류가 발생했다. 그렇다면 트리거에 어떠한 요청이 오긴 했다는 것이므로 반쪼가리 성공이라고 할 수 있겠다.

![2차 테스트 결과](/assets/img/posts/2025-11-21-n8n-frontend-mapping/2.png)
*2차 테스트 결과*

![workflow 실행 오류](/assets/img/posts/2025-11-21-n8n-frontend-mapping/1.png)
*workflow 실행 오류*

n8n에서 수동 트리거를 통해 확인했을 때에는 정상적으로 작동했으므로 클라이언트의 요청을 받아 서버의 응답을 만들어내는 것까지는 성공적으로 확인했다.

다만, 서버의 응답으로 만들어 낸 PDF 파일 등을 다시 클라이언트(Webhook)에 전달하여 화면에 띄울 수 있는지는 확인하지 못했다.
