class BootstrapUser {
  const BootstrapUser({
    required this.id,
    required this.fullName,
  });

  final int id;
  final String fullName;

  factory BootstrapUser.fromJson(Map<String, dynamic> json) {
    return BootstrapUser(
      id: json['id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
    );
  }
}

class BootstrapState {
  const BootstrapState({
    required this.authenticated,
    required this.pinConfigured,
    required this.user,
  });

  final bool authenticated;
  final bool pinConfigured;
  final BootstrapUser? user;

  factory BootstrapState.fromJson(Map<String, dynamic> json) {
    return BootstrapState(
      authenticated: json['authenticated'] as bool? ?? false,
      pinConfigured: json['pin_configured'] as bool? ?? false,
      user: json['user'] is Map<String, dynamic>
          ? BootstrapUser.fromJson(json['user'] as Map<String, dynamic>)
          : null,
    );
  }
}

class UserProfile {
  const UserProfile({
    required this.id,
    required this.fullName,
    required this.age,
    required this.email,
    required this.phoneNumber,
    required this.careRoleKey,
    required this.careRoleLabel,
    required this.hasPersonalGeminiKey,
    required this.geminiKeyPreview,
  });

  final int id;
  final String fullName;
  final int age;
  final String email;
  final String phoneNumber;
  final String careRoleKey;
  final String careRoleLabel;
  final bool hasPersonalGeminiKey;
  final String geminiKeyPreview;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
      age: json['age'] as int? ?? 0,
      email: json['email'] as String? ?? '',
      phoneNumber: json['phone_number'] as String? ?? '',
      careRoleKey: json['care_role_key'] as String? ?? '',
      careRoleLabel: json['care_role_label'] as String? ?? '',
      hasPersonalGeminiKey: json['has_personal_gemini_key'] as bool? ?? false,
      geminiKeyPreview: json['gemini_key_preview'] as String? ?? '',
    );
  }
}

class FamilyMember {
  const FamilyMember({
    required this.membershipId,
    required this.userId,
    required this.fullName,
    required this.age,
    required this.email,
    required this.phoneNumber,
    required this.role,
    required this.joinedAt,
  });

  final int membershipId;
  final int userId;
  final String fullName;
  final int age;
  final String email;
  final String phoneNumber;
  final String role;
  final String joinedAt;

  factory FamilyMember.fromJson(Map<String, dynamic> json) {
    return FamilyMember(
      membershipId: json['membership_id'] as int? ?? 0,
      userId: json['user_id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
      age: json['age'] as int? ?? 0,
      email: json['email'] as String? ?? '',
      phoneNumber: json['phone_number'] as String? ?? '',
      role: json['role'] as String? ?? '',
      joinedAt: json['joined_at'] as String? ?? '',
    );
  }
}

class FamilyGroup {
  const FamilyGroup({
    required this.familyGroupId,
    required this.familyName,
    required this.role,
    required this.createdByUserId,
    required this.members,
  });

  final int familyGroupId;
  final String familyName;
  final String role;
  final int createdByUserId;
  final List<FamilyMember> members;

