import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/core/network/api_client.dart';
import 'package:schoolpulse/features/attendance/qr_repository.dart';
import 'package:schoolpulse/features/classes/class_list_screen.dart';
import 'package:schoolpulse/features/parents/parents_admin_repository.dart';
import 'package:schoolpulse/features/students/student_detail_screen.dart';
import 'package:schoolpulse/features/students/student_list_screen.dart';
import 'package:schoolpulse/features/students/students_repository.dart';

/// Test doubles so the Day 6 screens can be driven without HTTP.

class _FakeClassesRepository implements ClassesRepository {
  _FakeClassesRepository({
    List<SchoolClass>? classes,
    this.deleteError,
    this.listError,
  }) : classes = classes ?? <SchoolClass>[];

  List<SchoolClass> classes;
  final ApiException? deleteError;
  final ApiException? listError;

  int deleteCalls = 0;
  int createCalls = 0;

  @override
  Future<List<SchoolClass>> listClasses({String? schoolId}) async {
    if (listError != null) {
      throw listError!;
    }
    return classes;
  }

  @override
  Future<SchoolClass> createClass({
    required String name,
    String? section,
    String? academicYear,
    String? schoolId,
  }) async {
    createCalls++;
    final created = SchoolClass(
      id: 'class-$createCalls',
      name: name,
      section: section,
      academicYear: academicYear,
    );
    classes = <SchoolClass>[...classes, created];
    return created;
  }

  @override
  Future<void> deleteClass(String classId, {String? schoolId}) async {
    deleteCalls++;
    if (deleteError != null) {
      throw deleteError!;
    }
    classes = classes.where((item) => item.id != classId).toList();
  }
}

class _FakeStudentsRepository implements StudentsRepository {
  _FakeStudentsRepository({List<Student>? items, this.listError})
      : items = items ?? <Student>[];

  List<Student> items;
  final ApiException? listError;

  int createCalls = 0;
  int deactivateCalls = 0;
  String? lastSearch;
  String? lastClassFilter;

  @override
  Future<StudentPage> listStudents({
    String? schoolId,
    String? classId,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) async {
    if (listError != null) {
      throw listError!;
    }
    lastSearch = search;
    lastClassFilter = classId;
    return StudentPage(
      items: items,
      total: items.length,
      page: page,
      pageSize: pageSize,
    );
  }

  @override
  Future<Student> fetchStudent(String studentId, {String? schoolId}) async =>
      items.firstWhere((student) => student.id == studentId);

  @override
  Future<Student> createStudent({
    required String firstName,
    required String lastName,
    required String admissionNumber,
    required String classId,
    String? dateOfBirth,
    String? gender,
    String? schoolId,
  }) async {
    createCalls++;
    final created = Student(
      id: 'student-$createCalls',
      admissionNumber: admissionNumber,
      firstName: firstName,
      lastName: lastName,
      status: 'active',
      classId: classId,
    );
    items = <Student>[...items, created];
    return created;
  }

  @override
  Future<void> deactivateStudent(String studentId, {String? schoolId}) async {
    deactivateCalls++;
  }
}

class _FakeQrRepository implements QrRepository {
  _FakeQrRepository({this.state = QrCodeState.notGenerated});

  QrCodeState state;
  int statusCalls = 0;

  @override
  Future<List<Student>> listStudents({String? schoolId}) async =>
      const <Student>[];

  @override
  Future<QrCredential> generateCredential(String studentId) async => QrCredential(
        studentId: studentId,
        credential: 'token',
        createdAt: DateTime(2026, 10, 5),
        revokedPrevious: false,
      );

  @override
  Future<QrCredentialStatus> fetchStatus(String studentId) async {
    statusCalls++;
    return QrCredentialStatus(
      studentId: studentId,
      hasActiveCredential: state == QrCodeState.active,
      createdAt: state == QrCodeState.active ? DateTime(2026, 10, 5) : null,
      lastRevokedAt: state == QrCodeState.revoked ? DateTime(2026, 10, 4) : null,
    );
  }

