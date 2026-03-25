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
      title: 'UT Nguyen Mobile',
      debugShowCheckedModeBanner: false,
      navigatorKey: AppNavigator.navigatorKey,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF0F4C81)),
        useMaterial3: true,
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
        return const HomeScreen();
    }
  }
}
