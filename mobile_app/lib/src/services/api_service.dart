import 'dart:io';

import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:path_provider/path_provider.dart';

import '../config/app_config.dart';
import '../models/app_models.dart';
import 'local_store.dart';

class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ApiService {
  ApiService._(this._dio, this._store);

  final Dio _dio;
  final LocalStore _store;

  static Future<ApiService> create(LocalStore store) async {
    final directory = await getApplicationDocumentsDirectory();
    final cookieDirectory = Directory('${directory.path}/cookies');
    final jar = PersistCookieJar(storage: FileStorage(cookieDirectory.path));
    final dio = Dio(
      BaseOptions(
        baseUrl: AppConfig.baseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
        headers: {
          HttpHeaders.contentTypeHeader: 'application/json',
        },
      ),
    );
    dio.interceptors.add(CookieManager(jar));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final pinToken = store.pinToken;
          if (pinToken != null && pinToken.isNotEmpty) {
            options.headers['X-PIN-Token'] = pinToken;
          }
          handler.next(options);
        },
      ),
    );

    return ApiService._(dio, store);
  }

  ApiException _toApiException(Object error) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map<String, dynamic> && data['error'] is String) {
        return ApiException(data['error'] as String);
      }
      return ApiException(error.message ?? 'Yeu cau that bai.');
    }
    return ApiException(error.toString());
  }

  Future<BootstrapState> bootstrap() async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/api/bootstrap');
      return BootstrapState.fromJson(response.data ?? const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<BootstrapState> login({
    required String identifier,
    required String password,
    required String deviceId,
    required String deviceName,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/auth/login',
        data: {
          'identifier': identifier,
          'password': password,
          'device_id': deviceId,
          'device_name': deviceName,
        },
      );
      return BootstrapState.fromJson(
          (response.data ?? const {})['bootstrap'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<BootstrapState> register({
    required String fullName,
    required int age,
    required String email,
    required String phoneNumber,
    required String password,
    required String deviceId,
    required String deviceName,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/auth/register',
        data: {
          'full_name': fullName,
          'age': age,
          'email': email,
          'phone_number': phoneNumber,
          'password': password,
          'device_id': deviceId,
          'device_name': deviceName,
        },
      );
      return BootstrapState.fromJson(
          (response.data ?? const {})['bootstrap'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> setupPin(String pin, String confirmPin) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/auth/pin/setup',
        data: {
          'pin': pin,
          'confirm_pin': confirmPin,
        },
      );
      await _store
          .savePinToken((response.data ?? const {})['pin_token'] as String?);
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> verifyPin(String pin) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/auth/pin/verify',
        data: {'pin': pin},
      );
      await _store
          .savePinToken((response.data ?? const {})['pin_token'] as String?);
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> logout() async {
    try {
      await _dio.post<Map<String, dynamic>>('/api/auth/logout');
      await _store.savePinToken(null);
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<UserProfile> getProfile() async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/api/me');
      return UserProfile.fromJson(
          (response.data ?? const {})['user'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<List<FamilyRelationship>> getRelationships() async {
    final bundle = await getCallRelationshipBundle();
    return bundle.relationships;
  }

  Future<CallRelationshipBundle> getCallRelationshipBundle() async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/call-relationships');
      final rows =
          (response.data ?? const {})['relationships'] as List<dynamic>? ??
              const [];
      final supportedRows = (response.data ??
              const {})['supported_relationships'] as List<dynamic>? ??
          const [];

      return CallRelationshipBundle(
        relationships: rows
            .whereType<Map<String, dynamic>>()
            .map(FamilyRelationship.fromJson)
            .toList(),
        supportedRelationships: supportedRows
            .whereType<Map<String, dynamic>>()
            .map(RelationshipOption.fromJson)
            .toList(),
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<List<RelationshipOption>> getRelationshipOptions() async {
    final bundle = await getCallRelationshipBundle();
    return bundle.supportedRelationships;
  }

  Future<List<FamilyRelationship>> saveRelationship({
    required int relativeUserId,
    required String relationshipKey,
    required int priorityOrder,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/call-relationships',
        data: {
          'relative_user_id': relativeUserId,
          'relationship_key': relationshipKey,
          'priority_order': priorityOrder,
        },
      );
      final rows =
          (response.data ?? const {})['relationships'] as List<dynamic>? ??
              const [];
      return rows
          .whereType<Map<String, dynamic>>()
          .map(FamilyRelationship.fromJson)
          .toList();
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> deleteRelationship(int relationshipId) async {
    try {
      await _dio.delete<Map<String, dynamic>>(
        '/api/call-relationships/$relationshipId',
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<FamilyGroup?> getCurrentFamily() async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/families/current');
      final family = (response.data ?? const {})['family'];
      if (family is! Map<String, dynamic>) {
        return null;
      }
      return FamilyGroup.fromJson(family);
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<List<FamilyInvitation>> getPendingFamilyInvitations() async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/families/invitations');
      final rows =
          (response.data ?? const {})['invitations'] as List<dynamic>? ??
              const [];
      return rows
          .whereType<Map<String, dynamic>>()
          .map(FamilyInvitation.fromJson)
          .toList();
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> respondToFamilyInvitation({
    required int invitationId,
    required String action,
  }) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        '/api/families/invitations/$invitationId/respond',
        data: {'action': action},
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> registerPushToken({
    required String platform,
    required String pushToken,
  }) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        '/api/device-push-tokens/register',
        data: {
          'platform': platform,
          'push_token': pushToken,
        },
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<CallSession> createVoiceCall(String transcriptText) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/calls/voice-intent',
        data: {'transcript_text': transcriptText},
      );
      final action = (response.data ?? const {})['action'] as String? ?? '';
      if (action != 'calling') {
        throw ApiException((response.data ?? const {})['question'] as String? ??
            'He thong chua tao duoc cuoc goi.');
      }
      return CallSession.fromJson(
          (response.data ?? const {})['call'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<CallSession> getCallSession(int callSessionId) async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/calls/$callSessionId');
      return CallSession.fromJson(
          (response.data ?? const {})['call'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<List<CallSession>> getCallHistory() async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/calls/history');
      final rows =
          (response.data ?? const {})['calls'] as List<dynamic>? ?? const [];
      return rows
          .whereType<Map<String, dynamic>>()
          .map(CallSession.fromJson)
          .toList();
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<CallSession> acceptCall(int callSessionId) async {
    try {
      final response = await _dio
          .post<Map<String, dynamic>>('/api/calls/$callSessionId/accept');
      return CallSession.fromJson(
          (response.data ?? const {})['call'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<CallSession> declineCall(int callSessionId) async {
    try {
      final response = await _dio
          .post<Map<String, dynamic>>('/api/calls/$callSessionId/decline');
      return CallSession.fromJson(
          (response.data ?? const {})['call'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<CallSession> endCall(int callSessionId) async {
    try {
      final response = await _dio
          .post<Map<String, dynamic>>('/api/calls/$callSessionId/end');
      return CallSession.fromJson(
          (response.data ?? const {})['call'] as Map<String, dynamic>? ??
              const {});
    } catch (error) {
      throw _toApiException(error);
    }
  }
}
