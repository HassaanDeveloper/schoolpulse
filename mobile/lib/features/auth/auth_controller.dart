import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../core/network/supabase_service.dart';

enum AuthStage { loading, unauthenticated, authenticated }

/// Holds the authentication state for the whole application.
///
/// Flutter's built-in [ValueNotifier] is used deliberately: the MVP does not
/// justify a state-management framework.
class AuthController extends ValueNotifier<AuthStage> {
  AuthController() : super(AuthStage.loading) {
    _listen();
  }

  final SupabaseService _supabase = SupabaseService.instance;

  String? _lastEmail;
  String? _lastUserId;

  void _listen() {
    if (!_supabase.isConfigured) {
      value = AuthStage.unauthenticated;
      return;
    }
    _supabase.authStateChanges.listen((AuthState state) {
      _lastEmail = state.session?.user.email;
      _lastUserId = state.session?.user.id;
      value = state.session == null
          ? AuthStage.unauthenticated
          : AuthStage.authenticated;
    });
  }

  /// Called once after Supabase has finished restoring any persisted session.
  void completeStartup() {
    if (!_supabase.isConfigured) {
      value = AuthStage.unauthenticated;
      return;
    }
    if (_supabase.currentSession != null) {
      value = AuthStage.authenticated;
    } else {
      value = AuthStage.unauthenticated;
    }
  }

  String? get email => _lastEmail;

  String? get userId => _lastUserId;

  /// Returns `null` on success, otherwise a safe message for display.
  Future<String?> signIn(String email, String password) async {
    if (!_supabase.isConfigured) {
      return 'Sign in is unavailable because Supabase is not configured.';
    }
    try {
      await _supabase.client.auth.signInWithPassword(
        email: email.trim(),
        password: password,
      );
      _lastEmail = email.trim();
      return null;
    } on AuthException catch (error) {
      // Deliberately does not distinguish "unknown email" from "wrong password".
      debugPrint('Supabase sign-in failed: ${error.code}');
      return 'Unable to sign in. Please check your email and password.';
    } catch (error) {
      debugPrint('Unexpected sign-in failure: $error');
      return 'Unable to sign in right now. Please try again.';
    }
  }

  Future<void> signOut() async {
    if (!_supabase.isConfigured) {
      return;
    }
    await _supabase.client.auth.signOut();
    _lastEmail = null;
    _lastUserId = null;
    value = AuthStage.unauthenticated;
  }
}