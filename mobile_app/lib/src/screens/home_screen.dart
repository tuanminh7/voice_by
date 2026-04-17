import 'package:flutter_tts/flutter_tts.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../models/app_models.dart';
import '../state/app_controller.dart';

enum HomeMenuSection { voice, family, emotion, chat, calls, settings }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _speech = SpeechToText();
  final _tts = FlutterTts();
  final _transcript = TextEditingController();
  final _chatComposer = TextEditingController();
  final _familyName = TextEditingController();
  final _inviteIdentifier = TextEditingController();
  final _priorityOrder = TextEditingController(text: '1');

  HomeMenuSection _section = HomeMenuSection.voice;
  String? _selectedRelationshipKey;
  int? _selectedRelativeUserId;
  bool _isListening = false;
  String? _lastSpokenAssistantMessage;

  @override
  void initState() {
    super.initState();
    _configureTts();
  }

  Future<void> _configureTts() async {
    await _tts.setLanguage('vi-VN');
    await _tts.setSpeechRate(0.52);
    await _tts.setPitch(1.0);
    await _tts.awaitSpeakCompletion(true);
  }

  @override
  void dispose() {
    _tts.stop();
    _transcript.dispose();
    _chatComposer.dispose();
    _familyName.dispose();
    _inviteIdentifier.dispose();
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
          content: Text('Thiết bị này chưa sẵn sàng nhận diện giọng nói.'),
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
    if (mounted) {
      setState(() {
        _isListening = false;
      });
    }
  }

  String _sectionTitle(HomeMenuSection section) {
    switch (section) {
      case HomeMenuSection.voice:
        return 'Voice';
      case HomeMenuSection.family:
        return 'Gia đình';
      case HomeMenuSection.emotion:
        return 'Giám sát cảm xúc';
      case HomeMenuSection.chat:
        return 'Tin nhắn';
      case HomeMenuSection.calls:
        return 'Cuộc gọi';
      case HomeMenuSection.settings:
        return 'Cài đặt';
    }
  }

  IconData _sectionIcon(HomeMenuSection section) {
    switch (section) {
      case HomeMenuSection.voice:
        return Icons.graphic_eq_rounded;
      case HomeMenuSection.family:
        return Icons.family_restroom_rounded;
      case HomeMenuSection.emotion:
        return Icons.monitor_heart_rounded;
      case HomeMenuSection.chat:
        return Icons.chat_bubble_rounded;
      case HomeMenuSection.calls:
        return Icons.call_rounded;
      case HomeMenuSection.settings:
        return Icons.settings_rounded;
    }
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

  Future<void> _speakAssistantReply(String? message) async {
    final content = message?.trim() ?? '';
    if (content.isEmpty || content == _lastSpokenAssistantMessage) {
      return;
    }

    _lastSpokenAssistantMessage = content;
    await _tts.stop();
    await _tts.speak(content);
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
    final assistantMessage = controller.latestVoiceAssistantResult?.message;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _speakAssistantReply(assistantMessage);
    });

    return Scaffold(
      appBar: AppBar(title: Text(_sectionTitle(_section))),
      drawer: Drawer(
        child: SafeArea(
          child: Column(
            children: [
              DrawerHeader(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: const Color(0xFF0F4C81),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Icon(Icons.favorite_rounded,
                          color: Colors.white),
                    ),
                    const SizedBox(height: 16),
                    Text('Icare',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 6),
                    Text(profile?.fullName ?? 'Chưa có hồ sơ'),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  children: HomeMenuSection.values.map((section) {
                    return ListTile(
                      leading: Icon(_sectionIcon(section)),
                      title: Text(_sectionTitle(section)),
                      selected: section == _section,
                      onTap: () {
                        setState(() {
                          _section = section;
                        });
                        Navigator.of(context).pop();
                      },
                    );
                  }).toList(),
                ),
              ),
            ],
          ),
        ),
      ),
      body: RefreshIndicator(
        onRefresh: controller.loadHomeData,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (controller.errorMessage?.isNotEmpty == true) ...[
              _Panel(
                title: 'Thông báo',
                child: Text(
                  controller.errorMessage!,
                  style: const TextStyle(color: Color(0xFFB91C1C)),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (_section == HomeMenuSection.voice)
              _VoiceView(
                profile: profile,
                transcriptController: _transcript,
                assistantResult: controller.latestVoiceAssistantResult,
                activeCall: controller.activeCall,
                currentUserId: profile?.id,
                busy: controller.busy,
                hasRealtimeCallConfig: controller.hasRealtimeCallConfig,
                isListening: _isListening,
                onListen: _startListening,
                onStop: _stopListening,
                onSubmit: () async {
                  final value = _transcript.text.trim();
                  if (value.isEmpty) {
                    return;
                  }
                  await controller.submitVoiceInput(value);
                },
                onAcceptCall: controller.acceptActiveCall,
                onDeclineCall: controller.declineActiveCall,
                onEndCall: controller.endActiveCall,
                onRedialCall: controller.redialActiveCall,
              ),
            if (_section == HomeMenuSection.family)
              _FamilyView(
                currentUserId: profile?.id,
                family: family,
                invitations: controller.pendingInvitations,
                relationships: controller.relationships,
                options: options,
                familyMembers: familyMembers,
                busy: controller.busy,
                familyNameController: _familyName,
                inviteIdentifierController: _inviteIdentifier,
                priorityController: _priorityOrder,
                selectedRelationshipKey: selectedRelationshipKey,
                selectedRelativeUserId: selectedRelativeUserId,
                onCreateFamily: () async {
                  final value = _familyName.text.trim();
                  if (value.isNotEmpty) {
                    await controller.createFamily(value);
                    _familyName.clear();
                  }
                },
                onInviteMember: () async {
                  final value = _inviteIdentifier.text.trim();
                  if (value.isNotEmpty) {
                    await controller.inviteFamilyMember(value);
                    _inviteIdentifier.clear();
                  }
                },
                onRespondInvitation: controller.respondToInvitation,
                onSaveRelationship: selectedRelationshipKey == null ||
                        selectedRelativeUserId == null
                    ? null
                    : () => controller.saveRelationship(
                          relativeUserId: selectedRelativeUserId,
                          relationshipKey: selectedRelationshipKey,
                          priorityOrder:
                              int.tryParse(_priorityOrder.text.trim()) ?? 1,
                        ),
                onDeleteRelationship: controller.deleteRelationship,
                onLeaveFamily: controller.leaveFamily,
                onDissolveFamily: controller.dissolveFamily,
                onSelectRelationship: (value) {
                  setState(() {
                    _selectedRelationshipKey = value;
                  });
                },
                onSelectRelativeUser: (value) {
                  setState(() {
                    _selectedRelativeUserId = value;
                  });
                },
              ),
            if (_section == HomeMenuSection.emotion)
              _EmotionView(
                family: family,
                dashboard: controller.emotionDashboard,
              ),
            if (_section == HomeMenuSection.chat)
              _ChatView(
                currentUserId: profile?.id,
                threads: controller.chatThreads,
                activeThread: controller.activeChatThread,
                messages: controller.activeChatMessages,
                composer: _chatComposer,
                busy: controller.busy,
                onSelectThread: controller.openChatThread,
                onSend: () async {
                  final value = _chatComposer.text.trim();
                  if (value.isNotEmpty) {
                    await controller.sendChatMessage(value);
                    _chatComposer.clear();
                  }
                },
              ),
            if (_section == HomeMenuSection.calls)
              _CallsView(
                activeCall: controller.activeCall,
                callHistory: controller.callHistory,
                currentUserId: profile?.id,
                busy: controller.busy,
                hasRealtimeCallConfig: controller.hasRealtimeCallConfig,
                onAccept: controller.acceptActiveCall,
                onDecline: controller.declineActiveCall,
                onEnd: controller.endActiveCall,
                onRedial: controller.redialActiveCall,
              ),
            if (_section == HomeMenuSection.settings)
              _SettingsView(
                profile: profile,
                busy: controller.busy,
                pushStatusMessage: controller.pushStatusMessage,
                hasPushMessagingConfig: controller.hasPushMessagingConfig,
                hasRealtimeCallConfig: controller.hasRealtimeCallConfig,
                onLogout: controller.logout,
              ),
          ],
        ),
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 14),
            child,
          ],
        ),
      ),
    );
  }
}

