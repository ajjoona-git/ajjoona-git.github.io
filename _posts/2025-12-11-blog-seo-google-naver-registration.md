---
title: "블로그 검색 노출을 위한 구글 & 네이버 서치 콘솔 등록 가이드"
date: 2025-12-11 09:00:00 +0900
categories: [Blog, Config]
tags: [Jekyll, Chirpy, SEO, GoogleSearchConsole, NaverSearchAdvisor, Sitemap]
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-12-11-blog-seo-google-naver-registration/6.png
description: Jekyll Chirpy 블로그의 검색 유입을 늘리기 위해 구글 서치 콘솔과 네이버 서치어드바이저에 사이트를 등록하고 사이트맵을 제출하는 방법을 상세히 다룹니다.
---

내가 쓴 블로그가 많은 사람들에게 읽혔으면 했는데, 구글에 검색해도 안 나오는 것이 아닌가? 찾아보니, 블로그를 아무리 잘 만들어도 **검색 엔진(Google, Naver 등)에 등록**하지 않으면 사람들이 검색해서 들어올 수 없다고 한다. 현재 사용 중인 **Chirpy 테마**는 SEO 기능이 잘 갖춰져 있어서, 설정 파일만 조금 수정하고 검색 사이트에 등록만 하면 된다.

## Google 검색 엔진 등록하기

### **1단계: 구글 서치 콘솔 (Google Search Console) 등록**

