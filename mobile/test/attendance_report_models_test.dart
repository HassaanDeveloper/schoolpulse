import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/features/attendance/attendance_report_repository.dart';

void main() {
  group('AttendanceStatus', () {
    test('parses the three server statuses', () {
      expect(AttendanceStatus.parse('absent'), AttendanceStatus.absent);
      expect(AttendanceStatus.parse('present'), AttendanceStatus.present);
      expect(AttendanceStatus.parse('completed'), AttendanceStatus.completed);
    });

    test('falls back to unknown rather than throwing', () {
      expect(AttendanceStatus.parse('late'), AttendanceStatus.unknown);
      expect(AttendanceStatus.parse(null), AttendanceStatus.unknown);
    });

    test('sends lowercase wire values', () {
      expect(AttendanceStatus.absent.apiValue, 'absent');
      expect(AttendanceStatus.present.apiValue, 'present');
      expect(AttendanceStatus.completed.apiValue, 'completed');
    });

    test('treats present and completed as on site', () {
      expect(AttendanceStatus.present.isOnSite, isTrue);
      expect(AttendanceStatus.completed.isOnSite, isTrue);
      expect(AttendanceStatus.absent.isOnSite, isFalse);
    });

    test('has a label for every value', () {
      expect(AttendanceStatus.absent.label, 'Absent');
      expect(AttendanceStatus.present.label, 'Present');
      expect(AttendanceStatus.completed.label, 'Completed');
      expect(AttendanceStatus.unknown.label, 'Unknown');
    });
  });

  group('AttendanceSummary.fromJson', () {
    test('parses counts that reconcile with the total', () {
      final summary = AttendanceSummary.fromJson(<String, dynamic>{
        'date': '2026-10-04',
        'school_id': 'school-1',
        'school_name': 'Crescent Model',
        'class_id': null,
        'total_students': 30,
        'absent': 10,
        'present': 15,
        'completed': 5,
      });

      expect(summary.schoolName, 'Crescent Model');
      expect(summary.totalStudents, 30);
      expect(summary.absent + summary.present + summary.completed, 30);
      expect(summary.onSite, 20);
      expect(summary.date, DateTime(2026, 10, 4));
      expect(summary.classId, isNull);
    });

    test('survives missing counts', () {
      final summary = AttendanceSummary.fromJson(<String, dynamic>{
        'school_id': 'school-1',
      });

      expect(summary.totalStudents, 0);
      expect(summary.present, 0);
      expect(summary.date, isNull);
    });
  });

  group('TodayAttendancePage.fromJson', () {
    Map<String, dynamic> pageJson(List<Map<String, dynamic>> items, {int total = 2}) {
      return <String, dynamic>{
        'date': '2026-10-04',
        'school_id': 'school-1',
        'school_name': 'Crescent Model',
        'items': items,
        'total': total,
        'page': 1,
        'page_size': 2,
      };
    }

    Map<String, dynamic> itemJson(String name, String status) {
      return <String, dynamic>{
        'student_id': 'student-$name',
        'student_name': name,
        'admission_number': 'ADM-$name',
        'class_id': 'class-1',
        'class_name': 'Grade 5',
        'section': 'A',
        'status': status,
        'arrival_at': status == 'absent' ? null : '2026-10-04T03:30:00Z',
        'departure_at': status == 'completed' ? '2026-10-04T10:00:00Z' : null,
      };
    }

    test('parses items with derived status and timestamps', () {
      final page = TodayAttendancePage.fromJson(
        pageJson(<Map<String, dynamic>>[
          itemJson('Ayesha', 'present'),
          itemJson('Bilal', 'completed'),
        ]),
      );

      expect(page.items, hasLength(2));
      expect(page.items.first.status, AttendanceStatus.present);
      expect(page.items.first.arrivalAt, isNotNull);
      expect(page.items.first.departureAt, isNull);
      expect(page.items.last.status, AttendanceStatus.completed);
      expect(page.items.last.departureAt, isNotNull);
    });

    test('renders an absent row with no timestamps', () {
      final page = TodayAttendancePage.fromJson(
        pageJson(<Map<String, dynamic>>[itemJson('Ayesha', 'absent')], total: 1),
      );

      expect(page.items.single.status, AttendanceStatus.absent);
      expect(page.items.single.arrivalAt, isNull);
      expect(page.items.single.departureAt, isNull);
    });

    test('handles a malformed status without crashing', () {
      final page = TodayAttendancePage.fromJson(
        pageJson(<Map<String, dynamic>>[itemJson('Ayesha', 'tardy')]),
      );

      expect(page.items.single.status, AttendanceStatus.unknown);
    });

    test('derives the class label from the section', () {
      final page = TodayAttendancePage.fromJson(
        pageJson(<Map<String, dynamic>>[itemJson('Ayesha', 'present')]),
      );

      expect(page.items.single.classLabel, 'Grade 5 - A');
    });

    test('omits an absent section from the class label', () {
      final json = itemJson('Ayesha', 'present')..['section'] = null;
      final page = TodayAttendancePage.fromJson(pageJson(<Map<String, dynamic>>[json]));

      expect(page.items.single.classLabel, 'Grade 5');
    });

    test('computes pagination from the unpaginated total', () {
      final json = pageJson(<Map<String, dynamic>>[itemJson('Ayesha', 'present')], total: 5)
        ..['page_size'] = 2;

      final page = TodayAttendancePage.fromJson(json);

      expect(page.pageCount, 3);
      expect(page.hasNextPage, isTrue);
      expect(page.hasPreviousPage, isFalse);
    });

    test('tolerates a missing item list', () {
      final page = TodayAttendancePage.fromJson(<String, dynamic>{'total': 0});

      expect(page.items, isEmpty);
      expect(page.pageSize, 20);
    });
  });

  group('AttendanceHistoryRecord.fromJson', () {
    test('parses an absent day with no timestamps', () {
      final record = AttendanceHistoryRecord.fromJson(<String, dynamic>{
        'date': '2026-10-02',
        'status': 'absent',
        'arrival_at': null,
        'departure_at': null,
      });

      expect(record.date, DateTime(2026, 10, 2));
      expect(record.status, AttendanceStatus.absent);
      expect(record.arrivalAt, isNull);
    });

    test('converts instants to local time', () {
      final record = AttendanceHistoryRecord.fromJson(<String, dynamic>{
        'date': '2026-10-03',
        'status': 'completed',
        'arrival_at': '2026-10-03T03:30:00Z',
        'departure_at': '2026-10-03T10:00:00Z',
      });

      expect(record.arrivalAt!.isUtc, isFalse);
      expect(record.departureAt!.isAfter(record.arrivalAt!), isTrue);
    });
  });

  group('AttendanceHistoryPage.fromJson', () {
    test('parses the range echoed by the server', () {
      final page = AttendanceHistoryPage.fromJson(<String, dynamic>{
        'student_id': 'student-1',
        'student_name': 'Ayesha Khan',
        'start_date': '2026-09-28',
        'end_date': '2026-10-04',
        'items': <Map<String, dynamic>>[
          <String, dynamic>{'date': '2026-10-04', 'status': 'present'},
        ],
        'total': 7,
        'page': 1,
        'page_size': 20,
      });

      expect(page.studentName, 'Ayesha Khan');
      expect(page.startDate, DateTime(2026, 9, 28));
      expect(page.endDate, DateTime(2026, 10, 4));
      expect(page.total, 7);
      expect(page.pageCount, 1);
      expect(page.hasNextPage, isFalse);
    });
  });

  group('StudentAttendanceSummary', () {
    test('adds present and completed into days on site', () {
      final summary = StudentAttendanceSummary.fromJson(<String, dynamic>{
        'total_days': 10,
        'present_days': 4,
        'absent_days': 3,
        'completed_days': 3,
      });

      expect(summary.daysOnSite, 7);
      expect(summary.attendanceRate, closeTo(0.7, 0.0001));
      expect(
        summary.presentDays + summary.absentDays + summary.completedDays,
        summary.totalDays,
      );
    });

    test('reports a zero rate for an empty range instead of dividing by zero', () {
      final summary = StudentAttendanceSummary.fromJson(<String, dynamic>{});

      expect(summary.totalDays, 0);
      expect(summary.attendanceRate, 0);
    });
  });

  group('StudentAttendanceDetail.fromJson', () {
    test('parses the student, records and summary together', () {
      final detail = StudentAttendanceDetail.fromJson(<String, dynamic>{
        'student': <String, dynamic>{
          'id': 'student-1',
          'name': 'Ayesha Khan',
          'admission_number': 'ADM-001',
          'class_name': 'Grade 5',
          'section': 'A',
        },
        'start_date': '2026-10-01',
        'end_date': '2026-10-05',
        'records': <Map<String, dynamic>>[
          <String, dynamic>{'date': '2026-10-05', 'status': 'absent'},
          <String, dynamic>{'date': '2026-10-04', 'status': 'present'},
        ],
        'summary': <String, dynamic>{
          'total_days': 5,
          'present_days': 1,
          'absent_days': 3,
          'completed_days': 1,
        },
        'total': 5,
        'page': 1,
        'page_size': 2,
      });

      expect(detail.student.name, 'Ayesha Khan');
      expect(detail.student.classLabel, 'Grade 5 - A');
      expect(detail.records, hasLength(2));
      // The summary counts the whole range, not just the page.
      expect(detail.total, 5);
      expect(detail.summary.totalDays, 5);
      expect(detail.pageCount, 3);
      expect(detail.hasNextPage, isTrue);
    });

    test('survives a response missing the student and summary blocks', () {
      final detail = StudentAttendanceDetail.fromJson(<String, dynamic>{});

      expect(detail.student.name, '');
      expect(detail.records, isEmpty);
      expect(detail.summary.totalDays, 0);
    });
  });

  group('AttendanceClassOption.fromJson', () {
    test('builds a label from the section', () {
      final option = AttendanceClassOption.fromJson(<String, dynamic>{
        'id': 'class-1',
        'name': 'Grade 5',
        'section': 'B',
      });

      expect(option.label, 'Grade 5 - B');
    });

    test('uses the name alone when there is no section', () {
      final option = AttendanceClassOption.fromJson(<String, dynamic>{
        'id': 'class-1',
        'name': 'Grade 5',
        'section': null,
      });

      expect(option.label, 'Grade 5');
    });
  });

  group('formatDateOnly', () {
    test('zero pads month and day', () {
      expect(formatDateOnly(DateTime(2026, 1, 5)), '2026-01-05');
      expect(formatDateOnly(DateTime(2026, 12, 31)), '2026-12-31');
    });
  });

  group('parseDateOnly', () {
    test('rejects empty and non-string values', () {
      expect(parseDateOnly(null), isNull);
      expect(parseDateOnly(''), isNull);
      expect(parseDateOnly(20261004), isNull);
    });

    test('parses a date-only string', () {
      expect(parseDateOnly('2026-10-04'), DateTime(2026, 10, 4));
    });
  });

  group('parseList', () {
    test('ignores entries that are not objects', () {
      final items = parseList(
        <dynamic>[
          <String, dynamic>{'id': 'a'},
          'garbage',
          null,
          <String, dynamic>{'id': 'b'},
        ],
        AttendanceClassOption.fromJson,
      );

      expect(items.map((i) => i.id), <String>['a', 'b']);
    });

    test('returns empty for a missing list', () {
      expect(parseList(null, AttendanceClassOption.fromJson), isEmpty);
    });
  });
}
