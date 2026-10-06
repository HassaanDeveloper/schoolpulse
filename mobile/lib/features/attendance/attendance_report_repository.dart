import '../../core/network/api_client.dart';

/// A student's derived attendance state for one day.
///
/// The server derives this from the timestamps it already stores, so the app
/// never recomputes it. [unknown] exists so an unrecognised value from a newer
/// server renders safely instead of crashing the list.
enum AttendanceStatus {
  absent,
  present,
  completed,
  unknown;

  static AttendanceStatus parse(String? value) => switch (value) {
        'absent' => AttendanceStatus.absent,
        'present' => AttendanceStatus.present,
        'completed' => AttendanceStatus.completed,
        _ => AttendanceStatus.unknown,
      };

  /// The lowercase wire value, for sending back as a filter.
  String get apiValue => switch (this) {
        AttendanceStatus.absent => 'absent',
        AttendanceStatus.present => 'present',
        AttendanceStatus.completed => 'completed',
        AttendanceStatus.unknown => 'absent',
      };

  String get label => switch (this) {
        AttendanceStatus.absent => 'Absent',
        AttendanceStatus.present => 'Present',
        AttendanceStatus.completed => 'Completed',
        AttendanceStatus.unknown => 'Unknown',
      };

  /// Whether this day counts as the student being in school.
  bool get isOnSite =>
      this == AttendanceStatus.present || this == AttendanceStatus.completed;
}

/// Headline counts from `GET /api/v1/attendance/summary`.
class AttendanceSummary {
  const AttendanceSummary({
    required this.date,
    required this.schoolId,
    required this.schoolName,
    required this.classId,
    required this.totalStudents,
    required this.absent,
    required this.present,
    required this.completed,
  });

  final DateTime? date;
  final String schoolId;
  final String schoolName;
  final String? classId;
  final int totalStudents;
  final int absent;
  final int present;
  final int completed;

  factory AttendanceSummary.fromJson(Map<String, dynamic> json) {
    return AttendanceSummary(
      date: parseDateOnly(json['date']),
      schoolId: '${json['school_id']}',
      schoolName: json['school_name'] as String? ?? '',
      classId: json['class_id'] == null ? null : '${json['class_id']}',
      totalStudents: _asInt(json['total_students']),
      absent: _asInt(json['absent']),
      present: _asInt(json['present']),
      completed: _asInt(json['completed']),
    );
  }

  /// Students currently on site: arrived but not yet signed out.
  int get onSite => present + completed;
}

/// One row of the "today" list.
class TodayAttendanceItem {
  const TodayAttendanceItem({
    required this.studentId,
    required this.studentName,
    required this.admissionNumber,
    required this.classId,
    required this.className,
    required this.section,
    required this.status,
    required this.arrivalAt,
    required this.departureAt,
  });

  final String studentId;
  final String studentName;
  final String admissionNumber;
  final String classId;
  final String className;
  final String? section;
  final AttendanceStatus status;
  final DateTime? arrivalAt;
  final DateTime? departureAt;

  factory TodayAttendanceItem.fromJson(Map<String, dynamic> json) {
    return TodayAttendanceItem(
      studentId: '${json['student_id']}',
      studentName: json['student_name'] as String? ?? '',
      admissionNumber: json['admission_number'] as String? ?? '',
      classId: '${json['class_id']}',
      className: json['class_name'] as String? ?? '',
      section: json['section'] as String?,
      status: AttendanceStatus.parse(json['status'] as String?),
      arrivalAt: parseInstant(json['arrival_at']),
      departureAt: parseInstant(json['departure_at']),
    );
  }

  String get classLabel => section == null || section!.isEmpty ? className : '$className - $section';
}

