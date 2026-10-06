import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/core/network/api_client.dart';
import 'package:schoolpulse/features/attendance/attendance_dashboard_screen.dart';
import 'package:schoolpulse/features/attendance/attendance_report_repository.dart';

/// Test double so the dashboard can be driven without HTTP.
class _FakeRepository implements AttendanceReportRepository {
  _FakeRepository({
    this.todayPage,
    this.classes = const <AttendanceClassOption>[],
    this.summaryError,
    this.gate,
  });

  TodayAttendancePage? todayPage;
  List<AttendanceClassOption> classes;
  ApiException? summaryError;

  /// When set, the fetch methods wait on this before answering, so the loading
  /// state can be observed.
  Completer<void>? gate;

  int summaryCalls = 0;
  int todayCalls = 0;
  int classCalls = 0;

  String? lastSchoolId;
  String? lastClassId;
  String? lastSearch;
  AttendanceStatus? lastStatus;
  int lastPage = 1;

  Future<void> _wait() async {
    final gate = this.gate;
    if (gate != null) {
      await gate.future;
    }
  }

  @override
  Future<AttendanceSummary> fetchSummary({String? schoolId, String? classId}) async {
    summaryCalls++;
    lastSchoolId = schoolId;
    lastClassId = classId;
    await _wait();
    if (summaryError != null) {
      throw summaryError!;
    }
    return _summary();
  }

  @override
  Future<TodayAttendancePage> fetchToday({
    String? schoolId,
    String? classId,
    AttendanceStatus? status,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) async {
    todayCalls++;
    lastSearch = search;
    lastStatus = status;
    lastPage = page;
    await _wait();
    return todayPage ?? _page(page: page, pageSize: pageSize);
  }

  @override
  Future<List<AttendanceClassOption>> fetchFilterClasses({String? schoolId}) async {
    classCalls++;
    return classes;
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
  Future<StudentAttendanceDetail> fetchStudentDetail({
    required String studentId,
    String? schoolId,
    DateTime? startDate,
    DateTime? endDate,
    int page = 1,
    int pageSize = 20,
  }) {
    throw UnimplementedError();
  }
}

AttendanceSummary _summary({int total = 30}) {
  return AttendanceSummary(
    date: DateTime(2026, 10, 4),
    schoolId: 'school-1',
    schoolName: 'Crescent Model School',
    classId: null,
    totalStudents: total,
    absent: 10,
    present: 15,
    completed: 5,
  );
}

TodayAttendanceItem _item(
  String name, {
  AttendanceStatus status = AttendanceStatus.present,
  String admission = 'ADM-001',
}) {
  return TodayAttendanceItem(
    studentId: 'student-$name',
    studentName: name,
    admissionNumber: admission,
    classId: 'class-1',
    className: 'Grade 5',
    section: 'A',
    status: status,
    arrivalAt: status == AttendanceStatus.absent ? null : DateTime(2026, 10, 4, 9, 15),
    departureAt: status == AttendanceStatus.completed ? DateTime(2026, 10, 4, 15, 5) : null,
  );
}

TodayAttendancePage _page({
  List<TodayAttendanceItem>? items,
  int total = 30,
  int page = 1,
  int pageSize = 20,
}) {
  return TodayAttendancePage(
    date: DateTime(2026, 10, 4),
    schoolId: 'school-1',
    schoolName: 'Crescent Model School',
    items: items ??
        <TodayAttendanceItem>[
          _item('Ayesha Khan'),
          _item('Bilal Ahmed', status: AttendanceStatus.completed, admission: 'ADM-002'),
          _item('Chaudhry Noor', status: AttendanceStatus.absent, admission: 'ADM-003'),
        ],
    total: total,
    page: page,
    pageSize: pageSize,
  );
}

Widget _wrap(AttendanceReportRepository repository, {String? schoolId, int pageSize = 20}) {
  return MaterialApp(
    home: AttendanceDashboardScreen(
      repository: repository,
      schoolId: schoolId,
      pageSize: pageSize,
    ),
  );
}

void main() {
  testWidgets('shows a loading indicator before data arrives', (tester) async {
    final repository = _FakeRepository(gate: Completer<void>());
    await tester.pumpWidget(_wrap(repository));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Crescent Model School'), findsNothing);

    // Releasing the request swaps the spinner for the dashboard.
    repository.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('Crescent Model School'), findsOneWidget);
  });

  testWidgets('renders the summary counts for the school day', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Crescent Model School'), findsOneWidget);
    expect(find.textContaining('2026-10-04'), findsOneWidget);
    expect(find.text('15'), findsOneWidget); // present
    expect(find.text('5'), findsOneWidget); // completed
    expect(find.text('10'), findsOneWidget); // absent
    expect(find.text('Present'), findsOneWidget);
    expect(find.text('Completed'), findsOneWidget);
    expect(find.text('Absent'), findsOneWidget);
  });

