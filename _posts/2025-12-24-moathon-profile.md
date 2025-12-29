---
title: "[모아톤] 프로필 페이지 구현과 데이터 동기화 이슈 해결 (Pinia, Serializer)"
date: 2025-12-24 09:00:00 +0900
categories: [Projects, 모아톤]
tags: [Django, Vue.js, Pinia, Troubleshooting, Serializer, API, FormData, Refactoring]
toc: true 
comments: true
image: /assets/img/posts/2025-12-24-moathon-profile/3.png
description: "회원가입 후 온보딩과 프로필 수정 기능을 구현하면서 발생한 Pinia 상태 동기화 문제, 이미지 경로 처리, 그리고 Serializer 유효성 검증 충돌 문제를 해결한 트러블슈팅 로그입니다."
---

오늘의 작업 목표는 **"유저 데이터 흐름의 완성"**이었다.
회원가입 후 이어지는 온보딩(추가 정보 입력)부터 마이페이지에서의 프로필 수정까지, 프론트엔드와 백엔드가 데이터를 주고받는 과정에서 발생한 동기화 문제와 유효성 검증 오류들을 하나씩 해결해 나갔다.

실무에서 빈번하게 마주칠 법한 이슈들을 정리해 둔다.

---

## 트러블슈팅 로그 (Troubleshooting Log)

### 1. Pinia 상태 동기화 이슈 (Data Synchronization)

- **상황 (Problem):**
  회원가입 후 온보딩 페이지에서 금융 정보를 입력하고 저장(`PUT`)했다. DB에는 정상적으로 저장되었으나, 막상 메인 페이지나 상세 페이지로 이동하면 **Pinia Store의 `user` 객체에는 방금 입력한 정보가 반영되지 않은(누락된) 상태**였다.

- **원인 (Cause):**
  백엔드 API가 저장 성공 시 단순히 성공 메시지(`{"onboarding_completed": True}`)만 반환하고 있었고, 프론트엔드에서는 이 응답만 받고 Store 상태를 업데이트하는 로직이 빠져 있었다. 즉, **DB는 최신 상태인데 Store는 과거 상태**인 불일치가 발생한 것이다.

- **해결 (Solution):**
  저장(`updateProfile`) 액션이 성공한 직후, 내부에서 **`getProfile()` 액션을 호출하여 DB의 최신 데이터를 강제로 다시 불러와 Store를 갱신**하도록 수정했다. (Command-Query 분리 패턴 적용)

```javascript
// frontend/src/stores/accounts.js

const updateProfile = async function (payload) {
  try {
    const res = await axios({ 
      method: 'put', 
      url: `${API_URL}/accounts/profile/`, 
      data: payload,
      // ... header config 
    })

    // [Fix] DB 저장 성공 후, 최신 유저 정보를 다시 조회하여 State 갱신
    await getProfile() 

    return res.data
  } catch (err) {
    console.error(err)
  }
}
```

### 2. 이미지 경로 404 이슈 (Static Files)

- **상황**: 프로필 이미지가 DB에는 상대 경로(`/media/profiles/img.pn`g)로 저장되어 있는데, 프론트엔드 화면에서는 이미지가 깨져서(엑박) 나왔다.

- **원인**: 브라우저는 이미지 경로를 찾을 때 현재 도메인(프론트엔드: `localhost:5173`)을 기준으로 찾는다. 하지만 실제 이미지는 백엔드 서버(`localhost:8000`)에 있기 때문에 404 에러가 발생했다.

- **해결**: 프론트엔드에 `getImageUrl` 유틸리티 함수를 만들었다. 경로가 `http`로 시작하지 않는 상대 경로라면, 앞에 백엔드 도메인(`VITE_API_URL`)을 붙여주도록 처리했다.

```js
// Vue Component Script (utils)

const getImageUrl = (path) => {
  if (!path) return '/default-profile.png' // 이미지가 없으면 기본 이미지
  if (path.startsWith('http')) return path // 절대 경로면 그대로 사용

  // [Fix] 백엔드 주소(VITE_API_URL)를 prefix로 붙임
  return `${import.meta.env.VITE_API_URL}${path}`
}
```

### 3. Serializer 유효성 검증 충돌 (Validation Conflict)

- **상황**: **'온보딩'**은 프로필 사진을 제외한 모든 금융 정보(자산, 연봉 등)가 필수여야 하고, **'프로필 수정'**은 일부만 수정 가능해야 한다. 하나의 `Serializer`로 두 상황을 모두 처리하려다 보니, 수정 시 빈 값을 보내면 400 Bad Request가 뜨거나, 반대로 온보딩 시 필수값을 체크하지 못하는 딜레마에 빠졌다.

