---
title: "승인 대기 중인 브랜치에서 이어서 작업하기 (Stacked PR 전략)"
date: 2025-12-15 09:00:00 +0900
categories: [Tech, DevOps]
tags: [Git, PullRequest, Workflow, StackedPR, BranchStrategy, Collaboration]
description: "선행 작업(Branch A)이 아직 머지되지 않은 상태에서 이를 기반으로 후행 작업(Branch B)을 시작해야 할 때, 의존성을 관리하며 PR을 작성하는 'Stacked PR' 전략과 구체적인 Git 명령어 흐름을 소개합니다."
toc: true 
comments: true
---

**아직 머지되지 않은 이전 작업(Branch A)의 코드가 필요한 상태에서 다음 작업(Branch B)을 이어서 해야 할 때** 어떻게 하는지 알아보았다.

이 방식을 **"Stacked PR (쌓아 올리기)"** 전략이라고 부른다.

---

## PR 승인 대기 중인 작업에 이어서 새로운 작업 시작하기

- **상황**: `feat/prev-work` 브랜치의 PR이 승인 대기 중인데, 이 코드를 기반으로 `feat/next-work`를 시작하고 싶음

### 1. 작업 공간 정리

브랜치를 이동하기 전에는 항상 현재 작업 내용을 안전하게 처리해야 한다.

```bash
# 1. 현재 작업 내용 확인
git status

# 2. 작업 중인 내용이 있다면 저장(Commit)하거나 임시 저장(Stash)
git add .
git commit -m "Save: 현재 작업 내용 저장"
```

### 2. 이전 작업 브랜치에서 시작

`dev`가 아니라, **내용이 들어있는 `feat/prev-work` 브랜치**에서 새 가지(branch)를 쳐야 한다.

```bash
# 1. 이전 작업 브랜치로 이동 및 최신화
git checkout feat/prev-work
git pull origin feat/prev-work

# 2. 거기서 새로운 브랜치 생성 (A -> B)
git checkout -b feat/next-work
```

> 이렇게 하면 `feat/prev-work`의 모든 코드를 `feat/next-work`가 그대로 물려받는다.
> 

### 3. 개발 및 커밋

이제 `feat/next-work` 브랜치에서 마음껏 기능을 개발하고 커밋한다.

```bash
git add .
git commit -m "Feat: 새로운 기능 구현 완료"
git push origin feat/next-work
```

### 4. PR 생성 (⭐ 중요!)

GitHub에서 PR을 생성할 때 **도착지(Base)**를 잘 설정해야 한다.

1. **Base (도착지)**: `dev` (X) -> **`feat/prev-work` (O)**
2. **Compare (출발지)**: `feat/next-work`
3. **내용 작성**: "이 PR은 #1번 PR이 머지된 후에 리뷰해주세요"라는 멘트 남기기.

> Base를 dev로 하면, prev-work의 커밋까지 몽땅 '새로운 변경 사항'으로 잡혀서 리뷰어가 헷갈릴 수 있다. 
Base를 prev-work로 잡으면 새로 작업한 내용만 깔끔하게 보인다.
> 

### 5. 이전 PR 머지 후 처리

`feat/prev-work`가 승인되어 dev에 머지되었다면, 

이제 붕 떠버린 내 PR(`feat/next-work`)의 방향을 다시 잡아준다.

1. 내 PR 페이지 접속 -> 제목 옆 **[Edit]** 클릭.
2. **Base**를 `feat/prev-work` -> **`dev`**로 변경.
3. GitHub이 자동으로 `dev`에 들어간 코드를 인식하여, 내 PR에는 **오직 `next-work` 내용만** 남게 된다.

---

### 💡 요약 체크리스트

- [ ]  현재 작업 내용을 커밋했는가?
- [ ]  `dev`가 아닌 **이전 브랜치**에서 `git checkout -b` 했는가?
- [ ]  PR 보낼 때 Base를 **이전 브랜치**로 설정했는가?
- [ ]  이전 브랜치가 머지되면 Base를 `dev`로 바꿨는가?

이 흐름만 기억하면, PR이 밀려 있어도 끊김 없이 개발 속도를 유지할 수 있다.