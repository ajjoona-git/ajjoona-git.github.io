---
title: "[둥지] FastAPI + GitHub Actions: Pydantic 환경 변수(ValidationError) 트러블슈팅"
date: 2026-02-25 10:00:00 +0900
categories: [Projects, 둥지]
tags: [FastAPI, Pydantic, GitHubActions, CI/CD, Troubleshooting, Pytest, EnvironmentVariables]
toc: true
comments: true
description: "FastAPI 프로젝트에 GitHub Actions CI를 도입하며 겪은 환경 변수 주입 문제를 해결합니다. Pydantic의 엄격한 타입 검증(ValidationError)으로 인한 CI 빌드 실패 원인과, 더미 파일(.env.example) 및 GitHub Secrets를 활용한 해결 과정을 공유합니다."
---

FastAPI와 `pydantic-settings` 모듈의 조합은 애플리케이션 시작 시점에 필수 환경 변수가 정확한 타입으로 존재하는지 검증해 준다.
하지만 이 '엄격함' 때문에, 로컬 PC에서는 완벽하게 돌아가던 테스트 코드가 **CI 서버(GitHub Actions)에만 올라가면 실패하는 현상**을 자주 겪게 된다.

이번 포스트에서는 '둥지' 프로젝트의 통합 테스트 및 CI/CD 파이프라인 구축 과정에서 마주한 **환경 변수 누락 및 Pydantic 검증 에러(ValidationError)**의 연쇄적인 트러블슈팅 과정을 기록한다.

---

### 1. 로컬 환경 - 통합 테스트 Skip 현상

- **발생 로그:** 로컬 환경에서 `make test` (`uv run pytest`) 실행 시, 외부 API(행정안전부 주소 검색 등)를 호출하는 통합 테스트(`test_juso_client_integration.py`)가 실행되지 않고 `s` (Skip) 처리되었다.
    
    ```bash
    # 발생 로그
    collected 25 items
    
    tests\clients\test_juso_client.py ...........                                                          [ 44%]
    tests\clients\test_juso_client_integration.py sssssssssss                                              [ 88%]
    tests\test_sample.py ...                                                                               [100%]
    ```
    
- **원인:** 통합 테스트 코드 내부에 `JUSO_API_KEY`를 찾지 못할 경우 실패(`F`)가 아닌 스킵(`s`)하도록 방어 로직(`pytest.skip("JUSO_API_KEY not found")`)이 작성되어 있었다. 기존 환경 변수 파일명의 불일치로 API 키가 로드되지 않았던 것이다.
- **해결:** 로컬 테스트 프레임워크가 정상적으로 읽을 수 있도록 파일명을 `.env`에서 `.env.local`로 수정하여 API 키가 올바르게 주입되도록 조치했다.

### 2. CI 환경 (GitHub Actions) - 환경 변수 누락 에러

- **현상:** CI 파이프라인에서 테스트 실행 시 Pydantic의 `ValidationError`가 대량으로 발생하며 빌드 실패(`Exit code 2`).
    
    ```bash
    # 발생 로그 (12개의 필수 환경 변수 누락)
    E   pydantic_core._pydantic_core.ValidationError: 12 validation errors for Settings
    E   SECRET_KEY
    E     Field required [type=missing, input_value={}, input_type=dict]
    ...
    E   POSTGRES_USER
    E     Field required [type=missing, input_value={}, input_type=dict]
    ```
    
- **원인:** 깃허브 레포지토리에는 보안상 
실제 `.env.local` 파일이 올라가지 않는다. 따라서 텅 빈 우분투 러너(Runner)가 테스트를 돌리기 위해 `config.py`의 `Settings` 객체를 생성하는 순간, 필수 값을 찾지 못해 대량의 검증 에러를 발생시킨 것이다.
- **1차 해결:** `ci.yml`의 테스트 단계에 `cp .env.example .env.local` 명령어를 추가하여 가짜(Dummy) 설정 파일을 복사하여 CI 서버가 이를 읽도록 유도했다.

---

