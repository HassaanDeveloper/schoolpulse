import 'package:flutter/material.dart';

import 'auth_controller.dart';
import 'login_screen.dart';
import '../home/home_screen.dart';

/// Root gate: resolves the session on startup and routes to either the
/// login screen or the authenticated home screen.
class AuthGate extends StatefulWidget {
  const AuthGate({super.key, required this.auth});

  final AuthController auth;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.auth.completeStartup();
    });
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<AuthStage>(
      valueListenable: widget.auth,
      builder: (context, stage, _) {
        switch (stage) {
          case AuthStage.loading:
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          case AuthStage.unauthenticated:
            return LoginScreen(auth: widget.auth);
          case AuthStage.authenticated:
            return HomeScreen(auth: widget.auth);
        }
      },
    );
  }
}