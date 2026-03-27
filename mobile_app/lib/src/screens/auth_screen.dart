import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config/app_config.dart';
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
      appBar: AppBar(title: const Text('Dang nhap v2')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isRegister
                    ? 'Tao tai khoan cho app mobile'
                    : 'Dang nhap lai bang tai khoan da co',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              const Text(
                'Flow nay se dung lai backend v1 hien tai, sau do vao PIN va chuc nang goi khan cap.',
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Backend URL',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      SelectableText(AppConfig.baseUrl),
                      const SizedBox(height: 8),
                      Text(
                        AppConfig.backendConnectionHint,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 20),
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment<bool>(value: false, label: Text('Dang nhap')),
                  ButtonSegment<bool>(value: true, label: Text('Dang ky')),
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
                      labelText: 'Email hoac so dien thoai'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _loginPassword,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Mat khau'),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: controller.busy
                      ? null
                      : () => controller.login(
                            identifier: _loginIdentifier.text.trim(),
                            password: _loginPassword.text,
                          ),
                  child: const Text('Dang nhap'),
                ),
              ] else ...[
                TextField(
                  controller: _fullName,
                  decoration: const InputDecoration(labelText: 'Ho ten'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _age,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Tuoi'),
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
                  decoration: const InputDecoration(labelText: 'So dien thoai'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _registerPassword,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Mat khau'),
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
                  child: const Text('Tao tai khoan'),
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
