---
title: "[GitHub] Issue 템플릿 설정하기"
date: 2025-11-08 09:00:00 +0900
categories: [프로젝트 - 마자, 기획]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [github, issue, label]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
# image: /assets/img/my-post-banner.png # (선택) 대표 이미지
---

어제 관통 프로젝트의 기획을 시작하면서 한 가지 다짐한 것이 있다면,

## **GitHub의 모든 탭을 사용해보겠다**

는 것.

영운언니랑 짝하면서 핀봇팀 프로젝트를 시작하는 것부터 지켜보았는데, 깃허브에 그렇게 다양한 기능이 있는 줄은 몰랐다. 차근차근 세팅하고 issue - branch - PR까지 이어지는 흐름이 너무 아름다워서 훔치고 싶었다. 그래서 이번 프로젝트에서는 기필코 깃허브를 잘 활용해보리라 다짐했다. 깃허브에 작업을 왜 했고, 어떻게 했고, 모든 workflow가 남으니까, 포트폴리오로서도 더 좋고 앞으로 협업하는 데에도 훨씬 도움이 될 거라고 생각한다.

그 첫 걸음으로, **Issues** 탭을 뜯어보려고 한다.

![Issues](/assets/img/posts/2025-11-08-github-issue-setting/1.png)

---

## 1. Label 설정하기

label은 issues, discussions, projects, PR 까지 관통하는 태그(tag)역할을 한다.
레포지토리에서 필터링해서 확인할 때 요긴하게 사용된다.

프로젝트를 진행하면서 자주 작업할 만한 영역을 기준으로 다음과 같은 초기 label 구성을 마쳤다.
- FE, BE, AI 등 작업에 대한 큰 카테고리를 설정했다.
- fix, feat, refactor, design 등 작업 내용이 어떤 것인지 알 수 있도록 분류했다. (버그 수정, 기능 구현, 코드 구조 변경, 디자인 수정 등)
- docs, chore, question, urgent 등 작업 분류에 속하지 않거나 추가적으로 제기해야 하는 이슈들에 대해서 추가했다.

![label 1](/assets/img/posts/2025-11-08-github-issue-setting/10.png)
![label 2](/assets/img/posts/2025-11-08-github-issue-setting/11.png)

---

## 2. Issue Template 설정하기

Issue 템플릿을 설정하는 방법은 두 가지가 있다.

### 2-1. GitHub에서 "Set up templates"

친절한 GitHub는 yml 파일같은 걸 몰라도 쓸 수 있도록 템플릿 변경 UI를 제공해준다.

레포지토리의 `Settings` > `General` > `Features` > `Issues`의 "Set up templates" 버튼을 누르면 템플릿을 추가/수정할 수 있다.

![settings](/assets/img/posts/2025-11-08-github-issue-setting/2.png)

`Add template` 버튼을 누르면 기본으로 제공해주는 Bug report / Feature request 와 Custom template, 3가지 옵션이 있다.

![add template](/assets/img/posts/2025-11-08-github-issue-setting/3.png)

Bug report / Feature request을 수정해서 사용할 수도, 필요하다면 Custom template으로 새로 만들어서 사용할 수도 있다.

Preview and edit 버튼을 눌러 세부 내용을 수정하고, Propose changes 버튼을 눌러 commit하면 완성된다.

| 항목 | 내용 |
| :-- | -- |
| Template name | 템플릿의 이름 |
| About | 템플릿에 대한 간단한 설명 (템플릿을 선택할 때 이름과 같이 노출된다.) |
| Template comtent | 템플릿 스타일을 markdown 형식으로 작성 |
| (선택) Issue default title | 이슈의 제목 (주로 고정된 말머리를 작성한다. 예: [FIX]) |
| (선택) Assignees | 작업 담당자 |
| (선택) Labels | 작업과 관련된 라벨 |


- 장점: 직관적이고 간편하다
- 단점: 브랜치 관리가 어렵다.

---

