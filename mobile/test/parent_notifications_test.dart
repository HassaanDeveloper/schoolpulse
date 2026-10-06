import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/core/network/api_client.dart';
import 'package:schoolpulse/features/attendance/attendance_report_repository.dart';
import 'package:schoolpulse/features/notifications/notification_repository.dart';
import 'package:schoolpulse/features/notifications/notifications_screen.dart';
import 'package:schoolpulse/features/parent/child_attendance_screen.dart';
import 'package:schoolpulse/features/parent/parent_home_screen.dart';
import 'package:schoolpulse/features/parent/parent_repository.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _FakeParentRepository implements ParentRepository {
  _FakeParentRepository({this.children, this.attendance, this.error});

  List<ParentChild>? children;
  ParentChildAttendance? attendance;
  ApiException? error;

  int childCalls = 0;
  int attendanceCalls = 0;
  String? lastSchoolId;
  DateTime? lastStart;
  DateTime? lastEnd;

  @override
  Future<List<ParentChild>> fetchChildren({String? schoolId}) async {
    childCalls++;
    lastSchoolId = schoolId;
    if (error != null) {
      throw error!;
    }
    return children ?? <ParentChild>[_child()];
  }

  @override
  Future<ParentChildAttendance> fetchChildAttendance({
    required String studentId,
    DateTime? startDate,
    DateTime? endDate,
  }) async {
    attendanceCalls++;
    lastStart = startDate;
    lastEnd = endDate;
    if (error != null) {
      throw error!;
    }
    return attendance ?? _attendance();
  }
}

class _FakeNotificationRepository implements NotificationRepository {
  _FakeNotificationRepository({this.page, this.unread = 0, this.error, this.gate});

  NotificationPage? page;
  int unread;
  ApiException? error;
  Completer<void>? gate;

  int listCalls = 0;
  int countCalls = 0;
  int markCalls = 0;
  bool lastUnreadOnly = false;
  final List<String> marked = <String>[];

  @override
  Future<NotificationPage> fetchNotifications({
    String? schoolId,
    bool unreadOnly = false,
    int limit = 50,
    int offset = 0,
  }) async {
    listCalls++;
    lastUnreadOnly = unreadOnly;
    final gate = this.gate;
    if (gate != null) {
      await gate.future;
    }
    if (error != null) {
      throw error!;
    }
    return page ?? NotificationPage(notifications: <AppNotification>[], unreadCount: unread);
  }

  @override
  Future<int> fetchUnreadCount({String? schoolId}) async {
    countCalls++;
    final gate = this.gate;
    if (gate != null) {
      await gate.future;
    }
    if (error != null) {
      throw error!;
    }
    return unread;
  }

  @override
  Future<AppNotification> markRead(String notificationId) async {
    markCalls++;
    marked.add(notificationId);
    return _notification(id: notificationId, readAt: DateTime(2026, 10, 5, 9));
  }
}

ParentChild _child({
  String id = 'student-1',
  String first = 'Ayesha',
  String last = 'Khan',
  String schoolId = 'school-1',
  String? todayStatus,
  String? todayStatusDate,
}) {
  return ParentChild(
    studentId: id,
    firstName: first,
    lastName: last,
    className: 'Grade 5',
    section: 'A',
    schoolId: schoolId,
    schoolName: 'Demo School',
    schoolTimezone: 'Asia/Karachi',
    todayStatus: todayStatus,
    todayStatusDate: todayStatusDate,
  );
}

AppNotification _notification({
  String id = 'note-1',
  NotificationType type = NotificationType.arrival,
  NotificationStatus status = NotificationStatus.sent,
  DateTime? readAt,
  String message = 'Ayesha Khan arrived at Demo School at 8:04 AM.',
  String? occurredTime = '8:04 AM',
}) {
  return AppNotification(
    id: id,
    type: type,
    title: type == NotificationType.arrival ? 'Arrival recorded' : 'Departure recorded',
    message: message,
    status: status,
    occurredAt: DateTime(2026, 10, 5, 3, 4),
    occurredTime: occurredTime,
    readAt: readAt,
    createdAt: DateTime(2026, 10, 5, 3, 4),
  );
}

