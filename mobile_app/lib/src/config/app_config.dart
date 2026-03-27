import 'dart:io';

class AppConfig {
  const AppConfig._();

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

  // Supply these via --dart-define when you are ready to test realtime calls.
  static const int zegoAppId = int.fromEnvironment(
    'ZEGO_APP_ID',
    defaultValue: 0,
  );
  static const String zegoAppSign = String.fromEnvironment(
    'ZEGO_APP_SIGN',
    defaultValue: '',
  );
  static const String zegoPushResourceId = String.fromEnvironment(
    'ZEGO_PUSH_RESOURCE_ID',
    defaultValue: '',
  );

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
