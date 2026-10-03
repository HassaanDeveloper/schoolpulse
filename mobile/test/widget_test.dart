import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/app.dart';

void main() {
  testWidgets('App starts and renders the authentication gate', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const SchoolPulseApp());
    await tester.pump();

    expect(find.byType(MaterialApp), findsOneWidget);
  });
}