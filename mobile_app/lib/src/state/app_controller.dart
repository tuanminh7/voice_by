import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../config/app_config.dart';
import '../models/app_models.dart';
import '../services/api_service.dart';
import '../services/firebase_messaging_service.dart';
import '../services/local_store.dart';
import '../services/zego_call_service.dart';

enum AppStage {
  loading,
  auth,
  pinSetup,
  pinUnlock,
  home,
}

class AppController extends ChangeNotifier {
  AppController._(
    this._store,
    this._apiService,
    this._callService,
    this._messagingService,
  );

  final LocalStore _store;
  final ApiService _apiService;
  final ZegoCallService _callService;
  final FirebaseMessagingService _messagingService;
  final String deviceId =
      'mobile-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(99999)}';

  AppStage stage = AppStage.loading;
  BootstrapState? bootstrapState;
  UserProfile? profile;
  FamilyGroup? family;
  List<FamilyInvitation> pendingInvitations = const [];
  List<FamilyRelationship> relationships = const [];
  List<RelationshipOption> relationshipOptions = const [];
  EmotionDashboard? emotionDashboard;
  List<FamilyChatThread> chatThreads = const [];
  List<FamilyChatMessage> activeChatMessages = const [];
  int? activeChatPartnerUserId;
  List<CallSession> callHistory = const [];
  CallSession? activeCall;
  String? errorMessage;
  bool busy = false;
  Timer? _callPollTimer;
  Timer? _incomingCallWatchTimer;
  StreamSubscription<CallPushMessage>? _pushSubscription;
  bool _incomingCallWatchBusy = false;

  bool get hasRealtimeCallConfig => _callService.isConfigured;
  bool get hasPushMessagingConfig => _messagingService.isAvailable;
  String? get autoPushToken => _messagingService.deviceToken;
  String? get pushStatusMessage => _messagingService.availabilityMessage;
  FamilyChatThread? get activeChatThread {
    final partnerUserId = activeChatPartnerUserId;
    if (partnerUserId == null) {
      return null;
    }
    for (final thread in chatThreads) {
      if (thread.partnerUserId == partnerUserId) {
        return thread;
      }
    }
    return null;
  }

  static Future<AppController> create() async {
    final store = await LocalStore.create();
    final api = await ApiService.create(store);
    final callService = ZegoCallService();
    final messagingService = FirebaseMessagingService();
    await messagingService.initialize();
    await callService.initialize();
    final controller = AppController._(
      store,
      api,
      callService,
      messagingService,
    );
    controller._listenToPushMessages();
    await controller.bootstrap();
    return controller;
  }

  Future<void> bootstrap() async {
    stage = AppStage.loading;
    notifyListeners();

    try {
      bootstrapState = await _apiService.bootstrap();
      if (bootstrapState?.authenticated != true) {
        stage = AppStage.auth;
      } else if (bootstrapState?.pinConfigured != true) {
        stage = AppStage.pinSetup;
      } else if ((_store.pinToken ?? '').isEmpty) {
        stage = AppStage.pinUnlock;
      } else {
        stage = AppStage.home;
        await loadHomeData();
      }
      errorMessage = null;
    } catch (error) {
      errorMessage = error.toString();
      stage = AppStage.auth;
    }
    notifyListeners();
  }

