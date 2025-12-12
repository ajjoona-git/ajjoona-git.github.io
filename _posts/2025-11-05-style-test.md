---
title: "마크다운 스타일 가이드"
date: 2025-11-05 09:00:00 +0900
categories: [Blog, Config]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [Markdown, Style, Guide]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
# image: /assets/img/my-post-banner.png # (선택) 대표 이미지
description: 블로그 포스팅 시 참고할 Markdown 문법과 Chirpy 테마의 스타일 적용 예시를 정리한 가이드 문서입니다.
---


이 문서는 깃허브 블로그에 적용된 마크다운(Markdown) 스타일을 확인하기 위한 테스트 페이지입니다. 모든 주요 마크다운 문법을 포함하고 있습니다.

---

## 1. 헤더 (Headings)
# H1: 가장 큰 헤더
## H2: 두 번째 큰 헤더
### H3: 세 번째 큰 헤더
#### H4: 네 번째 큰 헤더
##### H5: 다섯 번째 큰 헤더
###### H6: 가장 작은 헤더

---

## 2. 문단 및 텍스트 스타일 (Paragraphs & Text)

이것은 일반적인 문단입니다. 로렘 입숨(Lorem Ipsum)은 출판이나 그래픽 디자인에 사용되는 더미 텍스트입니다. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

문단과 문단 사이는 한 줄의 공백으로 구분됩니다.

강제 줄 바꿈을 하고 싶다면 문장 끝에 **스페이스 두 개**를 입력해야 합니다.  
이렇게 말이죠. (또는 `<br>` 태그를 사용할 수 있습니다.)

### 텍스트 강조 (Text Emphasis)

*이탤릭체 (Italic)* 또는 _이탤릭체_
**볼드체 (Bold)** 또는 __볼드체__
***볼드 이탤릭체 (Bold & Italic)*** 또는 ___볼드 이탤릭체___
~~취소선 (Strikethrough)~~
`인라인 코드 (Inline Code)`는 이렇게 사용합니다.

---

## 3. 인용문 (Blockquotes)

> 이것은 인용문입니다.
> 
> > 이것은 중첩된 인용문입니다.
> > > 세 번째 레벨까지 중첩할 수 있습니다.
> 
> > **참고:** 인용문 내부에서도 *다른* 마크다운 요소를 사용할 수 있습니다.
> > - 리스트 아이템 1
> > - 리스트 아이템 2

---

## 4. 리스트 (Lists)

### 순서 없는 리스트 (Unordered List)
* 아이템 1 (별표 *)
* 아이템 2
    * 중첩 아이템 2-1
    * 중첩 아이템 2-2
* 아이템 3

- 또는 하이픈(-) 사용
- 아이템 2
    - 중첩 아이템 2-1
+ 또는 플러스(+) 사용
+ 아이템 2

### 순서 있는 리스트 (Ordered List)
1. 첫 번째 아이템
2. 두 번째 아이템
    1. 중첩된 아이템 2-1
    2. 중첩된 아이템 2-2
3. 세 번째 아이템 (숫자를 `1.` `1.` `1.` 로 입력해도 자동으로 넘버링됩니다.)

### 작업 리스트 (Task List - GFM)
깃허브(GitHub Flavored Markdown)에서 지원하는 문법입니다.
- [x] 완료된 작업
- [ ] 미완료된 작업
- [ ] 마크다운 스타일 테스트 파일 작성하기

---

## 5. 코드 블럭 (Code Blocks)

`inline code`는 문장 내에서 이렇게 사용합니다.

### Fenced Code Blocks (코드 블럭)
백틱(```) 3개를 사용하여 코드 블럭을 만듭니다. 언어를 명시하여 구문 강조(Syntax Highlighting)를 테스트할 수 있습니다.

**Python 예제:**

```python
def hello_world():
    """Prints hello world."""
    print("Hello, world!")

# 함수 호출
hello_world()
````

**JavaScript 예제:**

```javascript
const greeting = "Hello";
document.getElementById("demo").innerHTML = greeting + " World!";

function sayHi(name) {
  console.log(`Hello, ${name}!`);
}
```

**언어 명시 없음 (Plain Text):**

```
이것은 일반 텍스트 블럭입니다.
구문 강조(하이라이팅)가 적용되지 않습니다.
```

-----

## 6. 링크 및 이미지 (Links & Images)

### 링크 (Links)

[Google로 이동](https://www.google.com)
[Google로 이동 (타이틀 포함)](https://www.google.com "Google 홈페이지")
[같은 페이지 내 헤더로 이동](https://www.google.com/search?q=%231-%ED%97%A4%EB%8D%94-headings)
[https://www.google.com](https://www.google.com) (URL 자동 링크)

### 이미지 (Images)

이미지 구문은 링크와 비슷하지만 앞에 `!`가 붙습니다.

*이미지 아래에 이런 식으로 캡션을 달 수 있습니다.*

-----

## 7. 테이블 (Tables - GFM)

테이블은 헤더와 본문, 그리고 정렬을 테스트해야 합니다.

| 정렬 없음 (기본) | 왼쪽 정렬 | 가운데 정렬 | 오른쪽 정렬 |
| :--- | :--- | :---: | ---: |
| 값 1 | Cell A | 100 | $1 |
| 값 2 (긴 텍스트) | Cell B | 2000 | $20 |
| 값 3 | Cell C | 30 | $300 |

-----

## 8. 수평선 (Horizontal Rules)

아래에 수평선이 3가지 다른 방법으로 표시됩니다.

---

***

___
