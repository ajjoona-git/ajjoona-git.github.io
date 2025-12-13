---
title: "PR이 꼬였을 때: Cherry-pick으로 커밋 분리하고 브랜치 복구하기"
date: 2025-12-10 09:00:00 +0900
categories: [Tech, Git]
tags: [Git, CherryPick, PullRequest, BranchStrategy, Troubleshooting, Workflow]
description: "하나의 브랜치에서 두 가지 작업을 동시에 진행하여 PR이 섞였을 때, git cherry-pick과 reset 명령어를 활용하여 특정 커밋만 새로운 브랜치로 옮기고 기존 브랜치를 원복하는 방법을 단계별로 소개합니다."
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true    
---

### *"아, 브랜치 새로 파는 거 깜빡하고 그냥 이어서 작업해버렸네..."*

최근 프로젝트를 진행하면서 하나의 브랜치에서 두 가지 이슈를 연달아 작업하다가 PR(Pull Request)이 꼬이는 상황을 생겼다. 
**Git의 `cherry-pick`과 `reset`을 활용하여 꼬인 커밋을 깔끔하게 분리해낸 과정**을 기록해본다.

## 사건 기록

- **작업 내용:** **Issue \#10**과 **Issue \#17**
- **브랜치:** `feat/vue-init`
- **상황:** 

먼저 Issue \#10 작업에 대해 **PR \#20**을 날렸다. 이후 같은 브랜치에서 곧바로 이어서 **Issue \#17** 작업을 진행했다.

그 결과, **PR \#20**에 **Issue \#17**을 위해 작업한 커밋들까지 모두 묶여버리는 상황이 발생했다.


## 새로운 브랜치로 커밋 옮겨 해결하기

이 문제를 해결하기 위해 **새로운 브랜치를 생성하여 Issue \#17 관련 커밋을 옮기고, 기존 브랜치는 원복**시키는 전략을 사용했다.

### 1\. 꼬인 커밋 확인하기

먼저 어떤 커밋들이 잘못 섞였는지 확인해야 한다. `git log`를 통해 최근 커밋 내역을 살펴본다.

```bash
git log --oneline -10
```

로그를 통해, `view` 작업과 관련된 **5개의 커밋**이 `feat/vue-init` 브랜치에 추가된 것을 확인했다.

### 2\. 새 브랜치로 커밋 옮기기 (Cherry-pick)

이제 이 5개의 커밋만 따로 떼어내기 위해, Issue \#17 작업을 위한 새로운 브랜치(`feat/fe-views-init`)를 생성한다. 기준은 `dev` 브랜치이다.

```bash
# dev 브랜치로 이동 후 새 브랜치 생성
git checkout dev 
git checkout -b feat/fe-views-init
```

그다음, **`cherry-pick`** 명령어를 사용하여 아까 확인해둔 5개의 커밋을 이 새 브랜치로 가져온다.

```bash
# 원하는 커밋들만 쏙쏙 골라오기
git cherry-pick 8d90027 3a43952 2ed1b83 363138b eb70e9f
```

이제 새 브랜치에 작업 내용이 잘 들어갔으므로 원격 저장소에 푸시한다.

```bash
git push -u origin feat/fe-views-init
```

### 3\. 기존 브랜치 원복하기 (Reset & Force Push)

이제 꼬여버린 기존 브랜치(`feat/vue-init`)를 정리할 차례다. Issue \#17 작업을 시작하기 전 상태(`cdb91c3`)로 되돌린다.

```bash
# 기존 브랜치로 이동
git checkout feat/vue-init

# 5개의 커밋이 쌓이기 전 시점으로 리셋 (Hard Reset)
git reset --hard cdb91c3
```

로컬 브랜치는 깔끔해졌지만, 원격 저장소(GitHub)에는 이미 5개의 커밋이 올라가 있는 상태이므로, 이를 맞추기 위해 **강제 푸시(Force Push)**를 진행한다.

> **주의:** 강제 푸시(`-f`)는 협업 중인 브랜치에서 사용할 때 매우 신중해야 한다. 이번 경우는 개인 작업 브랜치였기 때문에 사용했다.

```bash
git push -f origin feat/vue-init
```

---

### 마치며

이렇게 `cherry-pick`으로 필요한 커밋을 살리고, `reset`으로 잘못된 커밋을 지우는 방식으로 두 개의 섞인 작업을 깔끔하게 분리했다.

  * **PR \#22**: Issue \#17 작업이 포함된 새 PR 생성 완료
  * **PR \#20**: 원래 의도했던 Issue \#10 작업 내용만 깔끔하게 남음

**💡 오늘의 교훈:**
웬만하면 **기능(Issue) 별로 브랜치를 확실하게 구분**해서 작업하자!

-----

*참고 링크: [https://github.com/ajjoona-git/moathon/pull/22](https://github.com/ajjoona-git/moathon/pull/22)*