import 'package:supabase_flutter/supabase_flutter.dart';

import '../config/app_config.dart';

/// Owns the single Supabase client instance.
///
/// Supabase persists the session locally, so a returning user is restored
/// automatically after [initialize].
class SupabaseService {
  SupabaseService._();

  static final SupabaseService instance = SupabaseService._();

  SupabaseClient? _client;

  bool get isConfigured => AppConfig.hasSupabaseConfig;

  SupabaseClient get client {
    final existing = _client;
    if (existing != null) {
      return existing;
    }
    throw StateError(
      'Supabase is not configured. Provide SUPABASE_URL and SUPABASE_ANON_KEY.',
    );
  }

  Future<void> initialize() async {
    if (!isConfigured || _client != null) {
      return;
    }
    await Supabase.initialize(
      url: AppConfig.supabaseUrl,
      publishableKey: AppConfig.supabaseAnonKey,
    );
    _client = Supabase.instance.client;
  }

  Session? get currentSession => _client?.auth.currentSession;

  Stream<AuthState> get authStateChanges =>
      _client?.auth.onAuthStateChange ?? const Stream<AuthState>.empty();
}