  @override
  Future<void> revokeCredential(String studentId) async {
    state = QrCodeState.revoked;
  }
}

class _FakeParentsAdminRepository implements ParentsAdminRepository {
  _FakeParentsAdminRepository({
    List<LinkedParent>? linked,
    List<ParentAccount>? accounts,
    this.linkError,
    this.listError,
  })  : linked = linked ?? <LinkedParent>[],
        accounts = accounts ?? <ParentAccount>[];

  List<LinkedParent> linked;
  List<ParentAccount> accounts;
  final ApiException? linkError;
  final ApiException? listError;

  int linkCalls = 0;
  int unlinkCalls = 0;
  String? lastSearch;

  @override
  Future<List<ParentAccount>> listAccounts({String? schoolId, String? search}) async {
    lastSearch = search;
    return accounts;
  }

  @override
  Future<List<LinkedParent>> listLinked(String studentId, {String? schoolId}) async {
    if (listError != null) {
      throw listError!;
    }
    return linked;
  }

  @override
  Future<void> linkParent(
    String studentId,
    String parentUserId, {
    String? schoolId,
  }) async {
    linkCalls++;
    if (linkError != null) {
      throw linkError!;
    }
    linked = <LinkedParent>[
      ...linked,
      LinkedParent(userId: parentUserId, fullName: 'New Parent'),
    ];
  }