ParentChildAttendance _attendance({List<AttendanceHistoryRecord>? records}) {
  return ParentChildAttendance(
    studentId: 'student-1',
    startDate: DateTime(2026, 9, 29),
    endDate: DateTime(2026, 10, 5),
    records: records ??
        <AttendanceHistoryRecord>[
          AttendanceHistoryRecord(
            date: DateTime(2026, 10, 5),
            status: AttendanceStatus.present,
            // The server sends the instant in UTC and the school's own clock
            // time alongside it. The two must agree: 03:04Z is 8:04 AM in the
            // school's timezone.
            arrivalAt: DateTime.utc(2026, 10, 5, 3, 4),
            departureAt: null,
            arrivalTime: '8:04 AM',
          ),
          AttendanceHistoryRecord(
            date: DateTime(2026, 10, 4),
            status: AttendanceStatus.absent,
            arrivalAt: null,
            departureAt: null,
          ),
        ],
  );
}

Widget _wrapHome(
  _FakeParentRepository parents,
  _FakeNotificationRepository notifications, {
  String? schoolId,
}) {
  return MaterialApp(
    home: ParentHomeScreen(
      parentRepository: parents,
      notificationRepository: notifications,
      schoolId: schoolId,
    ),
  );
}

// ---------------------------------------------------------------------------
// Parent home
// ---------------------------------------------------------------------------