- **해결**: 애매하게 하나로 퉁치지 말고, `Serializer`를 명확하게 두 개로 분리하여 역할을 정의했다.

    - `OnboardingSerializer`: `extra_kwargs`로 `required=True`를 강제 (엄격한 검사)
    - `ProfileUpdateSerializer`: 모든 필드를 선택적으로 허용 (유연한 검사)

```python
# backend/accounts/serializers.py

# 1. 온보딩용 (엄격한 검사)
class OnboardingSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['salary', 'assets', 'tender', ...]
        extra_kwargs = {
            # 필수 입력 강제
            "assets": {"required": True, "allow_null": False},
            "salary": {"required": True, "allow_null": False},
        }

# 2. 수정용 (유연한 검사)
class ProfileUpdateSerializer(serializers.ModelSerializer):
    # 별도 제약 없음 -> 모델의 blank=True, null=True 설정을 따름 (partial update 가능)
    class Meta:
        model = User
        fields = ['nickname', 'salary', 'assets', 'tender', 'profile_img']
```

![프로필 수정용 API](/assets/img/posts/2025-12-24-moathon-profile/1.png)
*PATCH /accounts/profile/update/*

4. 400 Bad Request (FormData Empty String)

![프로필 수정 시 입력 이슈](/assets/img/posts/2025-12-24-moathon-profile/2.png)
*프로필 수정 시 입력 이슈*

- **상황**: 프로필 수정 시, 사용자가 건드리지 않은 필드(빈 값)가 `FormData`에 빈 문자열(`""`)로 담겨 전송되었다. 백엔드의 `IntegerField`(자산, 연봉 등)는 이를 숫자가 아니라고 판단하여 에러를 뱉었다.

- **해결**: 프론트엔드 `submitForm` 로직에서 값이 유효한 경우(`null`이 아니고 빈 문자열이 아닌 경우)에만 `FormData`에 `append` 하도록 필터링 로직을 추가했다.

```js
// frontend/src/components/user/ProfileForm.vue

const submitForm = async () => {
  const formData = new FormData();

  // [Fix] 값이 있을 때만 보낸다. (부분 수정 지원)
  if (assets.value !== null && assets.value !== '') {
    formData.append('assets', assets.value);
  }
  
  // ... 다른 필드들도 동일 처리 ...

  if (props.isEdit) {
    await accountStore.editProfile(formData);
  } else {
    await accountStore.updateProfile(formData);
  }
}
```

---

## 리팩토링: 컴포넌트 재사용성 개선

'온보딩 페이지'와 '마이페이지 수정 화면'은 사실상 동일한 UI(입력 폼)를 가지고 있다. 코드를 두 번 짜는 것은 낭비이므로 하나로 통합했다.

- **해결**: `ProfileForm.vue` 하나로 통합하되, `isEdit props`를 통해 모드를 구분했다.

- **로직**: 수정 모드(`isEdit=true`)일 때는 `Store`에서 기존 유저 데이터를 가져와 폼에 미리 채워주는(Pre-fill) 로직을 추가했다.

```js

// ProfileForm.vue
const props = defineProps({ 
  isEdit: Boolean 
})

// [Fix] 수정 모드면 기존 데이터를 채워넣음
const fillFormData = () => {
  if (props.isEdit && accountStore.user) {
    assets.value = accountStore.user.assets
    salary.value = accountStore.user.salary
    // ...
  }
}

// 컴포넌트 마운트 시 실행
onMounted(() => fillFormData())

// 비동기로 데이터가 늦게 로드될 경우를 대비해 watch 감시
watch(() => accountStore.user, () => fillFormData())

```

![프로필 수정 모드](/assets/img/posts/2025-12-24-moathon-profile/4.png)
*프로필 수정 모드*

---

## 마치며

오늘 겪은 400 에러들의 대부분은 **"프론트엔드와 백엔드 간의 데이터 명세(Contract) 불일치"**에서 비롯되었다.

백엔드는 상황(생성 vs 수정)에 맞게 `Serializer`를 분리하여 유연성을 확보해야 하고, 프론트엔드는 불필요한 데이터 전송을 막고 UI 상태를 즉시 동기화하는 패턴을 가져가야 한다는 것을 배웠다. 오늘 적용한 구조는 프로젝트의 데이터 무결성을 유지하는 데 큰 도움이 될 것이다.