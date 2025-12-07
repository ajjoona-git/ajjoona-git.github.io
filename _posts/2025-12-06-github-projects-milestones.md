---
title: "GitHub PR 템플릿 및 마일스톤 설정"
date: 2025-12-06 09:00:00 +0900
categories: [Tech, DevOps]
tags: [GitHub, PM, PRTemplate, Milestone, Automation]
toc: true 
comments: true 
image: /assets/img/posts/2025-12-06-github-projects-milestones/1.png
---

*이전 게시글 보고오기 >>*
{% linkpreview "https://ajjoona-git.github.io/posts/github-issue-setting/" %}

지난 github Issues 라벨과 템플릿을 설정한 것에 이어, 오늘은 Pull requests탭과 Projects 탭을 세팅해봤다.


## 1. PR Template

Pull requests 탭에서 PR을 작성할 때 사용할 템플릿이다.

issue 템플릿과 마찬가지로, `.github/` 폴더 안에 `PULL_REQUEST_TEMPLATE.md` 파일을 생성하면 된다.

```markdown
## 💡 개요 (Overview)
> 이 코드가 '왜' 작성되었는지 한 줄로 파악하게 합니다.

## 📃 작업 내용 (Details)
- [ ] 기능 구현 내용 1
- [ ] 기능 구현 내용 2


## 🔗 관련 이슈 (Links)
- Closes #이슈번호

## 📸 스크린샷 (Screenshots)

## 🎸 기타 사항 & 트러블 슈팅 (Notes)
> "이런 문제가 있어서 이렇게 해결했다"는 고민의 흔적을 남기세요.

## 📚 테스트 (Test)
- [ ] 로컬 환경에서 기능 테스트 완료
- [ ] 기존 기능에 영향 없는지 확인 완료
```

관련 이슈번호를 `Closes`와 함께 작성하면, PR이 merge되고 Close되면 자동으로 언급한 이슈가 Close된다.
즉, **이슈 생성 - 작업 후 커밋 - PR 생성 - 팀원 리뷰 및 승인 - [ PR Merge - PR Close - 이슈 Close ]** 순서로 이루어진다. 그리고 [ PR Merge - PR Close - 이슈 Close ] 해당 과정이 자동화되는 것이다.

![PR 진행 과정 예시](/assets/img/posts/2025-12-06-github-projects-milestones/8.png)
*PR 진행 과정 예시*


## 2. Project 생성

### 2-1. GitHub Projects 생성하기

레포지토리 상단의 `Projects` 탭에서 `New Project`를 클릭한다. 템플릿은 'Board'로 하고 이름은 서비스명인 'Moathon'으로 정했다.

그리고 Column에서 다음 4가지로 수정했다.

![Project column 설정](/assets/img/posts/2025-12-06-github-projects-milestones/7.png)
*Project column 설정*

- **Todo**: 이번 주 해야 할 작업들. Issue가 생성되면 이곳에 둔다.
- **In Progress**: "나 지금 이거 개발 중이야"
- **In Review**: PR(Pull Request)을 보내고 상대방의 리뷰를 기다리는 단계.
- **Done**: 머지(Merge)가 완료된 작업.

### 2-2. 워크플로우 자동화 (Automation)

GitHub Projects 설정(`Workflows` 탭)에서 간단한 자동화를 걸어둘 수 있다. Workflows 탭은 우측 상단에서 확인할 수 있다.

- Item added to project → Status: Todo (이슈를 프로젝트에 추가하면 자동으로 Todo로 감)
- Pull request merged → Status: Done (PR이 머지되면 자동으로 완료 처리)
- Pull request opened → Status: In Review (PR을 열면 자동으로 리뷰 단계로 이동)

이외에도 필요한 자동화 기능들을 자유롭게 선택해 관리할 수 있다.

![Workflows 예시](/assets/img/posts/2025-12-06-github-projects-milestones/6.png)
*Workflows 예시*

### 2-3. 기존 이슈 & PR 가져오기

현재 비어있는 보드에 이미 만들어둔 이슈나 PR을 채워 넣을 수 있다.

**방법 A: 프로젝트 보드에서 직접 추가**

1. 프로젝트 보드 하단의 `+ Add item` 버튼을 클릭한다.
2. 입력창에 `#` 키를 입력하면 레포지토리에 있는 기존 Issue와 PR 목록이 쫘르륵 뜬다.
3. 원하는 것을 클릭하면 Todo나 No Status 컬럼으로 들어온다.

**방법 B: 레포지토리에서 대량으로 보내기**
이슈가 이미 많다면 이 방법이 편하다.

1. 레포지토리 상단의 Issues 탭으로 이동한다.
2. 프로젝트에 넣고 싶은 이슈들을 **체크박스(✅)**로 다중 선택한다.
3. 우측 사이드바의 Projects 톱니바퀴를 클릭하여, 방금 만든 Moathon 프로젝트를 선택하면 자동으로 보드에 들어간다.


## 3. Milestones 생성

마일스톤은 프로젝트나 비즈니스 진행 과정에서 중요한 단계나 주요 목표 달성을 표시하는 포인트를 의미한다. 예를 들면 계약, 착수, 주요 중간 보고, 결과물 완성, 준공 등 프로젝트의 성공을 위한 중요한 이정표 역할을 한다. 

### 3-1. Milestones 생성하기

Issues 탭에서 `Labels`과 `New issue` 버튼 사이에 있는 `Milestones` 버튼을 클릭한다.

![Issues 탭](/assets/img/posts/2025-12-06-github-projects-milestones/5.png)
*Issues 탭*

이제 `New Milestone` 버튼을 통해 마일스톤을 생성할 수 있다.

우리 프로젝트는 개발기간이 3주이기 때문에 주차별로 계획을 세워 작성했다.

![milestone 생성 예시](/assets/img/posts/2025-12-06-github-projects-milestones/4.png)
*milestone 생성 예시*

![milestones](/assets/img/posts/2025-12-06-github-projects-milestones/3.png)
*milestones*

### 3-2. Projects에 연결하기

마일스톤을 만들었다고 프로젝트 보드에 바로 뜨지 않는다. 보드 설정에서 필드를 켜줘야 한다.

1. Projects 화면으로 돌아가서 우측 상단의 Settings -> Fields 메뉴로 들어간다.
2. Milestone 필드가 있는지 확인합니다. 
3. 없다면 `+ New field` 말고, 이미 있는 시스템 필드 중 Milestone을 켜거나, GitHub Project는 기본적으로 연동되므로 뷰 설정을 본다.
4. 보드 화면에서 View 1 옆의 화살표(▼)를 누르고 **Swimlanes**의 **Group by**를 **Milestone**으로 바꾼다. 

![Group by: Mileston 설정](/assets/img/posts/2025-12-06-github-projects-milestones/2.png)
*Group by: Mileston 설정*

이제 Todo/In Progress가 마일스톤 별로 층층이 나뉘어서 보여서 일정을 한눈에 볼 수 있다.

![마일스톤 별로 정렬된 Project](/assets/img/posts/2025-12-06-github-projects-milestones/1.png)
*마일스톤 별로 정렬된 Project*

---

이제 GitHub의 **행정(Project/Issue)과 도구(Milestone)** 세팅이 완벽하게 끝났다!

코드 짜러 가자!