1. [구글 서치 콘솔](https://search.google.com/search-console/welcome)에 접속해서 URL 접두어 유형에 블로그 주소(URL)를 등록한다.
2. 소유권 확인 방법 중 **HTML 태그**를 선택하고 메타 태그 중 **`content` 속성 값만 복사**한다.
    - 화면에 출력된 코드는 뒷부분이 잘려있으므로, 우측의 복사하기 버튼을 눌러 전체 코드를 복사한 뒤, content 속성 값만 추출해야 한다.

![Google Search Console](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/10.png)
*Google Search Console*

![HTML 메타태그 복사](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/9.png)
*HTML 메타태그 복사*

### 2단계: `_config.yml` 설정 채우기

앞서 복사한 `<meta>` 태그의 `content` 속성 값을 `_config.yml` 파일의 해당 부분에 붙여넣는다.

```yaml
# Site Verification Settings
webmaster_verifications:
  google: YOUR_META_CONTENT # fill in your Google verification code
  bing: # fill in your Bing verification code
  ...
```

### **2단계: 변경 사항 배포 (Commit & Push)**

`_config.yml`을 저장하고 변경 사항을 Git으로 배포(`push`)한다.

```bash
$ git add _config.yml
$ git commit -m "feat: 검색 유입을 위한 웹 마스터 인증 추가"
$ git push
```

### **3단계: 사이트맵(Sitemap) 제출**

배포가 완료되면, 

1. 다시 구글 서치 콘솔로 돌아가서 **소유권 확인 버튼**을 누른다. 인증이 성공했다고 뜬다.
    
    ![Google 소유권 확인](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/8.png)
    *Google 소유권 확인*
    
2. 그다음, 검색 엔진이 내 글을 잘 읽어가도록 Sitemap를 줘야 한다. Chirpy 테마는 자동으로 `/sitemap.xml`을 생성한다.
    - 왼쪽 메뉴의 [Sitemaps] -> 새 사이트맵 추가에 `sitemap.xml` 입력 -> [제출]

    ![Google Sitemap 추가](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/7.png)
    *Google Sitemap 추가*

## Naver 검색 엔진 등록하기

### 1단계: Naver 서치어드바이저 등록

1. [네이버 서치어드바이저](https://searchadvisor.naver.com/)에 접속해서 우측 상단의 **웹마스터 도구**로 이동하여 사이트 등록에 블로그 주소를 입력한다.
    
    ![네이버 서치어드바이저 초기 화면](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/6.png)
    *네이버 서치어드바이저 초기 화면*
    
2. 구글과 마찬가지로, **HTML 태그**를 선택하고 **`content` 속성 값을 복사**한다.
    
    ![웹마스터 도구 > 사이트 등록](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/5.png)
    *웹마스터 도구 > 사이트 등록*
    
3. 복사한 `<meta>` 태그의 `content` 속성 값을 `_config.yml` 파일의 해당 부분에 붙여넣는다. 단, `_config.yml`에는 기본적으로 `naver` 항목이 없으므로 직접 추가해 준다.

    ![HTML 메타태그 복사](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/4.png)
    *HTML 메타태그 복사*

```yaml
# Site Verification Settings
webmaster_verifications:
  google: YOUR_META_CONTENT # fill in your Google verification code
  naver: YOUR_NAVER_META_CONTENT  # 새롭게 작성
  bing: # fill in your Bing verification code
  ...
```

### **2단계: 변경 사항 배포 (Commit & Push)**

`_config.yml`을 저장하고 변경 사항을 Git으로 배포(`push`)한다.

```bash
$ git add _config.yml
$ git commit -m "feat: 검색 유입을 위한 웹마스터 인증 추가"
$ git push
```

### **3단계: 사이트맵(Sitemap) 제출**

배포가 완료되면, 

1. 다시 네이버 서치어드바이저로 돌아가서 **소유권 확인 버튼**을 누른다. 사이트 소유 확인이 완료되었다고 뜬다.
    
    ![Naver 소유권 확인 완료](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/3.png)
    *Naver 소유권 확인 완료*
    
2. 그다음, 검색 엔진이 내 글을 잘 읽어가도록 Sitemap를 줘야 한다. Chirpy 테마는 자동으로 `/sitemap.xml`을 생성한다.
    - **네이버 서치어드바이저**: [요청] -> [사이트맵 제출] -> `sitemap.xml` 입력 -> [확인]

    ![Naver 사이트맵 제출](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/2.png)
    *Naver 사이트맵 제출*

### (선택) 만약 소유권 확인에 실패했다면?

이전 단계에서 `_config.yml`에 `naver` 항목을 추가했지만, **Chirpy 테마가 사용하는 SEO 플러그인(`jekyll-seo-tag`)이 '네이버'를 기본적으로 지원하지 않아서** 실제 HTML에 코드가 생성되지 않았을 수 있다. 이 경우, **HTML 파일에 직접 코드를 심어줘야 한다.**

![Naver 소유권 확인 실패](/assets/img/posts/2025-12-11-blog-seo-google-naver-registration/1.png)
*Naver 소유권 확인 실패*

1. `_includes/head.html` 파일을 연다. 없다면, 직접 블로그 테마 깃허브에서 해당 파일을 복사해서 새로 생성한다.
2. 네이버 서치어드바이저의 웹마스터 도구에서 아까 등록한 사이트의 소유확인 페이지에서 **HTML 태그**를 복사한다.
3. 파일의 `<head>` 태그 바로 아래, 혹은 `<meta ...>` 태그들이 모여 있는 곳에 아래 코드를 추가한다.
    
    ```html
    <head>
      <meta name="naver-site-verification" content="YOUR_NAVER_META_CONTENT" />
      ...
    ```
    
4. 변경 사항을 저장하고, git에 배포한다.

---

## 글 작성 시 SEO 팁 (Front Matter)

기술적으로는 위 설정이면 끝이다. 며칠만 기다리면 구글, 네이버에 검색해서 내 블로그 포스트를 확인할 수 있을 것이다!

이제 글을 쓸 때, 포스트 상단(Front Matter)의 `title`과 `description` 등을 잘 적어주면 된다.

예를 들어 `2025-10-01-test-post.md` 파일처럼:

```yaml
---
title: "나의 첫 기술 블로그 포스트"  # 검색 결과 제목으로 나옴
description: "Jekyll과 Chirpy 테마로 기술 블로그를 만드는 과정을 기록했습니다."  # 검색 결과 요약으로 나옴 (중요!)
categories: [Blog, Config] 
tags: [Jekyll, Chirpy, Demo]  # 검색 키워드 도움
---
```

---

### 레퍼런스

[구글 서치 콘솔 (Google Search Console)](https://search.google.com/search-console/welcome)

[네이버 서치어드바이저 (Naver Search Advisor)](https://searchadvisor.naver.com/)
