import 'package:flutter/material.dart';
import 'package:zego_uikit_prebuilt_call/zego_uikit_prebuilt_call.dart';
import 'package:zego_uikit_signaling_plugin/zego_uikit_signaling_plugin.dart';

import '../app_navigator.dart';
import '../config/app_config.dart';
import '../models/app_models.dart';
import '../screens/call_room_screen.dart';

class ZegoCallService {
  ZegoCallService();

  final _plugins = [ZegoUIKitSignalingPlugin()];
  int? _activeCallSessionId;
  int? _initializedUserId;

  bool get isConfigured =>
      AppConfig.zegoAppId > 0 && AppConfig.zegoAppSign.isNotEmpty;

  Future<void> initialize() async {
    ZegoUIKitPrebuiltCallInvitationService().setNavigatorKey(
      AppNavigator.navigatorKey,
    );
  }

  Future<void> configureForUser(UserProfile user) async {
    if (!isConfigured) {
      return;
    }
    if (_initializedUserId == user.id) {
      return;
    }

    if (_initializedUserId != null) {
      await uninitialize();
    }

    await ZegoUIKitPrebuiltCallInvitationService().useSystemCallingUI(_plugins);

    await ZegoUIKitPrebuiltCallInvitationService().init(
      appID: AppConfig.zegoAppId,
      appSign: AppConfig.zegoAppSign,
      userID: '${user.id}',
      userName: user.fullName,
      plugins: _plugins,
      requireConfig: (data) {
        final config = ZegoUIKitPrebuiltCallConfig.oneOnOneVoiceCall()
          ..useSpeakerWhenJoining = true
          ..turnOnMicrophoneWhenJoining = true
          ..turnOnCameraWhenJoining = false;
        return config;
      },
      config: ZegoCallInvitationConfig(
        permissions: ZegoCallInvitationPermissions.audio,
        offline: ZegoCallInvitationOfflineConfig(
          autoEnterAcceptedOfflineCall: false,
        ),
        inCalling: ZegoCallInvitationInCallingConfig(
          canInvitingInCalling: false,
        ),
      ),
      notificationConfig: ZegoCallInvitationNotificationConfig(
        androidNotificationConfig: ZegoCallAndroidNotificationConfig(
          showOnLockedScreen: false,
          showOnFullScreen: false,
        ),
        iOSNotificationConfig: ZegoCallIOSNotificationConfig(
          appName: 'UT Nguyen Mobile',
        ),
      ),
    );
    ZegoUIKitPrebuiltCallInvitationService().enterAcceptedOfflineCall();

    _initializedUserId = user.id;
  }

  Future<void> joinAudioCall({
    required UserProfile user,
    required CallSession session,
    required Future<void> Function() onSyncEndCall,
  }) async {
    if (!isConfigured || session.roomId.isEmpty) {
      return;
    }
    if (_activeCallSessionId == session.callSessionId) {
      return;
    }

    final navigatorState = AppNavigator.navigatorKey.currentState;
    if (navigatorState == null) {
      return;
    }

    _activeCallSessionId = session.callSessionId;

    await navigatorState.push(
      MaterialPageRoute<void>(
        builder: (_) => CallRoomScreen(
          user: user,
          session: session,
          onSyncEndCall: onSyncEndCall,
        ),
      ),
    );

    if (_activeCallSessionId == session.callSessionId) {
      _activeCallSessionId = null;
    }
  }

  void clearActiveCall() {
    _activeCallSessionId = null;
  }

  Future<void> uninitialize() async {
    if (!isConfigured) {
      _initializedUserId = null;
      _activeCallSessionId = null;
      return;
    }

    ZegoUIKitPrebuiltCallInvitationService().uninit();
    _initializedUserId = null;
    _activeCallSessionId = null;
  }
}
