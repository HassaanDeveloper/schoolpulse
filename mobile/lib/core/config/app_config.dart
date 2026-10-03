/// Centralised, compile-time application configuration.
///
/// Values come from `--dart-define` so that no secret ever needs to be
/// committed and no machine-specific value is hardcoded in application logic.
///
/// Usage:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
///               --dart-define=SUPABASE_URL=... \
///               --dart-define=SUPABASE_ANON_KEY=...
class AppConfig {
  AppConfig._();

  /// Android emulators reach the host machine through 10.0.2.2.
  /// `localhost` inside an emulator refers to the emulator itself.
  static const String _defaultApiBaseUrl = 'http://10.0.2.2:8000';

  static String get apiBaseUrl {
    const String value = String.fromEnvironment('API_BASE_URL');
    return value.isNotEmpty ? value : _defaultApiBaseUrl;
  }

  static String get supabaseUrl {
    const String value = String.fromEnvironment('SUPABASE_URL');
    return value;
  }

  static String get supabaseAnonKey {
    const String value = String.fromEnvironment('SUPABASE_ANON_KEY');
    return value;
  }

  static bool get hasSupabaseConfig =>
      supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty;

  static bool get hasApiBaseUrl => apiBaseUrl.isNotEmpty;
}