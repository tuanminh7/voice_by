import 'package:flutter/material.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'src/app.dart';
import 'src/services/firebase_messaging_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  runApp(const EmergencyCallApp());
}
