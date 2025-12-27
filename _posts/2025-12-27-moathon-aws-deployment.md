---
title: "[모아톤] AWS 풀스택 배포 가이드 (EC2, S3, Nginx, Gunicorn)"
date: 2025-12-27 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [AWS, EC2, S3, Django, Vue.js, Nginx, Gunicorn, Deployment, DevOps]
toc: true 
comments: true
image: /assets/img/posts/2025-12-27-moathon-aws-deployment/3.png
description: "AWS EC2(Ubuntu)에 Django와 Nginx, Gunicorn을 연동하여 백엔드를 구축하고, S3 정적 호스팅을 통해 Vue.js 프론트엔드를 배포하는 전체 과정을 정리했습니다. CORS 설정과 Vite 빌드 시 정적 에셋 경로 문제 해결 방법도 포함합니다."
---

모아톤 프로젝트의 배포 아키텍처는 **백엔드(Django)는 AWS EC2**에서, **프론트엔드(Vue.js)는 AWS S3**를 통해 서비스하는 구조로 설계했다. 

다음은 Nginx를 리버스 프록시로 두고 Gunicorn을 WSGI 서버로 사용하여 안정적인 서비스를 구축한 과정이다.

```
graph TD
    User((사용자))
    
    subgraph AWS Cloud
        subgraph Frontend Hosting
            S3[S3 Bucket - Vue 빌드 파일]
        end
        
        subgraph Backend Infrastructure
            subgraph EC2 Instance
                Nginx[Nginx - Web Server]
                Gunicorn[Gunicorn - WSGI]
                Django[Django App]
            end
            
            RDS[(AWS RDS - PostgreSQL)]
        end
    end

    %% 현재 구현은 HTTPS가 아닌 HTTP이며, S3 엔드포인트로 직접 접속한다.
    User -- "http://moathon-client... (접속)" --> S3
    S3 -- "정적 파일 제공" --> User
    
    User -- "API 요청 (http://EC2_IP/api/)" --> Nginx
    Nginx -- "Reverse Proxy" --> Gunicorn
    Gunicorn -- "Python 코드 실행" --> Django
    Django -- "데이터 조회" --> RDS
```

# 1. AWS EC2 인스턴스 생성 및 접속

## 1-1. EC2 인스턴스 시작

### 애플리케이션 및 OS 이미지 (Amazon Machine Image)

- **OS:** Ubuntu Server 24.04 LTS
- **인스턴스 유형:** t2.micro

### 키 페어 (로그인)

- **이름:** `moathon-key`
- **유형:** `RSA`
- **파일 형식:** `.pem` (OpenSSH용)
- **[키 페어 생성]** 버튼을 누르면 `moathon-key.pem` 파일이 다운로드된다. **절대 삭제하지 말고 안전한 곳에 보관할 것.**

### 네트워크 설정

보안 그룹 규칙 추가

- **SSH (22):** 관리자 접속용
- **HTTP (80):** 웹 서비스용 (위치 무관, `0.0.0.0/0`)
- **사용자 지정 TCP (8000):** Django 개발 서버(`runserver`) 테스트용

![네트워크 설정](/assets/img/posts/2025-12-27-moathon-aws-deployment/17.png)
*네트워크 설정*

### 인스턴스 생성

![인스턴스 생성 성공](/assets/img/posts/2025-12-27-moathon-aws-deployment/16.png)
*인스턴스 생성 성공*

인스턴스를 클릭한 후 아래 정보창에 `퍼블릭 IPv4 주소`를 복사한다.

## 1-2. 내 컴퓨터에서 서버 접속하기 (SSH)

다운로드한 키 페어(pem)를 이용해 로컬 터미널에서 EC2 서버 (Ubuntu)에 접속한다.

### 접속 명령어 입력

터미널(git bash 사용)에 다음 명령어를 입력한다.

```bash
# 형식: ssh -i "키파일위치" ubuntu@퍼블릭IP
ssh -i "C:\Users\USER\Downloads\moathon-key.pem" ubuntu@54.180.xx.xx
```

처음 접속하면 `Are you sure...?` 라고 묻는데 `yes`라고 입력하고 엔터를 치면 된다.

### 성공 확인

터미널 화면이 내 컴퓨터 이름에서 `ubuntu@ip-172-xx-xx-xx:~$` 와 같이 바뀌었다면 **접속 성공**! 이제 AWS 데이터센터의 컴퓨터를 제어할 수 있다.

