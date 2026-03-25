class AppConfig {
  const AppConfig._();

  static const String baseUrl = String.fromEnvironment(
    'APP_BASE_URL',
    defaultValue: 'http://10.0.2.2:5000',
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
}