String _formatTimestamp(String? value) {
  if (value == null || value.isEmpty) {
    return 'đang cập nhật';
  }
  return value.replaceFirst('T', ' ').split('.').first;
}

class _VoiceView extends StatelessWidget {
  const _VoiceView({
    required this.profile,
    required this.transcriptController,
    required this.assistantResult,
    required this.activeCall,
    required this.currentUserId,
    required this.busy,
    required this.hasRealtimeCallConfig,
    required this.isListening,
    required this.onListen,
    required this.onStop,
    required this.onSubmit,
    required this.onAcceptCall,
    required this.onDeclineCall,
    required this.onEndCall,
    required this.onRedialCall,
  });

  final UserProfile? profile;
  final TextEditingController transcriptController;
  final VoiceAssistantResult? assistantResult;
  final CallSession? activeCall;
  final int? currentUserId;
  final bool busy;
  final bool hasRealtimeCallConfig;
  final bool isListening;
  final Future<void> Function() onListen;
  final Future<void> Function() onStop;
  final Future<void> Function() onSubmit;
  final Future<void> Function() onAcceptCall;
  final Future<void> Function() onDeclineCall;
  final Future<void> Function() onEndCall;
  final Future<void> Function() onRedialCall;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF0F4C81), Color(0xFF1F7A8C)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(28),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Xin chào ${profile?.fullName ?? ''}',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Đây là màn hình chính. Bạn có thể nói hoặc nhập câu lệnh như "Gọi con trai".',
                style: TextStyle(color: Colors.white, height: 1.5),
              ),
              const SizedBox(height: 18),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: const Color(0xFF0F4C81),
                    ),
                    onPressed: busy
                        ? null
                        : () async {
                            if (isListening) {
                              await onStop();
                            } else {
                              await onListen();
                            }
                          },
                    icon: Icon(
                        isListening ? Icons.stop_rounded : Icons.mic_rounded),
                    label: Text(isListening ? 'Dừng nghe' : 'Bắt đầu nói'),
                  ),
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: const BorderSide(color: Colors.white70),
                    ),
                    onPressed: busy ? null : () async => onSubmit(),
                    child: const Text('Gửi lệnh'),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        _Panel(
          title: 'Lệnh thoại',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                  'Ví dụ: "Gọi con trai", "Gọi con gái", "Nhắn cho con trai là tối nay mẹ nấu cơm rồi nhé".'),
              const SizedBox(height: 12),
              TextField(
                controller: transcriptController,
                minLines: 3,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: 'Nội dung nhận diện hoặc nhập tay',
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        _Panel(
          title: 'Phản hồi từ Icare',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (assistantResult != null) ...[
                if (assistantResult!.isConfirmationRequired)
                  Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF7ED),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: const Text(
                      'Đang chờ xác nhận cuộc gọi',
                      style: TextStyle(
                        color: Color(0xFF9A3412),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                Text(
                  assistantResult!.message,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                if (assistantResult!.emotionSignal != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: _emotionSignalColor(
                        assistantResult!.emotionSignal!.riskLevel,
                      ).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(
                        color: _emotionSignalColor(
                          assistantResult!.emotionSignal!.riskLevel,
                        ).withValues(alpha: 0.28),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Phân tích cảm xúc: ${_emotionSignalLabel(assistantResult!.emotionSignal!)}',
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: _emotionSignalColor(
                              assistantResult!.emotionSignal!.riskLevel,
                            ),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Điểm hiện tại ${assistantResult!.emotionSignal!.emotionScore}/100.',
                        ),
                        if (assistantResult!.emotionSignal!.detectedKeywords.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text(
                            'Tín hiệu nhận ra: ${assistantResult!.emotionSignal!.detectedKeywords.join(', ')}.',
                          ),
                        ],
                        const SizedBox(height: 6),
                        Text(
                          assistantResult!.emotionSignal!.alertSent
                              ? 'Hệ thống đã gửi cảnh báo cho quản trị viên gia đình.'
                              : 'Hệ thống đã ghi nhận trạng thái cảm xúc này để theo dõi tiếp.',
                        ),
                      ],
                    ),
                  ),
                ],
              ] else
                const Text(
                  'Bác có thể trò chuyện bình thường với Icare. Nếu muốn gọi người thân, hãy nói như "Gọi con trai", sau đó nói "xác nhận". Nếu muốn nhắn hộ, hãy nói như "Nhắn cho con trai là tối nay mẹ nấu cơm rồi nhé".',
                ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        _ActiveCallPanel(
          activeCall: activeCall,
          currentUserId: currentUserId,
          busy: busy,
          hasRealtimeCallConfig: hasRealtimeCallConfig,
          onAccept: onAcceptCall,
          onDecline: onDeclineCall,
          onEnd: onEndCall,
          onRedial: onRedialCall,
        ),
      ],
    );
  }

  String _emotionSignalLabel(EmotionSignal signal) {
    switch (signal.riskLevel) {
      case 'critical':
        return 'Rất buồn, cần quan tâm sớm';
      case 'warning':
        return 'Buồn chán, cần chú ý';
      case 'watch':
        return 'Tâm trạng giảm nhẹ';
      default:
        return 'Ổn định';
    }
  }

  Color _emotionSignalColor(String riskLevel) {
    switch (riskLevel) {
      case 'critical':
        return const Color(0xFFB91C1C);
      case 'warning':
        return const Color(0xFFD97706);
      case 'watch':
        return const Color(0xFFCA8A04);
      default:
        return const Color(0xFF15803D);
    }
  }
}

