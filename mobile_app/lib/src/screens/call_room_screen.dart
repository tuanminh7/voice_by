import 'package:flutter/material.dart';
import 'package:zego_uikit_prebuilt_call/zego_uikit_prebuilt_call.dart';
import 'package:zego_uikit_signaling_plugin/zego_uikit_signaling_plugin.dart';

import '../config/app_config.dart';
import '../models/app_models.dart';

class CallRoomScreen extends StatefulWidget {
  const CallRoomScreen({
    super.key,
    required this.user,
    required this.session,
    required this.onSyncEndCall,
  });

  final UserProfile user;
  final CallSession session;
  final Future<void> Function() onSyncEndCall;

  @override
  State<CallRoomScreen> createState() => _CallRoomScreenState();
}

class _CallRoomScreenState extends State<CallRoomScreen> {
  bool _endingSynced = false;

  Future<void> _syncEndCallOnce() async {
    if (_endingSynced) {
      return;
    }
    await widget.onSyncEndCall();
    _endingSynced = true;
  }

  @override
  Widget build(BuildContext context) {
    final config = ZegoUIKitPrebuiltCallConfig.oneOnOneVoiceCall()
      ..useSpeakerWhenJoining = true
      ..turnOnMicrophoneWhenJoining = true;

    return Scaffold(
      body: ZegoUIKitPrebuiltCall(
        appID: AppConfig.zegoAppId,
        appSign: AppConfig.zegoAppSign,
        userID: '${widget.user.id}',
        userName: widget.user.fullName,
        callID: widget.session.roomId,
        config: config,
        plugins: [ZegoUIKitSignalingPlugin()],
        events: ZegoUIKitPrebuiltCallEvents(
          onHangUpConfirmation: (event, defaultAction) async {
            await _syncEndCallOnce();
            return defaultAction();
          },
          onCallEnd: (event, defaultAction) async {
            await _syncEndCallOnce();
            defaultAction();
          },
        ),
      ),
    );
  }
}