자주 사용할 것 같은 label을 중심으로 BUG, FEAT, REFACTOR, DOCS, TASK 다섯 가지의 템플릿을 만들었다.

#### BUG

![Bug issue template](/assets/img/posts/2025-11-08-github-issue-setting/12.png)

```markdown
## #️⃣ 어떤 버그인가요?

> #어떤 버그인지 간결하게 설명해주세요.

## #️⃣ 어떤 상황에서 발생한 버그인가요?

> 버그를 재현할 수 있는 단계를 순서대로 작성해주세요.

## #️⃣ 예상 결과

> 예상했던 정상적인 결과가 어떤 것이었는지 설명해주세요.

## #️⃣ 실제 결과

> 실제로 어떤 결과가 발생했는지 설명해주세요. (스크린샷/로그 첨부)

## 📝 Todo

> 해결을 위해 필요한 작업 목록을 작성헤주세요.
- [ ] TODO
- [ ] TODO
- [ ] TODO

## 🔗 관련 이슈

> 관련된 이슈가 있다면 링크를 남겨주세요. (예: #1, #2)
> 관련 문서, 스크린샷, 또는 예시 등이 있다면 여기에 첨부해주세요
```

#### FEAT

![Feat issue template](/assets/img/posts/2025-11-08-github-issue-setting/4.png)

```markdown
## #️⃣ 어떤 기능인가요?

> 추가하려는 기능에 대해 어떤 기능인지, 왜 필요한지 설명해주세요.

## 📝 Todo

> 구현을 위해 필요한 작업 목록을 작성해주세요.
- [ ] TODO
- [ ] TODO
- [ ] TODO

## 🔗 관련 이슈

> 관련된 이슈가 있다면 링크를 남겨주세요. (예: #1, #2)
```

#### REFACTOR

![Refactor issue template](/assets/img/posts/2025-11-08-github-issue-setting/5.png)

```markdown
## #️⃣ 리팩토링 대상

> 어떤 파일이나 기능의 코드를 개선할 것인지 작성해주세요.

## #️⃣ 왜 필요한가요?

> 왜 이 코드를 리팩토링해야 하는지, 어떻게 개선할 것인지 설명해주세요. (가독성, 성능, 유지보수성 등)

## 📝 Todo

> 구현을 위해 필요한 작업 목록을 작성해주세요.
- [ ] TODO
- [ ] TODO
- [ ] TODO

## 🔗 관련 이슈

> 관련된 이슈가 있다면 링크를 남겨주세요. (예: #1, #2)
```

#### DOCS

![Docs issue template](/assets/img/posts/2025-11-08-github-issue-setting/6.png)

```markdown
## #️⃣ 어떤 문서인가요?

> 어떤 문서를 어떻게 추가/수정할 것인지 설명해주세요.

## 📝 Todo

- [ ] TODO
- [ ] TODO
- [ ] TODO

## 🔗 관련 이슈

> 관련된 이슈가 있다면 링크를 남겨주세요. (예: #1, #2)
```

#### TASK

![Task issue template](/assets/img/posts/2025-11-08-github-issue-setting/7.png)

```markdown
## #️⃣ 어떤 작업인가요?

> 어떤 작업이 필요한지 설명해주세요.

## 📝 Todo

- [ ] TODO
- [ ] TODO
```

---

첫 커밋으로 해당 작업을 남기게 되었는데, 브랜치를 만들고 PR하는 옵션을 선택했음에도 브랜치가 꼬이는 상황이 생겼다. 왜냐하면 `master` 브랜치만 존재하는 상황이었기 때문에 merge PR을 master로 해야만 했다. (약식 git Flow 브랜치 전략을 따르자면 master가 아닌 dev 브랜치에 병합해야 했다.)

![template 저장 후 커밋](/assets/img/posts/2025-11-08-github-issue-setting/8.png)


### 2-2. markdown 또는 yml 파일 생성

레포지토리에 `./github/ISSUE_TEMPLATE/` 폴더를 만들고 yml 또는 md 파일을 추가하는 방법이다.

