---
title: "[둥지] GitHub Actions CD 파이프라인 구축과 SSM 트러블슈팅"
date: 2026-04-23 11:00:00 +0900
categories: [Project, 둥지]
tags: [GitHubActions, CD, AWS, SSM, Docker, Troubleshooting, CI/CD, Backend, DevOps, S3]
toc: true
comments: true
image: /assets/img/posts/2026-04-23-doongzi-github-actions-cd-troubleshooting/1.png
description: "SSH 없는 Keyless Prod 환경에서 GitHub Actions CD 파이프라인을 구성하며 마주한 세 가지 트러블슈팅을 기록합니다. SSM Waiter의 100초 하드코딩 타임아웃, /bin/sh의 pipefail 미지원, ssm-user와 ubuntu 간 권한 격리, 그리고 SSH 없이 Compose 파일을 EC2로 전달하는 S3 경유 방식까지 다룹니다."
---

[이전 포스트](/posts/doongzi-prod-infrastructure)에서 SSH 없이 SSM으로만 접근하는 Prod EC2를 구축했습니다. 이번에는 GitHub Actions에서 이 서버로 자동 배포하는 CD 파이프라인을 구성하며 마주한 문제들을 기록합니다.

---

## CD 파이프라인 전체 구조

GitHub Actions를 컨트롤 타워로 삼고, **Docker Hub → S3 → SSM → EC2** 순으로 흐르는 Pull 기반 배포 구조를 채택했습니다.

```
CI 통과
  └─ Docker 이미지 빌드 → Docker Hub Push (SHORT_SHA 태그)
  └─ Compose 설정 파일 → S3 업로드
  └─ SSM send-command → EC2 내부에서:
        S3에서 Compose 파일 Pull
        alembic upgrade head (마이그레이션)
        docker compose pull + up -d
```


## 트러블슈팅

### 이슈 1: SSM Waiter의 100초 하드코딩 타임아웃

**현상**

`aws ssm wait command-executed`로 배포 완료를 기다리는 중, Docker 이미지 Pull이나 Alembic 마이그레이션이 조금 길어지면 Actions 로그에 실패가 뜨는데 실제 EC2에서는 배포가 정상 진행 중인 상황이 반복됐습니다.

**원인**

`aws ssm wait command-executed`는 내부적으로 **5초 간격 × 20회 = 최대 100초**로 하드코딩되어 있습니다. 초과하면 Waiter가 예외를 던지고 Actions 스텝이 실패로 기록됩니다. CI/CD의 결과(Success/Fail)가 실제 배포 상태와 1:1로 일치해야 한다는 원칙을 위반합니다.

**해결: 커스텀 폴링 루프**

기본 Waiter를 버리고 Bash로 직접 상태를 폴링하도록 교체했습니다.

```bash
for i in {1..40}; do
  STATUS=$(aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "${{ secrets.PROD_EC2_INSTANCE_ID }}" \
    --query "Status" --output text 2>/dev/null || echo "Pending")

  if [ "$STATUS" == "Success" ]; then
    echo "Deployment succeeded on EC2!"
    exit 0
  elif [[ "$STATUS" =~ ^(Failed|Cancelled|TimedOut)$ ]]; then
    echo "::error::Deployment failed with status: $STATUS"
    # StandardErrorContent 출력 후 exit 1
    exit 1
  fi

  sleep 15
done

echo "::error::Deployment verification timed out after 10 minutes."
exit 1
```

15초 간격 × 40회 = **최대 10분**으로 여유를 확보했고, 실패 시에는 `StandardErrorContent`를 Actions 로그로 긁어와 CloudWatch 없이 디버깅 가시성을 유지했습니다.


### 이슈 2: `/bin/sh`의 `pipefail` 미지원

**현상**

SSM `send-command`가 배포 스크립트 시작과 동시에 에러를 뱉으며 실패했습니다.

```
/bin/sh: Illegal option -o pipefail
```

**원인**

SSM `AWS-RunShellScript`는 기본적으로 `/bin/sh`로 스크립트를 실행합니다. `set -o pipefail`은 Bash 전용 옵션이라 `/bin/sh`(dash)에서는 지원하지 않습니다. 로컬에서는 bash로 테스트하다 보니 이 차이를 간과했습니다.