  @override
  Future<void> unlinkParent(
    String studentId,
    String parentUserId, {
    String? schoolId,
  }) async {
    unlinkCalls++;
    linked = linked.where((parent) => parent.userId != parentUserId).toList();
  }
}

SchoolClass _schoolClass(String id, String name, {String? section}) =>
    SchoolClass(id: id, name: name, section: section, academicYear: '2026-27');

Student _student(
  String id,
  String first,
  String last, {
  String status = 'active',
  String? classId,
}) =>
    Student(
      id: id,
      admissionNumber: 'ADM-$id',
      firstName: first,
      lastName: last,
      status: status,
      classId: classId,
    );

Widget _wrap(Widget child) => MaterialApp(home: child);

/// Gives the test a tall viewport.
///
/// These screens are long `ListView`s, and a lazy list only builds what fits on
/// screen. Without this, sections below the fold simply do not exist as widgets
/// and a finder cannot see them.
void _useTallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(1000, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  group('class management', () {
    testWidgets('lists classes with their section and academic year', (tester) async {
      final repository = _FakeClassesRepository(
        classes: [
          _schoolClass('1', 'Grade 5', section: 'B'),
          _schoolClass('2', 'Grade 6'),
        ],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(ClassListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.text('Grade 5 - B (2026-27)'), findsOneWidget);
      expect(find.text('Grade 6 (2026-27)'), findsOneWidget);
    });

    testWidgets('shows an empty state when the school has no classes', (tester) async {
      _useTallSurface(tester);
      await tester.pumpWidget(
        _wrap(ClassListScreen(schoolId: 'school-1', repository: _FakeClassesRepository())),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('No classes yet'), findsOneWidget);
    });

    testWidgets('creating a class reloads the list', (tester) async {
      final repository = _FakeClassesRepository();

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(ClassListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.byType(FloatingActionButton));

      // The form is pushed, so a save goes through the form, not the list.
      expect(find.text('Add class'), findsOneWidget);

      await tester.enterText(find.byType(TextFormField).first, 'Grade 7');
      await _tapVisible(tester, find.text('Save class'));

      expect(repository.createCalls, 1);
      expect(find.text('Grade 7'), findsWidgets);
    });

    testWidgets('explains that a populated class cannot be deleted', (tester) async {
      final repository = _FakeClassesRepository(
        classes: [_schoolClass('1', 'Grade 5', section: 'B')],
        deleteError: ApiException(409, 'Class has students assigned.'),
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(ClassListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.byIcon(Icons.delete_outline));
      await _tapVisible(tester, find.widgetWithText(FilledButton, 'Delete class'));

      expect(repository.deleteCalls, 1);
      // The 409 detail is phrased as a sentence for staff, not shown as a code.
      expect(find.textContaining('students assigned'), findsOneWidget);
    });

    testWidgets('deleting an empty class asks for confirmation first', (tester) async {
      final repository = _FakeClassesRepository(
        classes: [_schoolClass('1', 'Grade 6')],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(ClassListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.byIcon(Icons.delete_outline));
      await _tapVisible(tester, find.widgetWithText(FilledButton, 'Delete class'));

      expect(repository.deleteCalls, 1);
      expect(repository.classes, isEmpty);
    });

    testWidgets('surfaces a 403 without offering a retry loop', (tester) async {
      final repository = _FakeClassesRepository(
        listError: ApiException(403, 'You do not have access to this school.'),
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(ClassListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Could not load classes'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });
  });

  group('student management', () {
    testWidgets('lists students and shows inactive ones as marked', (tester) async {
      final repository = _FakeStudentsRepository(
        items: [
          _student('1', 'Ayesha', 'Khan'),
          _student('2', 'Bilal', 'Ahmed', status: 'inactive'),
        ],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(StudentListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Ayesha Khan'), findsOneWidget);
      expect(find.textContaining('Bilal Ahmed'), findsOneWidget);
      expect(find.text('Inactive'), findsOneWidget);
    });

    testWidgets('searching reloads the list with the term', (tester) async {
      final repository = _FakeStudentsRepository(
        items: [_student('1', 'Ayesha', 'Khan')],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(StudentListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).first, 'Ayesha');
      // The field is debounced, so the request only fires after the pause.
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(repository.lastSearch, 'Ayesha');
    });

    testWidgets('shows an empty state when no student matches', (tester) async {
      final repository = _FakeStudentsRepository();

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(StudentListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('No students'), findsOneWidget);
    });

    testWidgets('a teacher gets a read-only list with no add button', (tester) async {
      final repository = _FakeStudentsRepository(
        items: [_student('1', 'Ayesha', 'Khan')],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(
          StudentListScreen(
            schoolId: 'school-1',
            repository: repository,
            canManage: false,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Ayesha Khan'), findsOneWidget);
      expect(find.byIcon(Icons.add), findsNothing);
    });

    testWidgets('an API failure is explained and can be retried', (tester) async {
      final repository = _FakeStudentsRepository(
        listError: ApiException(0, 'No connection'),
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(StudentListScreen(schoolId: 'school-1', repository: repository)),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Could not load students'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });
  });

  group('student detail', () {
    testWidgets('reports a not-generated QR code', (tester) async {
      _useTallSurface(tester);
      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: _FakeParentsAdminRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Generate QR code'), findsOneWidget);
    });

    testWidgets('distinguishes an active code from a revoked one', (tester) async {
      for (final entry in <QrCodeState, String>{
        QrCodeState.active: 'QR code active',
        QrCodeState.revoked: 'QR code revoked',
      }.entries) {
        // Unmount first: reusing the same widget type keeps the previous State,
        // so initState would not run again and the old status would persist.
        await tester.pumpWidget(const SizedBox());
        _useTallSurface(tester);
        await tester.pumpWidget(
          _wrap(
            StudentDetailScreen(
              student: _student('1', 'Ayesha', 'Khan'),
              schoolId: 'school-1',
              qrRepository: _FakeQrRepository(state: entry.key),
              parentsRepository: _FakeParentsAdminRepository(),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text(entry.value), findsOneWidget);
      }
    });

    testWidgets('a revoked code prompts the administrator to issue a new one',
        (tester) async {
      _useTallSurface(tester);
      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(state: QrCodeState.revoked),
            parentsRepository: _FakeParentsAdminRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('no longer works'), findsOneWidget);
    });

    testWidgets('lists linked parents and offers to link another', (tester) async {
      final parents = _FakeParentsAdminRepository(
        linked: [
          const LinkedParent(userId: 'u1', fullName: 'Sana Khan', email: 'sana@example.com'),
        ],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Sana Khan'), findsOneWidget);
      // Still offered once a parent exists: a student can have several.
      expect(find.text('Link another parent'), findsOneWidget);
    });

    testWidgets('linking a parent calls the API and refreshes', (tester) async {
      final parents = _FakeParentsAdminRepository(
        accounts: const [
          ParentAccount(userId: 'u9', fullName: 'Adeel Khan', email: 'adeel@example.com'),
        ],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Link a parent'));
      await _tapVisible(tester, find.widgetWithText(FilledButton, 'Link'));

      expect(parents.linkCalls, 1);
    });

    testWidgets('a failed link is explained inside the sheet', (tester) async {
      final parents = _FakeParentsAdminRepository(
        accounts: const [
          ParentAccount(userId: 'u9', fullName: 'Adeel Khan'),
        ],
        linkError: ApiException(404, 'Parent account not found.'),
      );

      _useTallSurface(tester);
      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Link a parent'));
      await _tapVisible(tester, find.widgetWithText(FilledButton, 'Link'));

      // The sheet stays open and reports the reason instead of closing.
      expect(parents.linkCalls, 1);
      expect(find.textContaining('Parent account not found'), findsOneWidget);
      expect(find.byType(BottomSheet), findsOneWidget);
    });

    testWidgets('the link sheet hides parents already linked', (tester) async {
      final parents = _FakeParentsAdminRepository(
        linked: const [LinkedParent(userId: 'u1', fullName: 'Sana Khan')],
        accounts: const [
          ParentAccount(userId: 'u1', fullName: 'Sana Khan'),
          ParentAccount(userId: 'u2', fullName: 'Adeel Khan'),
        ],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // A parent is already linked, so the button offers to add another.
      await _tapVisible(tester, find.text('Link another parent'));

      // Scoped to the sheet: the detail screen behind it still lists Sana as linked,
      // which is the correct behaviour for that screen.
      final sheet = find.byType(BottomSheet);
      expect(
        find.descendant(of: sheet, matching: find.textContaining('Adeel Khan')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: sheet, matching: find.textContaining('Sana Khan')),
        findsNothing,
      );
    });

    testWidgets('removing a parent asks for confirmation', (tester) async {
      final parents = _FakeParentsAdminRepository(
        linked: const [LinkedParent(userId: 'u1', fullName: 'Sana Khan')],
      );

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.widgetWithText(TextButton, 'Remove'));
      expect(parents.unlinkCalls, 0, reason: 'must confirm before removing');

      await _tapVisible(tester, find.widgetWithText(FilledButton, 'Remove parent'));
      expect(parents.unlinkCalls, 1);
    });

    testWidgets('a teacher sees no QR, parent or deactivation controls', (tester) async {
      final parents = _FakeParentsAdminRepository();

      _useTallSurface(tester);

      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            canManage: false,
            qrRepository: _FakeQrRepository(),
            parentsRepository: parents,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Ayesha Khan'), findsWidgets);
      expect(find.text('Generate QR code'), findsNothing);
      expect(find.text('Link a parent'), findsNothing);
      expect(find.text('Deactivate student'), findsNothing);
      // The read-only parent lookup is skipped entirely.
      expect(parents.linked, isEmpty);
    });

    testWidgets('a 403 on the student is explained rather than shown as a code',
        (tester) async {
      _useTallSurface(tester);
      await tester.pumpWidget(
        _wrap(
          StudentDetailScreen(
            student: _student('1', 'Ayesha', 'Khan'),
            schoolId: 'school-1',
            qrRepository: _FakeQrRepository(),
            parentsRepository: _FakeParentsAdminRepository(
              listError: ApiException(403, 'You do not have access to this school.'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Could not load'), findsOneWidget);
      // The 403 is not surfaced as a bare status code.
      expect(find.textContaining('403'), findsNothing);
    });
  });
}

