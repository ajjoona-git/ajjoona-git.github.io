---
title: "[GitHub] HttpError: Not Found 이것 뭐에요?"
date: 2025-11-10 09:00:00 +0900
categories: [블로그, GitHub]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [github, actions, deploy]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-10-httperror/7.png # (선택) 대표 이미지
---

### 어느날 갑자기 블로그가 없어졌다..?

어느 정도 블로그 세팅이 마무리되면서 블로그 포스팅하는 습관을 들이고 있다.

열심히 포스트해서 commit, push하고 있었는데 블로그에 접속하니까 별안간 페이지가 없어졌다.

![404 PageNotFoundError](/assets/img/posts/2025-11-10-httperror/7.png)

*띠로리...*

분명 로컬 서버에서 포스팅 확인하고 업로드했는데, 뭐가 문제일까?


### GitHub Actions를 살펴보자

![GitHub Actions](/assets/img/posts/2025-11-10-httperror/6.png)

workflows를 보니 #15 "post: [GitHub] Issue 템플릿 설정하기" commit부터 빨간색으로 **Build and Deploy 실패** 표시가 되어있다.
자세히 알아보자.

![Build Failure](/assets/img/posts/2025-11-10-httperror/5.png)

![Build and Deployment](/assets/img/posts/2025-11-10-httperror/4.png)

deploy과정까지는 가지도 못했다.

build에서 `HttpError: Not Found` 에러가 발생했다.

```Bash
# 오류 메세지
Get Pages site failed. Please verify that the repository has Pages enabled and configured to build using GitHub Actions, or consider exploring the `enablement` parameter for this action.
```

오류 메세지 `Get Pages site failed. Please verify that the repository has Pages enabled...`를 보아하니, 페이지 설정을 가져오지 못해 발생한 오류인 것 같다.

GPT 도움을 받아 원인과 해결방법을 알아왔다.

pages-deploy.yml 워크플로우는 "GitHub Actions"를 사용해 사이트를 빌드하고 배포하도록 설정되어 있다. 하지만 **GitHub 저장소의 'Settings'**가 "GitHub Actions"를 사용하도록 설정되어 있지 않아, 액션이 페이지 설정을 가져오지 못해(Not Found) 실패한 것이라고 한다.


### Build and Deployment 설정하기

이를 해결하기 위해, GitHub 저장소 설정에서 **"GitHub Actions"**를 배포 소스(Source)로 지정해야 한다.

레포지토리 > [Settings] 탭 > [Pages] > "Build and deployment" 섹션

"Source" 옵션을 **"GitHub Actions"**로 변경한다. (아마 "Deploy from a branch"로 되어 있을 것)

![Settings](/assets/img/posts/2025-11-10-httperror/3.png)

이렇게 하면 해결된다!


### Public인지 확인하기 

만약 [Pages] 탭에서 "Build and deployment" 섹션이 보이지 않는다면 (아래 사진 참고),

![private repo](/assets/img/posts/2025-11-10-httperror/2.png)

레포지토리가 **private**으로 설정되어 있을 것이다!

GitHub 정책상, GitHub Pages 기능은 Public(공개) 저장소에서는 무료로 제공되지만, 

Private(비공개) 저장소에서 GitHub Pages를 사용하려면 GitHub Pro (유료) 플랜으로 업그레이드해야 한다고 한다.

 

알고 보니 나도 Private으로 전환한 다음에 Build 오류가 생긴 거였다...

Public으로 전환하고 위의 "GitHub Actions" 옵션을 적용했더니, 바로 해결!

![Blog 화면](/assets/img/posts/2025-11-10-httperror/1.png)