yaml 문법을 모른다면 어렵게 느껴질 수 있겠지만, 사용자가 직접 코드를 작성하기 때문에 속성을 추가/삭제할 수 있다는 점이 좋다. 특히 yml 파일로 만들면 각 섹션별로 구분된 작성 칸이 있어 더 예쁘고 깔끔하다.

단, Issue 템플릿은 반드시 정해진 디렉토리 경로 (`./github/ISSUE_TEMPLATE/`)에 있어야 하며, 디렉토리 이름은 대문자여야 한다.

- 장점: 세부적으로 설정 가능, 브랜치/커밋 관리 용이
- 단점: 코드로 작성해야 하는 번거로움

---

#### BUG

```yaml
name: "🐞BUG"
description: "버그 리포트 템플릿"
title: "[BUG] "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: "버그 리포트를 작성해주셔서 감사합니다. 아래 양식에 맞춰 상세히 작성해주세요."
  - type: textarea
    id: description
    attributes:
      label: "버그 설명"
      description: "어떤 버그인지 명확하게 설명해주세요."
      placeholder: "예: '로그인 버튼 클릭 시 500 에러가 발생합니다.'"
    validations:
      required: true
  - type: textarea
    id: steps-to-reproduce
    attributes:
      label: "재현 단계"
      description: "버그를 재현할 수 있는 단계를 순서대로 작성해주세요."
      placeholder: |
        1. '...' 페이지로 이동
        2. '...' 버튼 클릭
        3. '...' 에러 확인
    validations:
      required: true
  - type: textarea
    id: expected-behavior
    attributes:
      label: "예상 결과"
      description: "정상적으로 동작했을 때의 결과를 작성해주세요."
      placeholder: "예: '로그인이 성공하고 메인 페이지로 이동합니다.'"
  - type: textarea
    id: actual-behavior
    attributes:
      label: "실제 결과 (스크린샷/로그)"
      description: "현재 발생하는 오류와, 가능하다면 스크린샷이나 콘솔 로그를 첨부해주세요."
  - type: textarea
    id: environment
    attributes:
      label: "환경"
      description: "버그가 발생한 환경을 알려주세요 (OS, 브라우저, 버전 등)"
      placeholder: "예: Windows 11, Chrome 100.0"
  - type: textarea
    id: todo
    attributes:
      label: "📝 Todo"
      description: "해결을 위해 필요한 작업 목록을 작성해주세요."
      placeholder: |
        - [ ] 원인 분석
        - [ ] 코드 수정
        - [ ] 테스트 코드 작성
  - type: input
    id: related-issues
    attributes:
      label: "🔗 관련 이슈"
      description: "관련된 이슈가 있다면 링크를 남겨주세요."
      placeholder: "예: #1, #2"
```

#### FEAT

```yaml
name: "✨FEAT"
description: "새로운 기능 제안 템플릿"
title: "[FEAT] "
labels: ["enhancement", "feature"]
body:
  - type: textarea
    id: description
    attributes:
      label: "기능 설명"
      description: "어떤 기능인지, 왜 필요한지 설명해주세요."
      placeholder: "예: '사용자가 프로필 이미지를 직접 업로드할 수 있는 기능이 필요합니다.'"
    validations:
      required: true
  - type: textarea
    id: details
    attributes:
      label: "작업 상세 내용 (Optional)"
      description: "기능 구현을 위해 고려해야 할 세부 사항이 있다면 작성해주세요."
      placeholder: "예: '이미지 크기 제한', '지원 파일 형식 (jpg, png)' 등"
  - type: textarea
    id: todo
    attributes:
      label: "📝 Todo"
      description: "구현을 위해 필요한 작업 목록을 작성해주세요."
      placeholder: |
        - [ ] API 설계
        - [ ] UI 디자인
        - [ ] 기능 구현
        - [ ] 테스트
  - type: input
    id: related-issues
    attributes:
      label: "🔗 관련 이슈"
      description: "관련된 이슈가 있다면 링크를 남겨주세요."
      placeholder: "예: #1, #2"
```

