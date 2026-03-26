import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../models/app_models.dart';
import '../state/app_controller.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _speech = SpeechToText();
  final _transcript = TextEditingController();
  final _pushToken = TextEditingController();
  final _priorityOrder = TextEditingController(text: '1');
  String? _selectedRelationshipKey;
  int? _selectedRelativeUserId;
  bool _isListening = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      context.read<AppController>().loadHomeData();
    });
  }

  @override
  void dispose() {
    _transcript.dispose();
    _pushToken.dispose();
    _priorityOrder.dispose();
    super.dispose();
  }

  Future<void> _startListening() async {
    final available = await _speech.initialize();
    if (!available) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Thiet bi nay chua san sang speech-to-text.'),
        ),
      );
      return;
    }

    setState(() {
      _isListening = true;
    });

    await _speech.listen(
      localeId: 'vi_VN',
      onResult: (result) {
        _transcript.text = result.recognizedWords;
      },
    );
  }

  Future<void> _stopListening() async {
    await _speech.stop();
    if (!mounted) {
      return;
    }
    setState(() {
      _isListening = false;
    });
  }

  String? _resolveRelationshipKey(List<RelationshipOption> options) {
    final selected = _selectedRelationshipKey;
    if (selected != null && options.any((option) => option.key == selected)) {
      return selected;
    }
    return options.isNotEmpty ? options.first.key : null;
  }

  int? _resolveRelativeUserId(List<FamilyMember> members) {
    final selected = _selectedRelativeUserId;
    if (selected != null &&
        members.any((member) => member.userId == selected)) {
      return selected;
    }
    return members.isNotEmpty ? members.first.userId : null;
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AppController>();
    final profile = controller.profile;
    final family = controller.family;
    final options = controller.relationshipOptions;

    final familyMembers = (family?.members ?? const <FamilyMember>[])
        .where((member) => member.userId != profile?.id)
        .toList();
    final selectedRelationshipKey = _resolveRelationshipKey(options);
    final selectedRelativeUserId = _resolveRelativeUserId(familyMembers);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Emergency Call V2'),
        actions: [
          IconButton(
            onPressed: controller.busy ? null : controller.logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: controller.loadHomeData,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (profile != null) ...[
              Text(
                'Xin chao ${profile.fullName}',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text('${profile.email} | ${profile.phoneNumber}'),
            ],
            const SizedBox(height: 20),
            _FamilyCard(
              family: family,
              realtimeConfigured: controller.hasRealtimeCallConfig,
              pushConfigured: controller.hasPushMessagingConfig,
            ),
            const SizedBox(height: 20),
            _InvitationCard(
              invitations: controller.pendingInvitations,
              busy: controller.busy,
              onAccept: (invitationId) => controller.respondToInvitation(
                invitationId: invitationId,
                action: 'accept',
              ),
              onDecline: (invitationId) => controller.respondToInvitation(
                invitationId: invitationId,
                action: 'decline',
              ),
            ),
            const SizedBox(height: 20),
            _ActiveCallCard(
              activeCall: controller.activeCall,
              busy: controller.busy,
              onRefresh: controller.refreshActiveCall,
              onAccept: controller.acceptActiveCall,
              onDecline: controller.declineActiveCall,
              onEnd: controller.endActiveCall,
            ),
            const SizedBox(height: 20),
            _VoiceCallCard(
              transcriptController: _transcript,
              isListening: _isListening,
              onListen: _startListening,
              onStop: _stopListening,
              onSubmit: () =>
                  controller.createVoiceCall(_transcript.text.trim()),
              busy: controller.busy,
            ),
            const SizedBox(height: 20),
            _RelationshipCard(
              familyMembers: familyMembers,
              options: options,
              selectedRelationshipKey: selectedRelationshipKey,
              selectedRelativeUserId: selectedRelativeUserId,
              priorityController: _priorityOrder,
              relationships: controller.relationships,
              busy: controller.busy,
              onSelectRelationship: (value) {
                setState(() {
                  _selectedRelationshipKey = value;
                });
              },
              onSelectRelative: (value) {
                setState(() {
                  _selectedRelativeUserId = value;
                });
              },
              onSave: selectedRelationshipKey == null ||
                      selectedRelativeUserId == null
                  ? null
                  : () => controller.saveRelationship(
                        relativeUserId: selectedRelativeUserId,
                        relationshipKey: selectedRelationshipKey,
                        priorityOrder:
                            int.tryParse(_priorityOrder.text.trim()) ?? 1,
                      ),
              onDelete: controller.deleteRelationship,
            ),
            const SizedBox(height: 20),
            _PushTokenCard(
              controller: _pushToken,
              busy: controller.busy,
              autoPushToken: controller.autoPushToken,
              pushConfigured: controller.hasPushMessagingConfig,
              onSubmit: () => context.read<AppController>().registerPushToken(
                    platform: 'android',
                    pushToken: _pushToken.text.trim(),
                  ),
            ),
            const SizedBox(height: 20),
            _CallHistoryCard(
              callHistory: controller.callHistory,
              currentUserId: profile?.id,
            ),
            if (controller.errorMessage != null) ...[
              const SizedBox(height: 16),
              Text(
                controller.errorMessage!,
                style: const TextStyle(color: Colors.red),
              ),
            ],
            const SizedBox(height: 20),
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Backend call orchestration da chay duoc. Phan con lai de len '
                  'realtime production la Firebase Messaging + ZEGOCLOUD native invitation/audio room.',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FamilyCard extends StatelessWidget {
  const _FamilyCard({
    required this.family,
    required this.realtimeConfigured,
    required this.pushConfigured,
  });

  final FamilyGroup? family;
  final bool realtimeConfigured;
  final bool pushConfigured;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Gia dinh hien tai',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            if (family == null)
              const Text(
                'Tai khoan nay chua co nhom gia dinh, nen chua map duoc nguoi than de goi.',
              )
            else ...[
              Text('${family!.familyName} | role: ${family!.role}'),
              const SizedBox(height: 8),
              Text(
                realtimeConfigured
                    ? 'Realtime audio da san sang cau hinh SDK.'
                    : 'Realtime audio chua du credential ZEGOCLOUD, tam thoi dang dung API orchestration.',
              ),
              const SizedBox(height: 4),
              Text(
                pushConfigured
                    ? 'Firebase Messaging da duoc mo, app se tu lay token neu project Firebase da cau hinh.'
                    : 'Firebase Messaging chua san sang, hien van co the test bang token nhap tay.',
              ),
              const SizedBox(height: 12),
              ...family!.members.map(
                (member) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(member.fullName),
                  subtitle: Text('${member.role} | ${member.phoneNumber}'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _VoiceCallCard extends StatelessWidget {
  const _VoiceCallCard({
    required this.transcriptController,
    required this.isListening,
    required this.onListen,
    required this.onStop,
    required this.onSubmit,
    required this.busy,
  });

  final TextEditingController transcriptController;
  final bool isListening;
  final Future<void> Function() onListen;
  final Future<void> Function() onStop;
  final VoidCallback onSubmit;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Voice intent call',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            const Text('Vi du: Goi con trai'),
            const SizedBox(height: 12),
            TextField(
              controller: transcriptController,
              minLines: 2,
              maxLines: 3,
              decoration: const InputDecoration(labelText: 'Transcript text'),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                FilledButton.icon(
                  onPressed: busy
                      ? null
                      : () async {
                          if (isListening) {
                            await onStop();
                          } else {
                            await onListen();
                          }
                        },
                  icon: Icon(isListening ? Icons.stop : Icons.mic),
                  label: Text(isListening ? 'Dung nghe' : 'Bat dau noi'),
                ),
                OutlinedButton(
                  onPressed: busy ? null : onSubmit,
                  child: const Text('Gui lenh goi'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _InvitationCard extends StatelessWidget {
  const _InvitationCard({
    required this.invitations,
    required this.busy,
    required this.onAccept,
    required this.onDecline,
  });

  final List<FamilyInvitation> invitations;
  final bool busy;
  final Future<void> Function(int invitationId) onAccept;
  final Future<void> Function(int invitationId) onDecline;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Loi moi gia dinh',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            if (invitations.isEmpty)
              const Text('Khong co loi moi nao dang cho.')
            else
              ...invitations.map(
                (invitation) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(invitation.familyName),
                    subtitle: Text(
                      'Moi boi ${invitation.invitedByName} | ${_formatTimestamp(invitation.createdAt)}',
                    ),
                    trailing: Wrap(
                      spacing: 8,
                      children: [
                        IconButton(
                          onPressed: busy
                              ? null
                              : () => onAccept(invitation.id),
                          icon: const Icon(Icons.check_circle_outline),
                        ),
                        IconButton(
                          onPressed: busy
                              ? null
                              : () => onDecline(invitation.id),
                          icon: const Icon(Icons.cancel_outlined),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _formatTimestamp(String value) {
    return value.replaceFirst('T', ' ').split('.').first;
  }
}

class _ActiveCallCard extends StatelessWidget {
  const _ActiveCallCard({
    required this.activeCall,
    required this.busy,
    required this.onRefresh,
    required this.onAccept,
    required this.onDecline,
    required this.onEnd,
  });

  final CallSession? activeCall;
  final bool busy;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onAccept;
  final Future<void> Function() onDecline;
  final Future<void> Function() onEnd;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Active call session',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            if (activeCall == null)
              const Text('Chua co cuoc goi nao dang active.')
            else ...[
              Text('Session: ${activeCall!.callSessionId}'),
              Text('Trang thai: ${activeCall!.status}'),
              if (activeCall!.caller != null)
                Text('Nguoi goi: ${activeCall!.caller!.fullName}'),
              if (activeCall!.relationshipLabel != null)
                Text('Quan he: ${activeCall!.relationshipLabel}'),
              if (activeCall!.currentTargetName != null)
                Text('Dang ring: ${activeCall!.currentTargetName}'),
              if (activeCall!.acceptedBy != null)
                Text('Da nhan boi: ${activeCall!.acceptedBy!.fullName}'),
              if (activeCall!.transcriptText?.isNotEmpty == true)
                Text('Transcript: ${activeCall!.transcriptText}'),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  OutlinedButton(
                    onPressed: busy ? null : onRefresh,
                    child: const Text('Refresh'),
                  ),
                  FilledButton(
                    onPressed: busy ? null : onAccept,
                    child: const Text('Accept'),
                  ),
                  OutlinedButton(
                    onPressed: busy ? null : onDecline,
                    child: const Text('Decline'),
                  ),
                  FilledButton.tonal(
                    onPressed: busy ? null : onEnd,
                    child: const Text('End'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ...activeCall!.targets.map(
                (target) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(target.fullName),
                  subtitle: Text(
                    '${target.relationshipKey} | priority=${target.priorityOrder}',
                  ),
                  trailing: Text(target.status),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RelationshipCard extends StatelessWidget {
  const _RelationshipCard({
    required this.familyMembers,
    required this.options,
    required this.selectedRelationshipKey,
    required this.selectedRelativeUserId,
    required this.priorityController,
    required this.relationships,
    required this.busy,
    required this.onSelectRelationship,
    required this.onSelectRelative,
    required this.onSave,
    required this.onDelete,
  });

  final List<FamilyMember> familyMembers;
  final List<RelationshipOption> options;
  final String? selectedRelationshipKey;
  final int? selectedRelativeUserId;
  final TextEditingController priorityController;
  final List<FamilyRelationship> relationships;
  final bool busy;
  final ValueChanged<String?> onSelectRelationship;
  final ValueChanged<int?> onSelectRelative;
  final VoidCallback? onSave;
  final Future<void> Function(int relationshipId) onDelete;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Quan he goi khan cap',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            if (familyMembers.isEmpty)
              const Text(
                'Can co it nhat 1 nguoi than trong nhom gia dinh thi moi tao duoc mapping goi khan cap.',
              )
            else ...[
              DropdownButtonFormField<int>(
                initialValue: selectedRelativeUserId,
                decoration: const InputDecoration(labelText: 'Nguoi than'),
                items: familyMembers
                    .map(
                      (member) => DropdownMenuItem<int>(
                        value: member.userId,
                        child: Text('${member.fullName} (${member.role})'),
                      ),
                    )
                    .toList(),
                onChanged: busy ? null : onSelectRelative,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: selectedRelationshipKey,
                decoration: const InputDecoration(labelText: 'Quan he'),
                items: options
                    .map(
                      (option) => DropdownMenuItem<String>(
                        value: option.key,
                        child: Text(option.label),
                      ),
                    )
                    .toList(),
                onChanged: busy ? null : onSelectRelationship,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: priorityController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Thu tu uu tien'),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: busy ? null : onSave,
                child: const Text('Luu quan he'),
              ),
            ],
            const SizedBox(height: 16),
            if (relationships.isEmpty)
              const Text('Chua co mapping nao duoc luu.')
            else
              ...relationships.map(
                (relationship) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    '${relationship.relationshipLabel}: ${relationship.relativeFullName}',
                  ),
                  subtitle: Text(
                    'relative_user_id=${relationship.relativeUserId} | priority=${relationship.priorityOrder}',
                  ),
                  trailing: IconButton(
                    onPressed: busy ? null : () => onDelete(relationship.id),
                    icon: const Icon(Icons.delete_outline),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PushTokenCard extends StatelessWidget {
  const _PushTokenCard({
    required this.controller,
    required this.onSubmit,
    required this.busy,
    required this.autoPushToken,
    required this.pushConfigured,
  });

  final TextEditingController controller;
  final VoidCallback onSubmit;
  final bool busy;
  final String? autoPushToken;
  final bool pushConfigured;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Push token', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              pushConfigured
                  ? 'App dang co san luong lay token tu dong. Neu Firebase chua cau hinh xong, ban van co the nhap tay token de test.'
                  : 'Firebase chua cau hinh xong, tam thoi nhap tay token de test backend nhanh.',
            ),
            if (autoPushToken?.isNotEmpty == true) ...[
              const SizedBox(height: 8),
              Text('Auto token: $autoPushToken'),
            ],
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              decoration: const InputDecoration(labelText: 'Push token'),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: busy ? null : onSubmit,
              child: const Text('Dang ky push token'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CallHistoryCard extends StatelessWidget {
  const _CallHistoryCard({
    required this.callHistory,
    required this.currentUserId,
  });

  final List<CallSession> callHistory;
  final int? currentUserId;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Call history',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            if (callHistory.isEmpty)
              const Text('Chua co lich su cuoc goi nao.')
            else
              ...callHistory.take(10).map(
                    (session) => ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(_historyTitle(session, currentUserId)),
                      subtitle: Text(_historySubtitle(session)),
                      trailing: Text(session.status),
                    ),
                  ),
          ],
        ),
      ),
    );
  }

  String _historyTitle(CallSession session, int? currentUserId) {
    final isCaller =
        currentUserId != null && session.caller?.id == currentUserId;
    final direction = isCaller ? 'Ban goi' : 'Ban nhan';
    final relation = session.relationshipLabel ?? session.relationshipKey;
    return '$direction | $relation';
  }

  String _historySubtitle(CallSession session) {
    final callerName = session.caller?.fullName ?? 'Khong ro';
    final acceptedBy = session.acceptedBy?.fullName;
    final endedAt = _formatTimestamp(session.endedAt ?? session.createdAt);

    if (acceptedBy != null && acceptedBy.isNotEmpty) {
      return 'Caller: $callerName | Nguoi nghe: $acceptedBy | $endedAt';
    }
    return 'Caller: $callerName | $endedAt';
  }

  String _formatTimestamp(String? value) {
    if (value == null || value.isEmpty) {
      return 'dang cap nhat';
    }
    return value.replaceFirst('T', ' ').split('.').first;
  }
}
