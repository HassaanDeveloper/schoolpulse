import '../../core/network/api_client.dart';
import '../students/students_repository.dart';

/// The student model lives with the students API and is re-exported here so
/// QR screens and their tests keep one shared definition.
export '../students/students_repository.dart' show Student;

/// A freshly issued QR credential.
///
/// [credential] is the plaintext token. The API returns it exactly once and
/// only its SHA-256 hash is stored, so the app must never persist or log it.
class QrCredential {
  const QrCredential({
    required this.studentId,
    required this.credential,
    required this.createdAt,
    required this.revokedPrevious,
  });

  final String studentId;
  final String credential;
  final DateTime? createdAt;
  final bool revokedPrevious;

  factory QrCredential.fromJson(Map<String, dynamic> json) {
    return QrCredential(
      studentId: '${json['student_id']}',
      credential: json['credential'] as String? ?? '',
      createdAt: _parseDate(json['created_at']),
      revokedPrevious: json['revoked_previous'] as bool? ?? false,
    );
  }
}

/// Credential state for a student, without exposing the secret.
class QrCredentialStatus {
  const QrCredentialStatus({
    required this.studentId,
    required this.hasActiveCredential,
    required this.createdAt,
    this.lastRevokedAt,
  });

  final String studentId;
  final bool hasActiveCredential;
  final DateTime? createdAt;

  /// When the previous code was revoked. The server sends this so the app can
  /// tell "revoked" apart from "never issued", which a boolean alone cannot.
  final DateTime? lastRevokedAt;

  factory QrCredentialStatus.fromJson(Map<String, dynamic> json) {
    return QrCredentialStatus(
      studentId: '${json['student_id']}',
      hasActiveCredential: json['has_active_credential'] as bool? ?? false,
      createdAt: _parseDate(json['created_at']),
      lastRevokedAt: _parseDate(json['last_revoked_at']),
    );
  }

  /// The three states an administrator needs to see.
  QrCodeState get state {
    if (hasActiveCredential) {
      return QrCodeState.active;
    }
    return lastRevokedAt == null ? QrCodeState.notGenerated : QrCodeState.revoked;
  }
}

enum QrCodeState { active, revoked, notGenerated }

DateTime? _parseDate(dynamic value) {
  if (value is! String || value.isEmpty) {
    return null;
  }
  return DateTime.tryParse(value)?.toLocal();
}

/// Reads students and drives the Day 3 QR credential endpoints.
class QrRepository {
  const QrRepository();

  Future<List<Student>> listStudents({String? schoolId}) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/students',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        'page_size': 100,
      },
    );
    final items = json['items'] as List<dynamic>? ?? const <dynamic>[];
    return items
        .whereType<Map<String, dynamic>>()
        .map(Student.fromJson)
        .toList();
  }

  Future<QrCredential> generateCredential(String studentId) async {
    final Map<String, dynamic> json = await ApiClient.instance
        .post('/api/v1/students/$studentId/qr', <String, dynamic>{});
    return QrCredential.fromJson(json);
  }

  Future<QrCredentialStatus> fetchStatus(String studentId) async {
    final Map<String, dynamic> json =
        await ApiClient.instance.get('/api/v1/students/$studentId/qr');
    return QrCredentialStatus.fromJson(json);
  }

  Future<void> revokeCredential(String studentId) async {
    await ApiClient.instance.delete('/api/v1/students/$studentId/qr');
  }
}