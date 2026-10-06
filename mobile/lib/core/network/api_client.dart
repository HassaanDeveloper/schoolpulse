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
    return _asMap(await _send(() => _client.get(_uri(path, query), headers: _headers())));
  }

  /// For endpoints that answer with a JSON array, such as `GET /classes` and
  /// `GET /students/{id}/parents`.
  Future<List<dynamic>> getList(
    String path, [
    Map<String, dynamic>? query,
  ]) async {
    return _asList(await _send(() => _client.get(_uri(path, query), headers: _headers())));
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, [
    Map<String, dynamic>? query,
  ]) async {
    return _asMap(
      await _send(
        () => _client.post(
          _uri(path, query),
          headers: _headers(),
          body: jsonEncode(body),
        ),
      ),
    );
  }

  Future<Map<String, dynamic>> patch(
    String path,
    Map<String, dynamic> body, [
    Map<String, dynamic>? query,
  ]) async {
    return _asMap(
      await _send(
        () => _client.patch(
          _uri(path, query),
          headers: _headers(),
          body: jsonEncode(body),
        ),
      ),
    );
  }

  Future<void> delete(String path, [Map<String, dynamic>? query]) async {
    await _send(() => _client.delete(_uri(path, query), headers: _headers()));
  }

  Map<String, dynamic> _asMap(dynamic decoded) =>
      decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};

  List<dynamic> _asList(dynamic decoded) => decoded is List ? decoded : const <dynamic>[];

  Future<dynamic> _send(Future<http.Response> Function() call) async {
    final http.Response response;
    try {
      response = await call().timeout(const Duration(seconds: 15));
    } on SocketException {
      throw ApiException(0, 'Could not reach the SchoolPulse server.');
    } on http.ClientException {
      // DNS failure, refused connection, dropped socket: a connectivity problem
      // rather than a server answer, so it must not read as a server error.
      throw ApiException(0, 'Could not reach the SchoolPulse server.');
    } on TimeoutException {
      throw ApiException(0, 'The server took too long to respond.');
    }

    final dynamic decoded = response.body.isEmpty
        ? <String, dynamic>{}
        : _tryDecode(response.body);

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded;
    }

    throw ApiException(
      response.statusCode,
      _extractDetail(decoded) ?? 'Request failed.',
    );
  }

  /// A non-JSON error body (a proxy error page, for instance) must not crash the
  /// app; it is simply treated as having no detail.
  dynamic _tryDecode(String body) {
    try {
      return jsonDecode(body);
    } on FormatException {
      return null;
    }
  }

  /// Flattens FastAPI's error shapes into one readable line.
  ///
  /// A plain `detail` string is used as-is. A 422 sends a list of field errors,
  /// each with a `loc`/`msg` pair, which is reduced to "field: message" so the
  /// person filling in the form learns which field is wrong.
  String? _extractDetail(dynamic body) {
    if (body is! Map<String, dynamic>) {
      return null;
    }

    final dynamic detail = body['detail'];
    if (detail is String) {
      return detail;
    }

    if (detail is List && detail.isNotEmpty) {
      final messages = <String>[];
      for (final item in detail) {
        if (item is Map<String, dynamic>) {
          final message = item['msg'];
          if (message is! String) {
            continue;
          }
          // `loc` is like ["body", "first_name"]; the field name is the last
          // entry, and list indices are noise in a form.
          final location = item['loc'];
          String field = '';
          if (location is List && location.isNotEmpty) {
            final last = location.last;
            if (last is String && last != 'body' && last != 'query') {
              field = last.replaceAll('_', ' ');
            }
          }
          messages.add(field.isEmpty ? message : '$field: $message');
        }
      }
      if (messages.isNotEmpty) {
        return messages.join('\n');
      }
    }

    return null;
  }
}