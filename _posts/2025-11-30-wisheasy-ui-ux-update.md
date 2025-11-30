---
title: "[쉽길] 역 정보 및 경로 안내 UI/UX 대개편"
date: 2025-11-30 09:00:00 +0900
categories: [Projects, 쉽길]
tags: [Frontend, Backend, UI/UX, API, Refactoring]
toc: true                            # 이 게시글에 플로팅 목차 표시
comments: true                         # 이 게시글에 Giscus 댓글 창 표시
image: /assets/img/posts/2025-11-30-wisheasy-ui-ux-update/9.png # (선택) 대표 이미지
---

## 📝 [개발 일지] 역 정보 및 경로 안내 서비스 고도화

오늘 하루 동안 **프론트엔드 UI/UX 대개편**부터 **백엔드 데이터 처리 로직 수정**, **버그 수정**까지 많은 작업을 했다. 오늘이 마지막 작업이길 바라면서…

### 0. 역 상세 편의시설 API 

역 이름을 포함한 API 요청을 보내면, 편의시설 정보를 받아볼 수 있는 API 가 구현되었다.

역 상세 편의시설 조회 시,

```
GET /api/stations/{station_id}/facilities/?line_id={line_id}

```

- `{station_id}`: 선택한 역의 ID
- `line_id`: 멀티 라인인 역이면 필터용, 단일 라인이면 생략 가능
- 응답 배열을 돌면서:
    - `facility_name` + `detail_loc`로 상세 편의시설 리스트 구성
    - `station_name`, `line_name`은 화면 상단 정보 등에 활용


### 1. 역 상세 정보 페이지 (`station_info`)

- **API 연동 및 목업 제거**: 기존 더미 데이터(Mock Data) 기반의 로직을 제거하고, 실제 백엔드 API와 연동하여 실시간으로 역 정보를 불러오도록 전면 수정함.
- **UI 디자인 개편:** 불필요한 탭(Tab) 구조를 제거하고 **단일 뷰(Single View)** 형태로 정보 구조 단순화.
    - 호선 정보, 실시간 도착 정보 탭 삭제
    - 호선 정보는 역이름 밑에 뱃지 형태로 제공
- **호선별 시설 정보 분리**: 환승역 조회 시, 편의시설 정보가 섞이지 않고 **호선별로 섹션이 나뉘어 표시**되도록 로직 개선 (`Promise.all` 병렬 호출 적용).
    - 다중 호선을 가진 역의 경우 각 호선별로 편의시설 API를 호출함
- **편의시설 필터링**: 상세 페이지용(전체 표시)과 경로 안내용(필수 시설만 표시) 필터링 로직 분리 구현.

![강남역](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/13.png)
*강남역*

![건대입구](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/12.png)
*건대입구*

![건대입구](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/11.png)
*건대입구*

---

### 2. 경로 안내 페이지 내 편의시설 모달 수정 (route)

- 목업 데이터 삭제
- 출발역, (환승역,) 도착역 정보를 받아와 각 역의 편의시설 정보를 api 호출함
    - 다중 호선을 가진 역의 경우 각 호선별로 편의시설 API를 호출함
    
![BEFORE (목업 데이터)](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/10.png)
*BEFORE (목업 데이터)*

![AFTER (환승역) 호선별로 편의시설 정보 제공](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/9.png)
*AFTER (환승역) 호선별로 편의시설 정보 제공*

![AFTER 환승역 없는 경로](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/8.png)
*AFTER 환승역 없는 경로*


---

### 3. 경로 안내 페이지 (`route`)

- **프로그레스 바 UI 전면 리뉴얼 (Subway Map Style)**:
    - 기존의 단순 진행 바를 **지하철 노선도 스타일**로 디자인 변경.
    - 트랙을 둥근 라인으로 교체하고, 역 마커를 심플한 점(Dot) 형태로 변경.
    - **환승역 마커 추가**: 출발/도착역뿐만 아니라 경로상의 **환승역**을 동적으로 생성하고, 호선별 고유 색상 적용.
    - **열차 아이콘 고도화**: 입체적인 핀(Pin) 스타일 디자인 및 부드러운 이동 애니메이션(`transition`) 적용.
    - 역 이름 텍스트 정렬 높이 보정 및 상단 배치로 가독성 확보.
- **지시문 아이콘 시각화**: 텍스트 분석 로직을 통해 이동 수단(에스컬레이터, 승차, 도보 등)에 맞는 아이콘을 동적으로 표시.
- **미사용 UI 제거**: MVP 스펙 조정에 따라 '구간별 소요 시간' 표시 영역 삭제.

**경로안내 아이콘 내용이랑 맞추기**

![‘승차’](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/7.png)
*‘승차’*

![‘에스컬레이터’](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/6.png)
*‘에스컬레이터’*

![‘완료’](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/5.png)
*‘완료’*

**경로안내 헤더 환승역 추가, 색깔 호선별로 맞추기**

![환승역 추가 및 호선색 매칭](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/4.png)
*환승역 추가 및 호선색 매칭*

![디자인 수정](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/3.png)
*디자인 수정*

---

### 4. 백엔드 및 공통 로직

- **검색 자동완성 버그 수정**: 리스트에서 역 선택 시 검색창이 채워진 후 리스트가 다시 열리는 오류 해결 (`isStationSelected` 플래그 도입).
- **API 응답 구조 개선 (`views.py`)**:
    - 역 검색 API: `station_id` 및 상세 호선 리스트(`lines`) 반환 필드 추가.
    - 경로 탐색 뷰: 환승역 리스트 및 호선 정보를 추출하여 템플릿으로 전달하는 로직 구현.
- **코드 리팩토링**: 공통적으로 사용되는 검색 및 시설 조회 함수를 `search-util.js`로 분리하여 코드 재사용성 향상.
- **데이터 정합성**: CSV 데이터 내 오타 수정 ('엘레베이터' → '엘리베이터').

![길찾기](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/2.gif)
*길찾기*

![역 정보](/assets/img/posts/2025-11-30-wisheasy-ui-ux-update/1.gif)
*역 정보*