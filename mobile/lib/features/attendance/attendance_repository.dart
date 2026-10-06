import '../../core/network/api_client.dart';

/// Outcome of a single attendance scan.
enum ScanStatus {
  arrivalRecorded,
  departureRecorded,
  alreadyRecorded,
  unknown;

  static ScanStatus parse(String? value) => switch (value) {
        'ARRIVAL_RECORDED' => ScanStatus.arrivalRecorded,
        'DEPARTURE_RECORDED' => ScanStatus.departureRecorded,
        'ALREADY_RECORDED' => ScanStatus.alreadyRecorded,
        _ => ScanStatus.unknown,
      };

  String get label => switch (this) {
        ScanStatus.arrivalRecorded => 'Arrival recorded',
        ScanStatus.departureRecorded => 'Departure recorded',
        ScanStatus.alreadyRecorded => 'Already recorded',
        ScanStatus.unknown => 'Recorded',
      };

  /// Whether this scan changed the attendance record, which decides if the
  /// app should show a positive confirmation.
  bool get isNew => this == ScanStatus.arrivalRecorded || this == ScanStatus.departureRecorded;
}

/// Minimal student identification returned to the scanner.
class ScannedStudent {
  const ScannedStudent({
    required this.id,
    required this.name,
    required this.admissionNumber,
  });

  final String id;
  final String name;
  final String admissionNumber;

  factory ScannedStudent.fromJson(Map<String, dynamic> json) {
    return ScannedStudent(
      id: '${json['id']}',
      name: json['name'] as String? ?? '',
      admissionNumber: json['admission_number'] as String? ?? '',
    );
  }
}

/// Result of `POST /api/v1/attendance/scan`.
class ScanResult {
  const ScanResult({
    required this.status,
    required this.student,
    required this.attendanceDate,
    required this.arrivalAt,
    required this.departureAt,
    required this.timestamp,
  });

  final ScanStatus status;
  final ScannedStudent student;
  final DateTime? attendanceDate;
  final DateTime? arrivalAt;
  final DateTime? departureAt;
  final DateTime? timestamp;

  factory ScanResult.fromJson(Map<String, dynamic> json) {
    return ScanResult(
      status: ScanStatus.parse(json['status'] as String?),
      student: ScannedStudent.fromJson(
        json['student'] as Map<String, dynamic>? ?? <String, dynamic>{},
      ),
      attendanceDate: _parseDate(json['attendance_date']),
      arrivalAt: _parseInstant(json['arrival_at']),
      departureAt: _parseInstant(json['departure_at']),
      timestamp: _parseInstant(json['timestamp']),
    );
  }
}

DateTime? _parseDate(dynamic value) {
  if (value is! String || value.isEmpty) {
    return null;
  }
  return DateTime.tryParse(value);
}

DateTime? _parseInstant(dynamic value) => _parseDate(value)?.toLocal();

/// Posts scanned credentials to the attendance endpoint.
///
/// The server decides who is marked present; the client only ever sends the
/// opaque credential.
class AttendanceRepository {
  const AttendanceRepository();

  Future<ScanResult> scan(String credential) async {
    final Map<String, dynamic> json = await ApiClient.instance.post(
      '/api/v1/attendance/scan',
      <String, dynamic>{'credential': credential},
    );
    return ScanResult.fromJson(json);
  }
}