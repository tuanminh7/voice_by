import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

class CallPushMessage {
  const CallPushMessage({
    required this.eventType,
    required this.callSessionId,
    required this.payload,
  });

  final String eventType;
  final int? callSessionId;
  final Map<String, dynamic> payload;
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
  } catch (_) {
    return;
  }
}

class FirebaseMessagingService {
  FirebaseMessagingService();

  final StreamController<CallPushMessage> _callMessageController =
      StreamController<CallPushMessage>.broadcast();

  StreamSubscription<RemoteMessage>? _onMessageSubscription;
  StreamSubscription<RemoteMessage>? _onMessageOpenedSubscription;
  StreamSubscription<String>? _tokenRefreshSubscription;

  bool _initialized = false;
  bool _available = false;
  String? _deviceToken;
  CallPushMessage? _launchMessage;
  String? _availabilityMessage;

  bool get isAvailable => _available;
  String? get deviceToken => _deviceToken;
  CallPushMessage? get launchMessage => _launchMessage;
  String? get availabilityMessage => _availabilityMessage;
  Stream<CallPushMessage> get callMessages => _callMessageController.stream;

  Future<void> initialize() async {
    if (_initialized) {
      return;
    }
    _initialized = true;

    try {
      await Firebase.initializeApp();
      _available = true;
      _availabilityMessage = 'Firebase Messaging da san sang.';
      FirebaseMessaging.onBackgroundMessage(
        firebaseMessagingBackgroundHandler,
      );

      final initialMessage =
          await FirebaseMessaging.instance.getInitialMessage();
      _launchMessage = _parseCallMessage(initialMessage);

      _onMessageSubscription = FirebaseMessaging.onMessage.listen(
        _handleRemoteMessage,
      );
      _onMessageOpenedSubscription =
          FirebaseMessaging.onMessageOpenedApp.listen(
        _handleRemoteMessage,
      );
      _tokenRefreshSubscription =
          FirebaseMessaging.instance.onTokenRefresh.listen((token) {
        _deviceToken = token;
        _availabilityMessage = 'Da nhan duoc FCM token tu dong.';
      });
    } catch (error) {
      _available = false;
      _availabilityMessage =
          'Firebase chua duoc cau hinh native tren app nay. Can them google-services.json hoac GoogleService-Info.plist. Chi tiet: $error';
    }
  }

  Future<String?> prepareDeviceToken() async {
    if (!_available) {
      return null;
    }

    try {
      final messaging = FirebaseMessaging.instance;

      if (!kIsWeb &&
          (Platform.isIOS || Platform.isMacOS || Platform.isAndroid)) {
        await messaging.requestPermission(
          alert: true,
          badge: true,
          sound: true,
        );
      }

      await messaging.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );

      _deviceToken ??= await messaging.getToken();
      _availabilityMessage = _deviceToken?.isNotEmpty == true
          ? 'Da lay duoc FCM token tu dong.'
          : 'Firebase da khoi tao nhung chua lay duoc FCM token.';
      return _deviceToken;
    } catch (error) {
      _availabilityMessage = 'Khong lay duoc FCM token: $error';
      return null;
    }
  }

  void clearLaunchMessage() {
    _launchMessage = null;
  }

  void _handleRemoteMessage(RemoteMessage message) {
    final parsed = _parseCallMessage(message);
    if (parsed == null) {
      return;
    }

    _callMessageController.add(parsed);
  }

  CallPushMessage? _parseCallMessage(RemoteMessage? message) {
    if (message == null) {
      return null;
    }

    final eventType = '${message.data['event_type'] ?? ''}'.trim();
    final rawValue =
        message.data['call_session_id'] ?? message.data['callSessionId'];
    final callSessionId = int.tryParse('$rawValue');
    if ((callSessionId == null || callSessionId <= 0) && eventType.isEmpty) {
      return null;
    }

    return CallPushMessage(
      eventType: eventType,
      callSessionId: callSessionId,
      payload: Map<String, dynamic>.from(message.data),
    );
  }

  Future<void> dispose() async {
    await _onMessageSubscription?.cancel();
    await _onMessageOpenedSubscription?.cancel();
    await _tokenRefreshSubscription?.cancel();
    await _callMessageController.close();
  }
}