#### REFACTOR

```yaml
name: "♻️ REFACTOR"
description: "코드 개선 템플릿"
title: "[REFACTOR] "
labels: ["refactor"]
body:
  - type: input
    id: target
    attributes:
      label: "리팩토링 대상"
      description: "어떤 파일이나 기능의 코드를 개선할 것인지 작성해주세요."
      placeholder: "예: 'src/utils/parser.py'의 'parse_data' 함수"
    validations:
      required: true
  - type: textarea
    id: reason
    attributes:
      label: "개선 이유"
      description: "왜 이 코드를 리팩토링해야 하는지 설명해주세요. (가독성, 성능, 유지보수성 등)"
      placeholder: "예: '가독성 향상', '성능 최적화', '중복 코드 제거'"
    validations:
      required: true
  - type: textarea
    id: details
    attributes:
      label: "작업 상세 내용 (개선 방안)"
      description: "어떻게 개선할 것인지 구체적인 방안을 작성해주세요."
      placeholder: "예: '기존 for문을 list comprehension으로 변경'"
  - type: textarea
    id: todo
    attributes:
      label: "📝 Todo"
      description: "작업 목록을 작성해주세요."
      placeholder: |
        - [ ] 대상 코드 분석
        - [ ] 리팩토링 적용
        - [ ] 기존 테스트 통과 확인
  - type: input
    id: related-issues
    attributes:
      label: "🔗 관련 이슈"
      description: "관련된 이슈가 있다면 링크를 남겨주세요."
      placeholder: "예: #1, #2"
```

#### DOCS

```yaml
name: "📚 DOCS"
description: "문서 추가 또는 수정"
title: "[DOCS] "
labels: ["documentation"]
body:
  - type: dropdown
    id: doc-type
    attributes:
      label: "문서 작업 유형"
      options:
        - 새로운 문서 작성
        - 기존 문서 수정 (오타, 내용 보강)
        - 문서 번역
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: "작업 상세 내용"
      description: "어떤 문서를 어떻게 추가/수정할 것인지 설명해주세요."
    validations:
      required: true
  - type: textarea
    id: todo
    attributes:
      label: "📝 Todo"
      placeholder: |
        - [ ] 초안 작성
        - [ ] 리뷰
        - [ ] 반영
  - type: input
    id: related-issues
    attributes:
      label: "🔗 관련 이슈"
```

#### TASK

```yaml
name: "⚙️ TASK"
description: "기타 단순 작업 (CI/CD, 라이브러리 업데이트 등)"
title: "[TASK] "
labels: ["chore"]
body:
  - type: textarea
    id: description
    attributes:
      label: "작업 상세 내용"
      description: "어떤 작업이 필요한지 설명해주세요."
      placeholder: "예: 'requirements.txt의 'django' 라이브러리 최신 버전으로 업데이트'"
    validations:
      required: true
  - type: textarea
    id: todo
    attributes:
      label: "📝 Todo"
      placeholder: |
        - [ ] 작업 진행
        - [ ] 테스트
```


---

merge PR까지 모두 마쳤고, 이제 "New issue" 버튼을 클릭하면 다음과 같은 화면이 뜬다.
원하는 이슈 카테고리를 고르면 앞서 저장한 템플릿을 확인할 수 있다!

![issue template 적용](/assets/img/posts/2025-11-08-github-issue-setting/9.png)


---

#### 레퍼런스

[GitHub Docs: Configuring issue templates for your repository](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository)

[[GitHub] Issue 템플릿 & PR 템플릿 만들기](https://yejinlife.tistory.com/entry/GitHub-Issue-%ED%85%9C%ED%94%8C%EB%A6%BF-PR-%ED%85%9C%ED%94%8C%EB%A6%BF-%EB%A7%8C%EB%93%A4%EA%B8%B0)

[[GitHub]Issue 및 Pr Template](https://soo-develop.tistory.com/43)

[13aek/finbot](https://github.com/13aek/finbot)