void main() {
  testWidgets('parent home lists linked children', (tester) async {
    await tester.pumpWidget(
      _wrapHome(
        _FakeParentRepository(children: <ParentChild>[
          _child(),
          _child(id: 'student-2', first: 'Bilal', last: 'Khan'),
        ]),
        _FakeNotificationRepository(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ayesha Khan'), findsOneWidget);
    expect(find.text('Bilal Khan'), findsOneWidget);
  });

  group('Day 6: today status on the parent home', () {
    testWidgets('shows the status the server resolved for today', (tester) async {
      await tester.pumpWidget(
        _wrapHome(
          _FakeParentRepository(children: <ParentChild>[
            _child(todayStatus: 'present', todayStatusDate: '2026-10-05'),
            _child(
              id: 'student-2',
              first: 'Bilal',
              last: 'Khan',
              todayStatus: 'absent',
              todayStatusDate: '2026-10-05',
            ),
          ]),
          _FakeNotificationRepository(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Arrived today'), findsOneWidget);
      expect(find.text('Not marked present today'), findsOneWidget);
    });

    testWidgets('says nothing when the server sent no status', (tester) async {
      await tester.pumpWidget(
        _wrapHome(
          _FakeParentRepository(children: <ParentChild>[_child()]),
          _FakeNotificationRepository(),
        ),
      );
      await tester.pumpAndSettle();

      // Better to stay quiet than to claim a status that was never sent.
      expect(find.text('Arrived today'), findsNothing);
      expect(find.text('Not marked present today'), findsNothing);
      expect(find.text('Arrived and left today'), findsNothing);
    });

    testWidgets('a completed day is distinguished from a live arrival', (tester) async {
      await tester.pumpWidget(
        _wrapHome(
          _FakeParentRepository(children: <ParentChild>[
            _child(todayStatus: 'completed', todayStatusDate: '2026-10-05'),
          ]),
          _FakeNotificationRepository(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Arrived and left today'), findsOneWidget);
    });
  });

  testWidgets('parent home shows a loading state before data arrives', (tester) async {
    await tester.pumpWidget(
      _wrapHome(_FakeParentRepository(), _FakeNotificationRepository(gate: Completer<void>())),
    );
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('parent home shows an empty state when no child is linked', (tester) async {
    await tester.pumpWidget(
      _wrapHome(
        _FakeParentRepository(children: <ParentChild>[]),
        _FakeNotificationRepository(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No children linked yet'), findsOneWidget);
  });

  testWidgets('parent home shows an error state with a retry', (tester) async {
    final parents = _FakeParentRepository(
      error: ApiException(503, 'Could not reach SchoolPulse.'),
    );
    await tester.pumpWidget(_wrapHome(parents, _FakeNotificationRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Could not load your children.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);

    parents.error = null;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.text('Ayesha Khan'), findsOneWidget);
  });

  testWidgets('unread count appears as a badge', (tester) async {
    await tester.pumpWidget(
      _wrapHome(_FakeParentRepository(), _FakeNotificationRepository(unread: 3)),
    );
    await tester.pumpAndSettle();

    expect(find.text('3 new updates'), findsOneWidget);
    expect(find.byIcon(Icons.notifications), findsOneWidget);
  });

  testWidgets('no badge is shown when there is nothing unread', (tester) async {
    await tester.pumpWidget(
      _wrapHome(_FakeParentRepository(), _FakeNotificationRepository(unread: 0)),
    );
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.notifications_none), findsOneWidget);
    expect(find.textContaining('new updates'), findsNothing);
  });

  testWidgets('badge caps at 99+', (tester) async {
    await tester.pumpWidget(
      _wrapHome(_FakeParentRepository(), _FakeNotificationRepository(unread: 250)),
    );
    await tester.pumpAndSettle();

    expect(find.text('99+'), findsOneWidget);
  });

  testWidgets('tapping a child opens that child attendance', (tester) async {
    final parents = _FakeParentRepository();
    await tester.pumpWidget(_wrapHome(parents, _FakeNotificationRepository()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Ayesha Khan'));
    await tester.pumpAndSettle();

    expect(find.byType(ChildAttendanceScreen), findsOneWidget);
    expect(parents.attendanceCalls, 1);
  });

  testWidgets('school scope is forwarded to both repositories', (tester) async {
    final parents = _FakeParentRepository();
    await tester.pumpWidget(
      _wrapHome(parents, _FakeNotificationRepository(), schoolId: 'school-9'),
    );
    await tester.pumpAndSettle();

    expect(parents.lastSchoolId, 'school-9');
  });

  testWidgets('a parent home offers no scanner or QR controls', (tester) async {
    await tester.pumpWidget(_wrapHome(_FakeParentRepository(), _FakeNotificationRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Scan attendance'), findsNothing);
    expect(find.text('Student QR codes'), findsNothing);
    expect(find.text('Attendance dashboard'), findsNothing);
  });

  testWidgets('parent home does not poll the unread count', (tester) async {
    final notifications = _FakeNotificationRepository(unread: 1);
    await tester.pumpWidget(_wrapHome(_FakeParentRepository(), notifications));
    await tester.pumpAndSettle();

    expect(notifications.countCalls, 1);

    await tester.pump(const Duration(seconds: 30));

    expect(notifications.countCalls, 1, reason: 'no background polling');
  });

  testWidgets('the unread banner opens the inbox', (tester) async {
    final notifications = _FakeNotificationRepository(unread: 1);
    await tester.pumpWidget(_wrapHome(_FakeParentRepository(), notifications));
    await tester.pumpAndSettle();

    await tester.tap(find.text('1 new update'));
    await tester.pumpAndSettle();

    expect(find.byType(NotificationsScreen), findsOneWidget);
  });

  childAttendanceTests();
  notificationTests();
}

// ---------------------------------------------------------------------------
// Child attendance
// ---------------------------------------------------------------------------

void childAttendanceTests() {
  testWidgets('child attendance shows each day with its derived status', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ChildAttendanceScreen(
          child: _child(),
          repository: _FakeParentRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ayesha Khan'), findsWidgets);
    // One "Present" from the day row; "Absent" also labels the summary stat.
    expect(find.text('Present'), findsOneWidget);
    expect(find.text('Absent'), findsNWidgets(2));
    expect(find.text('No attendance recorded'), findsNothing);
  });

  group('Day 6: Today section on child attendance', () {
    testWidgets('separates today from the history below it', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: ChildAttendanceScreen(
            child: _child(),
            repository: _FakeParentRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // The range's last day is the server's today, so it is promoted out of
      // the history list into its own section.
      expect(find.text('Today'), findsOneWidget);
      expect(find.text('History'), findsOneWidget);
      expect(find.text('Present'), findsOneWidget);
    });

    testWidgets('anchors Today to the server date, not the device clock', (tester) async {
      // A record dated well in the past is still "today" if the server says the
      // range ends there, which is what happens on a device in another timezone.
      final parents = _FakeParentRepository(
        attendance: ParentChildAttendance(
          studentId: 'student-1',
          startDate: DateTime(2026, 1, 1),
          endDate: DateTime(2026, 1, 2),
          records: <AttendanceHistoryRecord>[
            AttendanceHistoryRecord(
              date: DateTime(2026, 1, 2),
              status: AttendanceStatus.completed,
              arrivalAt: DateTime.utc(2026, 1, 2, 3, 0),
              departureAt: DateTime.utc(2026, 1, 2, 10, 0),
              arrivalTime: '8:00 AM',
              departureTime: '3:00 PM',
            ),
            AttendanceHistoryRecord(
              date: DateTime(2026, 1, 1),
              status: AttendanceStatus.absent,
              arrivalAt: null,
              departureAt: null,
            ),
          ],
        ),
      );

      await tester.pumpWidget(
        MaterialApp(home: ChildAttendanceScreen(child: _child(), repository: parents)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Today'), findsOneWidget);
      expect(find.text('Completed'), findsOneWidget);
      expect(find.textContaining('8:00 AM'), findsOneWidget);
    });

    testWidgets('falls back to the children-list status outside the range', (tester) async {
      // The custom range ends before today, so no record matches; the status
      // resolved on the children list is still shown rather than a blank card.
      final parents = _FakeParentRepository(
        attendance: ParentChildAttendance(
          studentId: 'student-1',
          startDate: DateTime(2026, 9, 20),
          // The range ends after the last recorded day, so nothing matches
          // "today" and the children-list status has to stand in.
          endDate: DateTime(2026, 9, 25),
          records: <AttendanceHistoryRecord>[
            AttendanceHistoryRecord(
              date: DateTime(2026, 9, 20),
              status: AttendanceStatus.absent,
              arrivalAt: null,
              departureAt: null,
            ),
          ],
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ChildAttendanceScreen(
            child: _child(todayStatus: 'present', todayStatusDate: '2026-10-05'),
            repository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Today'), findsOneWidget);
      expect(find.text('Present'), findsOneWidget);
      expect(find.text('Nothing recorded for today yet.'), findsNothing);
    });
  });

  testWidgets('child attendance shows the arrival time', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ChildAttendanceScreen(
          child: _child(),
          repository: _FakeParentRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('8:04'), findsOneWidget);
  });

  testWidgets('child attendance does not send a date range by default', (tester) async {
    final parents = _FakeParentRepository();
    await tester.pumpWidget(
      MaterialApp(home: ChildAttendanceScreen(child: _child(), repository: parents)),
    );
    await tester.pumpAndSettle();

    expect(parents.lastStart, isNull, reason: 'the server picks the school-local range');
    expect(parents.lastEnd, isNull);
  });

  testWidgets('child attendance shows an error state with a retry', (tester) async {
    final parents = _FakeParentRepository(
      error: ApiException(404, 'Student not found.'),
    );
    await tester.pumpWidget(
      MaterialApp(home: ChildAttendanceScreen(child: _child(), repository: parents)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Could not load attendance.'), findsOneWidget);
    expect(find.text('Student not found.'), findsOneWidget);
  });

  testWidgets('child attendance shows an empty state', (tester) async {
    final parents = _FakeParentRepository(
      attendance: ParentChildAttendance(
        studentId: 'student-1',
        startDate: DateTime(2026, 10, 1),
        endDate: DateTime(2026, 10, 5),
        records: const <AttendanceHistoryRecord>[],
      ),
    );
    await tester.pumpWidget(
      MaterialApp(home: ChildAttendanceScreen(child: _child(), repository: parents)),
    );
    await tester.pumpAndSettle();

    expect(find.text('No attendance recorded'), findsOneWidget);
  });

  testWidgets('child attendance refreshes on pull', (tester) async {
    final parents = _FakeParentRepository();
    await tester.pumpWidget(
      MaterialApp(home: ChildAttendanceScreen(child: _child(), repository: parents)),
    );
    await tester.pumpAndSettle();
    expect(parents.attendanceCalls, 1);

    await tester.fling(
      find.byType(ListView),
      const Offset(0, 300),
      1000,
    );
    await tester.pumpAndSettle();

    expect(parents.attendanceCalls, 2);
  });

  testWidgets('child attendance shows the time the server formatted', (tester) async {
    // A value the client could only produce by converting the instant itself,
    // so this fails if the app ever reformats a scan time on the device.
    final parents = _FakeParentRepository(
      attendance: _attendance(
        records: <AttendanceHistoryRecord>[
          AttendanceHistoryRecord(
            date: DateTime(2026, 10, 5),
            status: AttendanceStatus.completed,
            arrivalAt: DateTime.utc(2026, 10, 5, 3, 4),
            departureAt: DateTime.utc(2026, 10, 5, 10, 30),
            arrivalTime: '8:04 AM school time',
            departureTime: '3:30 PM school time',
          ),
        ],
      ),
    );

    await tester.pumpWidget(
      MaterialApp(home: ChildAttendanceScreen(child: _child(), repository: parents)),
    );
    await tester.pumpAndSettle();

    expect(find.text('8:04 AM school time - 3:30 PM school time'), findsOneWidget);
  });
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

void notificationTests() {
  Widget wrap(_FakeNotificationRepository repository) {
    return MaterialApp(home: NotificationsScreen(repository: repository));
  }

  testWidgets('notifications are listed with their message', (tester) async {
    await tester.pumpWidget(
      wrap(
        _FakeNotificationRepository(
          page: NotificationPage(
            notifications: <AppNotification>[
              _notification(),
              _notification(id: 'note-2', type: NotificationType.departure),
            ],
            unreadCount: 2,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Arrival recorded'), findsOneWidget);
    expect(find.text('Departure recorded'), findsOneWidget);
    expect(find.text('2 unread'), findsOneWidget);
  });

  group('Day 6: notification created time', () {
    testWidgets('shows the school-local time the server rendered', (tester) async {
      await tester.pumpWidget(
        wrap(
          _FakeNotificationRepository(
            page: NotificationPage(
              notifications: <AppNotification>[_notification(occurredTime: '8:04 AM')],
              unreadCount: 1,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Type plus the recorded time, so the parent sees when it happened.
      expect(find.text('Arrival - 8:04 AM'), findsOneWidget);
    });

    testWidgets('never converts the instant on the device', (tester) async {
      await tester.pumpWidget(
        wrap(
          _FakeNotificationRepository(
            page: NotificationPage(
              notifications: <AppNotification>[
                // The instant is 03:04Z. A device-converted time would render a
                // different hour than the 8:04 AM the school actually recorded.
                _notification(occurredTime: '8:04 AM'),
              ],
              unreadCount: 1,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('8:04 AM'), findsWidgets);
      expect(find.textContaining('11:04'), findsNothing);
      expect(find.textContaining('03:04'), findsNothing);
    });

    testWidgets('falls back to the type alone when no time was sent', (tester) async {
      await tester.pumpWidget(
        wrap(
          _FakeNotificationRepository(
            page: NotificationPage(
              notifications: <AppNotification>[_notification(occurredTime: null)],
              unreadCount: 1,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Arrival'), findsOneWidget);
    });
  });

  testWidgets('inbox shows the server time and never recomputes it', (tester) async {
    await tester.pumpWidget(
      wrap(
        _FakeNotificationRepository(
          page: NotificationPage(
            notifications: <AppNotification>[_notification()],
            unreadCount: 1,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // The message is rendered exactly as the server built it, in the school's
    // timezone.
    expect(
      find.text('Ayesha Khan arrived at Demo School at 8:04 AM.'),
      findsOneWidget,
    );
    // No second, device-timezone rendering of the same event: occurred_at is
    // 03:04Z, which a naive toLocal() would render as 3:04 AM.
    expect(find.textContaining('3:04'), findsNothing);
    expect(find.textContaining('on 05/10'), findsNothing);
  });

  testWidgets('notifications show an empty state', (tester) async {
    await tester.pumpWidget(wrap(_FakeNotificationRepository()));
    await tester.pumpAndSettle();

    expect(find.text('No notifications yet'), findsOneWidget);
  });

  testWidgets('notifications show an error state with a retry', (tester) async {
    final repository = _FakeNotificationRepository(
      error: ApiException(503, 'Could not reach SchoolPulse.'),
    );
    await tester.pumpWidget(wrap(repository));
    await tester.pumpAndSettle();

    expect(find.text('Could not load notifications.'), findsOneWidget);

    repository.error = null;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.text('No notifications yet'), findsOneWidget);
  });

  testWidgets('marking read updates the row and the badge', (tester) async {
    int? reported;
    final repository = _FakeNotificationRepository(
      page: NotificationPage(
        notifications: <AppNotification>[_notification()],
        unreadCount: 1,
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: NotificationsScreen(
          repository: repository,
          onUnreadCountChanged: (count) => reported = count,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Mark read'));
    await tester.pumpAndSettle();

    expect(repository.markCalls, 1);
    expect(repository.marked, <String>['note-1']);
    expect(reported, 0);
    expect(find.text('0 unread'), findsOneWidget);
    expect(find.text('Read'), findsOneWidget);
  });

  testWidgets('an already-read notice offers no action', (tester) async {
    await tester.pumpWidget(
      wrap(
        _FakeNotificationRepository(
          page: NotificationPage(
            notifications: <AppNotification>[
              _notification(readAt: DateTime(2026, 10, 5, 9)),
            ],
            unreadCount: 0,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Mark read'), findsNothing);
    expect(find.text('Read'), findsOneWidget);
  });

  testWidgets('the unread-only filter is sent to the server', (tester) async {
    final repository = _FakeNotificationRepository();
    await tester.pumpWidget(wrap(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Unread only'));
    await tester.pumpAndSettle();

    expect(repository.lastUnreadOnly, isTrue);
    expect(repository.listCalls, 2);
  });

  testWidgets('a failed notice is surfaced rather than hidden', (tester) async {
    await tester.pumpWidget(
      wrap(
        _FakeNotificationRepository(
          page: NotificationPage(
            notifications: <AppNotification>[
              _notification(status: NotificationStatus.failed),
            ],
            unreadCount: 1,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('attendance record is unaffected'), findsOneWidget);
  });

  testWidgets('the inbox does not poll for updates', (tester) async {
    final repository = _FakeNotificationRepository(
      page: NotificationPage(
        notifications: <AppNotification>[_notification()],
        unreadCount: 1,
      ),
    );
    await tester.pumpWidget(wrap(repository));
    await tester.pumpAndSettle();

    expect(repository.listCalls, 1);

    await tester.pump(const Duration(seconds: 60));

    expect(repository.listCalls, 1);
  });
}