---
title: "[둥지] AI Agent와 MCP의 차이, 그리고 n8n 적용기"
date: 2025-11-22 09:00:00 +0900
categories: [Projects, 둥지]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [n8n, Agent, MCP, Backend, Automation]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-22-n8n-aiagent-mcp/2.png # (선택) 대표 이미지
description: AI Agent와 MCP(Model Context Protocol)의 개념적 차이를 이해하고, 이를 둥지 서비스의 핵심 기능인 '둥지 스캔하기'에 적용한 설계를 다룹니다.
---

'둥지: 집 찾는 아기새' 서비스를 기획하며 n8n, Supabase, 그리고 MCP(Model Context Protocol)를 활용해 백엔드 로직을 설계했다. 특히 AI Agent가 외부 도구를 어떻게 호출하고 판단하는지, 그 과정에서 **MCP Client Node**의 역할이 무엇인지에 대한 기술적 정의와 워크플로우 설계 과정을 정리해보았다.

---

## n8n 내 MCP Client Node와 AI Agent Node의 관계

들어가기에 앞서, 내가 원래 알고 있었던 MCP는 ‘표준 규약’이고, AI Agent는 본인이 가진 모델과 툴을 사용해서 답을 도출해내는 AI 였다. 그래서 n8n의 MCP Client Node의 역할과 사용법에 대해 의문이 많이 생겼다.

*“MCP Client는 뭐지?”*

*“MCP 서버를 개발한다는 건 또 무슨 말이지?”*

*"AI Agent가 MCP를 포함하는 상위 개념인가?”*

*…*

가장 먼저 정립해야 했던 개념은 **MCP Client Node**와 **AI Agent Node**의 역할 차이다. 결론부터 말하면, 포함 관계라기보다는 **역할(Role)과 통신 방식(Protocol)의 관계**라고 보는 것이 더 정확하다. 

![AI Agent Node](/assets/img/posts/2025-11-22-n8n-aiagent-mcp/2.png)
*AI Agent Node*

---

## AI Agent: 스스로 판단하는 "두뇌"

**AI Agent**는 단순한 LLM(거대언어모델)을 넘어, **주어진 목표를 달성하기 위해 스스로 생각하고 행동하는 시스템**이다.

워크플로우의 '두뇌' 역할을 한다. 사용자의 자연어 요청을 이해하고, 목표를 달성하기 위해 **어떤 도구를 사용해야 할지 스스로 추론(Reasoning)**하고 **결정**한다.

1. 사용자 질문: "관악구 쑥고개로 123 깡통전세 위험해?"
2. Agent 판단: "이건 단순 대화가 아니라, 실거래가 조회와 위험도 분석 도구가 필요하겠군."
3. 도구 실행: 등기부등본 분석 도구 호출 -> 결과 수집.
4. 최종 답변: 사용자에게 위험도 리포트 제공.

즉, AI Agent는 도구를 "선택하고 사용하는 주체"다.

## MCP (Model Context Protocol): 만능 "연결 표준"

**MCP**는 AI 모델이 외부 데이터나 도구와 소통하기 위한 **개방형 표준 프로토콜**이다. 과거에는 AI에게 '구글 캘린더'를 연결하려면 캘린더 전용 코드를 짜야 했고, '슬랙'을 연결하려면 슬랙 전용 코드를 짜야 했다. 하지만 MCP를 사용하면, **MCP 표준만 맞추면 어떤 도구든 AI에 즉시 갖다 꽂을 수 있게 된다.**

MCP는 크게 두 가지로 나뉜다.

- **MCP Host (Client):** AI 애플리케이션 (예: Claude Desktop, Cursor, 혹은 우리가 만든 '둥지' 챗봇). 도구를 사용하려는 쪽.
- **MCP Server:** 실제 데이터나 기능을 제공하는 쪽 (예: 구글 드라이브, 슬랙, 포스트그레SQL, 로컬 파일 시스템).