class _FamilyView extends StatelessWidget {
  const _FamilyView({
    required this.currentUserId,
    required this.family,
    required this.invitations,
    required this.relationships,
    required this.options,
    required this.familyMembers,
    required this.busy,
    required this.familyNameController,
    required this.inviteIdentifierController,
    required this.priorityController,
    required this.selectedRelationshipKey,
    required this.selectedRelativeUserId,
    required this.onCreateFamily,
    required this.onInviteMember,
    required this.onRespondInvitation,
    required this.onSaveRelationship,
    required this.onDeleteRelationship,
    required this.onLeaveFamily,
    required this.onDissolveFamily,
    required this.onSelectRelationship,
    required this.onSelectRelativeUser,
  });

  final int? currentUserId;
  final FamilyGroup? family;
  final List<FamilyInvitation> invitations;
  final List<FamilyRelationship> relationships;
  final List<RelationshipOption> options;
  final List<FamilyMember> familyMembers;
  final bool busy;
  final TextEditingController familyNameController;
  final TextEditingController inviteIdentifierController;
  final TextEditingController priorityController;
  final String? selectedRelationshipKey;
  final int? selectedRelativeUserId;
  final Future<void> Function() onCreateFamily;
  final Future<void> Function() onInviteMember;
  final Future<void> Function({
    required int invitationId,
    required String action,
  }) onRespondInvitation;
  final VoidCallback? onSaveRelationship;
  final Future<void> Function(int relationshipId) onDeleteRelationship;
  final Future<void> Function() onLeaveFamily;
  final Future<void> Function() onDissolveFamily;
  final ValueChanged<String?> onSelectRelationship;
  final ValueChanged<int?> onSelectRelativeUser;

