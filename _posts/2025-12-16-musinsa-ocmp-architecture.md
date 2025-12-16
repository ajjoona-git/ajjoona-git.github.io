---
title: "무신사 기술 블로그 분석: OCMP 통합 회원 시스템과 대규모 마이그레이션"
date: 2025-12-16 09:00:00 +0900
categories: [Tech, Web]
tags: [Musinsa, SystemArchitecture, Migration, Legacy, CDC, Backend, StranglerFigPattern]
toc: true 
comments: true
image: /assets/img/posts/2025-12-16-musinsa-ocmp-architecture/1.png
description: "무신사의 파편화된 회원 시스템을 하나로 통합하는 OCMP 프로젝트를 분석합니다. 10년 된 PHP 레거시를 중단 없이 마이그레이션하기 위한 'Strangler Fig' 패턴, CDC를 활용한 데이터 동기화, 그리고 결정론적 라우팅을 통한 무중단 배포 전략을 다룹니다."
---


이 글은 무신사의 파편화된 서비스들을 **하나의 ID**로 연결하기 위해 진행한 **OCMP(One Core Multi Platform)** 프로젝트에 대한 블로그 포스트를 읽고 작성했다.

## **왜 통합 회원 시스템이 필요했을까?**

무신사는 무신사 스토어뿐만 아니라 29CM, 솔드아웃(Soldout), 레이지나잇 등 다양한 패션 플랫폼을 운영하고 있다. 하지만 플랫폼 간의 통합 문제로 인해, **파편화된 경험**, **레거시의 한계**와 같은 문제가 생겼다.

- **서비스마다 다른 ID:** 고객이 무신사 스토어 아이디가 있어도, 29CM나 솔드아웃을 이용하려면 회원가입을 또 해야 했다. 이는 고객 입장에서 매우 번거로운 경험이다.
- **비효율적인 관리:** 서비스 개수만큼 회원 정보를 따로 관리하다 보니, 정보 수정이나 탈퇴 처리가 복잡하고 보안 리스크도 컸다.
- **글로벌 확장의 걸림돌:** 기존 시스템은 한국의 '본인인증(CI/DI)' 기반으로 설계되어 있었다. 이메일 기반 가입이 보편적인 글로벌 시장으로 진출하기에는 구조적인 한계가 있었다.
- **거대한 레거시(PHP):** 10년 넘게 운영된 거대한 PHP 기반 시스템에 회원 로직이 강하게 결합되어 있어, 새로운 기능을 추가하거나 분리해 내기가 매우 어렵다.
- 플랫폼별 사일로(Silo): 각 플랫폼이 독립적으로 성장하다보니, 고객 데이터와 멤버 시스템이 플랫폼별로 격리되고 접근할 수 없다.

## 무엇을 해결하려 했나?

팀 무신사는 **OCMP(One Core Multi Platform)**라는 비전 아래 세 가지 목표를 세웠다.

1. **통합된 사용자 경험 (SSO):** 한 번의 로그인(Single Sign-On)으로 무신사의 모든 서비스를 끊김 없이 이용하게 한다.
2. **유연한 아키텍처:** 새로운 브랜드나 플랫폼이 추가되어도 즉시 붙일 수 있는 '플러그 앤 플레이' 구조를 만든다.
3. **글로벌 표준 보안:** 한국식 본인인증을 넘어, 글로벌 표준 인증 방식을 지원하고 보안성을 강화한다.

## 기술적으로 어떻게 해결했나?

### ① 데이터 모델: 연합 ID 패턴 (Federated Identity)

*"운영 중인 거대한 플랫폼들의 데이터를 어떻게 중단 없이 하나로 묶느냐"*

고객이 새벽에 주문하든, 주말에 반품하든 로그인은 항상 가능해야 한다. 멤버 시스템의 중단은 치명적이고, 고객이 눈치채지 못하게 시스템을 교체해야 했다. 

**Federated Identity (연합 ID)** 패턴은 여러 개의 **서로 다른 보안 도메인(Security Domain)** 간에 사용자의 신원(Identity)을 공유하고 관리하는 아키텍처 패턴이다. 무신사는 내부의 레거시 시스템들을 하나로 묶는 전략으로 이 패턴을 사용했다. 기존 DB를 억지로 하나로 합치는 대공사(물리적 통합)를 하지 않고도, `one_uuid_mappings`라는 연결 고리를 통해 논리적으로 하나의 ID처럼 동작하게 했다.

![Federated Identity Pattern | *Microsoft Learn*](/assets/img/posts/2025-12-16-musinsa-ocmp-architecture/2.png)
*Federated Identity Pattern | Microsoft Learn*

- **작동 원리 (Workflow)**
    - 중앙(IdP)에 **Global UUID (통합 ID)**를 하나 만든다.
    - 사용자가 로그인을 하면, 시스템은 Global UUID를 기준으로 "아, 이 사람은 29CM에서는 저 계정이고, 무신사에서는 이 계정이구나"를 식별하여 연결해준다.
- **Mapping Layer (one_uuid_mappings):**
    - 기존 DB를 억지로 합치는 대신, **매핑 계층**을 두어 서로 다른 시스템의 ID를 논리적으로 연결한다.
    - 중앙의 '통합 회원 시스템 (Global UUID, 통합 ID)'이 핵심 식별 정보를 관리하고, 각 플랫폼(무신사, 29CM 등)은 이 매핑 테이블을 통해 연결된다.
    - 예를 들어, 29CM에는 'user_29'라는 ID가 있고, 무신사에는 'user_musinsa'라는 ID가 있다. (둘은 물리적으로 다른 DB에 있다.)
        - Global UUID `XYZ-001` ↔ 29CM `user_29`
        - Global UUID `XYZ-001` ↔ Musinsa `user_musinsa`

