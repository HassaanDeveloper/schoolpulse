import '../../core/network/api_client.dart';
import '../attendance/attendance_report_repository.dart';

/// One of the caller's children, from `GET /api/v1/me/students`.
///
/// Deliberately carries only what a parent needs. The API does not send date of
/// birth, gender or admission number, so neither can leak into the app.
class ParentChild {
  const ParentChild({
    required this.studentId,
    required this.firstName,
    required this.lastName,
    required this.className,
    required this.section,
    required this.schoolId,
    required this.schoolName,
    required this.schoolTimezone,
    this.todayStatus,
    this.todayStatusDate,
  });

  final String studentId;
  final String firstName;
  final String lastName;
  final String? className;
  final String? section;
  final String schoolId;
  final String schoolName;
  final String schoolTimezone;

  /// The child's derived status for the school's local today, resolved by the
  /// server so the children list needs one request rather than one per child.
  final String? todayStatus;

  /// The school's local date [todayStatus] refers to. Rendered instead of the
  /// device's own date so a parent abroad is not shown the wrong day.
  final String? todayStatusDate;

  factory ParentChild.fromJson(Map<String, dynamic> json) {
    return ParentChild(
      studentId: '${json['student_id']}',
      firstName: json['first_name'] as String? ?? '',
      lastName: json['last_name'] as String? ?? '',
      className: json['class_name'] as String?,
      section: json['section'] as String?,
      schoolId: '${json['school_id']}',
      schoolName: json['school_name'] as String? ?? '',
      schoolTimezone: json['school_timezone'] as String? ?? 'Asia/Karachi',
      todayStatus: json['today_status'] as String?,
      todayStatusDate: json['today_status_date'] as String?,
    );
  }

  String get fullName {
    final String name = '$firstName $lastName'.trim();
    return name.isEmpty ? 'Student' : name;
  }

  String get classLabel {
    final String name = className ?? '';
    if (section == null || section!.isEmpty) {
      return name;
    }
    return name.isEmpty ? section! : '$name - $section';
  }

  /// Plain-language form of [todayStatus] for display on the children list.
  ///
  /// Null when an older server did not send the field, so the caller can stay
  /// silent rather than claim a status it was not told.
  String? get todayStatusLabel {
    switch (todayStatus) {
      case 'present':
        return 'Arrived today';
      case 'completed':
        return 'Arrived and left today';
      case 'absent':
        return 'Not marked present today';
      default:
        return null;
    }
  }
}

/// A child's attendance history, from `GET /api/v1/me/students/{id}/attendance`.
class ParentChildAttendance {
  const ParentChildAttendance({
    required this.studentId,
    required this.startDate,
    required this.endDate,
    required this.records,
  });

  final String studentId;
  final DateTime? startDate;
  final DateTime? endDate;
  final List<AttendanceHistoryRecord> records;

  factory ParentChildAttendance.fromJson(Map<String, dynamic> json) {
    return ParentChildAttendance(
      studentId: '${json['student_id']}',
      startDate: parseDateOnly(json['start_date']),
      endDate: parseDateOnly(json['end_date']),
      records: parseList(json['records'], AttendanceHistoryRecord.fromJson),
    );
  }

  /// The most recent day in the range, which the summary card shows.
  AttendanceHistoryRecord? get latest => records.isEmpty ? null : records.first;

  int get presentDays => records
      .where((record) => record.status == AttendanceStatus.present)
      .length;

  int get completedDays => records
      .where((record) => record.status == AttendanceStatus.completed)
      .length;

  int get absentDays => records
      .where((record) => record.status == AttendanceStatus.absent)
      .length;

  int get daysOnSite => presentDays + completedDays;
}

/// Reads the parent's own children and their attendance.
///
/// No request sends a date by default: the server decides the school-local
/// range, so a phone in another timezone cannot shift what "today" means.
class ParentRepository {
  const ParentRepository();

  Future<List<ParentChild>> fetchChildren({String? schoolId}) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/me/students',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return parseList(json['students'], ParentChild.fromJson);
  }

  Future<ParentChildAttendance> fetchChildAttendance({
    required String studentId,
    DateTime? startDate,
    DateTime? endDate,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/me/students/$studentId/attendance',
      <String, dynamic>{
        if (startDate != null) 'start_date': formatDateOnly(startDate),
        if (endDate != null) 'end_date': formatDateOnly(endDate),
      },
    );
    return ParentChildAttendance.fromJson(json);
  }
}