  Future<bool> _confirmAction(
    BuildContext context, {
    required String title,
    required String message,
    required String confirmLabel,
  }) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(confirmLabel),
          ),
        ],
      ),
    );
    return result == true;
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = family?.role == 'admin';
    final adminCount =
        family?.members.where((member) => member.role == 'admin').length ?? 0;
    final memberCount = family?.members.length ?? 0;
    final isLastAdminWithMembers =
        isAdmin && adminCount <= 1 && memberCount > 1;

    return Column(
      children: [
        _Panel(
          title: 'Gia đình hiện tại',
          child: family == null
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Bạn chưa có nhóm gia đình. Hãy tạo nhóm để quản lý người thân và gọi khẩn cấp.',
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: familyNameController,
                      decoration:
                          const InputDecoration(labelText: 'Tên gia đình'),
                    ),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: busy ? null : () async => onCreateFamily(),
                      child: const Text('Tạo gia đình'),
                    ),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      family!.familyName,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 8),
                    Text('Vai trò: ${family!.role}'),
                    const SizedBox(height: 12),
                    ...family!.members.map(
                      (member) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: CircleAvatar(
                          child: Text(member.fullName.isEmpty
                              ? '?'
                              : member.fullName[0].toUpperCase()),
                        ),
                        title: Text(member.fullName),
                        subtitle:
                            Text('${member.role} • ${member.phoneNumber}'),
                      ),
                    ),
                  ],
                ),
        ),
        const SizedBox(height: 20),
        if (family != null)
          _Panel(
            title: 'Hành động nhóm',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (currentUserId != null && isLastAdminWithMembers)
                  const Padding(
                    padding: EdgeInsets.only(bottom: 12),
                    child: Text(
                      'Bạn đang là admin cuối cùng. Hãy bổ nhiệm admin khác trước khi rời nhóm, hoặc dùng giải tán nhóm nếu muốn xóa cả nhóm.',
                    ),
                  ),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    OutlinedButton.icon(
                      onPressed: busy
                          ? null
                          : () async {
                              final confirmed = await _confirmAction(
                                context,
                                title: 'Rời nhóm gia đình?',
                                message:
                                    'Bạn sẽ không còn thấy chat và thông tin của nhóm này nữa.',
                                confirmLabel: 'Rời nhóm',
                              );
                              if (confirmed) {
                                await onLeaveFamily();
                              }
                            },
                      icon: const Icon(Icons.logout_rounded),
                      label: const Text('Rời nhóm'),
                    ),
                    if (isAdmin)
                      FilledButton.icon(
                        onPressed: busy
                            ? null
                            : () async {
                                final firstConfirm = await _confirmAction(
                                  context,
                                  title: 'Giải tán nhóm?',
                                  message:
                                      'Thao tác này sẽ xóa nhóm, lời mời và chat gia đình liên quan.',
                                  confirmLabel: 'Tiếp tục',
                                );
                                if (!firstConfirm) {
                                  return;
                                }
                                if (!context.mounted) {
                                  return;
                                }
                                final secondConfirm = await _confirmAction(
                                  context,
                                  title: 'Xác nhận lần cuối',
                                  message:
                                      'Bạn chắc chắn muốn giải tán nhóm "${family!.familyName}"?',
                                  confirmLabel: 'Giải tán',
                                );
                                if (secondConfirm) {
                                  await onDissolveFamily();
                                }
                              },
                        icon: const Icon(Icons.delete_forever_rounded),
                        label: const Text('Giải tán nhóm'),
                      ),
                  ],
                ),
              ],
            ),
          ),
        if (family != null) const SizedBox(height: 20),
        if (family?.role == 'admin')
          _Panel(
            title: 'Mời thành viên',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Nhập email hoặc số điện thoại để gửi lời mời.'),
                const SizedBox(height: 12),
                TextField(
                  controller: inviteIdentifierController,
                  decoration: const InputDecoration(
                    labelText: 'Email hoặc số điện thoại',
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: busy || family == null
                      ? null
                      : () async => onInviteMember(),
                  child: const Text('Gửi lời mời'),
                ),
              ],
            ),
          ),
        if (family?.role == 'admin') const SizedBox(height: 20),
        _Panel(
          title: 'Lời mời',
          child: invitations.isEmpty
              ? const Text('Hiện chưa có lời mời nào cần xử lý.')
              : Column(
                  children: invitations.map((invitation) {
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(invitation.familyName),
                      subtitle: Text(
                        'Mời bởi ${invitation.invitedByName} • ${_formatTimestamp(invitation.createdAt)}',
                      ),
                      trailing: Wrap(
                        spacing: 8,
                        children: [
                          IconButton(
                            onPressed: busy
                                ? null
                                : () => onRespondInvitation(
                                      invitationId: invitation.id,
                                      action: 'accept',
                                    ),
                            icon:
                                const Icon(Icons.check_circle_outline_rounded),
                          ),
                          IconButton(
                            onPressed: busy
                                ? null
                                : () => onRespondInvitation(
                                      invitationId: invitation.id,
                                      action: 'decline',
                                    ),
                            icon: const Icon(Icons.cancel_outlined),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
        ),
        const SizedBox(height: 20),
        _Panel(
          title: 'Thiết lập gọi khẩn cấp',
          child: family == null
              ? const Text(
                  'Hãy tạo hoặc tham gia gia đình trước khi thiết lập gọi khẩn cấp.')
              : familyMembers.isEmpty
                  ? const Text(
                      'Gia đình cần thêm ít nhất một người thân để tạo mapping gọi khẩn cấp.')
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        DropdownButtonFormField<int>(
                          initialValue: selectedRelativeUserId,
                          decoration:
                              const InputDecoration(labelText: 'Người thân'),
                          items: familyMembers
                              .map(
                                (member) => DropdownMenuItem<int>(
                                  value: member.userId,
                                  child: Text(member.fullName),
                                ),
                              )
                              .toList(),
                          onChanged: busy ? null : onSelectRelativeUser,
                        ),
                        const SizedBox(height: 12),
                        DropdownButtonFormField<String>(
                          initialValue: selectedRelationshipKey,
                          decoration:
                              const InputDecoration(labelText: 'Quan hệ'),
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
                          decoration: const InputDecoration(
                              labelText: 'Thứ tự ưu tiên'),
                        ),
                        const SizedBox(height: 12),
                        FilledButton(
                          onPressed: busy ? null : onSaveRelationship,
                          child: const Text('Lưu cấu hình'),
                        ),
                        const SizedBox(height: 16),
                        if (relationships.isEmpty)
                          const Text('Chưa có cấu hình nào được lưu.')
                        else
                          ...relationships.map(
                            (relationship) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(
                                '${relationship.relationshipLabel}: ${relationship.relativeFullName}',
                              ),
                              subtitle:
                                  Text('Ưu tiên ${relationship.priorityOrder}'),
                              trailing: IconButton(
                                onPressed: busy
                                    ? null
                                    : () =>
                                        onDeleteRelationship(relationship.id),
                                icon: const Icon(Icons.delete_outline_rounded),
                              ),
                            ),
                          ),
                      ],
                    ),
        ),
      ],
    );
  }
}