즉, DB를 억지로 합치는 '물리적 통합'의 리스크를 피하고, 각 서비스의 독립성을 존중하면서 연결성을 확보하할 수 있었다.

### ② App-to-App SSO: OS의 장벽을 넘는 보안 터널 (Universal Link + PKCE)

*"무신사 앱에 로그인하면, 29CM 앱도 자동으로 로그인되어야 한다."*

하지만 Android와 iOS는 보안 정책으로 인해 앱 간 데이터 공유가 제한되었다. 이를 해결하기 위해 **Universal Link**와 **PKCE**를 결합한 인증 터널을 도입했다.

- **PKCE (Proof Key for Code Exchange) 도입:**
    - **Code Verifier:** 29CM 앱이 로그인 시도 시, 암호화된 검증값(`code_verifier`)을 생성해 로컬에 저장한다.
    - **터널링:** 29CM 앱은 `code_challenge`(verifier를 해싱한 값)를 서버에 등록한 뒤, Universal Link를 통해 무신사 앱을 호출한다. 이 방식은 iOS 시스템 레벨에서 앱의 소유권을 검증하므로 피싱 앱의 개입을 원천 차단한다.
    - **검증 및 토큰 발급:** 무신사 앱에서 인증 후 다시 Universal Link를 통해 29CM 앱에 토큰을 전달한다. 서버는 처음에 만든 검증값(`code_verifier`)과 현재 값(`code_challenge`)이 수학적으로 쌍을 이루는지 확인하고 최종 액세스 토큰을 발급한다.

이로써 OS 샌드박스 제약을 뛰어넘으면서도, 탈취가 불가능한 안전한 SSO 환경을 구축했다.

![MUSINSA OCMP Architecture | *MUSINSA tech*](/assets/img/posts/2025-12-16-musinsa-ocmp-architecture/1.png)
*MUSINSA OCMP Architecture | MUSINSA tech*

### ③ 무결점 A/B 테스트: MurmurHash3와 자가 치유(Self-Healing)

점진적 배포 과정에서 사용자가 어떤 상황(비로그인, 기기 변경 등)에서도 **일관된 경험**을 하는 것이 중요했다.

- **결정론적 라우팅 (Deterministic Routing):**
    - Experiment System은 디바이스 단위로 고유 식별자를 발급하고 관리하며, 이 식별자를 사용자 식별자와 연결한다. 이 관계는 사용자가 여러 디바이스를 활용하거나 비로그인 상태이더라도 일관된 실험 세그먼트를 할당하는 주요 데이터이다.
    - 사용자 식별자를 **MurmurHash3 알고리즘**으로 연산하여 10,000개의 마이크로 버킷으로 나눴다. DB 조회 없이 수학적 연산만으로 0.01% 단위의 정밀하고 일관된 그룹 할당이 가능하다.
- **자가 치유 (Self-Healing) 파이프라인:**
    - 사용자가 기기를 변경하여 그룹 정보가 불일치하는 상황이 발생하면? 시스템이 이를 즉시 감지한다.
    - **10ms 이내**에 백그라운드에서 그룹 정보를 재할당(치유)하고, 사용자를 올바른 페이지로 리다이렉트한다.
    - 배포 기간 동안 관련 VOC 0건을 달성했다.

## 안정적인 런치를 위한 운영 전략

### ① 준실시간 트랜잭션 감사

데이터의 복제하는 것에 더해, 비즈니스 로직의 동일성을 보장해야 한다. 이를 위해 모든 데이터 변경 이벤트(가입, 수정, 탈퇴)를 트래픽 발생 직후 비교/검증하는 시스템을 구축하여 데이터 정합성을 100% 확보했다.

### ② AI Agent를 활용한 시나리오 검증

복잡한 유저 시나리오 테스트를 위해 **Cursor AI Agent**를 도입했다.

- 엔지니어가 "무신사 가입 -> 29CM 로그인 -> 비번 변경" 같은 시나리오를 자연어로 던지면, AI가 테스트 스크립트를 작성하고 검증한다.
- 이를 통해 사람이 놓치기 쉬운 극단적인 예외 케이스(Timeout 등)까지 사전에 잡아냈다.

### ③ 점진적 런치 (Incremental Launch)

'빅뱅 오픈'의 리스크를 피하기 위해 트래픽을 **1% → 5% → 10%** 단위로 천천히 늘렸다. 각 단계마다 로그인 성공률과 에러율을 실시간 모니터링하며, 확신이 들 때만 다음 단계로 넘어가는 돌다리 전략을 취했다.

---

### 레퍼런스

[MUSINSA tech | 하나의 ID로 모든 경험을 잇다: 팀 무신사 통합 회원 시스템 런치 여정](https://medium.com/musinsa-tech/%ED%95%98%EB%82%98%EC%9D%98-id%EB%A1%9C-%EB%AA%A8%EB%93%A0-%EA%B2%BD%ED%97%98%EC%9D%84-%EC%9E%87%EB%8B%A4-%ED%8C%80-%EB%AC%B4%EC%8B%A0%EC%82%AC-%ED%86%B5%ED%95%A9-%ED%9A%8C%EC%9B%90-%EC%8B%9C%EC%8A%A4%ED%85%9C-%EB%9F%B0%EC%B9%98-%EC%97%AC%EC%A0%95-72f5b0218c72?source=rss----f107b03c406e---4)

[Microsoft Learn | Federated Identity pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/federated-identity)