import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/core/network/api_client.dart';
import 'package:schoolpulse/features/attendance/attendance_report_repository.dart';
import 'package:schoolpulse/features/attendance/student_attendance_screen.dart';

class _FakeRepository implements AttendanceReportRepository {
  _FakeRepository({this.detail, this.error, this.gate});

  StudentAttendanceDetail? detail;
  ApiException? error;
  Completer<void>? gate;

  int calls = 0;
  DateTime? lastStart;
  DateTime? lastEnd;
  int lastPage = 1;
  String? lastSchoolId;

  Future<void> _wait() async {
    final gate = this.gate;
    if (gate != null) {
      await gate.future;
    }
  }

  @override
  Future<StudentAttendanceDetail> fetchStudentDetail({
    required String studentId,
    String? schoolId,
    DateTime? startDate,
    DateTime? endDate,
    int page = 1,
    int pageSize = 20,
  }) async {
    calls++;
    lastStart = startDate;
    lastEnd = endDate;
    lastPage = page;
    lastSchoolId = schoolId;
    await _wait();
    if (error != null) {
      throw error!;
    }
    return detail ?? _detail();
  }

  @override
  Future<AttendanceSummary> fetchSummary({String? schoolId, String? classId}) {
    throw UnimplementedError();
  }

  @override
  Future<TodayAttendancePage> fetchToday({
    String? schoolId,
    String? classId,
    AttendanceStatus? status,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<AttendanceHistoryPage> fetchHistory({
    required String studentId,
    String? schoolId,
    DateTime? startDate,
    DateTime? endDate,
    int page = 1,
    int pageSize = 20,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<List<AttendanceClassOption>> fetchFilterClasses({String? schoolId}) {
    throw UnimplementedError();
  }
}

AttendanceHistoryRecord _record(
  DateTime date,
  AttendanceStatus status, {
  DateTime? arrival,
  DateTime? departure,
}) {
  return AttendanceHistoryRecord(
    date: date,
    status: status,
    arrivalAt: arrival,
    departureAt: departure,
  );
}

StudentAttendanceDetail _detail({
  List<AttendanceHistoryRecord>? records,
  int total = 7,
  int page = 1,
  int pageSize = 20,
  int totalDays = 7,
  int presentDays = 3,
  int absentDays = 3,
  int completedDays = 1,
}) {
  return StudentAttendanceDetail(
    student: const AttendanceStudent(
      id: 'student-1',
      name: 'Ayesha Khan',
      admissionNumber: 'ADM-001',
      className: 'Grade 5',
      section: 'A',
    ),
    startDate: DateTime(2026, 9, 28),
    endDate: DateTime(2026, 10, 4),
    records: records ??
        <AttendanceHistoryRecord>[
          _record(
            DateTime(2026, 10, 4),
            AttendanceStatus.present,
            arrival: DateTime(2026, 10, 4, 8, 30),
          ),
          _record(DateTime(2026, 10, 3), AttendanceStatus.absent),
          _record(
            DateTime(2026, 10, 2),
            AttendanceStatus.completed,
            arrival: DateTime(2026, 10, 2, 8, 15),
            departure: DateTime(2026, 10, 2, 15, 30),
          ),
        ],
    summary: StudentAttendanceSummary(
      totalDays: totalDays,
      presentDays: presentDays,
      absentDays: absentDays,
      completedDays: completedDays,
    ),
    total: total,
    page: page,
    pageSize: pageSize,
  );
}

Widget _wrap(
  _FakeRepository repository, {
  String? schoolId,
  int pageSize = 20,
}) {
  return MaterialApp(
    home: StudentAttendanceScreen(
      studentId: 'student-1',
      studentName: 'Ayesha Khan',
      admissionNumber: 'ADM-001',
      repository: repository,
      schoolId: schoolId,
      pageSize: pageSize,
      today: DateTime(2026, 10, 4),
    ),
  );
}

/// Scrolls the lazily-built pager fully into view before interacting with it.
Future<void> _tapNextPage(WidgetTester tester) async {
  final scrollable = find.byType(Scrollable).first;
  await tester.scrollUntilVisible(find.text('Next'), 120, scrollable: scrollable);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Next'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows a loading indicator while fetching', (tester) async {
    final repository = _FakeRepository(gate: Completer<void>());
    await tester.pumpWidget(_wrap(repository));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    repository.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.text('Ayesha Khan'), findsWidgets);
  });

  testWidgets('requests the default seven day range', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    expect(repository.lastStart, DateTime(2026, 9, 28));
    expect(repository.lastEnd, DateTime(2026, 10, 4));
    expect(find.text('2026-09-28  to  2026-10-04'), findsOneWidget);
  });

  testWidgets('shows the student identity and class', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Ayesha Khan'), findsWidgets);
    expect(find.text('ADM-001 - Grade 5 - A'), findsOneWidget);
  });

