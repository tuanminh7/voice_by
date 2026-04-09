import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../config/app_config.dart';
import '../models/app_models.dart';
import '../services/api_service.dart';
import '../services/call_ringtone_service.dart';
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
    this._ringtoneService,
    this._messagingService,
    this.deviceId,
  );

  final LocalStore _store;
  final ApiService _apiService;
  final ZegoCallService _callService;
  final CallRingtoneService _ringtoneService;
  final FirebaseMessagingService _messagingService;
  final String deviceId;

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
  VoiceAssistantResult? latestVoiceAssistantResult;
  String? errorMessage;
  bool busy = false;
  Timer? _callPollTimer;
  Timer? _incomingCallWatchTimer;
  Timer? _chatPollTimer;
  StreamSubscription<CallPushMessage>? _pushSubscription;
  StreamSubscription<String>? _pushTokenSubscription;
  bool _callPollBusy = false;
  bool _incomingCallWatchBusy = false;
  bool _chatPollBusy = false;
  bool _homeRealtimeSyncBusy = false;
  bool _homeRealtimeSyncQueued = false;

  bool get hasRealtimeCallConfig => _callService.isConfigured;
  bool get hasPushMessagingConfig => _messagingService.isAvailable;
  String? get autoPushToken => _messagingService.deviceToken;
  String? get pushStatusMessage => _messagingService.availabilityMessage;
  bool get _hasRegisteredPushTokenForCurrentUser {
    final currentUser = profile;
    final token = autoPushToken;
    return currentUser != null &&
        token != null &&
        token.isNotEmpty &&
        _store.pushTokenUserId == currentUser.id &&
        _store.pushToken == token;
  }

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
    final ringtoneService = CallRingtoneService();
    final messagingService = FirebaseMessagingService();
    final deviceId = await store.ensureDeviceId();
    await messagingService.initialize();
    await callService.initialize();
    final controller = AppController._(
      store,
      api,
      callService,
      ringtoneService,
      messagingService,
      deviceId,
    );
    controller._listenToPushMessages();
    controller._listenToPushTokenChanges();
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
        _enterHome();
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
      if (!await _recoverFromApiError(error)) {
        errorMessage = error.toString();
      }
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  void _showRealtimeCallSetupError([String? message]) {
    errorMessage = message ?? AppConfig.realtimeCallSetupHint;
    notifyListeners();
  }

  bool _ensureRealtimeCallReady() {
    if (hasRealtimeCallConfig) {
      return true;
    }
    _showRealtimeCallSetupError();
    return false;
  }

  Future<bool> _recoverFromApiError(Object error) async {
    if (error is! ApiException) {
      return false;
    }

    if (error.isAuthRequired) {
      await _moveToAuthState(error.message);
      return true;
    }
    if (error.isPinRequired) {
      await _moveToPinState(AppStage.pinUnlock, error.message);
      return true;
    }
    if (error.isPinNotConfigured) {
      await _moveToPinState(AppStage.pinSetup, error.message);
      return true;
    }
    return false;
  }

  Future<void> _moveToAuthState(String message) async {
    await _store.savePinToken(null);
    await _store.clearPushTokenRegistration();
    await _ringtoneService.stop();
    _stopPollingCall();
    _stopIncomingCallWatcher();
    _stopChatPolling();
    _callService.clearActiveCall();
    bootstrapState = null;
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
    activeCall = null;
    latestVoiceAssistantResult = null;
    stage = AppStage.auth;
    errorMessage = message;
    notifyListeners();
  }

  Future<void> _moveToPinState(AppStage nextStage, String message) async {
    await _store.savePinToken(null);
    await _ringtoneService.stop();
    _stopPollingCall();
    _stopIncomingCallWatcher();
    _stopChatPolling();
    _callService.clearActiveCall();
    activeCall = null;
    stage = nextStage;
    errorMessage = message;
    notifyListeners();
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
    required String careRoleKey,
  }) async {
    await _runBusy(() async {
      bootstrapState = await _apiService.register(
        fullName: fullName,
        age: age,
        email: email,
        phoneNumber: phoneNumber,
        password: password,
        careRoleKey: careRoleKey,
        deviceId: deviceId,
        deviceName: defaultTargetPlatform.name,
      );
      stage = AppStage.pinSetup;
    });
  }

  Future<void> setupPin(String pin, String confirmPin) async {
    await _runBusy(() async {
      await _apiService.setupPin(pin, confirmPin);
      _enterHome();
    });
  }

  Future<void> unlockWithPin(String pin) async {
    await _runBusy(() async {
      await _apiService.verifyPin(pin);
      _enterHome();
    });
  }

  void _enterHome() {
    stage = AppStage.home;
    notifyListeners();
    unawaited(_loadHomeDataInBackground());
  }

  Future<void> _loadHomeDataInBackground() async {
    try {
      await loadHomeData();
    } catch (error) {
      if (!await _recoverFromApiError(error) && stage == AppStage.home) {
        errorMessage = error.toString();
        notifyListeners();
      }
    }
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
      emotionDashboard = family!.role == 'admin'
          ? await _apiService.getEmotionDashboard()
          : null;
      chatThreads = await _apiService.getFamilyChatThreads();
      await _refreshActiveChatMessages(
        allowAutoSelect: true,
        refreshThreadsAfterFetch: false,
      );
    } else {
      emotionDashboard = null;
      chatThreads = const [];
      activeChatMessages = const [];
      activeChatPartnerUserId = null;
      _syncChatPolling();
    }

    _syncActiveCallFromHistory();
    notifyListeners();
    _scheduleHomeRealtimeSync();
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

  Future<void> submitVoiceInput(String transcriptText) async {
    await _runBusy(() async {
      latestVoiceAssistantResult = await _apiService.submitVoiceInput(
        transcriptText,
        realtimeCallReady: hasRealtimeCallConfig,
      );
      final createdCall = latestVoiceAssistantResult?.call;
      if (createdCall != null) {
        activeCall = createdCall;
        _mergeCallIntoHistory(createdCall);
        _syncActiveCallFromHistory();
      }
    });
  }

  Future<void> openChatThread(int partnerUserId) async {
    await _runBusy(() async {
      activeChatPartnerUserId = partnerUserId;
      await _refreshChatThreads();
      await _refreshActiveChatMessages(allowAutoSelect: false);
      _syncChatPolling();
    });
  }

  Future<void> sendChatMessage(String messageText) async {
    var partnerUserId = activeChatPartnerUserId;
    if (partnerUserId == null && chatThreads.isNotEmpty) {
      partnerUserId = chatThreads.first.partnerUserId;
      activeChatPartnerUserId = partnerUserId;
    }
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
      await _refreshActiveChatMessages(allowAutoSelect: false);
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
    if (!_ensureRealtimeCallReady()) {
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

  Future<void> redialActiveCall() async {
    final session = activeCall;
    if (session == null || session.relationshipKey.trim().isEmpty) {
      return;
    }
    if (!_ensureRealtimeCallReady()) {
      return;
    }

    await _runBusy(() async {
      final restartedCall = await _apiService.createManualCall(
        session.relationshipKey,
      );
      latestVoiceAssistantResult = VoiceAssistantResult(
        action: 'calling',
        message:
            'Đang gọi lại ${session.relationshipLabel ?? session.relationshipKey}.',
        question: null,
        call: restartedCall,
      );
      activeCall = restartedCall;
      _mergeCallIntoHistory(restartedCall);
      _syncActiveCallFromHistory();
    });
  }

  Future<void> logout() async {
    final registeredPushToken = _store.pushToken;
    await _runBusy(() async {
      if (registeredPushToken != null && registeredPushToken.isNotEmpty) {
        try {
          await _apiService.unregisterPushToken(pushToken: registeredPushToken);
        } catch (_) {
          // Continue with local logout even if push token cleanup fails.
        }
      }
      try {
        await _apiService.logout();
      } catch (_) {
        // Continue with local logout even if backend logout fails.
      }
      await _store.savePinToken(null);
      await _store.clearPushTokenRegistration();
      await _callService.uninitialize();
      await _ringtoneService.stop();
      _stopPollingCall();
      _stopIncomingCallWatcher();
      _stopChatPolling();
      bootstrapState = null;
      activeCall = null;
      latestVoiceAssistantResult = null;
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
        if (_callPollBusy || stage != AppStage.home) {
          return;
        }

        _callPollBusy = true;
        try {
          activeCall = await _apiService.getCallSession(session.callSessionId);
          _mergeCallIntoHistory(activeCall!);
          await _maybeJoinAcceptedCall(activeCall);
          _syncActiveCallFromHistory();
          notifyListeners();
        } catch (error) {
          await _recoverFromApiError(error);
        } finally {
          _callPollBusy = false;
        }
      },
    );
  }

  void _stopPollingCall() {
    _callPollTimer?.cancel();
    _callPollTimer = null;
    _callPollBusy = false;
  }

  void _startIncomingCallWatcher() {
    if (_incomingCallWatchTimer != null) {
      return;
    }

    unawaited(_refreshIncomingCalls());
    _incomingCallWatchTimer = Timer.periodic(
      const Duration(seconds: AppConfig.incomingCallWatchIntervalSeconds),
      (_) async {
        await _refreshIncomingCalls();
      },
    );
  }

  void _stopIncomingCallWatcher() {
    _incomingCallWatchTimer?.cancel();
    _incomingCallWatchTimer = null;
  }

  void _startChatPolling() {
    if (_chatPollTimer != null) {
      return;
    }

    unawaited(_pollChatUpdates(notifyAfterRefresh: true));
    _chatPollTimer = Timer.periodic(
      const Duration(seconds: AppConfig.chatPollIntervalSeconds),
      (_) async {
        await _pollChatUpdates(notifyAfterRefresh: true);
      },
    );
  }

  void _stopChatPolling() {
    _chatPollTimer?.cancel();
    _chatPollTimer = null;
  }

  void _syncChatPolling() {
    if (stage == AppStage.home && family != null) {
      _startChatPolling();
    } else {
      _stopChatPolling();
    }
  }

  Future<void> _pollChatUpdates({
    required bool notifyAfterRefresh,
  }) async {
    if (_chatPollBusy || stage != AppStage.home || family == null) {
      return;
    }

    _chatPollBusy = true;
    try {
      await _refreshChatThreads();
      if (activeChatPartnerUserId != null) {
        await _refreshActiveChatMessages(
          allowAutoSelect: false,
          refreshThreadsAfterFetch: false,
        );
      } else {
        _syncChatPolling();
      }
      if (notifyAfterRefresh) {
        notifyListeners();
      }
    } catch (error) {
      await _recoverFromApiError(error);
    } finally {
      _chatPollBusy = false;
    }
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
    } catch (error) {
      await _recoverFromApiError(error);
    } finally {
      _incomingCallWatchBusy = false;
    }
  }

  void _listenToPushMessages() {
    _pushSubscription = _messagingService.callMessages.listen((message) async {
      await _handlePushCallMessage(message);
    });
  }

  void _listenToPushTokenChanges() {
    _pushTokenSubscription = _messagingService.tokenChanges.listen((_) async {
      final currentUser = profile;
      if (currentUser == null || stage != AppStage.home) {
        return;
      }

      try {
        await _syncAutomaticPushToken(currentUser);
        _syncActiveCallFromHistory();
        notifyListeners();
      } catch (error) {
        if (!await _recoverFromApiError(error)) {
          // Ignore token sync hiccups; app reload or next token update can retry.
        }
      }
    });
  }

  void _scheduleHomeRealtimeSync() {
    _homeRealtimeSyncQueued = true;
    if (_homeRealtimeSyncBusy) {
      return;
    }
    unawaited(_runHomeRealtimeSync());
  }

  Future<void> _runHomeRealtimeSync() async {
    if (_homeRealtimeSyncBusy) {
      return;
    }

    _homeRealtimeSyncBusy = true;
    try {
      while (_homeRealtimeSyncQueued) {
        _homeRealtimeSyncQueued = false;
        try {
          await _syncRealtimeServices();
          if (stage != AppStage.home) {
            continue;
          }
          _syncActiveCallFromHistory();
          await _consumeLaunchPushMessage();
        } catch (error) {
          if (!await _recoverFromApiError(error) && stage == AppStage.home) {
            errorMessage = error.toString();
          }
        }
      }
    } finally {
      _homeRealtimeSyncBusy = false;
      if (stage == AppStage.home) {
        notifyListeners();
      }
    }
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
      if (message.eventType == 'family_chat_message') {
        await _handleIncomingChatPush(message);
        return;
      }

      if ({
        'family_invitation',
        'family_invitation_accepted',
        'family_invitation_declined',
        'emotion_alert',
      }.contains(message.eventType)) {
        await loadHomeData();
        return;
      }

      final callSessionId = message.callSessionId;
      if (callSessionId == null || callSessionId <= 0) {
        return;
      }

      var session = await _apiService.getCallSession(callSessionId);
      final currentUser = profile;
      if (currentUser != null &&
          message.openedFromNotification &&
          session.canAccept(currentUser.id)) {
        session = await _apiService.acceptCall(callSessionId);
      }

      activeCall = session;
      _mergeCallIntoHistory(session);
      await _maybeJoinAcceptedCall(session);
      _syncActiveCallFromHistory();
      notifyListeners();
    } catch (error) {
      if (!await _recoverFromApiError(error)) {
        // Ignore malformed or outdated push payloads.
      }
    }
  }

  Future<void> _handleIncomingChatPush(CallPushMessage message) async {
    final senderUserId =
        int.tryParse('${message.payload['sender_user_id'] ?? ''}');
    final recipientUserId =
        int.tryParse('${message.payload['recipient_user_id'] ?? ''}');

    await _refreshChatThreads();

    final activePartnerId = activeChatPartnerUserId;
    final shouldRefreshActiveThread = activePartnerId != null &&
        (activePartnerId == senderUserId || activePartnerId == recipientUserId);

    if (shouldRefreshActiveThread) {
      await _refreshActiveChatMessages(allowAutoSelect: false);
    }

    notifyListeners();
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
    bool refreshThreadsAfterFetch = true,
  }) async {
    var partnerUserId = activeChatPartnerUserId;
    if (partnerUserId == null && allowAutoSelect && chatThreads.isNotEmpty) {
      partnerUserId = chatThreads.first.partnerUserId;
      activeChatPartnerUserId = partnerUserId;
    }

    if (partnerUserId == null) {
      activeChatMessages = const [];
      _syncChatPolling();
      return;
    }

    final threadExists = chatThreads.any(
      (thread) => thread.partnerUserId == partnerUserId,
    );
    if (!threadExists) {
      if (allowAutoSelect && chatThreads.isNotEmpty) {
        partnerUserId = chatThreads.first.partnerUserId;
        activeChatPartnerUserId = partnerUserId;
      } else {
        activeChatPartnerUserId = null;
        activeChatMessages = const [];
        _syncChatPolling();
        return;
      }
    }

    activeChatMessages = await _apiService.getFamilyChatMessages(partnerUserId);
    if (refreshThreadsAfterFetch) {
      chatThreads = await _apiService.getFamilyChatThreads();
    }
    _syncChatPolling();
  }

  Future<void> _maybeJoinAcceptedCall(CallSession? session) async {
    final currentUser = profile;
    if (currentUser == null ||
        session == null ||
        session.status != 'accepted') {
      return;
    }

    await _ringtoneService.stop();
    final joinError = await _callService.joinAudioCall(
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
    if (joinError != null && joinError.trim().isNotEmpty) {
      errorMessage = joinError;
      notifyListeners();
    }
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
    _syncIncomingCallRingtone();
    if (activeCall != null && !_isCallFinished(activeCall)) {
      _stopIncomingCallWatcher();
      _startPollingCall();
    } else {
      _stopPollingCall();
      _callService.clearActiveCall();
      if (stage == AppStage.home && !_hasRegisteredPushTokenForCurrentUser) {
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

  void _syncIncomingCallRingtone() {
    final currentUser = profile;
    final session = activeCall;
    final shouldRing = currentUser != null &&
        session != null &&
        session.canAccept(currentUser.id);
    unawaited(_ringtoneService.sync(shouldRing: shouldRing));
  }

  @override
  void dispose() {
    unawaited(_ringtoneService.stop());
    _stopPollingCall();
    _stopIncomingCallWatcher();
    _stopChatPolling();
    _pushSubscription?.cancel();
    _pushTokenSubscription?.cancel();
    _callService.uninitialize();
    _messagingService.dispose();
    super.dispose();
  }
}
