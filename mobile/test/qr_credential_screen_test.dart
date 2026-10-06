import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/core/network/api_client.dart';
import 'package:schoolpulse/features/attendance/qr_credential_screen.dart';
import 'package:schoolpulse/features/attendance/qr_repository.dart';

/// Test double so the screen can be driven without HTTP.
class _FakeQrRepository implements QrRepository {
  _FakeQrRepository({required this.students, this.generateError});

  final List<Student> students;
  final ApiException? generateError;

  int generateCalls = 0;
  int revokeCalls = 0;
  bool revoked = false;

  @override
  Future<List<Student>> listStudents({String? schoolId}) async => students;

  @override
  Future<QrCredential> generateCredential(String studentId) async {
    generateCalls++;
    if (generateError != null) {
      throw generateError!;
    }
    return QrCredential(
      studentId: studentId,
      credential: 'generated-token-$generateCalls',
      createdAt: DateTime(2026, 3, 2),
      revokedPrevious: generateCalls > 1,
    );
  }

  @override
  Future<QrCredentialStatus> fetchStatus(String studentId) async {
    return QrCredentialStatus(
      studentId: studentId,
      hasActiveCredential: !revoked,
      createdAt: DateTime(2026, 3, 2),
    );
  }

  @override
  Future<void> revokeCredential(String studentId) async {
    revokeCalls++;
    revoked = true;
  }
}

Student _student(String id, String first, String last, {String status = 'active'}) {
  return Student(
    id: id,
    admissionNumber: 'ADM-$id',
    firstName: first,
    lastName: last,
    status: status,
  );
}

Widget _wrap(QrRepository repository) {
  return MaterialApp(
    home: QrCredentialScreen(repository: repository),
  );
}

/// Scrolls a widget into view before tapping it, since the issued credential
/// card can sit below the fold of the test viewport.
Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lists students and generates a QR credential', (tester) async {
    final repository = _FakeQrRepository(
      students: [
        _student('1', 'Ayesha', 'Khan'),
        _student('2', 'Bilal', 'Ahmed'),
      ],
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    // The first student is preselected.
    expect(find.text('Generate QR code'), findsOneWidget);
    expect(find.textContaining('Ayesha Khan'), findsOneWidget);

    await _tapVisible(tester, find.text('Generate QR code'));

    expect(repository.generateCalls, 1);
    // The issued code and the one-time warning are both shown.
    expect(find.textContaining('only once'), findsOneWidget);
    expect(find.text('Revoke this QR code'), findsOneWidget);
  });

  testWidgets('regeneration asks for confirmation before replacing', (tester) async {
    final repository = _FakeQrRepository(
      students: [_student('1', 'Ayesha', 'Khan')],
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Generate QR code'));
    expect(repository.generateCalls, 1);

    // The button now offers regeneration, which must confirm first.
    expect(find.text('Regenerate QR code'), findsOneWidget);
    await _tapVisible(tester, find.text('Regenerate QR code'));

    expect(find.text('Replace existing QR code?'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(repository.generateCalls, 1, reason: 'cancelling must not regenerate');
  });

  testWidgets('confirming regeneration issues a new credential', (tester) async {
    final repository = _FakeQrRepository(
      students: [_student('1', 'Ayesha', 'Khan')],
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Generate QR code'));

    await _tapVisible(tester, find.text('Regenerate QR code'));
    await tester.tap(find.text('Replace'));
    await tester.pumpAndSettle();

    expect(repository.generateCalls, 2);
    expect(find.textContaining('previous code'), findsOneWidget);
  });

  testWidgets('revoking requires confirmation and clears the code', (tester) async {
    final repository = _FakeQrRepository(
      students: [_student('1', 'Ayesha', 'Khan')],
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Generate QR code'));

    await _tapVisible(tester, find.text('Revoke this QR code'));
    expect(find.text('Revoke QR code?'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(repository.revokeCalls, 0);

    await _tapVisible(tester, find.text('Revoke this QR code'));
    await tester.tap(find.widgetWithText(FilledButton, 'Revoke'));
    await tester.pumpAndSettle();

    expect(repository.revokeCalls, 1);
    expect(find.text('Generate QR code'), findsOneWidget);
  });

  testWidgets('shows an empty state when there are no students', (tester) async {
    await tester.pumpWidget(_wrap(_FakeQrRepository(students: const <Student>[])));
    await tester.pumpAndSettle();

    expect(find.textContaining('No students yet'), findsOneWidget);
  });

  testWidgets('warns that an inactive student cannot be scanned', (tester) async {
    await tester.pumpWidget(
      _wrap(
        _FakeQrRepository(
          students: [_student('1', 'Ayesha', 'Khan', status: 'inactive')],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('inactive'), findsOneWidget);
  });

  testWidgets('surfaces an API error when generation fails', (tester) async {
    final repository = _FakeQrRepository(
      students: [_student('1', 'Ayesha', 'Khan')],
      generateError: ApiException(403, 'You do not have access to this school.'),
    );

    await tester.pumpWidget(_wrap(repository));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Generate QR code'));

    // Day 6: a 403 is rephrased for a parent-facing audience rather than shown
    // as the server's own wording.
    expect(find.text('You do not have permission to do this.'), findsOneWidget);
    expect(find.text('Generate QR code'), findsOneWidget);
  });
}
