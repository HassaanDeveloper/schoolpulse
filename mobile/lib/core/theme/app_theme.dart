import 'package:flutter/material.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get lightTheme {
    final ColorScheme colorScheme = ColorScheme.fromSeed(
      seedColor: Colors.indigo,
    );

    return ThemeData(
      colorScheme: colorScheme,
      useMaterial3: true,
    );
  }
}