![터미널 화면](/assets/img/posts/2025-12-27-moathon-aws-deployment/15.png)
*터미널 화면*


# 3. 백엔드 서버 세팅 (Django + Gunicorn)

## 3-1. 서버 업데이트 및 필수 프로그램 설치

서버의 패키지 목록을 업데이트하고, 프로젝트 구동에 필요한 필수 패키지를 설치했다. libpq-dev는 추후 PostgreSQL(RDS) 연결을 위해 필요하다.

```bash
# 1. 패키지 목록 업데이트
sudo apt update

# 2. 필수 프로그램 설치 (Python, pip, venv, nginx, git, postgresql 라이브러리)
# 중간에 'Do you want to continue? [Y/n]' 나오면 엔터(Enter)
sudo apt install python3-pip python3-venv git nginx libpq-dev -y
```

## 3-2. 깃허브에서 코드 가져오기 (Clone)

```bash
# 1. 홈 디렉토리로 이동
cd ~

# 2. 깃 클론 (멘티님의 레포지토리 주소를 입력)
git clone https://github.com/ajjoona-git/moathon.git

# 3. 잘 받아졌는지 확인 (moathon 폴더가 보여야 함)
ls
```

![image.png](/assets/img/posts/2025-12-27-moathon-aws-deployment/14.png)
*moathon 폴더가 보여야 함*

## 3-3. 가상환경 구성

프로젝트별 의존성 격리를 위해 가상환경을 생성하고 패키지를 설치한다.

```bash
cd moathon/backend
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
pip install gunicorn psycopg2-binary  # 배포용 패키지 추가
```

## 3-4. 환경 변수(.env) 설정

GitHub에는 업로드되지 않은 비밀 정보들을 관리하기 위해 서버에 .env 파일을 직접 생성한다.

```bash
nano .env
# 로컬의 .env 내용을 복사하여 붙여넣기
```

![image.png](/assets/img/posts/2025-12-27-moathon-aws-deployment/13.png)
*환경 변수 설정*

**저장하고 나가기:**

- `Ctrl + O` (저장) -> `Enter`
- `Ctrl + X` (종료)

## 3-5. 개발 서버 테스트

배포 전, 장고 개발 서버(runserver)가 정상적으로 뜨는지 확인한다.

```bash
# 0.0.0.0은 외부 접속을 허용한다는 의미
python manage.py runserver 0.0.0.0:8000
```

![개발 서버 (runserver) 실행](/assets/img/posts/2025-12-27-moathon-aws-deployment/12.png)
*개발 서버 (runserver) 실행*

### 접속 확인

`http://[아까 복사한 퍼블릭 IP]:8000`

