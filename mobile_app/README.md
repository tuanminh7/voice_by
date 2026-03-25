# Mobile App V2

Thu muc nay chua Flutter client cho `v2` emergency call.

## Trang thai hien tai

Da co san:

- `pubspec.yaml`
- ma nguon trong `lib/`
- platform folders `android/` va `ios/`
- service goi backend Flask
- flow co ban:
  - login/register
  - PIN setup / PIN unlock
  - lay profile + family current
  - chon thanh vien gia dinh that de map quan he goi
  - voice intent call
  - auto lay FCM token neu Firebase da cau hinh dung
  - nghe incoming push payload co `call_session_id`
  - call state polling
  - tu mo audio room ZEGOCLOUD khi session da `accepted`
  - call history
  - quan he goi khan cap

Con thieu de len ban realtime that:

- Firebase native config thuc te (`google-services.json` / iOS config)
- ZEGOCLOUD app credentials cua ban
- incoming call native/fullscreen thuc te qua provider + offline invitation

## Cach bat dau khi may da co Flutter

1. Cai Flutter SDK neu may chua co.
2. Mo terminal trong thu muc `mobile_app`.
3. Cai package:

```powershell
flutter pub get
```

4. Dien cau hinh trong code:

- khuyen nghi dung `--dart-define` thay vi sua tay trong code

Vi du:

```powershell
flutter run `
  --dart-define=APP_BASE_URL=http://192.168.1.10:5000 `
  --dart-define=ZEGO_APP_ID=123456789 `
  --dart-define=ZEGO_APP_SIGN=your_zego_app_sign `
  --dart-define=ZEGO_PUSH_RESOURCE_ID=your_zego_push_resource_id
```

5. Them Firebase config cho Android/iOS.
6. Chay:

```powershell
flutter run
```

## Luu y quan trong

- Backend hien tai dung session cookie + PIN token.
- Client Flutter trong `lib/` da chuan bi de luu cookie va goi API hien co.
- Incoming call native va media realtime se can bo sung tiep phan cau hinh ZEGOCLOUD/Firebase.

## Checklist Firebase va ZEGOCLOUD

### Firebase Android

1. Tao Firebase project.
2. Them Android app voi package name trung voi `applicationId` trong `android/app/build.gradle.kts`.
3. Tai `google-services.json` va dat vao:

```text
mobile_app/android/app/google-services.json
```

4. Chay lai:

```powershell
flutter clean
flutter pub get
flutter run
```

### Firebase iOS

1. Them iOS app trong Firebase.
2. Tai `GoogleService-Info.plist` va dat vao:

```text
mobile_app/ios/Runner/GoogleService-Info.plist
```

### ZEGOCLOUD

1. Tao project trong ZEGOCLOUD console.
2. Lay `AppID` va `AppSign`.
3. Neu dung offline push/incoming call native, tao them `Push Resource ID`.
4. Truyen cac gia tri nay bang `--dart-define`.
