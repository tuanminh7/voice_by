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
  });

  final int id;
  final String fullName;
  final int age;
  final String email;
  final String phoneNumber;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] as int? ?? 0,
      fullName: json['full_name'] as String? ?? '',
      age: json['age'] as int? ?? 0,
      email: json['email'] as String? ?? '',
      phoneNumber: json['phone_number'] as String? ?? '',
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