![실행 결과: DisallowedHost at /](/assets/img/posts/2025-12-27-moathon-aws-deployment/11.png)
*실행 결과: DisallowedHost at /*

실행 결과, `DisallowedHost` 에러가 떴다. 접속은 성공했는데, 보안 설정 때문에 막힌 것.


### 보안 설정

.env 혹은 settings.py의 `ALLOWED_HOSTS`에 EC2의 퍼블릭 IP를 추가해주어야 한다.

- 참고: `django-environ` 라이브러리는 `.env` 파일에서 리스트를 읽을 때 **파이썬 문법(`['...']`)을 쓰지 않고, 콤마(`,`)로 구분**한다.

```bash
# .env
...
ALLOWED_HOSTS=54.180.xx.xx
```

```python
# settings.py

# .env 파일에 있는 ALLOWED_HOSTS 값을 리스트로 가져온다.
# 만약 값이 없으면 빈 리스트를 반환한다.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
```

### 서버 재실행

![서버 접속 성공](/assets/img/posts/2025-12-27-moathon-aws-deployment/10.png)
*서버 접속 성공*

# 4. 웹 서버 구축 (Nginx + Gunicorn)

Django의 runserver는 개발용이므로, 실서비스를 위해 **Nginx(웹 서버)**와 **Gunicorn(WSGI 서버)**을 연동한다.

## 4-1. `settings.py`에 정적 파일 경로 추가

```bash
Not Found: /favicon.ico
[27/Dec/2025 10:16:51] "GET /favicon.ico HTTP/1.1" 404 3992
```

현재 `settings.py`에는 `STATIC_ROOT` 설정이 없다. 이 설정이 없으면 Nginx가 CSS나 JS 파일을 찾지 못해 화면이 깨진다. 

```python
# settings.py

# STATIC_URL 밑에 추가
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
```

### 정적 파일 모으기 (`collectstatic`)

Nginx가 CSS/JS 파일을 서빙할 수 있도록 `collectstatic`을 수행한다.

```bash
python3 manage.py collectstatic
```

## 4-2. Gunicorn 서비스 등록 (Daemon)

SSH 접속을 끊어도 서버가 계속 돌아가게 하려면 Gunicorn을 시스템 서비스로 등록해야 한다. 소켓 파일(`/tmp/gunicorn.sock`)을 통해 Nginx와 통신하도록 설정했다.

### 서비스 설정 파일 만들기

```bash
# /etc/systemd/system/gunicorn.service
[Unit]
Description=gunicorn daemon
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/moathon/backend
ExecStart=/home/ubuntu/moathon/backend/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/tmp/gunicorn.sock \
    moathon.wsgi:application

[Install]
WantedBy=multi-user.target
```

### gunicorn 시작 및 등록

```bash
sudo systemctl start gunicorn
sudo systemctl enable gunicorn

# 상태 확인
sudo systemctl status gunicorn
```

초록색 점으로 `active (running)`이 뜨면 성공이다.

![gunicorn 등록 성공](/assets/img/posts/2025-12-27-moathon-aws-deployment/9.png)
*gunicorn 등록 성공*

## 4-3. Nginx 리버스 프록시 설정

외부의 80번 포트 요청을 내부의 Gunicorn 소켓으로 전달(Proxy Pass)하는 설정을 추가한다.

### Nginx 설정 파일

```bash
# /etc/nginx/sites-available/moathon
server {
    listen 80;
    server_name 54.180.xx.xx;  # EC2 퍼블릭 IP

    location = /favicon.ico { access_log off; log_not_found off; }

    # 정적 파일 서빙
    location /static/ {
        alias /home/ubuntu/moathon/backend/staticfiles/;
    }

    # API 요청을 Gunicorn으로 전달
    location / {
        include proxy_params;
        proxy_pass http://unix:/tmp/gunicorn.sock;
    }
}
```

### 설정한 파일 연결

```bash
# 설정한 파일을 sites-enabled 폴더로 연결
sudo ln -s /etc/nginx/sites-available/moathon /etc/nginx/sites-enabled

sudo rm /etc/nginx/sites-enabled/default  # 기본 설정 삭제 (충돌 방지)
sudo nginx -t                             # 오타 없는지 검사
```

`syntax is ok` / `test is successful`이 나오면 성공.

### Nginx 재시작

설정 후 Nginx를 재시작하면, 포트 번호 없이 IP만으로 접속이 가능하다.

```bash
sudo systemctl restart nginx
```

### 최종 접속 확인

이제 **포트 번호 없이** 주소창에 IP만 입력해서 접속할 수 있다.

`http://[퍼블릭 IP]`

![웹 서버 연결 성공](/assets/img/posts/2025-12-27-moathon-aws-deployment/8.png)
*웹 서버 연결 성공*

# 5. 프론트엔드 배포 (S3 정적 호스팅)

Vue.js 프로젝트는 빌드 후 정적 파일 형태로 AWS S3에서 호스팅한다.

## 5-1. 환경 변수 및 CORS 설정 (Django)

### `settings.py` 설정

**Backend (Django)**: 프론트엔드(S3) 도메인에서의 요청을 허용하기 위해 CORS 설정을 수정한다.

다시 EC2 터미널에서 `settings.py`를 열고, `CORS_ALLOWED_ORIGINS`를 수정한다.

```python
# settings.py

# CORS_ALLOWED_ORIGINS = [
#     'http://127.0.0.1:5173',
#     'http://localhost:5173',
# ]
CORS_ALLOW_ALL_ORIGINS = True  # 테스트용 (실 운영 시 도메인 지정 권장)
```

### gunicorn 재시작

Gunicorn을 재시작해서 적용한다.

```bash
sudo systemctl restart gunicorn
```

## 5-2. 프론트엔드 API 주소 변경

### 배포용 `.env` 생성

**Frontend (Vue)**: 배포 환경에서는 EC2의 API 주소를 바라보도록 `.env.production`을 생성한다. 

`frontend` 폴더에 `.env.production` 파일을 만들어 아래 내용을 적어준다. (VS Code 사용)

```bash
# .env.production

VITE_API_URL=http://54.180.xx.xx  # Nginx가 80번 포트로 받으므로 포트 생략
```

### [잠깐] `.env.local` 이 있는데, `.env.production` 을 만드는 이유

- **개발할 때:** `npm run dev`를 치면 자동으로 `.env.local`을 읽어서 `localhost`와 통신한다.
- **배포할 때:** `npm run build`를 치면 자동으로 `.env.production`을 읽어서 `AWS IP`와 통신하도록 구워진다.

| **파일 이름** | **언제 쓰이나요?** | **어떤 주소가 들어가나요?** |
| --- | --- | --- |
| **`.env.local`** | **개발할 때** (`npm run dev`) | `http://127.0.0.1:8000` (내 컴퓨터) |
| **`.env.production`** | **배포할 때** (`npm run build`) | `http://54.180.xx.xx` (AWS EC2 IP) |

## 5-3. 빌드 및 S3 업로드

### 빌드 (Build)

사람이 짠 코드를 브라우저가 이해할 수 있는 파일(html, css, js)로 변환한다.

로컬에서 빌드 명령어를 실행하여 dist 폴더를 생성한다.

```bash
npm run build
```
탐색기에 `dist`라는 폴더가 새로 생겼는지 확인한다.

### AWS S3 버킷 만들기

AWS 콘솔에서 **S3 버킷**을 생성한다.

**이 버킷의 퍼블릭 액세스 차단 설정:**
- **'모든 퍼블릭 액세스 차단'**을 해제해야 외부에서 접근 가능하다.

### 파일 업로드

버킷의 **[업로드]** 버튼을 클릭하고, `dist` 폴더 내부의 파일들을 업로드한다.
- **주의:** `dist` 폴더 자체를 넣는 게 아니라, `dist` 폴더 안에 있는 `index.html`, `assets/` 등을 모두 선택해 넣어야 한다.

![image.png](/assets/img/posts/2025-12-27-moathon-aws-deployment/7.png)
*버킷에 파일 업로드*

![image.png](/assets/img/posts/2025-12-27-moathon-aws-deployment/6.png)
*업로드 성공*

## 5-4. 정적 웹 호스팅 활성화

### 정적 웹 사이트 호스팅 켜기

S3 버킷의 [속성] 탭에서 **'정적 웹 사이트 호스팅'**을 활성화하고, 인덱스 문서를 `index.html`로 지정한다. 

강제 새로고침 시에도 페이지가 로딩되도록 오류 문서에도 `index.html`을 지정한다.


![정적 웹 사이트 호스팅 편집](/assets/img/posts/2025-12-27-moathon-aws-deployment/5.png)
*정적 웹 사이트 호스팅 편집*

### 권한 설정 (Bucket Policy)

마지막으로 [권한] 탭에서 **버킷 정책(Bucket Policy)**을 추가하여 누구나 읽을 수 있게(`GetObject`) 권한을 부여했다.

```bash
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::moathon-client-dist/*"
        }
    ]
}
```

### 배포 완료!

생성된 **[버킷 웹 사이트 엔드포인트]** URL로 접속하면 Vue 애플리케이션이 정상적으로 로딩된다.

![image.png](/assets/img/posts/2025-12-27-moathon-aws-deployment/4.png)
*엔드포인트 URL*

![image.png](/assets/img/posts/2025-12-27-moathon-aws-deployment/3.png)
*연결 성공*

# 6. RDS에 데이터 적재

## 6-1. 초기 데이터 적재 (Data Seeding)

서버 DB가 비어있으므로, 로컬에서 준비한 데이터와 Fixture들을 loaddata 커맨드로 적재했다.

```bash
python manage.py migrate

# 금융상품 데이터 가져오기 (API 연동)
python manage.py sync_financial_products

# 페이크 유저 생성
python manage.py seed_fake_users_moathon --users 30 --moathons 100 --seed 42

# 금/은 데이터
python manage.py import_commodity --asset silver --path data/Silver_prices.xlsx
python manage.py import_commodity --asset gold --path data/Gold_prices.xlsx

# 뱃지 데이터
python manage.py loaddata accounts/fixtures/accounts/badge.json

# 소셜 데이터(댓글, 팔로우, 좋아요) 
python manage.py loaddata accounts/accounts_social.json
python manage.py loaddata challenges/challenges_social.json

```

## 6-2. 뱃지 이미지 경로 문제 해결

배포 후 뱃지 이미지가 엑스박스로 뜨는 문제가 발생했다.

**원인**: Vite 빌드 시 `src/assets`에 있는 이미지는 코드에서 직접 `import` 하지 않으면 번들링 과정에서 제외된다. 하지만 우리는 DB에서 이미지 파일명(String)을 받아와 동적으로 렌더링하는 방식이라 Vite가 이를 인지하지 못했다.

**해결**: 뱃지 이미지들을 `public/badges` 폴더로 이동시켰다. `public` 폴더의 내용은 빌드 시 그대로 `dist` 루트로 복사되므로, 정적 경로로 접근이 가능하다.

![뱃지 이미지를 불러오지 못함](/assets/img/posts/2025-12-27-moathon-aws-deployment/2.png)
*뱃지 이미지를 불러오지 못함*

### `public` 폴더로 이사 가기

`frontend/src/assets/badges` 폴더를 통째로 `frontend/public/badges`로 옮겼다.

- **변경 전:** `frontend/src/assets/badges/badge_achieve_3days.png`
- **변경 후:** `frontend/public/badges/badge_achieve_3days.png`

### 다시 빌드하고 S3 업로드

이제 다시 빌드하면 `dist` 폴더 안에 `badges` 폴더가 들어있다.

1. **빌드(VS code 터미널):** `npm run build`
2. **확인:** `frontend/dist/badges` 폴더가 생겼는지 확인
3. **S3 업로드:** `dist` 폴더의 모든 내용물을 AWS S3 버킷에 다시 **덮어쓰기(업로드)**

### EC2 서버 재시작

github에 push 한 코드를 적용하기 위해, 서버를 재시작한다.

1. EC2 서버 접속 (`ssh`)
2. `git pull origin main` (깃허브에서 새 코드 당겨오기)
3. `badge.json` fixture에서 url 부분을 수정했으므로, 서버에 변경된 데이터 반영 (EC2)
    
    ```bash
    python manage.py loaddata accounts/fixtures/accounts/badge.json
    ```
    
4. **`sudo systemctl restart gunicorn`** (서버 껐다 켜기)

![뱃지 이미지를 잘 불러옴](/assets/img/posts/2025-12-27-moathon-aws-deployment/1.png)
*뱃지 이미지를 잘 불러옴*

---

# 최종 아키텍처

![아키텍처](/assets/img/posts/2025-12-27-moathon-aws-deployment/19.png)
*아키텍처*

## **CSR(Client-Side Rendering) 배포 구조**

사용자는 S3 엔드포인트를 통해 접속하고, Vue 앱은 EC2의 Django 서버와 통신하며 데이터를 주고받는다.

- **Frontend:** AWS S3 (Static Hosting)
    - 사용자가 브라우저로 접속하면 S3가 `index.html`과 정적 파일들을 준다.
- **API Request:**
    - 사용자가 버튼을 누르면 브라우저가 **EC2(Django)**로 데이터를 요청한다.
- **Backend:** AWS EC2 (Ubuntu + Nginx + Gunicorn + Django)
    - Nginx가 요청을 받아 Gunicorn으로 넘기고, Django가 로직을 처리해 응답한다.
- **Database**: AWS RDS (PostgreSQL)

## 오늘의 배포 과정

### 프론트엔드 (Vue.js)

- `npm run build`로 최적화된 파일을 생성했다.
- **AWS S3**에 업로드하여 정적 웹 호스팅을 구현했다.
- `public` 폴더를 활용해 정적 에셋(뱃지) 경로 문제를 해결했다.

### 백엔드 (Django)

- **AWS EC2 (Ubuntu)** 가상 서버를 구축했다.
- **Gunicorn**과 **Systemd**를 이용해 24시간 꺼지지 않는 데몬 서버를 만들었다.
- **Nginx** 웹 서버를 붙여 요청을 효율적으로 관리하도록 했다.

### 데이터베이스 & 연동

- CORS 설정을 통해 프론트엔드와 백엔드의 보안 장벽을 뚫고 통신을 성공시켰다.
- `loaddata`를 통해 로컬에 있던 데이터(뱃지, 금융상품 등)를 서버 DB로 이관했다.

### 다음은?

이제 https:// 로 시작하는 도메인을 사용하기 위해, CloudFront를 도입해봐야겠다.

![목표 아키텍처](/assets/img/posts/2025-12-27-moathon-aws-deployment/18.png)
*목표 아키텍처*
