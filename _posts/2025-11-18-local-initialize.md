---
title: "[쉽길] 로컬 서버 초기 설정 가이드"
date: 2025-11-18 09:00:00 +0900
categories: [Projects, 쉽길]  # 계층적 카테고리 지원 [대분류, 소분류]
tags: [Environment, Python, DB, Guide]      # 태그 (소문자 권장)
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-18-local-initialize/3.png # (선택) 대표 이미지
---

쉽길 프로젝트를 기준으로, 로컬 서버에서 개발 환경을 초기화하는 과정이다.

매번 자리 바꿀 때마다 찾아보기 어려워서 정리해봤다.

 

### 1. 가상환경 실행

```bash
# 가상환경 생성
$ python -m venv venv
# 가상환경 활성화
$ source venv/Scripts/activate
# 라이브러리 설치
$ pip install -r requirements.txt 
```

![가상환경 실행 터미널](/assets/img/posts/2025-11-18-local-initialize/3.png)
*가상환경 실행 터미널*

 
### 2. 환경변수(.env) 설정

`.env.example` 파일을 복제해서 `.env` 파일을 만든다.

그리고 우리팀 Secrets 에서 각종 ID와 비밀번호, API KEY 등 노출되면 안 되는 환경변수들을 가져와 `.env` 파일에 입력한다.

`.env` 파일은 `.gitignore`에 쓰여 있어서 외부로 공유되지 않는다!

![.env.example](/assets/img/posts/2025-11-18-local-initialize/2.png)
*.env.example*

 
### 3. DB migrate

migrations 파일은 만들어져 있는 상태이기 때문에, makemigrations 과정은 생략하고 로컬 서버에 데이터베이스를 입력하는 과정(migrate + load_csv)만 진행하면 된다.

쉽길 프로젝트의 경우, csv 파일에 데이터를 저장해두고 업로드하는 방식을 사용하고 있다. 

배포용 서버에서는 DB 서버로 MySQL을 사용하고 yml 파일에서 load_csv하는 과정이 자동화되어 있지만, 

로컬 서버의 경우 사용자가 직접 load_csv 과정을 거쳐 SQLite에 데이터베이스를 올려야 한다. 

```bash
# migrate
$ python manage.py migrate --settings=config.settings.local

# load_csv
python manage.py load_csv --file station.csv --settings=config.settings.local
python manage.py load_csv --file line.csv --settings=config.settings.local
python manage.py load_csv --file stationline.csv --settings=config.settings.local
python manage.py load_csv --file node.csv --settings=config.settings.local
python manage.py load_csv --file edge.csv --settings=config.settings.local
python manage.py load_csv --file FastGate.csv --settings=config.settings.local
python manage.py load_csv --file lines.csv --settings=config.settings.local
```


이때 데이터를 올리는 순서에 주의해야 한다! **의존성이 없는 마스터 데이터부터** 로드해야 한다.

데이터 간 관계에 따라 다른 테이블을 참조하는 관계(외래키 등)라면, 해당 테이블이 비어있는 경우 아래와 같은 에러 화면을 만날 수 있다.

![load_csv 에러](/assets/img/posts/2025-11-18-local-initialize/1.png)
*load_csv 에러*


여기서 load_csv 과정은 csv에 있는 데이터를 DB에 적재하는 과정이다. 위 명령어를 통해 journeys 앱 내부에 `management/commands/load_csv.py`가 실행되고, 각 파일에서 데이터를 한줄한줄 읽어오면서 DB에 입력되는 것이다.

```
apps/
├── accounts/
├── common/
├── journeys/
│   ├── __pycache__/
│   ├── management/
│   │   └── commands/
│   │       ├── __pycache__/
│   │       ├── build_graph.py
│   │       └── load_csv.py
│   ├── migrations/
│   ├── services/
│   ├── templates/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
└── stations/
```

  
### 4. (구글 로그인) SocialApp 등록

구글 로그인을 위한 SocialApp을 등록하는 과정이 필요하다. 

shell을 실행해서 사이트를 연결하는 과정은 처음에 한번만 진행하면 된다.

```bash
# shell 실행 (처음 한 번만 진행)
python manage.py shell --settings=config.settings.local

from django.contrib.sites.models import Site
s = Site.objects.get(id=1)   # SITE_ID 확인해서 맞는 걸로 수정
s.domain = "localhost:8000"  # 스킴 없이, 포트 포함
s.name = "Local"
s.save()

# socialapp 등록
$ python manage.py apply_socialapp --settings=config.settings.local
```

 
### 5. git 브랜치 최신화

매 작업 전에 로컬 git을 최신화해주는 작업이 필수!!!

먼저, 로컬 dev를 최신화해준다. 

```bash
# 원격 저장소(origin) 최신 내역 가져오기
git fetch origin
# dev 브랜치로 이동
git checkout dev
# 로컬 dev 최신화
git pull --ff-only origin dev
```

 
로컬 feat 브랜치도 최신화해준다.

```bash
# 내 작업 브랜치로 이동 (이미 feat/...에 있을 경우 생략)
git checkout feat/...

# 2. 최신 dev 가져와서 리베이스
git fetch origin
git rebase origin/dev
```

 
이때 작업 브랜치를 새로 생성해야 한다면, 

```bash
# 작업 브랜치 생성
git switch -c feat/작업명
```