class _EmotionView extends StatelessWidget {
  const _EmotionView({
    required this.family,
    required this.dashboard,
  });

  final FamilyGroup? family;
  final EmotionDashboard? dashboard;

  @override
  Widget build(BuildContext context) {
    if (family == null) {
      return const _Panel(
        title: 'Giám sát cảm xúc',
        child: Text('Cần có gia đình trước để theo dõi cảm xúc của ông, bà.'),
      );
    }
    if (family!.role != 'admin') {
      return const _Panel(
        title: 'Giám sát cảm xúc',
        child: Text('Mục này chỉ dành cho quản trị viên gia đình.'),
      );
    }
    if (dashboard == null) {
      return const _Panel(
        title: 'Giám sát cảm xúc',
        child: Text('Chưa có dữ liệu cảm xúc để hiển thị.'),
      );
    }

    return Column(
      children: [
        _Panel(
          title: 'Tổng quan cảm xúc',
          child: Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _SummaryChip(
                label: 'Người theo dõi',
                value: '${dashboard!.summary.elderCount}',
                color: const Color(0xFF1D4ED8),
              ),
              _SummaryChip(
                label: 'Điểm trung bình',
                value: '${dashboard!.summary.averageScore}/100',
                color: const Color(0xFF0F766E),
              ),
              _SummaryChip(
                label: 'Cảnh báo cao',
                value: '${dashboard!.summary.criticalCount}',
                color: const Color(0xFFB91C1C),
              ),
              _SummaryChip(
                label: 'Cần chú ý',
                value: '${dashboard!.summary.warningCount}',
                color: const Color(0xFFD97706),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        ...dashboard!.elders.map((elder) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 20),
            child: _Panel(
              title: '${elder.careRoleLabel} • ${elder.fullName}',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Tuổi ${elder.age} • Trung bình 7 ngày ${elder.averageScore7d}/100',
                        ),
                      ),
                      Text(
                        '${elder.latestScore}/100',
                        style: TextStyle(
                          color: _emotionColor(elder.latestScore),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: LinearProgressIndicator(
                      minHeight: 12,
                      value: elder.latestScore / 100,
                      backgroundColor: Colors.grey.shade200,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        _emotionColor(elder.latestScore),
                      ),
                    ),
                  ),
                  if (elder.latestMessage.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Text('Nội dung gần nhất: "${elder.latestMessage}"'),
                  ],
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Color _emotionColor(int score) {
    if (score <= 25) {
      return const Color(0xFFB91C1C);
    }
    if (score <= 45) {
      return const Color(0xFFD97706);
    }
    if (score <= 70) {
      return const Color(0xFFCA8A04);
    }
    return const Color(0xFF15803D);
  }
}

class _ChatView extends StatelessWidget {
  const _ChatView({
    required this.currentUserId,
    required this.threads,
    required this.activeThread,
    required this.messages,
    required this.composer,
    required this.busy,
    required this.onSelectThread,
    required this.onSend,
  });

  final int? currentUserId;
  final List<FamilyChatThread> threads;
  final FamilyChatThread? activeThread;
  final List<FamilyChatMessage> messages;
  final TextEditingController composer;
  final bool busy;
  final ValueChanged<int> onSelectThread;
  final Future<void> Function() onSend;

  @override
  Widget build(BuildContext context) {
    final resolvedThread =
        activeThread ?? (threads.isNotEmpty ? threads.first : null);

    return _Panel(
      title: 'Tin nhắn gia đình',
      child: threads.isEmpty
          ? const Text('Chưa có cuộc trò chuyện nào trong gia đình.')
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: threads.map((thread) {
                    return ChoiceChip(
                      label: Text(
                        thread.unreadCount > 0
                            ? '${thread.partnerFullName} (${thread.unreadCount})'
                            : thread.partnerFullName,
                      ),
                      selected:
                          activeThread?.partnerUserId == thread.partnerUserId,
                      onSelected: busy
                          ? null
                          : (_) => onSelectThread(thread.partnerUserId),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 16),
                Container(
                  constraints:
                      const BoxConstraints(minHeight: 220, maxHeight: 420),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade50,
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: Colors.grey.shade300),
                  ),
                  child: messages.isEmpty
                      ? const Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                              'Hãy gửi lời hỏi thăm đầu tiên cho người thân.'),
                        )
                      : ListView.builder(
                          itemCount: messages.length,
                          itemBuilder: (context, index) {
                            final message = messages[index];
                            final isMine = currentUserId != null &&
                                message.isFromUser(currentUserId!);
                            return Align(
                              alignment: isMine
                                  ? Alignment.centerRight
                                  : Alignment.centerLeft,
                              child: Container(
                                margin: const EdgeInsets.only(bottom: 12),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 14,
                                  vertical: 12,
                                ),
                                constraints:
                                    const BoxConstraints(maxWidth: 290),
                                decoration: BoxDecoration(
                                  color: isMine
                                      ? const Color(0xFFDCEBFF)
                                      : Colors.white,
                                  borderRadius: BorderRadius.circular(16),
                                  border:
                                      Border.all(color: Colors.grey.shade300),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      message.senderFullName,
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                              fontWeight: FontWeight.w700),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(message.messageText),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: composer,
                        minLines: 1,
                        maxLines: 3,
                        decoration: InputDecoration(
                          labelText: resolvedThread == null
                              ? 'Chọn người thân để nhắn tin'
                              : 'Nhắn cho ${resolvedThread.partnerFullName}',
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    FilledButton(
                      onPressed: busy || resolvedThread == null
                          ? null
                          : () async => onSend(),
                      child: const Text('Gửi'),
                    ),
                  ],
                ),
              ],
            ),
    );
  }
}

class _CallsView extends StatelessWidget {
  const _CallsView({
    required this.activeCall,
    required this.callHistory,
    required this.currentUserId,
    required this.busy,
    required this.hasRealtimeCallConfig,
    required this.onAccept,
    required this.onDecline,
    required this.onEnd,
    required this.onRedial,
  });

  final CallSession? activeCall;
  final List<CallSession> callHistory;
  final int? currentUserId;
  final bool busy;
  final bool hasRealtimeCallConfig;
  final Future<void> Function() onAccept;
  final Future<void> Function() onDecline;
  final Future<void> Function() onEnd;
  final Future<void> Function() onRedial;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _ActiveCallPanel(
          activeCall: activeCall,
          currentUserId: currentUserId,
          busy: busy,
          hasRealtimeCallConfig: hasRealtimeCallConfig,
          onAccept: onAccept,
          onDecline: onDecline,
          onEnd: onEnd,
          onRedial: onRedial,
        ),
        const SizedBox(height: 20),
        _CallHistoryPanel(
          callHistory: callHistory,
          currentUserId: currentUserId,
        ),
      ],
    );
  }
}

