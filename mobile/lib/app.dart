import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/auth_gate.dart';

class SchoolPulseApp extends StatefulWidget {
  const SchoolPulseApp({super.key});

  @override
  State<SchoolPulseApp> createState() => _SchoolPulseAppState();
}

class _SchoolPulseAppState extends State<SchoolPulseApp> {
  late final AuthController _auth;

  @override
  void initState() {
    super.initState();
    _auth = AuthController();
  }

  @override
  void dispose() {
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SchoolPulse',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: AuthGate(auth: _auth),
    );
  }
}