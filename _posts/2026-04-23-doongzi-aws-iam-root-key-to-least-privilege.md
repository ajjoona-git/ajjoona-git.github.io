---
title: "[둥지] IAM 권한 세분화: root 액세스 키를 용도별 사용자로 분리하기"
date: 2026-04-23 12:00:00 +0900
categories: [Project, 둥지]
tags: [AWS, IAM, Security, S3, EC2, SSM, Backend, DevOps, LeastPrivilege]
toc: true
comments: true
description: "root 계정 액세스 키 하나로 모든 AWS 작업을 처리하던 구조를 환경(Dev/Prod)과 기능(Issuance/OCR/CI)별로 IAM 사용자를 세분화하여 교체했습니다. 최소 권한 원칙을 적용한 설계 과정과 EC2 IAM Role 전환, DeleteObject·HeadObject 권한 이슈까지 다룹니다."
---

운영 서버를 처음 세팅할 때, AWS 자격 증명을 가장 빠르게 해결하는 방법은 root 계정의 액세스 키를 발급해 `.env`에 박아두는 것입니다. 개발 초기에는 이 방식으로 빠르게 진행했지만, 실제 서비스 배포를 앞두고 이 구조를 전면 교체했습니다.

---

## root 액세스 키 하나가 모든 곳에

초기 구조에서 `AWS_ACCESS_KEY_ID`와 `AWS_SECRET_ACCESS_KEY`는 root 계정의 키였고, 동일한 키가 여러 곳에 복사되어 있었습니다.

- EC2 서버의 `.env` 파일
- 로컬 개발 `.env.local`
- GitHub Actions Secrets
- 로컬에서 실행하는 Celery 워커의 환경 변수

### 초기 구조의 문제

이 구조의 문제는 단순히 "키가 많이 퍼져 있다"는 것이 아닙니다.

### 1. 키 하나로 AWS 계정 전체를 제어할 수 있습니다.

root 계정은 IAM 설정 변경, EC2 인스턴스 삭제, RDS 스냅샷 공개, 결제 정보 조회 등 계정의 모든 작업을 수행할 수 있습니다. `.env` 파일이 실수로 GitHub에 올라가거나, 서버가 해킹당해 파일이 유출되면 AWS 계정 자체가 탈취됩니다.

### 2. 어떤 키가 어디서 왔는지 추적할 수 없습니다.

CloudTrail 로그를 봐도 "이 S3 요청이 EC2에서 온 건지, GitHub Actions에서 온 건지, 로컬 워커에서 온 건지"를 구분할 방법이 없습니다. 침해 발생 시 피해 범위를 특정할 수 없다는 뜻입니다.

### 3. 키를 교체하거나 차단하면 모든 환경이 멈춥니다.

키 하나를 비활성화하는 순간 EC2 서버, CI/CD 파이프라인, 로컬 개발 환경이 동시에 중단됩니다. 특정 키만 선별적으로 차단하는 것이 불가능합니다.

---

## 설계 원칙: 최소 권한 + 격리

교체의 기준은 두 가지였습니다.

***최소 권한(Least Privilege)***

각 주체에게 업무 수행에 꼭 필요한 권한만 부여합니다. OCR 워커가 이미지를 읽기만 하면 된다면 `GetObject`만, 업로드 워커가 파일을 올리기만 하면 된다면 `PutObject`만 줍니다.

***격리(Isolation)***

환경(Dev/Prod)이 다르거나 기능(Issuance/OCR)이 다르면 키도 다릅니다. 키 하나가 유출되더라도 그 역할에 한정된 피해로 막을 수 있습니다.

---

## EC2에는 액세스 키 대신 IAM Role

EC2 서버에서 S3에 접근하기 위해 `.env`에 키를 넣는 방식을 가장 먼저 교체했습니다. EC2는 IAM Role을 인스턴스에 직접 부착할 수 있습니다.

### IAM Role 동작 방식

EC2 인스턴스에 Role을 부착하면, 인스턴스 내부의 메타데이터 서버가 단기 유효한 임시 자격 증명을 주기적으로 자동 발급합니다. boto3 같은 AWS SDK는 이 메타데이터 서버를 자동으로 조회하기 때문에, 코드 어디에도 키를 명시하지 않아도 됩니다.

```python
import boto3

# 인증 정보 없이도 EC2에 부여된 역할을 자동으로 상속받아 실행됨
s3_client = boto3.client('s3', region_name='ap-northeast-2')
```

### 왜 키보다 Role이 나은가

- **유출 표면 제거:** `.env`에 키가 없으면 파일이 유출되더라도 AWS 자격 증명은 포함되지 않습니다.
- **즉각적인 권한 제어:** 키를 비활성화하고 서버를 재시작하는 절차 없이, IAM 콘솔에서 정책만 수정하면 실행 중인 서버의 권한이 즉시 변경됩니다.
- **임시 자격 증명:** Role이 발급하는 자격 증명은 수 시간마다 자동 갱신됩니다. 장기 유효한 정적 키와 달리, 탈취당해도 금방 만료됩니다.
- **비용 없음:** 별도의 키 관리 서비스를 쓰지 않아도 됩니다.

### 부여한 권한

- Dev EC2: S3(`doongzi-dev` 버킷)
- Prod EC2: S3(`doongzi-prod` 버킷) + SSM Session Manager 접근 + EC2 상태 조회

Prod EC2에 SSM 권한이 필요한 이유는 GitHub Actions에서 `ssm send-command`로 배포 명령을 내릴 때, EC2 인스턴스가 SSM Agent를 통해 해당 명령을 받아 실행하는 구조이기 때문입니다. EC2 Role에 SSM 수신 권한이 없으면 명령이 전달되지 않습니다.