### 3. CI 환경 (GitHub Actions) - Pydantic 타입 파싱 에러

- **현상:** 더미 파일을 복사하도록 조치한 후 다시 CI를 돌렸으나, 이번에는 빈 문자열을 숫자로 변환하지 못해 발생하는 **타입 파싱 에러**가 발생했다.
    
    ```bash
    # 발생 로그
    E   pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
    E   ACCESS_TOKEN_EXPIRE_MINUTES
    E     Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='', input_type=str]
    ```
    
- **원인:** `.env.example` 파일 내부에 `ACCESS_TOKEN_EXPIRE_MINUTES=` 처럼 값이 
비어있었다. Pydantic은 값이 비어있는 환경 변수를 **빈 문자열(`""`)**로 인식한다. 문자열(`str`) 타입은 에러가 나지 않지만, `int`나 `bool` 등의 타입은 빈 문자열을 형변환할 수 없어 `int_parsing` 에러가 발생한 것이다.
- **2차 해결:** 깃허브에 올라가는 `.env.example` 
파일의 비어있던 정수형/논리형 설정값에 Pydantic이 파싱할 수 있는 **더미 값(Dummy Value)**을 채워 넣었다. (예: `ACCESS_TOKEN_EXPIRE_MINUTES=1440`)

---

### 4. CI 환경 (GitHub Actions) - 외부 API 통합 테스트 처리 및 API 키 연동

- **현상:** 이제 Pydantic 검증은 통과했지만, 로컬에서 겪었던 **통합 테스트 Skip 현상**이 CI 서버에서도 똑같이 발생했다. `uv run pytest -m integration` 명령어 실행 시 11개의 테스트가 모두 Skip 되었다.
    
    ```bash
    # 발생 로그
    collected 25 items / 14 deselected / 11 selected
    
    tests\clients\test_juso_client_integration.py sssssssssss                                              [100%]
    ========================================================= 11 skipped, 14 deselected in 0.09s =======
    ```
    
- **해결 방안:** 실제 API 키를 코드나 템플릿 파일에 노출할 수는 없으므로, **GitHub Secrets**를 활용했다.
1. **GitHub Secrets 설정:** 실제 행안부 API 키를 코드에 노출하지 않기 위해 깃허브 레포지토리의 **Settings > Secrets and variables > Actions** 메뉴에 `JUSO_API_KEY`를 안전하게 등록.
2. **Workflow 파일(`ci.yml`) 수정:** CI 구동 시 깃허브 비밀 금고에서 값을 꺼내 환경 변수로 직접 주입하도록 구성.

```yaml
# ci.yml 적용 코드
- name: Run tests
  env:
    JUSO_API_KEY: ${{ secrets.JUSO_API_KEY }}  # Secrets에서 주입
  run: |
    cp .env.example .env.local
    uv run pytest -v
```

이 조치 이후, CI 서버에서도 외부 API 통합 테스트가 Skip 없이 정상적으로 `PASSED` 되었다. 🎉

---

## 마치며

결국 CI 환경에서 로직 테스트(pytest)를 무사히 통과시키려면, 진짜 운영 환경과 무관하더라도 **Pydantic의 엄격한 문지기 역할을 통과할 수 있는 형식에 맞는 가짜(Dummy) 데이터**가 필요하다.

1. CI 워크플로우 실행 시 `cp .env.example .env.local`로 껍데기 환경을 만들어 줄 것.
2. `.env.example` 안의 변수를 `KEY=` 형태의 빈칸으로 두지 말 것. 정수형에는 `1`, 논리형에는 `false` 등을 명시적으로 적어두어야 CI 에러를 예방할 수 있다.
3. 실제 동작에 필요한 외부 API 키 등은 GitHub Secrets를 통해 동적으로 주입할 것.

Pydantic의 이 엄격함이 CI 구축 초기에는 귀찮게 느껴질 수 있지만, 런타임에 발생할 수 있는 치명적인 환경 변수 설정 오류를 빌드 타임에 완벽하게 차단해 주는 든든한 보호막임을 다시 한번 깨달았다.