  factory FamilyGroup.fromJson(Map<String, dynamic> json) {
    final members = (json['members'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(FamilyMember.fromJson)
        .toList();

    return FamilyGroup(
      familyGroupId: json['family_group_id'] as int? ?? 0,
      familyName: json['family_name'] as String? ?? '',
      role: json['role'] as String? ?? '',
      createdByUserId: json['created_by_user_id'] as int? ?? 0,
      members: members,
    );
  }
}

class FamilyInvitation {
  const FamilyInvitation({
    required this.id,
    required this.familyGroupId,
    required this.familyName,
    required this.invitedByName,
    required this.createdAt,
    required this.status,
  });

  final int id;
  final int familyGroupId;
  final String familyName;
  final String invitedByName;
  final String createdAt;
  final String status;

  factory FamilyInvitation.fromJson(Map<String, dynamic> json) {
    return FamilyInvitation(
      id: json['id'] as int? ?? 0,
      familyGroupId: json['family_group_id'] as int? ?? 0,
      familyName: json['family_name'] as String? ?? '',
      invitedByName: json['invited_by_name'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }
}

class FamilyRelationship {
  const FamilyRelationship({
    required this.id,
    required this.relativeUserId,
    required this.relationshipKey,
    required this.relationshipLabel,
    required this.priorityOrder,
    required this.relativeFullName,
  });

  final int id;
  final int relativeUserId;
  final String relationshipKey;
  final String relationshipLabel;
  final int priorityOrder;
  final String relativeFullName;

  factory FamilyRelationship.fromJson(Map<String, dynamic> json) {
    return FamilyRelationship(
      id: json['id'] as int? ?? 0,
      relativeUserId: json['relative_user_id'] as int? ?? 0,
      relationshipKey: json['relationship_key'] as String? ?? '',
      relationshipLabel: json['relationship_label'] as String? ?? '',
      priorityOrder: json['priority_order'] as int? ?? 0,
      relativeFullName: json['relative_full_name'] as String? ?? '',
    );
  }
}

class RelationshipOption {
  const RelationshipOption({
    required this.key,
    required this.label,
  });

  final String key;
  final String label;

  factory RelationshipOption.fromJson(Map<String, dynamic> json) {
    return RelationshipOption(
      key: json['key'] as String? ?? '',
      label: json['label'] as String? ?? '',
    );
  }
}

class CallRelationshipBundle {
  const CallRelationshipBundle({
    required this.relationships,
    required this.supportedRelationships,
  });

  final List<FamilyRelationship> relationships;
  final List<RelationshipOption> supportedRelationships;
}

class VoiceAssistantResult {
  const VoiceAssistantResult({
    required this.action,
    required this.message,
    required this.question,
    required this.call,
    required this.pendingCallToken,
  });

  final String action;
  final String message;
  final String? question;
  final CallSession? call;
  final String? pendingCallToken;

  bool get isCalling => action == 'calling' && call != null;
  bool get isConfirmationRequired => action == 'confirm';

  factory VoiceAssistantResult.fromJson(Map<String, dynamic> json) {
    final rawMessage = json['message'] as String? ?? '';
    final rawQuestion = json['question'] as String?;
    return VoiceAssistantResult(
      action: json['action'] as String? ?? 'chat',
      message: rawMessage.isNotEmpty
          ? rawMessage
          : (rawQuestion ?? 'Trợ lý chưa có phản hồi.'),
      question: rawQuestion,
      call: json['call'] is Map<String, dynamic>
          ? CallSession.fromJson(json['call'] as Map<String, dynamic>)
          : null,
      pendingCallToken: json['pending_call_token'] as String?,
    );
  }
}

class CallParty {
  const CallParty({
    required this.id,
    required this.fullName,
  });

  final int id;
  final String fullName;

  factory CallParty.fromJson(Map<String, dynamic> json) {
    return CallParty(
      id: json['id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
    );
  }
}

class CallTarget {
  const CallTarget({
    required this.targetUserId,
    required this.fullName,
    required this.relationshipKey,
    required this.priorityOrder,
    required this.status,
  });

  final int targetUserId;
  final String fullName;
  final String relationshipKey;
  final int priorityOrder;
  final String status;

  factory CallTarget.fromJson(Map<String, dynamic> json) {
    return CallTarget(
      targetUserId: json['target_user_id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
      relationshipKey: json['relationship_key'] as String? ?? '',
      priorityOrder: json['priority_order'] as int? ?? 0,
      status: json['status'] as String? ?? '',
    );
  }
}

class CallSession {
  const CallSession({
    required this.callSessionId,
    required this.roomId,
    required this.provider,
    required this.status,
    required this.triggerSource,
    required this.relationshipKey,
    required this.relationshipLabel,
    required this.ringTimeoutSeconds,
    required this.caller,
    required this.acceptedBy,
    required this.currentTargetName,
    required this.targets,
    required this.transcriptText,
    required this.detectedIntent,
    required this.acceptedAt,
    required this.endedAt,
    required this.endReason,
    required this.createdAt,
  });

  final int callSessionId;
  final String roomId;
  final String provider;
  final String status;
  final String triggerSource;
  final String relationshipKey;
  final String? relationshipLabel;
  final int ringTimeoutSeconds;
  final CallParty? caller;
  final CallParty? acceptedBy;
  final String? currentTargetName;
  final List<CallTarget> targets;
  final String? transcriptText;
  final String? detectedIntent;
  final String? acceptedAt;
  final String? endedAt;
  final String? endReason;
  final String? createdAt;

  bool get isFinished {
    const finished = {'ended', 'failed', 'missed', 'declined', 'timeout'};
    return finished.contains(status);
  }

  bool isCaller(int userId) => caller?.id == userId;

  bool isAcceptedBy(int userId) => acceptedBy?.id == userId;

  CallTarget? targetForUser(int userId) {
    for (final target in targets) {
      if (target.targetUserId == userId) {
        return target;
      }
    }
    return null;
  }

  bool isRingingFor(int userId) {
    final target = targetForUser(userId);
    return status == 'ringing' && target?.status == 'ringing';
  }

  bool canAccept(int userId) => isRingingFor(userId);

  bool canDecline(int userId) => isRingingFor(userId);

  bool canEnd(int userId) => isCaller(userId) && !isFinished;

  bool canRedial(int userId) =>
      isCaller(userId) && isFinished && relationshipKey.trim().isNotEmpty;

  factory CallSession.fromJson(Map<String, dynamic> json) {
    final currentTarget = json['current_target'] as Map<String, dynamic>?;
    final targets = (json['targets'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(CallTarget.fromJson)
        .toList();

    return CallSession(
      callSessionId: json['call_session_id'] as int? ?? 0,
      roomId: json['room_id'] as String? ?? '',
      provider: json['provider'] as String? ?? '',
      status: json['status'] as String? ?? '',
      triggerSource: json['trigger_source'] as String? ?? '',
      relationshipKey: json['relationship_key'] as String? ?? '',
      relationshipLabel: json['relationship_label'] as String?,
      ringTimeoutSeconds: json['ring_timeout_seconds'] as int? ?? 0,
      caller: json['caller'] is Map<String, dynamic>
          ? CallParty.fromJson(json['caller'] as Map<String, dynamic>)
          : null,
      acceptedBy: json['accepted_by'] is Map<String, dynamic>
          ? CallParty.fromJson(json['accepted_by'] as Map<String, dynamic>)
          : null,
      currentTargetName: currentTarget?['full_name'] as String?,
      targets: targets,
      transcriptText: json['transcript_text'] as String?,
      detectedIntent: json['detected_intent'] as String?,
      acceptedAt: json['accepted_at'] as String?,
      endedAt: json['ended_at'] as String?,
      endReason: json['end_reason'] as String?,
      createdAt: json['created_at'] as String?,
    );
  }
}

class EmotionEntry {
  const EmotionEntry({
    required this.id,
    required this.userId,
    required this.fullName,
    required this.age,
    required this.messageText,
    required this.emotionLabel,
    required this.emotionScore,
    required this.riskLevel,
    required this.alertSent,
    required this.detectedKeywords,
    required this.createdAt,
  });

  final int id;
  final int userId;
  final String fullName;
  final int age;
  final String messageText;
  final String emotionLabel;
  final int emotionScore;
  final String riskLevel;
  final bool alertSent;
  final List<String> detectedKeywords;
  final String createdAt;

  factory EmotionEntry.fromJson(Map<String, dynamic> json) {
    return EmotionEntry(
      id: json['id'] as int? ?? 0,
      userId: json['user_id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
      age: json['age'] as int? ?? 0,
      messageText: json['message_text'] as String? ?? '',
      emotionLabel: json['emotion_label'] as String? ?? '',
      emotionScore: json['emotion_score'] as int? ?? 100,
      riskLevel: json['risk_level'] as String? ?? 'stable',
      alertSent: json['alert_sent'] as bool? ?? false,
      detectedKeywords:
          (json['detected_keywords'] as List<dynamic>? ?? const [])
              .map((item) => '$item')
              .toList(),
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}

class EmotionTrendPoint {
  const EmotionTrendPoint({
    required this.date,
    required this.averageScore,
    required this.entryCount,
  });

  final String date;
  final int averageScore;
  final int entryCount;

  factory EmotionTrendPoint.fromJson(Map<String, dynamic> json) {
    return EmotionTrendPoint(
      date: json['date'] as String? ?? '',
      averageScore: json['average_score'] as int? ?? 100,
      entryCount: json['entry_count'] as int? ?? 0,
    );
  }
}

class EmotionMemberSummary {
  const EmotionMemberSummary({
    required this.userId,
    required this.fullName,
    required this.age,
    required this.careRoleKey,
    required this.careRoleLabel,
    required this.latestScore,
    required this.latestLabel,
    required this.latestRiskLevel,
    required this.latestMessage,
    required this.latestCreatedAt,
    required this.averageScore7d,
    required this.recentEntries,
    required this.trend,
  });

  final int userId;
  final String fullName;
  final int age;
  final String careRoleKey;
  final String careRoleLabel;
  final int latestScore;
  final String latestLabel;
  final String latestRiskLevel;
  final String latestMessage;
  final String? latestCreatedAt;
  final int averageScore7d;
  final List<EmotionEntry> recentEntries;
  final List<EmotionTrendPoint> trend;

  factory EmotionMemberSummary.fromJson(Map<String, dynamic> json) {
    return EmotionMemberSummary(
      userId: json['user_id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
      age: json['age'] as int? ?? 0,
      careRoleKey: json['care_role_key'] as String? ?? '',
      careRoleLabel: json['care_role_label'] as String? ?? '',
      latestScore: json['latest_score'] as int? ?? 100,
      latestLabel: json['latest_label'] as String? ?? '',
      latestRiskLevel: json['latest_risk_level'] as String? ?? 'stable',
      latestMessage: json['latest_message'] as String? ?? '',
      latestCreatedAt: json['latest_created_at'] as String?,
      averageScore7d: json['average_score_7d'] as int? ?? 100,
      recentEntries: (json['recent_entries'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(EmotionEntry.fromJson)
          .toList(),
      trend: (json['trend'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(EmotionTrendPoint.fromJson)
          .toList(),
    );
  }
}

class EmotionDashboardSummary {
  const EmotionDashboardSummary({
    required this.elderCount,
    required this.averageScore,
    required this.criticalCount,
    required this.warningCount,
    required this.stableCount,
  });

  final int elderCount;
  final int averageScore;
  final int criticalCount;
  final int warningCount;
  final int stableCount;

  factory EmotionDashboardSummary.fromJson(Map<String, dynamic> json) {
    return EmotionDashboardSummary(
      elderCount: json['elder_count'] as int? ?? 0,
      averageScore: json['average_score'] as int? ?? 100,
      criticalCount: json['critical_count'] as int? ?? 0,
      warningCount: json['warning_count'] as int? ?? 0,
      stableCount: json['stable_count'] as int? ?? 0,
    );
  }
}

class EmotionDashboard {
  const EmotionDashboard({
    required this.familyGroupId,
    required this.generatedAt,
    required this.summary,
    required this.elders,
  });

  final int familyGroupId;
  final String generatedAt;
  final EmotionDashboardSummary summary;
  final List<EmotionMemberSummary> elders;

  factory EmotionDashboard.fromJson(Map<String, dynamic> json) {
    return EmotionDashboard(
      familyGroupId: json['family_group_id'] as int? ?? 0,
      generatedAt: json['generated_at'] as String? ?? '',
      summary: EmotionDashboardSummary.fromJson(
        json['summary'] as Map<String, dynamic>? ?? const {},
      ),
      elders: (json['elders'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(EmotionMemberSummary.fromJson)
          .toList(),
    );
  }
}

class FamilyChatMessage {
  const FamilyChatMessage({
    required this.id,
    required this.familyGroupId,
    required this.senderUserId,
    required this.senderFullName,
    required this.recipientUserId,
    required this.recipientFullName,
    required this.messageText,
    required this.readAt,
    required this.createdAt,
  });

  final int id;
  final int familyGroupId;
  final int senderUserId;
  final String senderFullName;
  final int recipientUserId;
  final String recipientFullName;
  final String messageText;
  final String? readAt;
  final String createdAt;

  bool isFromUser(int userId) => senderUserId == userId;

  factory FamilyChatMessage.fromJson(Map<String, dynamic> json) {
    return FamilyChatMessage(
      id: json['id'] as int? ?? 0,
      familyGroupId: json['family_group_id'] as int? ?? 0,
      senderUserId: json['sender_user_id'] as int? ?? 0,
      senderFullName: json['sender_full_name'] as String? ?? '',
      recipientUserId: json['recipient_user_id'] as int? ?? 0,
      recipientFullName: json['recipient_full_name'] as String? ?? '',
      messageText: json['message_text'] as String? ?? '',
      readAt: json['read_at'] as String?,
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}

class FamilyChatThread {
  const FamilyChatThread({
    required this.partnerUserId,
    required this.partnerFullName,
    required this.partnerRole,
    required this.lastMessage,
    required this.unreadCount,
  });

  final int partnerUserId;
  final String partnerFullName;
  final String partnerRole;
  final FamilyChatMessage? lastMessage;
  final int unreadCount;

  factory FamilyChatThread.fromJson(Map<String, dynamic> json) {
    return FamilyChatThread(
      partnerUserId: json['partner_user_id'] as int? ?? 0,
      partnerFullName: json['partner_full_name'] as String? ?? '',
      partnerRole: json['partner_role'] as String? ?? '',
      lastMessage: json['last_message'] is Map<String, dynamic>
          ? FamilyChatMessage.fromJson(
              json['last_message'] as Map<String, dynamic>,
            )
          : null,
      unreadCount: json['unread_count'] as int? ?? 0,
    );
  }
}
