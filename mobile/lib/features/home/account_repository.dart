import '../../core/network/api_client.dart';

/// Data returned by `GET /api/v1/me`.
class Membership {
  const Membership({
    required this.schoolId,
    required this.schoolName,
    required this.role,
  });

  final String schoolId;
  final String schoolName;
  final String role;

  factory Membership.fromJson(Map<String, dynamic> json) {
    return Membership(
      schoolId: '${json['school_id']}',
      schoolName: json['school_name'] as String? ?? '',
      role: json['role'] as String? ?? '',
    );
  }

  String get roleLabel => switch (role) {
        'school_admin' => 'School Admin',
        'teacher' => 'Teacher',
        'parent' => 'Parent',
        _ => role,
      };
}

class Me {
  const Me({required this.id, required this.memberships});

  final String id;
  final List<Membership> memberships;

  factory Me.fromJson(Map<String, dynamic> json) {
    final user = json['user'] as Map<String, dynamic>? ?? <String, dynamic>{};
    final rawMemberships =
        json['memberships'] as List<dynamic>? ?? const <dynamic>[];
    return Me(
      id: '${user['id']}',
      memberships: rawMemberships
          .whereType<Map<String, dynamic>>()
          .map(Membership.fromJson)
          .toList(),
    );
  }
}

/// Loads the caller's own identity and school memberships from the API.
class AccountRepository {
  const AccountRepository();

  Future<Me> fetchMe() async {
    final Map<String, dynamic> json =
        await ApiClient.instance.get('/api/v1/me');
    return Me.fromJson(json);
  }
}