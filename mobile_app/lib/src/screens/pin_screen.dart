import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_controller.dart';

enum PinScreenMode { setup, unlock }

class PinScreen extends StatefulWidget {
  const PinScreen({super.key, required this.mode});

  final PinScreenMode mode;

  @override
  State<PinScreen> createState() => _PinScreenState();
}

class _PinScreenState extends State<PinScreen> {
  final _pin = TextEditingController();
  final _confirmPin = TextEditingController();

  @override
  void dispose() {
    _pin.dispose();
    _confirmPin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AppController>();
    final isSetup = widget.mode == PinScreenMode.setup;

    return Scaffold(
      appBar:
          AppBar(title: Text(isSetup ? 'Tao PIN 4 so' : 'Nhap PIN de vao app')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isSetup
                  ? 'PIN nay se mo khoa nhanh tren thiet bi hien tai.'
                  : 'Ban da dang nhap tren thiet bi nay. Chi can nhap PIN de tiep tuc.',
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _pin,
              keyboardType: TextInputType.number,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'PIN 4 so'),
            ),
            if (isSetup) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _confirmPin,
                keyboardType: TextInputType.number,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Nhap lai PIN'),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: controller.busy
                  ? null
                  : () {
                      if (isSetup) {
                        controller.setupPin(
                            _pin.text.trim(), _confirmPin.text.trim());
                      } else {
                        controller.unlockWithPin(_pin.text.trim());
                      }
                    },
              child: Text(isSetup ? 'Luu PIN' : 'Mo khoa'),
            ),
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
    );
  }
}