  testWidgets('renders each day with its derived status', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.text('2026-10-04'), findsOneWidget);
    expect(find.text('2026-10-03'), findsOneWidget);
    expect(find.text('2026-10-02'), findsOneWidget);

    // The status words also appear in the summary strip, so scope these
    // assertions to the per-day rows.
    final statusIn = find.descendant(
      of: find.byType(ListTile),
      matching: find.text('Present'),
    );
    expect(statusIn, findsOneWidget);
    expect(
      find.descendant(of: find.byType(ListTile), matching: find.text('Absent')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: find.byType(ListTile), matching: find.text('Completed')),
      findsOneWidget,
    );
  });

  testWidgets('shows arrival and departure times when they exist', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Arrived 08:30'), findsOneWidget);
    expect(find.text('Arrived 08:15 - left 15:30'), findsOneWidget);
    expect(find.text('No record'), findsOneWidget);
  });

  testWidgets('summarises the whole range, not just the visible page', (tester) async {
    await tester.pumpWidget(
      _wrap(
        _FakeRepository(
          detail: _detail(total: 45, pageSize: 20, totalDays: 45, presentDays: 29, completedDays: 1),
        ),
        pageSize: 20,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('7 days'), findsNothing);
    expect(find.text('45 days'), findsOneWidget);
    expect(find.text('30'), findsOneWidget); // 29 present + 1 completed on site
  });

  testWidgets('shows the attendance rate', (tester) async {
    await tester.pumpWidget(
      _wrap(
        _FakeRepository(
          detail: _detail(totalDays: 10, presentDays: 4, absentDays: 3, completedDays: 3),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('70%'), findsOneWidget);
  });

  testWidgets('the 30 day preset widens the range', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Last 30 days'));
    await tester.pumpAndSettle();

    expect(repository.lastStart, DateTime(2026, 9, 5));
    expect(repository.lastEnd, DateTime(2026, 10, 4));
    expect(find.text('2026-09-05  to  2026-10-04'), findsOneWidget);
  });

  testWidgets('changing the range resets to the first page', (tester) async {
    final repository = _FakeRepository(detail: _detail(total: 45, pageSize: 20));
    await tester.pumpWidget(_wrap(repository, pageSize: 20));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Page 1 of 3'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await _tapNextPage(tester);
    expect(repository.lastPage, 2);

    await tester.tap(find.text('Last 30 days'));
    await tester.pumpAndSettle();
    expect(repository.lastPage, 1);
  });

  testWidgets('rejects a range longer than the server limit', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Date range'));
    await tester.pumpAndSettle();

    expect(find.text('Ranges are limited to 90 days.'), findsOneWidget);
  });

  testWidgets('surfaces an API error with a retry affordance', (tester) async {
    final repository = _FakeRepository(
      error: ApiException(404, 'Student not found.'),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    expect(find.text('Could not load this student.'), findsOneWidget);
    expect(find.text('Student not found.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('retrying after an error succeeds', (tester) async {
    final repository = _FakeRepository(
      error: ApiException(0, 'Could not reach the SchoolPulse server.'),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();
    expect(find.text('Could not load this student.'), findsOneWidget);

    repository.error = null;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.text('Could not load this student.'), findsNothing);
    expect(find.text('2026-10-04'), findsOneWidget);
  });

  testWidgets('shows an empty state for a range with no days', (tester) async {
    await tester.pumpWidget(
      _wrap(
        _FakeRepository(
          detail: _detail(records: const <AttendanceHistoryRecord>[], total: 0),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No days in this range.'), findsOneWidget);
  });

  testWidgets('paginates long ranges', (tester) async {
    final repository = _FakeRepository(detail: _detail(total: 45, pageSize: 20));
    await tester.pumpWidget(_wrap(repository, pageSize: 20));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Page 1 of 3'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await _tapNextPage(tester);

    expect(repository.lastPage, 2);
  });

  testWidgets('hides the pager when everything fits on one page', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Page 1 of 1'), findsNothing);
  });

  testWidgets('passes the school through to the API', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository, schoolId: 'school-9'));
    await tester.pumpAndSettle();

    expect(repository.lastSchoolId, 'school-9');
  });

  testWidgets('refresh reloads the history', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    final before = repository.calls;
    await tester.tap(find.byTooltip('Refresh'));
    await tester.pumpAndSettle();

    expect(repository.calls, greaterThan(before));
  });
}
