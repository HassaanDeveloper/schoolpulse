import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/features/auth/auth_controller.dart';
import 'package:schoolpulse/features/classes/class_list_screen.dart';
import 'package:schoolpulse/features/home/account_repository.dart';
import 'package:schoolpulse/features/home/home_screen.dart';
import 'package:schoolpulse/features/students/student_list_screen.dart';

class _FakeAccountRepository implements AccountRepository {
  _FakeAccountRepository(this.me);

  final Me me;

  @override
  Future<Me> fetchMe() async => me;
}

Membership _membership(String id, String name, String role) =>
    Membership(schoolId: id, schoolName: name, role: role);

void main() {
  late AuthController auth;

  setUp(() {
    auth = AuthController();
  });

  tearDown(() {
    auth.dispose();
  });

  Widget wrap(Me me) => MaterialApp(
        home: HomeScreen(
          auth: auth,
          repository: _FakeAccountRepository(me),
        ),
      );

  /// The staff home is a long list, so give the test room to build it.
  void useTallSurface(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
  }

  testWidgets('a single-school admin sees the management shortcuts', (tester) async {
    useTallSurface(tester);
    await tester.pumpWidget(
      wrap(
        Me(
          id: 'user-1',
          memberships: [_membership('school-1', 'Demo School', 'school_admin')],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Classes'), findsOneWidget);
    expect(find.text('Students'), findsOneWidget);
    expect(find.text('Student QR codes'), findsOneWidget);
    // A single school needs no switcher.
    expect(find.byIcon(Icons.apartment), findsNothing);
  });

  testWidgets('a single-school teacher gets view-only access', (tester) async {
    useTallSurface(tester);
    await tester.pumpWidget(
      wrap(
        Me(
          id: 'user-1',
          memberships: [_membership('school-1', 'Demo School', 'teacher')],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Scan attendance'), findsOneWidget);
    // Teachers may open classes and students, but not issue QR codes.
    expect(find.text('Student QR codes'), findsNothing);
  });

  testWidgets('a multi-school user can switch school', (tester) async {
    useTallSurface(tester);
    await tester.pumpWidget(
      wrap(
        Me(
          id: 'user-1',
          memberships: [
            _membership('school-1', 'Demo School', 'school_admin'),
            _membership('school-2', 'Second School', 'teacher'),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.apartment), findsOneWidget);
    // Admin at the selected school, so the QR shortcut is offered.
    expect(find.text('Student QR codes'), findsOneWidget);

await tester.tap(find.byIcon(Icons.apartment));
    await tester.pumpAndSettle();
    // The name also appears on the membership cards behind the menu, so the tap
    // is scoped to the menu entry.
    await tester.tap(
      find.descendant(
        of: find.byType(PopupMenuItem<String>),
        matching: find.textContaining('Second School'),
      ),
    );
    await tester.pumpAndSettle();

    // The role at the newly selected school governs the tools, so a teacher
    // role at Second School hides the QR shortcut.
    expect(find.text('Student QR codes'), findsNothing);
  });

  testWidgets('a parent-only account never sees staff tools', (tester) async {
    useTallSurface(tester);
    await tester.pumpWidget(
      wrap(
        Me(
          id: 'user-1',
          memberships: [_membership('school-1', 'Demo School', 'parent')],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Classes'), findsNothing);
    expect(find.text('Student QR codes'), findsNothing);
    expect(find.byType(ClassListScreen), findsNothing);
    expect(find.byType(StudentListScreen), findsNothing);
  });
}
