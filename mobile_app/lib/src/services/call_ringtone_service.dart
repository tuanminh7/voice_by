import 'package:flutter_ringtone_player/flutter_ringtone_player.dart';

class CallRingtoneService {
  final FlutterRingtonePlayer _player = FlutterRingtonePlayer();
  bool _isPlaying = false;

  Future<void> sync({required bool shouldRing}) async {
    if (shouldRing == _isPlaying) {
      return;
    }

    if (!shouldRing) {
      await stop();
      return;
    }

    _isPlaying = true;
    try {
      await _player.playRingtone(looping: true);
    } catch (_) {
      _isPlaying = false;
    }
  }

  Future<void> stop() async {
    if (!_isPlaying) {
      return;
    }

    _isPlaying = false;
    try {
      await _player.stop();
    } catch (_) {
      // Ignore platform-specific stop failures and let the UI continue.
    }
  }
}