  Future<void> _runBusy(Future<void> Function() action) async {
    busy = true;
    errorMessage = null;
    notifyListeners();
    try {
      await action();
    } catch (error) {
      errorMessage = error.toString();
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> login({
    required String identifier,
    required String password,
  }) async {
    await _runBusy(() async {
      bootstrapState = await _apiService.login(
        identifier: identifier,
        password: password,
        deviceId: deviceId,
        deviceName: defaultTargetPlatform.name,
      );
      stage = bootstrapState?.pinConfigured == true
          ? AppStage.pinUnlock
          : AppStage.pinSetup;
    });
  }

  Future<void> register({
    required String fullName,
    required int age,
    required String email,
    required String phoneNumber,
    required String password,
  }) async {
    await _runBusy(() async {
      bootstrapState = await _apiService.register(
        fullName: fullName,
        age: age,
        email: email,
        phoneNumber: phoneNumber,
        password: password,
        deviceId: deviceId,
        deviceName: defaultTargetPlatform.name,
      );
      stage = AppStage.pinSetup;
    });
  }

  Future<void> setupPin(String pin, String confirmPin) async {
    await _runBusy(() async {
      await _apiService.setupPin(pin, confirmPin);
      stage = AppStage.home;
      await loadHomeData();
    });
  }

  Future<void> unlockWithPin(String pin) async {
    await _runBusy(() async {
      await _apiService.verifyPin(pin);
      stage = AppStage.home;
      await loadHomeData();
    });
  }

  Future<void> loadHomeData() async {
    final results = await Future.wait<Object?>([
      _apiService.getProfile(),
      _apiService.getCallRelationshipBundle(),
      _apiService.getCurrentFamily(),
      _apiService.getPendingFamilyInvitations(),
      _apiService.getCallHistory(),
    ]);

    profile = results[0] as UserProfile;

    final bundle = results[1] as CallRelationshipBundle;
    relationships = bundle.relationships;
    relationshipOptions = bundle.supportedRelationships;

    family = results[2] as FamilyGroup?;
    pendingInvitations = results[3] as List<FamilyInvitation>;
    callHistory = results[4] as List<CallSession>;

    if (family != null) {
      emotionDashboard = await _apiService.getEmotionDashboard();
      chatThreads = await _apiService.getFamilyChatThreads();
      await _refreshActiveChatMessages(allowAutoSelect: true);
    } else {
      emotionDashboard = null;
      chatThreads = const [];
      activeChatMessages = const [];
      activeChatPartnerUserId = null;
    }

    await _syncRealtimeServices();
    _syncActiveCallFromHistory();
    await _consumeLaunchPushMessage();
    notifyListeners();
  }

  Future<void> saveRelationship({
    required int relativeUserId,
    required String relationshipKey,
    required int priorityOrder,
  }) async {
    await _runBusy(() async {
      relationships = await _apiService.saveRelationship(
        relativeUserId: relativeUserId,
        relationshipKey: relationshipKey,
        priorityOrder: priorityOrder,
      );
    });
  }

  Future<void> deleteRelationship(int relationshipId) async {
    await _runBusy(() async {
      await _apiService.deleteRelationship(relationshipId);
      final bundle = await _apiService.getCallRelationshipBundle();
      relationships = bundle.relationships;
      relationshipOptions = bundle.supportedRelationships;
    });
  }

  Future<void> registerPushToken({
    required String platform,
    required String pushToken,
  }) async {
    await _runBusy(() async {
      await _apiService.registerPushToken(
        platform: platform,
        pushToken: pushToken,
      );
      final currentUser = profile;
      if (currentUser != null) {
        await _store.savePushTokenRegistration(
          userId: currentUser.id,
          token: pushToken,
        );
      }
    });
  }

  Future<void> respondToInvitation({
    required int invitationId,
    required String action,
  }) async {
    await _runBusy(() async {
      await _apiService.respondToFamilyInvitation(
        invitationId: invitationId,
        action: action,
      );
      await loadHomeData();
    });
  }

  Future<void> createFamily(String familyName) async {
    await _runBusy(() async {
      family = await _apiService.createFamily(familyName);
      await loadHomeData();
    });
  }

  Future<void> inviteFamilyMember(String identifier) async {
    await _runBusy(() async {
      await _apiService.inviteFamilyMember(identifier);
      await loadHomeData();
    });
  }

  Future<void> saveGeminiApiKey(String apiKey) async {
    await _runBusy(() async {
      profile = await _apiService.saveGeminiApiKey(apiKey);
    });
  }

  Future<void> deleteGeminiApiKey() async {
    await _runBusy(() async {
      profile = await _apiService.deleteGeminiApiKey();
    });
  }

  Future<void> createVoiceCall(String transcriptText) async {
    await _runBusy(() async {
      activeCall = await _apiService.createVoiceCall(transcriptText);
      _mergeCallIntoHistory(activeCall!);
      _syncActiveCallFromHistory();
    });
  }

  Future<void> openChatThread(int partnerUserId) async {
    await _runBusy(() async {
      activeChatPartnerUserId = partnerUserId;
      await _refreshChatThreads();
      await _refreshActiveChatMessages(allowAutoSelect: false);
    });
  }

  Future<void> sendChatMessage(String messageText) async {
    final partnerUserId = activeChatPartnerUserId;
    if (partnerUserId == null) {
      return;
    }

    await _runBusy(() async {
      final sentMessage = await _apiService.sendFamilyChatMessage(
        recipientUserId: partnerUserId,
        messageText: messageText,
      );
      activeChatMessages = [...activeChatMessages, sentMessage];
      await _refreshChatThreads();
    });
  }

  Future<void> refreshActiveCall() async {
    final session = activeCall;
    if (session == null) {
      return;
    }

    await _runBusy(() async {
      activeCall = await _apiService.getCallSession(session.callSessionId);
      _mergeCallIntoHistory(activeCall!);
      _syncActiveCallFromHistory();
    });
  }

  Future<void> acceptActiveCall() async {
    final session = activeCall;
    if (session == null) {
      return;
    }

    await _runBusy(() async {
      activeCall = await _apiService.acceptCall(session.callSessionId);
      _mergeCallIntoHistory(activeCall!);
      await _maybeJoinAcceptedCall(activeCall);
      _syncActiveCallFromHistory();
    });
  }

  Future<void> declineActiveCall() async {
    final session = activeCall;
    if (session == null) {
      return;
    }

    await _runBusy(() async {
      activeCall = await _apiService.declineCall(session.callSessionId);
      _mergeCallIntoHistory(activeCall!);
      _syncActiveCallFromHistory();
    });
  }

  Future<void> endActiveCall() async {
    final session = activeCall;
    if (session == null) {
      return;
    }

    await _runBusy(() async {
      activeCall = await _apiService.endCall(session.callSessionId);
      _mergeCallIntoHistory(activeCall!);
      _syncActiveCallFromHistory();
    });
  }

  Future<void> logout() async {
    await _runBusy(() async {
      await _apiService.logout();
      await _callService.uninitialize();
      _stopPollingCall();
      _stopIncomingCallWatcher();
      activeCall = null;
      profile = null;
      family = null;
      pendingInvitations = const [];
      relationships = const [];
      relationshipOptions = const [];
      emotionDashboard = null;
      chatThreads = const [];
      activeChatMessages = const [];
      activeChatPartnerUserId = null;
      callHistory = const [];
      stage = AppStage.auth;
    });
  }

  void _startPollingCall() {
    _stopPollingCall();
    _callPollTimer = Timer.periodic(
      const Duration(seconds: AppConfig.callPollIntervalSeconds),
      (_) async {
        final session = activeCall;
        if (session == null) {
          _stopPollingCall();
          return;
        }

        try {
          activeCall = await _apiService.getCallSession(session.callSessionId);
          _mergeCallIntoHistory(activeCall!);
          await _maybeJoinAcceptedCall(activeCall);
          _syncActiveCallFromHistory();
          notifyListeners();
        } catch (_) {
          _stopPollingCall();
        }
      },
    );
  }

  void _stopPollingCall() {
    _callPollTimer?.cancel();
    _callPollTimer = null;
  }

  void _startIncomingCallWatcher() {
    if (_incomingCallWatchTimer != null) {
      return;
    }

    _incomingCallWatchTimer = Timer.periodic(
      const Duration(seconds: AppConfig.callPollIntervalSeconds),
      (_) async {
        await _refreshIncomingCalls();
      },
    );
  }

  void _stopIncomingCallWatcher() {
    _incomingCallWatchTimer?.cancel();
    _incomingCallWatchTimer = null;
  }

  Future<void> _refreshIncomingCalls() async {
    if (_incomingCallWatchBusy || stage != AppStage.home) {
      return;
    }
    if (activeCall != null && !_isCallFinished(activeCall)) {
      return;
    }

    _incomingCallWatchBusy = true;
    try {
      callHistory = await _apiService.getCallHistory();
      _syncActiveCallFromHistory();
      await _maybeJoinAcceptedCall(activeCall);
      notifyListeners();
    } catch (_) {
      // Keep watcher running; next tick can recover automatically.
    } finally {
      _incomingCallWatchBusy = false;
    }
  }

  void _listenToPushMessages() {
    _pushSubscription = _messagingService.callMessages.listen((message) async {
      await _handlePushCallMessage(message);
    });
  }

  Future<void> _consumeLaunchPushMessage() async {
    final launchMessage = _messagingService.launchMessage;
    if (launchMessage == null) {
      return;
    }

    _messagingService.clearLaunchMessage();
    await _handlePushCallMessage(launchMessage);
  }

  Future<void> _handlePushCallMessage(CallPushMessage message) async {
    if (stage != AppStage.home) {
      return;
    }

    try {
      if ({
        'family_invitation',
        'family_invitation_accepted',
        'family_invitation_declined',
        'family_chat_message',
        'emotion_alert',
      }.contains(message.eventType)) {
        await loadHomeData();
        return;
      }

      final callSessionId = message.callSessionId;
      if (callSessionId == null || callSessionId <= 0) {
        return;
      }

      final session = await _apiService.getCallSession(callSessionId);
      activeCall = session;
      _mergeCallIntoHistory(session);
      await _maybeJoinAcceptedCall(session);
      _syncActiveCallFromHistory();
      notifyListeners();
    } catch (_) {
      // Ignore malformed or outdated push payloads.
    }
  }

  Future<void> _syncRealtimeServices() async {
    final currentUser = profile;
    if (currentUser == null) {
      return;
    }

    await _callService.configureForUser(currentUser);
    await _syncAutomaticPushToken(currentUser);
  }

  Future<void> _syncAutomaticPushToken(UserProfile currentUser) async {
    final token = await _messagingService.prepareDeviceToken();
    if (token == null || token.isEmpty) {
      return;
    }

    final sameUser = _store.pushTokenUserId == currentUser.id;
    final sameToken = _store.pushToken == token;
    if (sameUser && sameToken) {
      return;
    }

    await _apiService.registerPushToken(
      platform: Platform.isIOS ? 'ios' : 'android',
      pushToken: token,
    );
    await _store.savePushTokenRegistration(
      userId: currentUser.id,
      token: token,
    );
  }

  Future<void> _refreshChatThreads() async {
    chatThreads = await _apiService.getFamilyChatThreads();
  }

  Future<void> _refreshActiveChatMessages({
    required bool allowAutoSelect,
  }) async {
    var partnerUserId = activeChatPartnerUserId;
    if (partnerUserId == null && allowAutoSelect && chatThreads.isNotEmpty) {
      partnerUserId = chatThreads.first.partnerUserId;
      activeChatPartnerUserId = partnerUserId;
    }

    if (partnerUserId == null) {
      activeChatMessages = const [];
      return;
    }

    final threadExists = chatThreads.any(
      (thread) => thread.partnerUserId == partnerUserId,
    );
    if (!threadExists) {
      activeChatPartnerUserId = null;
      activeChatMessages = const [];
      return;
    }

    activeChatMessages = await _apiService.getFamilyChatMessages(partnerUserId);
    chatThreads = await _apiService.getFamilyChatThreads();
  }

  Future<void> _maybeJoinAcceptedCall(CallSession? session) async {
    final currentUser = profile;
    if (currentUser == null ||
        session == null ||
        session.status != 'accepted') {
      return;
    }

    await _callService.joinAudioCall(
      user: currentUser,
      session: session,
      onSyncEndCall: () async {
        final updatedSession = await _apiService.endCall(session.callSessionId);
        activeCall = updatedSession;
        _mergeCallIntoHistory(updatedSession);
        _syncActiveCallFromHistory();
        notifyListeners();
      },
    );
  }

  void _mergeCallIntoHistory(CallSession session) {
    final items = [...callHistory];
    final index = items.indexWhere(
      (item) => item.callSessionId == session.callSessionId,
    );
    if (index >= 0) {
      items[index] = session;
    } else {
      items.insert(0, session);
    }
    callHistory = items;
  }

  void _syncActiveCallFromHistory() {
    CallSession? resolvedCall = activeCall;
    if (resolvedCall != null) {
      final currentCallId = resolvedCall.callSessionId;
      for (final item in callHistory) {
        if (item.callSessionId == currentCallId) {
          resolvedCall = item;
          break;
        }
      }
    }

    if (resolvedCall == null || _isCallFinished(resolvedCall)) {
      resolvedCall = _findLatestActiveCall();
    }

    activeCall = resolvedCall;
    if (activeCall != null && !_isCallFinished(activeCall)) {
      _stopIncomingCallWatcher();
      _startPollingCall();
    } else {
      _stopPollingCall();
      _callService.clearActiveCall();
      if (stage == AppStage.home) {
        _startIncomingCallWatcher();
      } else {
        _stopIncomingCallWatcher();
      }
    }
  }

  CallSession? _findLatestActiveCall() {
    for (final session in callHistory) {
      if (!_isCallFinished(session)) {
        return session;
      }
    }
    return null;
  }

  bool _isCallFinished(CallSession? session) {
    return session == null || session.isFinished;
  }

  @override
  void dispose() {
    _stopPollingCall();
    _stopIncomingCallWatcher();
    _pushSubscription?.cancel();
    _callService.uninitialize();
    _messagingService.dispose();
    super.dispose();
  }
}
