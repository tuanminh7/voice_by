import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_controller.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool isRegister = false;
  String _selectedCareRoleKey = '';

  static const List<({String key, String label})> _careRoleOptions = [
    (key: '', label: 'Chưa chọn'),
    (key: 'father', label: 'Ba'),
    (key: 'mother', label: 'Mẹ'),
    (key: 'grandfather', label: 'Ông'),
    (key: 'grandmother', label: 'Bà'),
    (key: 'son', label: 'Con trai'),
    (key: 'daughter', label: 'Con gái'),
    (key: 'grandchild', label: 'Cháu'),
    (key: 'wife', label: 'Vợ'),
    (key: 'husband', label: 'Chồng'),
    (key: 'brother', label: 'Anh/em trai'),
    (key: 'sister', label: 'Chị/em gái'),
    (key: 'caregiver', label: 'Người chăm sóc'),
    (key: 'family_member', label: 'Người nhà'),
  ];

  final _loginIdentifier = TextEditingController();
  final _loginPassword = TextEditingController();

  final _fullName = TextEditingController();
  final _age = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _registerPassword = TextEditingController();

  @override
  void dispose() {
    _loginIdentifier.dispose();
    _loginPassword.dispose();
    _fullName.dispose();
    _age.dispose();
    _email.dispose();
    _phone.dispose();
    _registerPassword.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AppController>();
    final screenSize = MediaQuery.of(context).size;
    final formWidth = screenSize.width > 720 ? 520.0 : double.infinity;

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [
              Color(0xFFF3F6FB),
              Color(0xFFE7EEF8),
              Color(0xFFF8FBFF),
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: formWidth),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 72,
                      height: 72,
                      decoration: BoxDecoration(
                        color: const Color(0xFF0F4C81),
                        borderRadius: BorderRadius.circular(24),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x220F4C81),
                            blurRadius: 24,
                            offset: Offset(0, 14),
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.favorite_rounded,
                        color: Colors.white,
                        size: 34,
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'Icare',
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: const Color(0xFF133B63),
                          ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      isRegister
                          ? 'Tạo tài khoản mới'
                          : 'Đăng nhập nhẹ nhàng, an tâm',
                      style:
                          Theme.of(context).textTheme.headlineMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: const Color(0xFF102A43),
                              ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Icare hỗ trợ trò chuyện bằng giọng nói, kết nối gia đình và gọi khẩn cấp cho người thân.',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: const Color(0xFF486581),
                            height: 1.5,
                          ),
                    ),
                    const SizedBox(height: 24),
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(28),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x140F172A),
                            blurRadius: 30,
                            offset: Offset(0, 18),
                          ),
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SegmentedButton<bool>(
                            showSelectedIcon: false,
                            style: ButtonStyle(
                              padding: WidgetStateProperty.all(
                                const EdgeInsets.symmetric(vertical: 16),
                              ),
                            ),
                            segments: const [
                              ButtonSegment<bool>(
                                value: false,
                                label: Text('Đăng nhập'),
                                icon: Icon(Icons.login_rounded),
                              ),
                              ButtonSegment<bool>(
                                value: true,
                                label: Text('Đăng ký'),
                                icon: Icon(Icons.person_add_alt_1_rounded),
                              ),
                            ],
                            selected: {isRegister},
                            onSelectionChanged: (selection) {
                              setState(() {
                                isRegister = selection.first;
                              });
                            },
                          ),
                          const SizedBox(height: 24),
                          if (!isRegister) ...[
                            _AuthField(
                              controller: _loginIdentifier,
                              label: 'Email hoặc số điện thoại',
                              keyboardType: TextInputType.emailAddress,
                              prefixIcon: Icons.alternate_email_rounded,
                            ),
                            const SizedBox(height: 14),
                            _AuthField(
                              controller: _loginPassword,
                              label: 'Mật khẩu',
                              obscureText: true,
                              prefixIcon: Icons.lock_outline_rounded,
                            ),
                            const SizedBox(height: 18),
                            SizedBox(
                              width: double.infinity,
                              child: FilledButton.icon(
                                onPressed: controller.busy
                                    ? null
                                    : () => controller.login(
                                          identifier:
                                              _loginIdentifier.text.trim(),
                                          password: _loginPassword.text,
                                        ),
                                icon: const Icon(Icons.arrow_forward_rounded),
                                label: const Text('Đăng nhập'),
                              ),
                            ),
                          ] else ...[
                            _AuthField(
                              controller: _fullName,
                              label: 'Họ và tên',
                              prefixIcon: Icons.badge_rounded,
                            ),
                            const SizedBox(height: 14),
                            _AuthField(
                              controller: _age,
                              label: 'Tuổi',
                              keyboardType: TextInputType.number,
                              prefixIcon: Icons.cake_outlined,
                            ),
                            const SizedBox(height: 14),
                            _AuthField(
                              controller: _email,
                              label: 'Email',
                              keyboardType: TextInputType.emailAddress,
                              prefixIcon: Icons.email_outlined,
                            ),
                            const SizedBox(height: 14),
                            _AuthField(
                              controller: _phone,
                              label: 'Số điện thoại',
                              keyboardType: TextInputType.phone,
                              prefixIcon: Icons.phone_outlined,
                            ),
                            const SizedBox(height: 14),
                            _AuthField(
                              controller: _registerPassword,
                              label: 'Mật khẩu',
                              obscureText: true,
                              prefixIcon: Icons.lock_outline_rounded,
                            ),
                            const SizedBox(height: 14),
                            DropdownButtonFormField<String>(
                              initialValue: _selectedCareRoleKey,
                              decoration: const InputDecoration(
                                labelText: 'Vai vế trong gia đình',
                                prefixIcon: Icon(Icons.family_restroom_rounded),
                              ),
                              items: _careRoleOptions
                                  .map(
                                    (option) => DropdownMenuItem<String>(
                                      value: option.key,
                                      child: Text(option.label),
                                    ),
                                  )
                                  .toList(),
                              onChanged: controller.busy
                                  ? null
                                  : (value) {
                                      setState(() {
                                        _selectedCareRoleKey = value ?? '';
                                      });
                                    },
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'Bạn có thể chọn trước vai vế của mình để app xưng hô và xử lý gia đình phù hợp hơn.',
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(
                                    color: const Color(0xFF486581),
                                    height: 1.4,
                                  ),
                            ),
                            const SizedBox(height: 18),
                            SizedBox(
                              width: double.infinity,
                              child: FilledButton.icon(
                                onPressed: controller.busy
                                    ? null
                                    : () => controller.register(
                                          fullName: _fullName.text.trim(),
                                          age: int.tryParse(_age.text.trim()) ??
                                              0,
                                          email: _email.text.trim(),
                                          phoneNumber: _phone.text.trim(),
                                          password: _registerPassword.text,
                                          careRoleKey: _selectedCareRoleKey,
                                        ),
                                icon: const Icon(
                                    Icons.check_circle_outline_rounded),
                                label: const Text('Tạo tài khoản'),
                              ),
                            ),
                          ],
                          if (controller.busy) ...[
                            const SizedBox(height: 18),
                            const LinearProgressIndicator(),
                            const SizedBox(height: 10),
                            Text(
                              'Icare đang kết nối tới máy chủ, bác chờ một chút nhé.',
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium
                                  ?.copyWith(
                                    color: const Color(0xFF486581),
                                  ),
                            ),
                          ],
                          const SizedBox(height: 18),
                          _InfoNote(
                            icon: Icons.cloud_sync_rounded,
                            title: 'Lưu ý khi mở app lần đầu',
                            message:
                                'Nếu server Render đang ngủ, lần đăng nhập đầu tiên có thể mất khoảng 20-60 giây để khởi động lại.',
                          ),
                          if (controller.errorMessage?.trim().isNotEmpty ==
                              true) ...[
                            const SizedBox(height: 16),
                            _ErrorNote(
                                message: controller.errorMessage!.trim()),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AuthField extends StatelessWidget {
  const _AuthField({
    required this.controller,
    required this.label,
    required this.prefixIcon,
    this.keyboardType,
    this.obscureText = false,
  });

  final TextEditingController controller;
  final String label;
  final IconData prefixIcon;
  final TextInputType? keyboardType;
  final bool obscureText;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      obscureText: obscureText,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(prefixIcon),
      ),
    );
  }
}

class _InfoNote extends StatelessWidget {
  const _InfoNote({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F8FF),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFD6E6FB)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: const Color(0xFF0F4C81)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: const Color(0xFF133B63),
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  message,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: const Color(0xFF486581),
                        height: 1.45,
                      ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ErrorNote extends StatelessWidget {
  const _ErrorNote({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF1F2),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFF8B4BC)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline_rounded, color: Color(0xFFBE123C)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: const Color(0xFF9F1239),
                    height: 1.45,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
