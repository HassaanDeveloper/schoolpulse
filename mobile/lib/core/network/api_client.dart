import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'supabase_service.dart';

/// Thrown for any non-2xx API response so screens never have to inspect
/// status codes themselves.
class ApiException implements Exception {
  ApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Minimal HTTP layer for the SchoolPulse REST API.
///
/// The Supabase access token is attached centrally here so that no screen
/// has to deal with authorization headers.
class ApiClient {
  ApiClient._internal();

  static final ApiClient instance = ApiClient._internal();

  final http.Client _client = http.Client();

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final base = Uri.parse(AppConfig.apiBaseUrl);
    return base.replace(
      path: path,
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
  }

  Map<String, String> _headers({bool json = true}) {
    final headers = <String, String>{};
    if (json) {
      headers['Content-Type'] = 'application/json';
      headers['Accept'] = 'application/json';
    }
    final session = SupabaseService.instance.currentSession;
    if (session != null) {
      headers['Authorization'] = 'Bearer ${session.accessToken}';
    }
    return headers;
  }

  Future<Map<String, dynamic>> get(
    String path, [
    Map<String, dynamic>? query,
  ]) async {
    return _send(() => _client.get(_uri(path, query), headers: _headers()));
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, [
    Map<String, dynamic>? query,
  ]) async {
    return _send(
      () => _client.post(
        _uri(path, query),
        headers: _headers(),
        body: jsonEncode(body),
      ),
    );
  }

  Future<Map<String, dynamic>> patch(
    String path,
    Map<String, dynamic> body, [
    Map<String, dynamic>? query,
  ]) async {
    return _send(
      () => _client.patch(
        _uri(path, query),
        headers: _headers(),
        body: jsonEncode(body),
      ),
    );
  }

  Future<void> delete(String path, [Map<String, dynamic>? query]) async {
    await _send(() => _client.delete(_uri(path, query), headers: _headers()));
  }

  Future<Map<String, dynamic>> _send(Future<http.Response> Function() call) async {
    final http.Response response;
    try {
      response = await call().timeout(const Duration(seconds: 15));
    } on SocketException {
      throw ApiException(0, 'Could not reach the SchoolPulse server.');
    } on TimeoutException {
      throw ApiException(0, 'The server took too long to respond.');
    }

    final dynamic decoded = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body);

    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      return <String, dynamic>{};
    }

    throw ApiException(
      response.statusCode,
      _extractDetail(decoded) ?? 'Request failed.',
    );
  }

  String? _extractDetail(dynamic body) {
    if (body is Map<String, dynamic>) {
      final detail = body['detail'];
      if (detail is String) {
        return detail;
      }
    }
    return null;
  }
}