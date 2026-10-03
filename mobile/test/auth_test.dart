import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/features/auth/login_screen.dart';
import 'package:schoolpulse/features/auth/auth_controller.dart';
import 'package:schoolpulse/features/auth/auth_gate.dart';

Widget wrap(Widget child, AuthController auth) {
  return MaterialApp(home: child);
}

void main() {
  late AuthController auth;

  setUp(() {
    auth = AuthController();
  });

  tearDown(() {
    auth.dispose();
  });

  testWidgets('Login screen shows email and password fields', (tester) async {
    await tester.pumpWidget(wrap(LoginScreen(auth: auth), auth));

    expect(find.byType(TextFormField), findsNWidgets(2));
    expect(find.text('Sign In'), findsOneWidget);
    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
  });

  testWidgets('Empty form shows validation messages', (tester) async {
    await tester.pumpWidget(wrap(LoginScreen(auth: auth), auth));

    await tester.tap(find.text('Sign In'));
    await tester.pump();

    expect(find.text('Enter your email address.'), findsOneWidget);
    expect(find.text('Enter your password.'), findsOneWidget);
  });

  testWidgets('Password visibility can be toggled', (tester) async {
    await tester.pumpWidget(wrap(LoginScreen(auth: auth), auth));

    expect(find.byIcon(Icons.visibility_outlined), findsOneWidget);
    await tester.tap(find.byIcon(Icons.visibility_outlined));
    await tester.pump();

    expect(find.byIcon(Icons.visibility_off_outlined), findsOneWidget);
  });

  testWidgets('Gate resolves to the login screen when unauthenticated', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(AuthGate(auth: auth), auth));
    await tester.pump();

    expect(find.byType(LoginScreen), findsOneWidget);
  });
}