**해결**

`pipefail`을 제거하고 `/bin/sh`에서도 동작하는 `set -eu`로 대체했습니다.

```bash
# 변경 전
set -euo pipefail

# 변경 후 (sh 호환)
set -eu
```

`-e`: 에러 발생 시 즉시 종료  
`-u`: 미정의 변수 참조 시 즉시 종료

`pipefail`이 빠졌지만, 파이프(`|`)를 쓰는 명령이 없는 단순 순차 스크립트였기 때문에 실질적 차이는 없었습니다.


### 이슈 3: ssm-user와 ubuntu 사용자의 권한 격리

**현상**

SSM을 통해 EC2에서 생성한 파일과 디렉터리가 `ssm-user` 소유로 만들어졌습니다. 이후 `ubuntu` 사용자가 해당 파일에 접근하거나 docker compose 명령을 실행할 때 권한 오류가 발생했습니다.

**원인**

SSM `send-command`는 `ssm-user`라는 별도 시스템 계정으로 명령을 실행합니다. Ubuntu 인스턴스의 기본 운영 사용자인 `ubuntu`와는 독립적입니다.

**해결**

모든 배포 파일 경로를 `/home/ubuntu/doongzi`로 단일화하고, 소유권을 `ubuntu:ubuntu`로 통일했습니다.

```bash
# 소유권 정리
sudo chown -R ubuntu:ubuntu /home/ubuntu/doongzi

# 이후 모든 배포 작업은 ubuntu 컨텍스트에서
sudo -E docker compose --env-file ../.env.prod -f docker-compose.yml -f docker-compose.cloud.yml up -d
```

`sudo -E` 옵션은 현재 셸의 환경 변수(`IMAGE_TAG` 등)를 sudo 컨텍스트로 전달합니다.


### 이슈 4: Compose 파일 동기화 누락 (SSH 없는 환경의 파일 전달 문제)

**현상**

`docker-compose.cloud.yml`을 수정했는데 EC2 서버가 변경 전 파일을 그대로 참조해 배포 설정이 반영되지 않았습니다.

**원인과 고려 대안**

Prod 서버는 보안상 22번 포트가 닫힌 Keyless 환경입니다. 로컬이나 GitHub Actions에서 직접 파일을 전달하는 전통적인 방법(`scp`)을 쓸 수 없었습니다.

| 대안 | 문제점 |
|---|---|
| SSH를 열고 `scp` 액션 사용 | 보안 원칙 훼손 |
| EC2 내부에서 `git fetch`/`checkout` | 서버에 GitHub 인증 키를 남겨야 하는 보안 부담 |
| **S3를 경유하는 방식** | **추가 비밀 키 없음, 기존 IAM 권한 재활용** |

**결정: S3 경유**

GitHub Actions 러너와 EC2 모두 이미 적절한 AWS IAM 권한을 가지고 있다는 점을 활용했습니다.

```bash
# GitHub Actions: Compose 파일을 S3에 업로드
aws s3 cp deploy/docker-compose.cloud.yml \
  s3://${{ secrets.PROD_S3_BUCKET_NAME }}/_deploy/docker-compose.cloud.yml

# EC2 내부 (SSM 명령): S3에서 내려받아 사용
aws s3 cp s3://${PROD_S3_BUCKET_NAME}/_deploy/docker-compose.cloud.yml .
```

기존 운영 S3 버킷 안에 `_deploy/` 전용 폴더를 만들어 유저 데이터(업로드 파일 등)와 인프라 설정을 논리적으로 격리했습니다. 새 버킷 생성 없이 최소한의 변경으로 해결했습니다.

---

## 정리

| 이슈 | 원인 | 해결 |
|---|---|---|
| SSM Waiter 조기 실패 | 100초 하드코딩 한계 | Bash 커스텀 폴링 루프 (15초 × 40회) |
| `pipefail` 오류 | SSM 기본 셸이 `/bin/sh` (dash) | `set -eu`로 교체 |
| 권한 격리 | ssm-user ≠ ubuntu | 배포 경로 단일화 + `chown -R ubuntu:ubuntu` |
| Compose 파일 미전달 | SSH 없는 Keyless 환경 | GitHub Actions → S3 → EC2 경유 |