class _SettingsView extends StatelessWidget {
  const _SettingsView({
    required this.profile,
    required this.busy,
    required this.pushStatusMessage,
    required this.hasPushMessagingConfig,
    required this.hasRealtimeCallConfig,
    required this.onLogout,
  });

  final UserProfile? profile;
  final bool busy;
  final String? pushStatusMessage;
  final bool hasPushMessagingConfig;
  final bool hasRealtimeCallConfig;
  final Future<void> Function() onLogout;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _Panel(
          title: 'Thông báo',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                hasPushMessagingConfig
                    ? 'Thông báo đẩy đang sẵn sàng trên thiết bị này.'
                    : 'Thông báo đẩy chưa sẵn sàng.',
              ),
              if (pushStatusMessage?.isNotEmpty == true) ...[
                const SizedBox(height: 8),
                Text(pushStatusMessage!),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        _Panel(
          title: 'Gọi thoại realtime',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                hasRealtimeCallConfig
                    ? 'Thiết bị này đã có cấu hình thoại realtime.'
                    : 'Thiết bị này chưa có cấu hình thoại realtime.',
              ),
              if (!hasRealtimeCallConfig) ...[
                const SizedBox(height: 8),
                const Text(
                  'Muốn gọi hoặc nghe máy ổn định, bạn cần build lại APK với ZEGO_APP_ID và ZEGO_APP_SIGN rồi cài lại app.',
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        _Panel(
          title: 'Tài khoản',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(profile?.fullName ?? ''),
              const SizedBox(height: 4),
              Text(profile?.email ?? ''),
              const SizedBox(height: 4),
              Text(profile?.phoneNumber ?? ''),
              const SizedBox(height: 16),
              FilledButton.tonalIcon(
                onPressed: busy ? null : () async => onLogout(),
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Đăng xuất'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _SummaryChip extends StatelessWidget {
  const _SummaryChip({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 4),
          Text(
            value,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w700,
                ),
          ),
        ],
      ),
    );
  }
}

class _ActiveCallPanel extends StatelessWidget {
  const _ActiveCallPanel({
    required this.activeCall,
    required this.currentUserId,
    required this.busy,
    required this.hasRealtimeCallConfig,
    required this.onAccept,
    required this.onDecline,
    required this.onEnd,
    required this.onRedial,
  });

