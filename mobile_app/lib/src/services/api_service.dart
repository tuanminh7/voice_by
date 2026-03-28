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
        connectTimeout: Duration(seconds: AppConfig.connectTimeoutSeconds),
        receiveTimeout: Duration(seconds: AppConfig.receiveTimeoutSeconds),
        sendTimeout: Duration(seconds: AppConfig.connectTimeoutSeconds),
        headers: {
          HttpHeaders.contentTypeHeader: 'application/json',
          HttpHeaders.userAgentHeader:
              'icare-mobile/1.0 (flutter; ${Platform.operatingSystem})',
          'X-Client-Source': 'flutter-mobile',
          'X-Client-Platform': Platform.operatingSystem,
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
    if (error is SocketException) {
      return ApiException(_buildConnectionErrorMessage(error.message));
    }

    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map<String, dynamic> && data['error'] is String) {
        return ApiException(data['error'] as String);
      }
      if (_isConnectionError(error)) {
        if (error.type == DioExceptionType.receiveTimeout) {
          return ApiException(
            'Server đang phản hồi chậm hoặc đang khởi động lại. Nếu đang dùng Render, bạn hãy đợi thêm khoảng 20-60 giây rồi thử lại.\n\n${AppConfig.backendConnectionHint}',
          );
        }
        final rawMessage = [
          error.message,
          if (error.error is SocketException)
            (error.error as SocketException).message,
        ].whereType<String>().join(' | ');
        return ApiException(_buildConnectionErrorMessage(rawMessage));
      }
      return ApiException(error.message ?? 'Yeu cau that bai.');
    }
    return ApiException(error.toString());
  }

  bool _isConnectionError(DioException error) {
    return error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout ||
        error.error is SocketException;
  }

  String _buildConnectionErrorMessage(String rawMessage) {
    final normalizedMessage = rawMessage.toLowerCase();
    var reason =
        'App chua ket noi duoc toi backend Flask. Hay kiem tra lai `APP_BASE_URL` va dam bao server dang chay.';

    if (normalizedMessage.contains('no route to host')) {
      reason =
          'Thiet bi hien tai khong the di toi host backend. Thuong la do `APP_BASE_URL` dang tro den dia chi chi hop voi emulator, khong hop voi may that.';
    } else if (normalizedMessage.contains('connection refused')) {
      reason =
          'Da tim thay host backend nhung cong dich vu dang tu choi ket noi. Kha nang cao la Flask/Gunicorn chua chay hoac dang chay sai cong.';
    } else if (normalizedMessage.contains('failed host lookup')) {
      reason =
          'Khong phan giai duoc ten mien backend. Hay kiem tra lai host trong `APP_BASE_URL`.';
    } else if (normalizedMessage.contains('timed out')) {
      reason =
          'Ket noi toi backend bi het thoi gian cho. Hay kiem tra mang giua thiet bi va may chay Flask.';
    } else if (normalizedMessage.contains('receive timeout')) {
      reason =
          'Server dang phan hoi cham hoac dang khoi dong lai. Neu ban dang dung Render, hay doi them 20-60 giay roi thu lai.';
    }

    return '$reason\n\n${AppConfig.backendConnectionHint}';
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
    required String careRoleKey,
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
          'care_role_key': careRoleKey,
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

  Future<FamilyGroup> createFamily(String familyName) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/families',
        data: {'family_name': familyName},
      );
      return FamilyGroup.fromJson(
        (response.data ?? const {})['family'] as Map<String, dynamic>? ??
            const {},
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<void> inviteFamilyMember(String identifier) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        '/api/families/current/invitations',
        data: {'identifier': identifier},
      );
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

  Future<UserProfile> saveGeminiApiKey(String apiKey) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/me/gemini-key',
        data: {'api_key': apiKey},
      );
      return UserProfile.fromJson(
        (response.data ?? const {})['user'] as Map<String, dynamic>? ??
            const {},
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<UserProfile> deleteGeminiApiKey() async {
    try {
      final response = await _dio.delete<Map<String, dynamic>>(
        '/api/me/gemini-key',
      );
      return UserProfile.fromJson(
        (response.data ?? const {})['user'] as Map<String, dynamic>? ??
            const {},
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<EmotionDashboard?> getEmotionDashboard() async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/emotions/dashboard');
      final payload = (response.data ?? const {})['dashboard'];
      if (payload is! Map<String, dynamic>) {
        return null;
      }
      return EmotionDashboard.fromJson(payload);
    } catch (error) {
      if (error is DioException && error.response?.statusCode == 403) {
        return null;
      }
      throw _toApiException(error);
    }
  }

  Future<List<FamilyChatThread>> getFamilyChatThreads() async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('/api/family-chat/threads');
      final rows =
          (response.data ?? const {})['threads'] as List<dynamic>? ?? const [];
      return rows
          .whereType<Map<String, dynamic>>()
          .map(FamilyChatThread.fromJson)
          .toList();
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<List<FamilyChatMessage>> getFamilyChatMessages(
      int partnerUserId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/api/family-chat/messages',
        queryParameters: {'partner_user_id': partnerUserId},
      );
      final rows =
          (response.data ?? const {})['messages'] as List<dynamic>? ?? const [];
      return rows
          .whereType<Map<String, dynamic>>()
          .map(FamilyChatMessage.fromJson)
          .toList();
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<FamilyChatMessage> sendFamilyChatMessage({
    required int recipientUserId,
    required String messageText,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/family-chat/messages',
        data: {
          'recipient_user_id': recipientUserId,
          'message_text': messageText,
        },
      );
      return FamilyChatMessage.fromJson(
        (response.data ?? const {})['chat_message'] as Map<String, dynamic>? ??
            const {},
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }

  Future<VoiceAssistantResult> submitVoiceInput(
    String transcriptText, {
    required bool realtimeCallReady,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/calls/voice-intent',
        data: {
          'transcript_text': transcriptText,
          'realtime_call_ready': realtimeCallReady,
        },
      );
      return VoiceAssistantResult.fromJson(response.data ?? const {});
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

  Future<CallSession> createManualCall(String relationshipKey) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/calls',
        data: {'relationship_key': relationshipKey},
      );
      return CallSession.fromJson(
        (response.data ?? const {})['call'] as Map<String, dynamic>? ??
            const {},
      );
    } catch (error) {
      throw _toApiException(error);
    }
  }
}
