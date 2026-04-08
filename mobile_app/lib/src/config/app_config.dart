import 'dart:io';

class AppConfig {
  const AppConfig._();

  static const String releaseLabel = 'build-2026-03-27-r2';
  static const String productionBaseUrl = 'https://voice-by.onrender.com';
  static const String localAndroidEmulatorBaseUrl = 'http://10.0.2.2:5000';
  static const String localIosSimulatorBaseUrl = 'http://127.0.0.1:5000';

  static const String baseUrl = String.fromEnvironment(
    'APP_BASE_URL',
    defaultValue: productionBaseUrl,
  );
  static const int callPollIntervalSeconds = int.fromEnvironment(
    'CALL_POLL_INTERVAL_SECONDS',
    defaultValue: 5,
  );
  static const int incomingCallWatchIntervalSeconds = int.fromEnvironment(
    'INCOMING_CALL_WATCH_INTERVAL_SECONDS',
    defaultValue: 30,
  );
  static const int chatPollIntervalSeconds = int.fromEnvironment(
    'CHAT_POLL_INTERVAL_SECONDS',
    defaultValue: 2,
  );
  static const int connectTimeoutSeconds = int.fromEnvironment(
    'CONNECT_TIMEOUT_SECONDS',
    defaultValue: 30,
  );
  static const int receiveTimeoutSeconds = int.fromEnvironment(
    'RECEIVE_TIMEOUT_SECONDS',
    defaultValue: 60,
  );

  // Test credentials are embedded here; --dart-define can still override them.
  static const int zegoAppId = int.fromEnvironment(
    'ZEGO_APP_ID',
    defaultValue: 2012540145,
  );
  static const String zegoAppSign = String.fromEnvironment(
    'ZEGO_APP_SIGN',
    defaultValue: '9a246e48a76ebe91abca379fc6d03bba9a81318a7dd5dc3c582ccbef7f26e5ba',
  );
  static const String zegoPushResourceId = String.fromEnvironment(
    'ZEGO_PUSH_RESOURCE_ID',
    defaultValue: '',
  );

  static bool get hasRealtimeCallConfig =>
      zegoAppId > 0 && zegoAppSign.trim().isNotEmpty;

  static String get realtimeCallSetupHint =>
      'Bản app hiện tại chưa được build kèm cấu hình gọi thoại realtime. '
      'Hãy build lại với `--dart-define=ZEGO_APP_ID=...` và '
      '`--dart-define=ZEGO_APP_SIGN=...`, rồi cài lại APK trước khi gọi hoặc nghe máy.';

  static String get backendConnectionHint {
    final suggestions = <String>[
      'Backend hien tai: $baseUrl.',
      'Mac dinh app dang tro ve server production: $productionBaseUrl.',
    ];

    if (Platform.isAndroid) {
      suggestions.add(
        'Neu test local tren Android emulator, override `APP_BASE_URL` thanh `$localAndroidEmulatorBaseUrl`; neu test tren may Android that, dung `http://<IP-LAN-cua-may-tinh>:5000`.',
      );
    } else if (Platform.isIOS) {
      suggestions.add(
        'Neu test local tren iOS Simulator, override `APP_BASE_URL` thanh `$localIosSimulatorBaseUrl`; neu test tren iPhone that, dung `http://<IP-LAN-cua-may-tinh>:5000`.',
      );
    } else {
      suggestions.add(
        'Neu can test local, hay doi `APP_BASE_URL` thanh dia chi Flask noi bo phu hop, vi du `http://<IP-LAN-cua-may-tinh>:5000`.',
      );
    }

    suggestions.add(
      'Vi du local: `flutter run --dart-define=APP_BASE_URL=http://192.168.1.10:5000`',
    );
    return suggestions.join('\n');
  }
}