/// A page of today's attendance from `GET /api/v1/attendance/today`.
class TodayAttendancePage {
  const TodayAttendancePage({
    required this.date,
    required this.schoolId,
    required this.schoolName,
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final DateTime? date;
  final String schoolId;
  final String schoolName;
  final List<TodayAttendanceItem> items;
  final int total;
  final int page;
  final int pageSize;

  factory TodayAttendancePage.fromJson(Map<String, dynamic> json) {
    return TodayAttendancePage(
      date: parseDateOnly(json['date']),
      schoolId: '${json['school_id']}',
      schoolName: json['school_name'] as String? ?? '',
      items: parseList(json['items'], TodayAttendanceItem.fromJson),
      total: _asInt(json['total']),
      page: _asInt(json['page'], fallback: 1),
      pageSize: _asInt(json['page_size'], fallback: 20),
    );
  }

  int get pageCount => pageSize <= 0 ? 1 : (total / pageSize).ceil();

  bool get hasNextPage => page < pageCount;

  bool get hasPreviousPage => page > 1;
}

/// One day of a student's history, including days with no record at all.
class AttendanceHistoryRecord {
  const AttendanceHistoryRecord({
    required this.date,
    required this.status,
    required this.arrivalAt,
    required this.departureAt,
    this.arrivalTime,
    this.departureTime,
  });

  final DateTime date;
  final AttendanceStatus status;
  final DateTime? arrivalAt;
  final DateTime? departureAt;

  /// Times already rendered by the server in the school's own timezone, for
  /// example `8:04 AM`. The Day 5 parent endpoint sends these so the app can
  /// show the school's clock time without converting an instant with the
  /// device's timezone. Absent on the Day 4 staff endpoints.
  final String? arrivalTime;
  final String? departureTime;

  factory AttendanceHistoryRecord.fromJson(Map<String, dynamic> json) {
    return AttendanceHistoryRecord(
      date: parseDateOnly(json['date']) ?? DateTime(1970),
      status: AttendanceStatus.parse(json['status'] as String?),
      arrivalAt: parseInstant(json['arrival_at']),
      departureAt: parseInstant(json['departure_at']),
      arrivalTime: json['arrival_time'] as String?,
      departureTime: json['departure_time'] as String?,
    );
  }
}

/// A page of history from `GET /api/v1/attendance/history`.
class AttendanceHistoryPage {
  const AttendanceHistoryPage({
    required this.studentId,
    required this.studentName,
    required this.startDate,
    required this.endDate,
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final String studentId;
  final String studentName;
  final DateTime? startDate;
  final DateTime? endDate;
  final List<AttendanceHistoryRecord> items;
  final int total;
  final int page;
  final int pageSize;

  factory AttendanceHistoryPage.fromJson(Map<String, dynamic> json) {
    return AttendanceHistoryPage(
      studentId: '${json['student_id']}',
      studentName: json['student_name'] as String? ?? '',
      startDate: parseDateOnly(json['start_date']),
      endDate: parseDateOnly(json['end_date']),
      items: parseList(json['items'], AttendanceHistoryRecord.fromJson),
      total: _asInt(json['total']),
      page: _asInt(json['page'], fallback: 1),
      pageSize: _asInt(json['page_size'], fallback: 20),
    );
  }

  int get pageCount => pageSize <= 0 ? 1 : (total / pageSize).ceil();

  bool get hasNextPage => page < pageCount;

  bool get hasPreviousPage => page > 1;
}

/// Counts across a student's whole history, not just the visible page.
class StudentAttendanceSummary {
  const StudentAttendanceSummary({
    required this.totalDays,
    required this.presentDays,
    required this.absentDays,
    required this.completedDays,
  });

  final int totalDays;
  final int presentDays;
  final int absentDays;
  final int completedDays;

  factory StudentAttendanceSummary.fromJson(Map<String, dynamic> json) {
    return StudentAttendanceSummary(
      totalDays: _asInt(json['total_days']),
      presentDays: _asInt(json['present_days']),
      absentDays: _asInt(json['absent_days']),
      completedDays: _asInt(json['completed_days']),
    );
  }

  /// Days the student was on site, whether or not they signed out.
  int get daysOnSite => presentDays + completedDays;

  /// Share of days on site, 0.0 to 1.0. Zero when the range is empty.
  double get attendanceRate {
    if (totalDays <= 0) {
      return 0;
    }
    return daysOnSite / totalDays;
  }
}

/// The student a detail response belongs to.
class AttendanceStudent {
  const AttendanceStudent({
    required this.id,
    required this.name,
    required this.admissionNumber,
    required this.className,
    required this.section,
  });

  final String id;
  final String name;
  final String admissionNumber;
  final String className;
  final String? section;

  factory AttendanceStudent.fromJson(Map<String, dynamic> json) {
    return AttendanceStudent(
      id: '${json['id']}',
      name: json['name'] as String? ?? '',
      admissionNumber: json['admission_number'] as String? ?? '',
      className: json['class_name'] as String? ?? '',
      section: json['section'] as String?,
    );
  }

  String get classLabel =>
      section == null || section!.isEmpty ? className : '$className - $section';
}

/// `GET /api/v1/students/{student_id}/attendance`.
class StudentAttendanceDetail {
  const StudentAttendanceDetail({
    required this.student,
    required this.startDate,
    required this.endDate,
    required this.records,
    required this.summary,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final AttendanceStudent student;
  final DateTime? startDate;
  final DateTime? endDate;
  final List<AttendanceHistoryRecord> records;
  final StudentAttendanceSummary summary;
  final int total;
  final int page;
  final int pageSize;

  factory StudentAttendanceDetail.fromJson(Map<String, dynamic> json) {
    return StudentAttendanceDetail(
      student: AttendanceStudent.fromJson(
        json['student'] as Map<String, dynamic>? ?? <String, dynamic>{},
      ),
      startDate: parseDateOnly(json['start_date']),
      endDate: parseDateOnly(json['end_date']),
      records: parseList(json['records'], AttendanceHistoryRecord.fromJson),
      summary: StudentAttendanceSummary.fromJson(
        json['summary'] as Map<String, dynamic>? ?? <String, dynamic>{},
      ),
      total: _asInt(json['total']),
      page: _asInt(json['page'], fallback: 1),
      pageSize: _asInt(json['page_size'], fallback: 20),
    );
  }

  int get pageCount => pageSize <= 0 ? 1 : (total / pageSize).ceil();

  bool get hasNextPage => page < pageCount;

  bool get hasPreviousPage => page > 1;
}

/// A class the dashboard may be filtered by.
class AttendanceClassOption {
  const AttendanceClassOption({
    required this.id,
    required this.name,
    required this.section,
  });

  final String id;
  final String name;
  final String? section;

  factory AttendanceClassOption.fromJson(Map<String, dynamic> json) {
    return AttendanceClassOption(
      id: '${json['id']}',
      name: json['name'] as String? ?? '',
      section: json['section'] as String?,
    );
  }

  String get label => section == null || section!.isEmpty ? name : '$name - $section';
}

/// Reads the Day 4 read-only attendance endpoints.
///
/// Every method is a GET: the app never writes attendance, and never sends a
/// date for the dashboard, because the server decides the school's local today.
class AttendanceReportRepository {
  const AttendanceReportRepository();

  Future<AttendanceSummary> fetchSummary({
    String? schoolId,
    String? classId,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/attendance/summary',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        if (classId != null) 'class_id': classId,
      },
    );
    return AttendanceSummary.fromJson(json);
  }

  Future<TodayAttendancePage> fetchToday({
    String? schoolId,
    String? classId,
    AttendanceStatus? status,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/attendance/today',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        if (classId != null) 'class_id': classId,
        if (status != null) 'status': status.apiValue,
        if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
        'page': page,
        'page_size': pageSize,
      },
    );
    return TodayAttendancePage.fromJson(json);
  }

  Future<AttendanceHistoryPage> fetchHistory({
    required String studentId,
    String? schoolId,
    DateTime? startDate,
    DateTime? endDate,
    int page = 1,
    int pageSize = 20,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/attendance/history',
      <String, dynamic>{
        'student_id': studentId,
        if (schoolId != null) 'school_id': schoolId,
        if (startDate != null) 'start_date': formatDateOnly(startDate),
        if (endDate != null) 'end_date': formatDateOnly(endDate),
        'page': page,
        'page_size': pageSize,
      },
    );
    return AttendanceHistoryPage.fromJson(json);
  }

  Future<StudentAttendanceDetail> fetchStudentDetail({
    required String studentId,
    String? schoolId,
    DateTime? startDate,
    DateTime? endDate,
    int page = 1,
    int pageSize = 20,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/students/$studentId/attendance',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        if (startDate != null) 'start_date': formatDateOnly(startDate),
        if (endDate != null) 'end_date': formatDateOnly(endDate),
        'page': page,
        'page_size': pageSize,
      },
    );
    return StudentAttendanceDetail.fromJson(json);
  }

  Future<List<AttendanceClassOption>> fetchFilterClasses({String? schoolId}) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/attendance/classes',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return parseList(json, AttendanceClassOption.fromJson);
  }
}

/// `YYYY-MM-DD`, the format the API uses for date parameters.
String formatDateOnly(DateTime value) {
  final String month = value.month.toString().padLeft(2, '0');
  final String day = value.day.toString().padLeft(2, '0');
  return '${value.year.toString().padLeft(4, '0')}-$month-$day';
}

/// Parses a `YYYY-MM-DD` value. Instants are converted to local time.
DateTime? parseDateOnly(dynamic value) {
  if (value is! String || value.isEmpty) {
    return null;
  }
  return DateTime.tryParse(value);
}

DateTime? parseInstant(dynamic value) => parseDateOnly(value)?.toLocal();

List<T> parseList<T>(
  dynamic raw,
  T Function(Map<String, dynamic>) parse,
) {
  final items = raw is List<dynamic> ? raw : const <dynamic>[];
  return items
      .whereType<Map<String, dynamic>>()
      .map(parse)
      .toList(growable: false);
}

int _asInt(dynamic value, {int fallback = 0}) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value) ?? fallback;
  }
  return fallback;
}