  final CallSession? activeCall;
  final int? currentUserId;
  final bool busy;
  final bool hasRealtimeCallConfig;
  final Future<void> Function() onAccept;
  final Future<void> Function() onDecline;
  final Future<void> Function() onEnd;
  final Future<void> Function() onRedial;

  @override
  Widget build(BuildContext context) {
    final userId = currentUserId;
    final session = activeCall;
    final canAccept = hasRealtimeCallConfig &&
        userId != null &&
        session?.canAccept(userId) == true;
    final canDecline = userId != null && session?.canDecline(userId) == true;
    final canEnd = userId != null && session?.canEnd(userId) == true;
    final canRedial = hasRealtimeCallConfig &&
        userId != null &&
        session?.canRedial(userId) == true;

    return _Panel(
      title: 'Cuộc gọi hiện tại',
      child: session == null
          ? const Text('Hiện chưa có cuộc gọi nào đang diễn ra.')
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Trạng thái: ${session.status}'),
                if (session.caller != null)
                  Text('Người gọi: ${session.caller!.fullName}'),
                if (session.relationshipLabel?.isNotEmpty == true)
                  Text('Quan hệ: ${session.relationshipLabel}'),
                if (session.currentTargetName?.isNotEmpty == true)
                  Text('Đang đổ chuông: ${session.currentTargetName}'),
                if (session.transcriptText?.isNotEmpty == true)
                  Text('Nội dung: ${session.transcriptText}'),
                if (!hasRealtimeCallConfig) ...[
                  const SizedBox(height: 12),
                  const Text(
                    'Thiết bị này chưa có cấu hình thoại realtime, nên chưa thể vào phòng nói chuyện sau khi nghe máy.',
                    style: TextStyle(color: Color(0xFFB91C1C)),
                  ),
                ],
                const SizedBox(height: 12),
                if (canAccept || canDecline || canEnd || canRedial)
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      if (canAccept)
                        FilledButton(
                          onPressed: busy ? null : () async => onAccept(),
                          child: const Text('Nhận cuộc gọi'),
                        ),
                      if (canDecline)
                        OutlinedButton(
                          onPressed: busy ? null : () async => onDecline(),
                          child: const Text('Không nhận'),
                        ),
                      if (canEnd)
                        FilledButton.tonal(
                          onPressed: busy ? null : () async => onEnd(),
                          child: const Text('Kết thúc'),
                        ),
                      if (canRedial)
                        FilledButton(
                          onPressed: busy ? null : () async => onRedial(),
                          child: const Text('Gọi lại'),
                        ),
                    ],
                  )
                else
                  const Text(
                    'Cuộc gọi đang được xử lý. Nếu đã nhận máy, màn hình phòng gọi sẽ điều khiển phần kết thúc cuộc gọi.',
                  ),
              ],
            ),
    );
  }
}

class _CallHistoryPanel extends StatelessWidget {
  const _CallHistoryPanel({
    required this.callHistory,
    required this.currentUserId,
  });

  final List<CallSession> callHistory;
  final int? currentUserId;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      title: 'Lịch sử cuộc gọi',
      child: callHistory.isEmpty
          ? const Text('Chưa có lịch sử cuộc gọi nào.')
          : Column(
              children: callHistory.take(20).map((session) {
                final isCaller = currentUserId != null &&
                    session.caller?.id == currentUserId;
                final direction = isCaller ? 'Bạn gọi' : 'Bạn nhận';
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    '$direction • ${session.relationshipLabel ?? session.relationshipKey}',
                  ),
                  subtitle: Text(
                    '${session.caller?.fullName ?? 'Không rõ'} • ${_formatTimestamp(session.endedAt ?? session.createdAt)}',
                  ),
                  trailing: Text(session.status),
                );
              }).toList(),
            ),
    );
  }
}
