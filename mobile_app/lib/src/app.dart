import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_navigator.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'screens/pin_screen.dart';
import 'state/app_controller.dart';

class EmergencyCallApp extends StatelessWidget {
  const EmergencyCallApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Icare',
      debugShowCheckedModeBanner: false,
      navigatorKey: AppNavigator.navigatorKey,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F4C81),
          primary: const Color(0xFF0F4C81),
          secondary: const Color(0xFF3D7EA6),
          surface: Colors.white,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF5F7FB),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFFF8FAFD),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: const BorderSide(color: Color(0xFFD0DCEA)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: const BorderSide(color: Color(0xFFD0DCEA)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: const BorderSide(color: Color(0xFF0F4C81), width: 1.4),
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 18,
            vertical: 18,
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF0F4C81),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(18),
            ),
            textStyle: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        cardTheme: CardThemeData(
          color: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
        ),
      ),
      home: FutureBuilder<AppController>(
        future: AppController.create(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }

          return ChangeNotifierProvider<AppController>.value(
            value: snapshot.data!,
            child: const _AppRouter(),
          );
        },
      ),
    );
  }
}

class _AppRouter extends StatelessWidget {
  const _AppRouter();

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AppController>();

    switch (controller.stage) {
      case AppStage.loading:
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      case AppStage.auth:
        return const AuthScreen();
      case AppStage.pinSetup:
        return const PinScreen(mode: PinScreenMode.setup);
      case AppStage.pinUnlock:
        return const PinScreen(mode: PinScreenMode.unlock);
      case AppStage.home:
        return const _HomeShell();
    }
  }
}

class _HomeShell extends StatelessWidget {
  const _HomeShell();

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AppController>();
    final currentUser = controller.profile;
    final activeCall = controller.activeCall;
    final showIncomingOverlay = currentUser != null &&
        activeCall != null &&
        activeCall.canAccept(currentUser.id);

    return Stack(
      children: [
        const HomeScreen(),
        if (showIncomingOverlay)
          Positioned.fill(
            child: _IncomingCallFullscreen(
              callerName: activeCall.caller?.fullName ?? 'Người thân',
              relationshipLabel:
                  activeCall.relationshipLabel ?? activeCall.relationshipKey,
              transcriptText: activeCall.transcriptText,
              hasRealtimeCallConfig: controller.hasRealtimeCallConfig,
              onAccept: controller.acceptActiveCall,
              onDecline: controller.declineActiveCall,
              busy: controller.busy,
            ),
          ),
      ],
    );
  }
}

class _IncomingCallFullscreen extends StatelessWidget {
  const _IncomingCallFullscreen({
    required this.callerName,
    required this.relationshipLabel,
    required this.transcriptText,
    required this.hasRealtimeCallConfig,
    required this.onAccept,
    required this.onDecline,
    required this.busy,
  });

  final String callerName;
  final String? relationshipLabel;
  final String? transcriptText;
  final bool hasRealtimeCallConfig;
  final Future<void> Function() onAccept;
  final Future<void> Function() onDecline;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Material(
      color: const Color(0xFF081A2B).withValues(alpha: 0.96),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
          child: Column(
            children: [
              const Spacer(),
              Container(
                width: 96,
                height: 96,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.24),
                    width: 1.5,
                  ),
                ),
                alignment: Alignment.center,
                child: Text(
                  callerName.isNotEmpty ? callerName[0].toUpperCase() : '?',
                  style: theme.textTheme.displaySmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(height: 28),
              Text(
                'Cuộc gọi đến',
                style: theme.textTheme.headlineMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                callerName,
                textAlign: TextAlign.center,
                style: theme.textTheme.displaySmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (relationshipLabel?.trim().isNotEmpty == true) ...[
                const SizedBox(height: 8),
                Text(
                  relationshipLabel!.trim(),
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: const Color(0xFFB7D9FF),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              if (transcriptText?.trim().isNotEmpty == true) ...[
                const SizedBox(height: 20),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.1),
                    ),
                  ),
                  child: Text(
                    transcriptText!.trim(),
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      color: Colors.white.withValues(alpha: 0.92),
                      height: 1.5,
                    ),
                  ),
                ),
              ],
              if (!hasRealtimeCallConfig) ...[
                const SizedBox(height: 18),
                Text(
                  'Bản app này chưa có cấu hình thoại realtime nên chưa thể nhận máy để vào nói chuyện.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: const Color(0xFFFFC9C9),
                    height: 1.5,
                  ),
                ),
              ],
              const Spacer(),
              if (busy)
                const Padding(
                  padding: EdgeInsets.only(bottom: 18),
                  child: CircularProgressIndicator(color: Colors.white),
                ),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: busy ? null : () async => onDecline(),
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF3B0D11),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 18),
                      ),
                      icon: const Icon(Icons.call_end_rounded),
                      label: const Text('Từ chối'),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: busy || !hasRealtimeCallConfig
                          ? null
                          : () async => onAccept(),
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF1E8E5A),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 18),
                      ),
                      icon: const Icon(Icons.call_rounded),
                      label: const Text('Nhận máy'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
