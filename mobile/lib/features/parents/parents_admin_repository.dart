import '../../core/network/api_client.dart';

/// A parent account an administrator may link to a student.
class ParentAccount {
  const ParentAccount({
    required this.userId,
    this.fullName,
    this.email,
  });

  /// The `user_profiles.id` that `POST /students/{id}/parents` expects.
  final String userId;
  final String? fullName;
  final String? email;

  factory ParentAccount.fromJson(Map<String, dynamic> json) {
    return ParentAccount(
      userId: '${json['user_id']}',
      fullName: json['full_name'] as String?,
      email: json['email'] as String?,
    );
  }

  /// Falls back to the email when a profile has no name, so the list never
  /// shows an unrecognisable blank row.
  String get displayName {
    final name = fullName?.trim() ?? '';
    if (name.isNotEmpty) {
      return name;
    }
    return email ?? 'Parent';
  }

  String get subtitle => email ?? 'No email on file';
}

/// A guardian already linked to a student.
class LinkedParent {
  const LinkedParent({
    required this.userId,
    this.fullName,
    this.email,
    this.linkedAt,
  });

  final String userId;
  final String? fullName;
  final String? email;
  final DateTime? linkedAt;

  factory LinkedParent.fromJson(Map<String, dynamic> json) {
    return LinkedParent(
      userId: '${json['user_id']}',
      fullName: json['full_name'] as String?,
      email: json['email'] as String?,
      linkedAt: _parseInstant(json['linked_at']),
    );
  }

  String get displayName {
    final name = fullName?.trim() ?? '';
    if (name.isNotEmpty) {
      return name;
    }
    return email ?? 'Parent';
  }

  String get subtitle => email ?? 'No email on file';
}

DateTime? _parseInstant(dynamic value) {
  if (value is! String || value.isEmpty) {
    return null;
  }
  return DateTime.tryParse(value)?.toLocal();
}

/// The admin-side parent API.
///
/// [listAccounts] reads `GET /api/v1/parents`, a read-only directory of
/// accounts that already hold a parent membership in the administrator's own
/// school. There is deliberately no create method: SchoolPulse has no public
/// parent registration, so this repository cannot mint an account.
class ParentsAdminRepository {
  const ParentsAdminRepository();

  Future<List<ParentAccount>> listAccounts({String? schoolId, String? search}) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/parents',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final items = json['parents'] as List<dynamic>? ?? const <dynamic>[];
    return items
        .whereType<Map<String, dynamic>>()
        .map(ParentAccount.fromJson)
        .toList();
  }

  Future<List<LinkedParent>> listLinked(String studentId, {String? schoolId}) async {
    final List<dynamic> json = await ApiClient.instance.getList(
      '/api/v1/students/$studentId/parents',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return json
        .whereType<Map<String, dynamic>>()
        .map(LinkedParent.fromJson)
        .toList();
  }

  Future<void> linkParent(
    String studentId,
    String parentUserId, {
    String? schoolId,
  }) async {
    await ApiClient.instance.post(
      '/api/v1/students/$studentId/parents',
      <String, dynamic>{'parent_user_id': parentUserId},
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
  }

  /// Removes the guardian's access to this student. Notifications already sent
  /// to them are kept as an audit trail.
  Future<void> unlinkParent(
    String studentId,
    String parentUserId, {
    String? schoolId,
  }) async {
    await ApiClient.instance.delete(
      '/api/v1/students/$studentId/parents/$parentUserId',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
  }
}