  testWidgets('lists students with their derived status', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Ayesha Khan'), findsOneWidget);
    expect(find.text('Bilal Ahmed'), findsOneWidget);
    expect(find.text('Chaudhry Noor'), findsOneWidget);
    expect(find.text('30 students'), findsOneWidget);
  });

  testWidgets('shows arrival and departure times for a completed day', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.textContaining('Arrived 09:15 - left 15:05'), findsOneWidget);
  });

  testWidgets('says so when a student has not been scanned', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    expect(find.textContaining('No scan yet today'), findsOneWidget);
  });

  testWidgets('passes the school through to the API', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository, schoolId: 'school-9'));
    await tester.pumpAndSettle();

    expect(repository.lastSchoolId, 'school-9');
  });

  testWidgets('surfaces an API error with a retry affordance', (tester) async {
    final repository = _FakeRepository(
      summaryError: ApiException(403, 'You do not have access to any school.'),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    expect(find.text('Could not load attendance.'), findsOneWidget);
    expect(find.text('You do not have access to any school.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('retrying after an error succeeds', (tester) async {
    final repository = _FakeRepository(
      summaryError: ApiException(0, 'Could not reach the SchoolPulse server.'),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();
    expect(find.text('Could not load attendance.'), findsOneWidget);

    repository.summaryError = null;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.text('Crescent Model School'), findsOneWidget);
  });

  testWidgets('shows an empty state when the school has no students', (tester) async {
    final repository = _FakeRepository(
      todayPage: _page(items: const <TodayAttendanceItem>[], total: 0),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    expect(find.text('No students to show yet.'), findsOneWidget);
  });

  testWidgets('search filters the list through the API', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'Ayesha');
    // The search box debounces before hitting the API.
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(repository.lastSearch, 'Ayesha');
    expect(repository.lastPage, 1);
  });

  testWidgets('filters by status through the filter panel', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ChoiceChip, 'Present'));
    await tester.pumpAndSettle();

    expect(repository.lastStatus, AttendanceStatus.present);
  });

  testWidgets('filters by class when classes are available', (tester) async {
    final repository = _FakeRepository(
      classes: const <AttendanceClassOption>[
        AttendanceClassOption(id: 'class-1', name: 'Grade 5', section: 'A'),
        AttendanceClassOption(id: 'class-2', name: 'Grade 6', section: 'B'),
      ],
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ChoiceChip, 'Grade 6 - B'));
    await tester.pumpAndSettle();

    expect(repository.lastClassId, 'class-2');
    expect(repository.lastPage, 1);
  });

  testWidgets('an empty class list does not break the filter panel', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();

    expect(find.text('No classes available to filter.'), findsOneWidget);
  });

  testWidgets('an active filter offers to clear every filter', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ChoiceChip, 'Absent'));
    await tester.pumpAndSettle();

    expect(find.text('Clear filters'), findsOneWidget);

    await tester.tap(find.text('Clear filters'));
    await tester.pumpAndSettle();

    expect(repository.lastStatus, isNull);
    expect(repository.lastSearch, isEmpty);
    expect(find.text('Clear filters'), findsNothing);
  });

  testWidgets('an empty filtered result explains itself', (tester) async {
    final repository = _FakeRepository(
      todayPage: _page(items: const <TodayAttendanceItem>[], total: 0),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Filters'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ChoiceChip, 'Completed'));
    await tester.pumpAndSettle();

    expect(find.text('No students match these filters.'), findsOneWidget);
  });

  testWidgets('paginates when the result set spans several pages', (tester) async {
    final repository = _FakeRepository(todayPage: _page(total: 45, pageSize: 20));
    await tester.pumpWidget(_wrap(repository, pageSize: 20));
    await tester.pumpAndSettle();

    // The pager sits below the lazily-built cards, so scroll it into view.
    await tester.scrollUntilVisible(
      find.text('Page 1 of 3'),
      200,
      scrollable: find.byType(Scrollable).first,
    );

    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();

    expect(repository.lastPage, 2);
  });

  testWidgets('disables the previous control on the first page', (tester) async {
    await tester.pumpWidget(
      _wrap(_FakeRepository(todayPage: _page(total: 45, pageSize: 20)), pageSize: 20),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Page 1 of 3'),
      200,
      scrollable: find.byType(Scrollable).first,
    );

    // `TextButton.icon` builds a private subclass, so match by `is` rather than
    // by exact runtime type.
    final previous = find.ancestor(
      of: find.text('Previous'),
      matching: find.byWidgetPredicate((widget) => widget is TextButton),
    );

    expect(tester.widget<TextButton>(previous).onPressed, isNull);
  });

  testWidgets('hides the pager for a single page of results', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository(todayPage: _page(total: 2))));
    await tester.pumpAndSettle();

    expect(find.text('Page 1 of 1'), findsNothing);
  });

  testWidgets('refresh reloads the summary and the list', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    final beforeSummary = repository.summaryCalls;
    final beforeToday = repository.todayCalls;

    await tester.tap(find.byTooltip('Refresh'));
    await tester.pumpAndSettle();

    expect(repository.summaryCalls, greaterThan(beforeSummary));
    expect(repository.todayCalls, greaterThan(beforeToday));
  });

  testWidgets('pull to refresh reloads the dashboard', (tester) async {
    final repository = _FakeRepository();
    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    final before = repository.todayCalls;
    await tester.fling(
      find.byType(ListView),
      const Offset(0, 300),
      1000,
    );
    await tester.pumpAndSettle();

    expect(repository.todayCalls, greaterThan(before));
  });

  testWidgets('does not leak credentials or scan internals', (tester) async {
    await tester.pumpWidget(_wrap(_FakeRepository()));
    await tester.pumpAndSettle();

    // Nothing on screen refers to the opaque QR credential.
    expect(find.textContaining('credential'), findsNothing);
    expect(find.textContaining('token'), findsNothing);
  });
}
