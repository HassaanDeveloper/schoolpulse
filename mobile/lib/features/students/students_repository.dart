import '../../core/network/api_client.dart';

/// A class as returned by `GET /api/v1/classes`.
class SchoolClass {
  const SchoolClass({
    required this.id,
    required this.name,
    this.section,
    this.academicYear,
  });

  final String id;
  final String name;
  final String? section;
  final String? academicYear;

  factory SchoolClass.fromJson(Map<String, dynamic> json) {
    return SchoolClass(
      id: '${json['id']}',
      name: json['name'] as String? ?? '',
      section: json['section'] as String?,
      academicYear: json['academic_year'] as String?,
    );
  }

  /// "Grade 5 - B (2026-27)", omitting the parts a school left blank.
  String get label {
    final buffer = StringBuffer(name);
    if (section != null && section!.isNotEmpty) {
      buffer.write(' - $section');
    }
    if (academicYear != null && academicYear!.isNotEmpty) {
      buffer.write(' ($academicYear)');
    }
    return buffer.toString();
  }
}

/// A student as returned by `GET /api/v1/students`.
///
/// This is the single student model for the admin app. `className` is not part
/// of the API response — the server returns a `class_id` — so the screens
/// resolve the display name from the class list they have already loaded.
class Student {
  const Student({
    required this.id,
    required this.admissionNumber,
    required this.firstName,
    required this.lastName,
    required this.status,
    this.classId,
    this.dateOfBirth,
    this.gender,
  });

  final String id;
  final String admissionNumber;
  final String firstName;
  final String lastName;
  final String status;
  final String? classId;
  final String? dateOfBirth;
  final String? gender;

  factory Student.fromJson(Map<String, dynamic> json) {
    return Student(
      id: '${json['id']}',
      admissionNumber: json['admission_number'] as String? ?? '',
      firstName: json['first_name'] as String? ?? '',
      lastName: json['last_name'] as String? ?? '',
      status: json['status'] as String? ?? 'active',
      classId: json['class_id'] == null ? null : '${json['class_id']}',
      dateOfBirth: json['date_of_birth'] as String?,
      gender: json['gender'] as String?,
    );
  }

  String get fullName {
    final name = '$firstName $lastName'.trim();
    return name.isEmpty ? admissionNumber : name;
  }

  bool get isActive => status == 'active';
}

/// One page of students from `GET /api/v1/students`.
class StudentPage {
  const StudentPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final List<Student> items;
  final int total;
  final int page;
  final int pageSize;

  factory StudentPage.fromJson(Map<String, dynamic> json) {
    final items = json['items'] as List<dynamic>? ?? const <dynamic>[];
    return StudentPage(
      items: items
          .whereType<Map<String, dynamic>>()
          .map(Student.fromJson)
          .toList(),
      total: _asInt(json['total']),
      page: _asInt(json['page'], fallback: 1),
      pageSize: _asInt(json['page_size'], fallback: 20),
    );
  }

  int get pageCount => pageSize <= 0 ? 1 : (total / pageSize).ceil();

  bool get hasNextPage => page < pageCount;

  bool get hasPreviousPage => page > 1;
}

int _asInt(dynamic value, {int fallback = 0}) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse('$value') ?? fallback;
}

/// Reads and writes classes through the existing Day 2 endpoints.
///
/// Every method is scoped to a school the administrator actually administers;
/// the server re-checks this and answers `404` for another school's classes.
class ClassesRepository {
  const ClassesRepository();

  Future<List<SchoolClass>> listClasses({String? schoolId}) async {
    final List<dynamic> items = await ApiClient.instance.getList(
      '/api/v1/classes',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return items
        .whereType<Map<String, dynamic>>()
        .map(SchoolClass.fromJson)
        .toList();
  }

  Future<SchoolClass> createClass({
    required String name,
    String? section,
    String? academicYear,
    String? schoolId,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.post(
      '/api/v1/classes',
      <String, dynamic>{
        'name': name,
        if (section != null && section.isNotEmpty) 'section': section,
        if (academicYear != null && academicYear.isNotEmpty)
          'academic_year': academicYear,
      },
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return SchoolClass.fromJson(json);
  }

  /// Deleting a class that still has students fails with `409`; the screen
  /// turns that into an explanation rather than an error code.
  Future<void> deleteClass(String classId, {String? schoolId}) async {
    await ApiClient.instance.delete(
      '/api/v1/classes/$classId',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
  }
}

/// Reads and writes students through the existing Day 2 endpoints.
///
/// Deletion is deliberately absent from this app's vocabulary: the API's
/// `DELETE /students/{id}` is a soft deactivation, and it is exposed here as
/// [deactivateStudent] so no screen can hard-delete a child by accident.
class StudentsRepository {
  const StudentsRepository();

  Future<StudentPage> listStudents({
    String? schoolId,
    String? classId,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/students',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        if (classId != null) 'class_id': classId,
        if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
        'page': page,
        'page_size': pageSize,
      },
    );
    return StudentPage.fromJson(json);
  }

  Future<Student> fetchStudent(String studentId, {String? schoolId}) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/students/$studentId',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return Student.fromJson(json);
  }

  Future<Student> createStudent({
    required String firstName,
    required String lastName,
    required String admissionNumber,
    required String classId,
    String? dateOfBirth,
    String? gender,
    String? schoolId,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.post(
      '/api/v1/students',
      <String, dynamic>{
        'first_name': firstName,
        'last_name': lastName,
        'admission_number': admissionNumber,
        'class_id': classId,
        if (dateOfBirth != null && dateOfBirth.isNotEmpty)
          'date_of_birth': dateOfBirth,
        if (gender != null && gender.isNotEmpty) 'gender': gender,
      },
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    return Student.fromJson(json);
  }

  /// Soft deactivates the student. The record and its attendance history stay
  /// intact; an inactive student simply stops appearing in daily counts and
  /// can no longer be scanned.
  Future<void> deactivateStudent(String studentId, {String? schoolId}) async {
    await ApiClient.instance.delete(
      '/api/v1/students/$studentId',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
  }
}