n8n의 MCP Client Node는 AI Agent가 사용하는 **'도구(Tool)'** 중 하나다. 외부(MCP Server)에 정의된 기능(함수)이나 데이터 소스를 n8n으로 가져와 실행할 수 있게 해주는 **연결 고리**다. 독자적인 판단 능력은 없으며, Agent의 명령을 수행하고 결과를 반환한다.

1. **User Input:** 사용자가 질문을 던짐.
2. **AI Agent (MCP Host):** 질문을 분석하고 필요한 도구를 찾음. 이때 `list_tools()` 같은 MCP 명령어를 사용.
3. **MCP Protocol:** Host와 Server 간의 표준화된 통신 통로.
4. **MCP Server:** 실제 기능(API 호출, DB 조회 등)을 수행하고 결과를 반환.
5. **AI Agent:** 반환된 결과를 해석하여 최종 답변 생성.

## 물리적 연결과 논리적 정의

AI Agent에게 도구를 쥐여줄 때는 두 가지 설정이 필수적이다.

- **물리적 연결:** 캔버스 상에서 MCP Client Node(또는 다른 툴 노드)를 AI Agent Node의 **`Tools` Input**에 선으로 연결해야 한다.
- **논리적 정의 (Description):** 연결만으로는 부족하다. 해당 도구를 "언제, 어떤 상황에서 사용해야 하는지"에 대한 설명을 **자연어**로 명확히 적어줘야 한다. LLM은 이 설명을 읽고 도구 사용 여부를 판단한다.

## ‘둥지’ 서비스에 어떻게 적용할 수 있을까?

AI Agentic한 서비스이면서 둥지의 MVP로 내세울 수 있는 것이 **‘둥지 스캔하기’** 기능이라고 생각했다. 

둥지 스캔하기는 사용자가 둥지를 처음 접했을 때 실행하는 기능으로, 사용자가 사전에 가지고 있던 계약 관련 서류 (등기부등본, 임대차 계약서, 건축물 대장 등)를 업로드하면, 간단한 분석과 함께 관련 체크리스트 항목을 자동 체크해주는 기능이다.

이를 통해 사용자 맞춤형 체크리스트를 초기화해주고 우리가 어떤 서비스를 제공해주는지 파악할 수 있게 해준다.

이 기능을 AI Agent로 개발한다면, 다음과 같은 기능을 포함할 수 있겠다.

![AI Agent Node Prompt](/assets/img/posts/2025-11-22-n8n-aiagent-mcp/1.png)
*AI Agent Node Prompt*

- **문서 종류 분류**: 등기부등본, 임대차 계약서, 건축물 대장
- **OCR**: 이미지 혹은 PDF 파일에서 텍스트를 추출한다.
- **텍스트 전처리**: 텍스트로 추출한 내용을 정제한다.
- **텍스트 분석**: 문서 종류별로 필요한 내용을 요약/분석한다.
- **DB 저장**: 원본 파일과 분석한 내용을 DB에 저장한다.
- **체크리스트 항목 체크**: 이미 수행한 관련 체크리스트 항목을 추출한다.

---

### 마치며

사용자는 자연어로 입력하고, AI Agent는 필요한 Tool을 알아서 판단하고 연쇄적으로 수행한다. MCP Client는 AI Agent의 Tool로 사용되며, 필요시 MCP Server에게 ‘이 기능 수행해줘’라고 명령을 내린다. MCP Server는 실제 기능을 수행하는 코드가 담긴 서버이다. n8n에서는 MCP 서버와 대화하기 위해 MCP Client Node를 사용하는 것!

---

### 레퍼런스

[Woowahan Tech Blog: AI Agent와 MCP](https://techblog.woowahan.com/22342/)

[Model Context Protocol Docs](https://modelcontextprotocol.io/docs/getting-started/intro)

[Cursor Docs: Building MCP Server](https://docs.cursor.com/ko/guides/tutorials/building-mcp-server#mcp-%EC%84%9C%EB%B2%84%EB%9E%80-%EB%AD%90%EC%95%BC)

[Wikidocs: AI Agent 개념](https://wikidocs.net/286550)