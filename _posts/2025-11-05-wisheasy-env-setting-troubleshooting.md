---
title: "[쉽길] 로컬 개발 환경 설정 중 DJANGO_SECRET_KEY 에러 해결"
date: 2025-11-05 09:00:00 +0900
categories: [Project, 쉽길]
tags: [Django, Troubleshooting, Debug, Environment, Configuration, SecretKey]
toc: true 
comments: true 
description: "Django 로컬 개발 환경 세팅 중 발생한 환경 변수(Secret Key) 설정 오류의 원인을 분석하고 해결하는 과정을 다룹니다."
---

로컬 서버 개발환경 세팅하는 과정에서 오류가 발생했습니다.

### 실행 과정
1. 가상환경 설정
2. requirements.txt 패키지 다운
3. .env 파일 설정
4. socialapp 설정  *<<<< 여기서 에러 발생*
5. db 업로드
6. 로컬 서버 실행
	
### CIL 코드
`python manage.py apply_socialapp --settings=config.settings.local`

### 에러 메세지
`KeyError: 'DJANGO_SECRET_KEY'`
`django.core.exceptions.ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable`

요약하자면, **'DJANGO_SECRET_KEY를 찾지 못했다'**

제가 생각한 이유(가설)로는
	1. .env의 `SECRET_KEY` 변수명과 settings/base.py의 `SECRET_KEY = env("DJANGO_SECRET_KEY")` 변수명이 일치하지 않아서
	2. SECRET KEY에 문제가 생겨서
	
아무래도 settings/base.py를 수정하는 과정에서 어긋난 것 같습니다.

(참고) 가장 마지막으로 로컬 서버 실행했을 때가 2025-10-22 입니다.

### 👍🏻 **오류 해결**
1. .env에서 변수명 변경 `SECRET_KEY` → `DJANGO_SECRET_KEY`
2. `settings/local.py` 수정

```bash
# settings/local.py
# 아래 두 줄 삭제
	# settings/base.py에 env 파일을 불러와 읽는 코드가 이미 있습니다.
	# base.py를 상속받는 local.py에서 중복하여 불러올 필요가 없으므로 삭제합니다.
env_file = os.path.join(BASE_DIR, ".env")
environ.Env.read_env(env_file)
```

### 오류 메세지 전문
    
```bash
$ python manage.py apply_socialapp --settings=config.settings.local

Traceback (most recent call last):

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\environ\environ.py", line 409, in get_value

    value = self.ENVIRON[var_name]

            ~~~~~~~~~~~~^^^^^^^^^^

  File "<frozen os>", line 679, in __getitem__

KeyError: 'DJANGO_SECRET_KEY'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\manage.py", line 23, in <module>

    main()

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\manage.py", line 19, in main

    execute_from_command_line(sys.argv)

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\django\core\management\__init__.py", line 442, in execute_from_command_line

    utility.execute()

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\django\core\management\__init__.py", line 436, in execute

    self.fetch_command(subcommand).run_from_argv(self.argv)

    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\django\core\management\__init__.py", line 262, in fetch_command

    settings.INSTALLED_APPS

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\django\conf\__init__.py", line 81, in __getattr__   

    self._setup(name)

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\django\conf\__init__.py", line 68, in _setup        

    self._wrapped = Settings(settings_module)

                    ^^^^^^^^^^^^^^^^^^^^^^^^^

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\django\conf\__init__.py", line 166, in __init__     

    mod = importlib.import_module(self.SETTINGS_MODULE)

          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "C:\Users\SSAFY\AppData\Local\Programs\Python\Python311\Lib\importlib\__init__.py", line 126, in import_module

    return _bootstrap._gcd_import(name[level:], package, level)

            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "<frozen importlib._bootstrap>", line 1204, in _gcd_import

  File "<frozen importlib._bootstrap>", line 1176, in _find_and_load

  File "<frozen importlib._bootstrap>", line 1147, in _find_and_load_unlocked

  File "<frozen importlib._bootstrap>", line 690, in _load_unlocked

  File "<frozen importlib._bootstrap_external>", line 940, in exec_module

  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\config\settings\local.py", line 3, in <module>

    from .base import *

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\config\settings\base.py", line 36, in <module>

    SECRET_KEY = env("DJANGO_SECRET_KEY") # 운영 환경에서는 반드시 설정되어야 함

                  ^^^^^^^^^^^^^^^^^^^^^^^^

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\environ\environ.py", line 207, in __call__

    return self.get_value(

            ^^^^^^^^^^^^^^^

  File "C:\Users\SSAFY\Desktop\joona\project-wisheasy\venv\Lib\site-packages\environ\environ.py", line 413, in get_value

    raise ImproperlyConfigured(error_msg) from exc

django.core.exceptions.ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable
```
