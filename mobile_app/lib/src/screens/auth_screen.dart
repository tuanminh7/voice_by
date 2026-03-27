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

    return Scaffold(
      appBar: AppBar(title: const Text('Icare')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isRegister
                    ? 'Tạo tài khoản'
                    : 'Đăng nhập',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              const Text(
                'Icare hỗ trợ trò chuyện, nhắn tin gia đình và gọi khẩn cấp cho người thân.',
              ),
              const SizedBox(height: 20),
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment<bool>(value: false, label: Text('Đăng nhập')),
                  ButtonSegment<bool>(value: true, label: Text('Đăng ký')),
                ],
                selected: {isRegister},
                onSelectionChanged: (selection) {
                  setState(() {
                    isRegister = selection.first;
                  });
                },
              ),
              const SizedBox(height: 20),
              if (!isRegister) ...[
                TextField(
                  controller: _loginIdentifier,
                  decoration: const InputDecoration(
                    labelText: 'Email hoặc số điện thoại',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _loginPassword,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Mật khẩu'),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: controller.busy
                      ? null
                      : () => controller.login(
                            identifier: _loginIdentifier.text.trim(),
                            password: _loginPassword.text,
                          ),
                  child: const Text('Đăng nhập'),
                ),
              ] else ...[
                TextField(
                  controller: _fullName,
                  decoration: const InputDecoration(labelText: 'Họ tên'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _age,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Tuổi'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _email,
                  decoration: const InputDecoration(labelText: 'Email'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _phone,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(labelText: 'Số điện thoại'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _registerPassword,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Mật khẩu'),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: controller.busy
                      ? null
                      : () => controller.register(
                            fullName: _fullName.text.trim(),
                            age: int.tryParse(_age.text.trim()) ?? 0,
                            email: _email.text.trim(),
                            phoneNumber: _phone.text.trim(),
                            password: _registerPassword.text,
                          ),
                  child: const Text('Tạo tài khoản'),
                ),
              ],
              if (controller.busy) ...[
                const SizedBox(height: 16),
                const LinearProgressIndicator(),
              ],
              if (controller.errorMessage != null) ...[
                const SizedBox(height: 16),
                Text(
                  controller.errorMessage!,
                  style: const TextStyle(color: Colors.red),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
