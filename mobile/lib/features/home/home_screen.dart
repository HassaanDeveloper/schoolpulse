import 'package:flutter/material.dart';

import '../attendance/attendance_dashboard_screen.dart';
import '../attendance/attendance_scanner_screen.dart';
import '../attendance/qr_credential_screen.dart';
import '../auth/auth_controller.dart';
import '../classes/class_list_screen.dart';
import '../parent/parent_home_screen.dart';
import '../students/student_list_screen.dart';
import 'account_repository.dart';

/// Role-aware home screen.
///
/// A parent-only account is sent to [ParentHomeScreen], which offers no scanner,
/// no QR management and no staff dashboard. Staff accounts keep the staff home.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.auth, this.repository});

  final AuthController auth;

  /// Injectable for tests; defaults to the real API-backed repository.
  final AccountRepository? repository;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final AccountRepository _repository;

  late Future<Me> _future;

  /// Null means "the first membership"; the staff home sets it when the user
  /// switches school from the menu.
  String? _selectedSchoolId;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const AccountRepository();
    _future = _repository.fetchMe();
  }

  Future<void> _signOut() async {
    await widget.auth.signOut();
  }

  Future<void> _refresh() async {
    setState(() => _future = _repository.fetchMe());
    await _future;
  }

  /// Teachers and school admins may record attendance. Parents may not.
  bool _canScan(Me me) => me.memberships.any(
        (m) => m.role == 'school_admin' || m.role == 'teacher',
      );

  /// A parent who is not also staff somewhere gets the parent experience. A user
  /// with any staff role keeps the staff home, so the two never mix.
  bool _isParentOnly(Me me) =>
      me.memberships.any((m) => m.role == 'parent') && !_canScan(me);

  String? _parentSchoolId(Me me) {
    for (final membership in me.memberships) {
      if (membership.role == 'parent') {
        return membership.schoolId;
      }
    }
    return null;
  }

  /// The membership the staff home is currently showing.
  ///
  /// A user can belong to several schools, and the role that matters is the one
  /// held *at the selected school*. Reading the role from any membership would
  /// let a teacher at one school see an administrator's tools at another.
  Membership _selectedMembership(Me me) {
    final selectedId = _selectedSchoolId;
    if (selectedId != null) {
      for (final membership in me.memberships) {
        if (membership.schoolId == selectedId) {
          return membership;
        }
      }
    }
    return me.memberships.first;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Me>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: SafeArea(child: Center(child: CircularProgressIndicator())),
          );
        }

        if (snapshot.hasError) {
          return _messageHome(
            icon: Icons.cloud_off_outlined,
            isError: true,
            title: 'Could not load your account.',
            detail: 'Check that the backend is running and try again.',
            onRetry: _refresh,
          );
        }

        final me = snapshot.data!;

        if (_isParentOnly(me)) {
          return ParentHomeScreen(
            auth: widget.auth,
            schoolId: _parentSchoolId(me),
          );
        }

        if (me.memberships.isEmpty) {
          return _messageHome(
            icon: Icons.domain_add_outlined,
            isError: false,
            title: 'No school yet',
            detail: 'You are signed in but not a member of any school. '
                'School setup is coming next.',
          );
        }

        return _staffHome(context, me);
      },
    );
  }

  Widget _staffHome(BuildContext context, Me me) {
    final theme = Theme.of(context);
    final membership = _selectedMembership(me);
    final schoolId = membership.schoolId;
    // Taken from the selected school, so an admin at one school and a teacher
    // at another each get exactly the tools their role allows there.
    final isAdmin = membership.role == 'school_admin';

    return Scaffold(
      appBar: AppBar(
        title: const Text('SchoolPulse'),
        actions: [
          if (me.memberships.length > 1)
            PopupMenuButton<String>(
              tooltip: 'Switch school',
              icon: const Icon(Icons.apartment),
              initialValue: membership.schoolId,
              onSelected: (schoolId) => setState(() => _selectedSchoolId = schoolId),
              itemBuilder: (context) => [
                for (final option in me.memberships)
                  PopupMenuItem<String>(
                    value: option.schoolId,
                    child: Row(
                      children: [
                        if (option.schoolId == membership.schoolId)
                          const Icon(Icons.check, size: 18)
                        else
                          const SizedBox(width: 18),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            '${option.schoolName} (${option.roleLabel})',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          IconButton(
            tooltip: 'Log out',
            onPressed: _signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Text('Welcome,', style: theme.textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                widget.auth.email ?? 'Signed in',
                style: theme.textTheme.headlineSmall,
              ),
              const SizedBox(height: 24),
              ...me.memberships.map(
                (m) => Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.school_outlined),
                    title: Text(m.schoolName),
                    subtitle: Text('Role: ${m.roleLabel}'),
                  ),
                ),
              ),
              if (_canScan(me)) ...[
                const SizedBox(height: 12),
                const _SectionHeading('Attendance'),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.insights_outlined),
                    title: const Text('Attendance dashboard'),
                    subtitle: const Text("Today's present, absent and completed"),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => AttendanceDashboardScreen(schoolId: schoolId),
                      ),
                    ),
                  ),
                ),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.qr_code_scanner),
                    title: const Text('Scan attendance'),
                    subtitle: const Text('Record arrival and departure'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const AttendanceScannerScreen(),
                      ),
                    ),
                  ),
                ),
              ],
              if (isAdmin) ...[
                const SizedBox(height: 12),
                const _SectionHeading('School'),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.school_outlined),
                    title: const Text('Classes'),
                    subtitle: const Text('Add or remove classes'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => ClassListScreen(
                          schoolId: schoolId,
                          canManage: true,
                        ),
                      ),
                    ),
                  ),
                ),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.groups_outlined),
                    title: const Text('Students'),
                    subtitle: const Text('Enrol students, issue QR codes, link parents'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => StudentListScreen(
                          schoolId: schoolId,
                          canManage: true,
                        ),
                      ),
                    ),
                  ),
                ),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.qr_code_2),
                    title: const Text('Student QR codes'),
                    subtitle: const Text('Generate and revoke student codes'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => QrCredentialScreen(schoolId: schoolId),
                      ),
                    ),
                  ),
                ),
              ] else if (_canScan(me)) ...[
                // A teacher may look up classes and students, but the add,
                // delete, QR and parent actions are hidden here as well as
                // refused by the server.
                const SizedBox(height: 12),
                const _SectionHeading('School'),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.school_outlined),
                    title: const Text('Classes'),
                    subtitle: const Text('View this school\'s classes'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => ClassListScreen(
                          schoolId: schoolId,
                          canManage: false,
                        ),
                      ),
                    ),
                  ),
                ),
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.groups_outlined),
                    title: const Text('Students'),
                    subtitle: const Text('Look up a student and their attendance'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => StudentListScreen(
                          schoolId: schoolId,
                          canManage: false,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _messageHome({
    required IconData icon,
    required bool isError,
    required String title,
    required String detail,
    VoidCallback? onRetry,
  }) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('SchoolPulse'),
        actions: [
          IconButton(
            tooltip: 'Log out',
            onPressed: _signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 48),
            Icon(
              icon,
              size: 48,
              color: isError ? theme.colorScheme.error : theme.colorScheme.primary,
            ),
            const SizedBox(height: 16),
            Text(title, textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(detail, textAlign: TextAlign.center),
            if (onRetry != null) ...[
              const SizedBox(height: 24),
              Center(
                child: FilledButton(onPressed: onRetry, child: const Text('Try again')),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SectionHeading extends StatelessWidget {
  const _SectionHeading(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(
        label,
        style: Theme.of(context).textTheme.titleSmall?.copyWith(
              color: Theme.of(context).colorScheme.primary,
            ),
      ),
    );
  }
}