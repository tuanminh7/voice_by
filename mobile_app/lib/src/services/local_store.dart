import 'package:shared_preferences/shared_preferences.dart';

class LocalStore {
  LocalStore(this._prefs);

  static const _deviceIdKey = 'device_id';
  static const _pinTokenKey = 'pin_token';
  static const _pushTokenKey = 'push_token';
  static const _pushTokenUserIdKey = 'push_token_user_id';

  final SharedPreferences _prefs;

  static Future<LocalStore> create() async {
    final prefs = await SharedPreferences.getInstance();
    return LocalStore(prefs);
  }

  String? get pinToken => _prefs.getString(_pinTokenKey);
  String? get pushToken => _prefs.getString(_pushTokenKey);
  int? get pushTokenUserId => _prefs.getInt(_pushTokenUserIdKey);

  Future<String> ensureDeviceId() async {
    final existing = _prefs.getString(_deviceIdKey);
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }

    final generated = 'mobile-${DateTime.now().microsecondsSinceEpoch}';
    await _prefs.setString(_deviceIdKey, generated);
    return generated;
  }

  Future<void> savePinToken(String? token) async {
    if (token == null || token.isEmpty) {
      await _prefs.remove(_pinTokenKey);
      return;
    }

    await _prefs.setString(_pinTokenKey, token);
  }

  Future<void> savePushTokenRegistration({
    required int userId,
    required String token,
  }) async {
    await _prefs.setString(_pushTokenKey, token);
    await _prefs.setInt(_pushTokenUserIdKey, userId);
  }
}