---

## 워커와 파이프라인에서는 용도별 IAM 사용자 분리

EC2처럼 Role을 붙일 수 없는 환경(로컬 PC, GitHub Actions, 로컬 Celery 워커)은 IAM 사용자를 개별 생성하고 최소 권한 정책을 인라인으로 부여했습니다.

### 서비스 워커: 환경과 기능으로 분리

| 사용자명 | 타겟 버킷 | 권한 | 역할 |
|---|---|---|---|
| dev-issuance-worker | doongzi-dev, doongzi-local | `PutObject`, `ListBucket` | 개발 환경 문서 업로드 전용 |
| dev-ocr-worker | doongzi-dev, doongzi-local | `GetObject`, `ListBucket` | 개발 환경 이미지 읽기·분석 전용 |
| prod-issuance-worker | doongzi-prod | `PutObject`, `ListBucket` | 운영 환경 문서 업로드 전용 |
| prod-ocr-worker | doongzi-prod | `GetObject`, `ListBucket` | 운영 환경 이미지 분석 전용 |

issuance(업로드)와 OCR(읽기) 워커를 같은 계정으로 묶지 않은 이유가 있습니다. OCR 워커의 키가 유출되더라도 `GetObject`만 있으면 파일을 읽을 수만 있고, 다른 파일을 업로드하거나 기존 파일을 덮어쓰는 것은 불가능합니다. 사고의 영향 범위가 읽기 접근으로 한정됩니다.

마찬가지로 Dev 워커와 Prod 워커의 키를 분리했기 때문에, 개발 환경 키가 유출되더라도 운영 데이터(`doongzi-prod` 버킷)에는 접근할 수 없습니다.

### 자동화 및 로컬 개발

| 사용자명 | 권한 | 특이 사항 |
|---|---|---|
| github-actions | `doongzi-prod`, `doongzi-dev` S3 `PutObject` + SSM `SendCommand` | CD 파이프라인 전용 |
| local-backend | `doongzi-local` S3 `Put`, `Get`, `Delete`, `List` | 로컬 전용 버킷만. `DeleteObject` 포함 |

`github-actions` 사용자는 CD 파이프라인에서 두 가지 작업만 합니다. Compose 파일을 S3에 올리는 것(`PutObject`)과 SSM을 통해 EC2에 배포 명령을 내리는 것(`SendCommand`)입니다. S3 읽기나 다른 EC2 조작 권한은 없습니다.

`local-backend`에만 `DeleteObject`를 부여한 이유는 로컬 테스트 후 잔여 파일을 정리하기 위해서입니다. 운영·개발 워커에는 삭제 권한이 없어, 코드 버그로 인한 데이터 손실을 방지했습니다.

### IAM 정책 예시: prod-ocr-worker

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::doongzi-prod/issuance",
        "arn:aws:s3:::doongzi-prod/issuance/*"
      ]
    }
  ]
}
```

버킷 자체(`arn:aws:s3:::doongzi-prod/issuance`)와 버킷 안의 객체(`arn:aws:s3:::doongzi-prod/issuance/*`) 두 ARN을 모두 명시해야 합니다. `ListBucket`은 버킷 레벨, `GetObject`는 객체 레벨 권한이기 때문입니다.

---

## 트러블슈팅

### `HeadObject` 권한 이슈

파일 존재 여부를 확인하기 위해 boto3의 `head_object`를 호출하는 코드가 있었습니다.

```python
try:
    s3_client.head_object(Bucket=bucket, Key=key)
    return True
except ClientError:
    return False
```

이 코드가 IAM 정책에 `s3:GetObject`가 있음에도 403 오류를 냈습니다. `s3:HeadObject`라는 별도 Action이 필요하다고 판단해 정책에 추가했지만 여전히 실패했습니다.

**원인**

`s3:HeadObject`라는 IAM Action은 존재하지 않습니다. AWS 문서에 따르면 `HeadObject` API 호출에 필요한 IAM 권한은 `s3:GetObject`입니다. 오류가 계속된 이유는 `ListBucket`이 빠져 있었기 때문이었습니다.

`head_object`는 내부적으로 객체가 없을 때 버킷 목록을 조회하는 동작을 포함하는데, 이때 `s3:ListBucket`이 없으면 403 대신 다른 오류가 발생합니다. `ListBucket`을 정책에 추가하자 정상 동작했습니다.

정리하면 `head_object` 호출에 필요한 권한은 `s3:GetObject` + `s3:ListBucket`이고, `s3:HeadObject`는 IAM에 존재하지 않는 Action입니다.

---

## 마치며

### 최종 구조 요약

```
EC2 (Dev)  → IAM Role: S3(doongzi-dev) + SSH (pem key)
EC2 (Prod) → IAM Role: S3(doongzi-prod) + SSM + EC2

로컬 Celery 워커
  ├─ dev-issuance-worker  → doongzi-dev PutObject + ListBucket
  ├─ dev-ocr-worker       → doongzi-dev GetObject + ListBucket
  ├─ prod-issuance-worker → doongzi-prod PutObject + ListBucket
  └─ prod-ocr-worker      → doongzi-prod GetObject + ListBucket

GitHub Actions
  └─ github-actions → doongzi-prod PutObject + SSM SendCommand

로컬 백엔드
  └─ local-backend → doongzi-local Put + Get + Delete + List

root 계정 액세스 키 → 전부 삭제
```

이 구조에서 키 유출이 발생하더라도, 해당 사용자의 키만 즉시 비활성화하면 나머지 환경과 기능은 영향을 받지 않습니다. 각 키가 접근할 수 있는 버킷과 권한이 다르기 때문에 피해 범위도 명확하게 한정됩니다.

