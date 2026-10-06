import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../core/widgets/state_views.dart';
import '../attendance/attendance_report_repository.dart';
import '../attendance/qr_credential_screen.dart';
import '../attendance/qr_repository.dart';
import '../attendance/student_attendance_screen.dart';
import '../parents/parent_link_sheet.dart';
import '../parents/parents_admin_repository.dart';
import 'students_repository.dart';

/// Everything an administrator needs about one student, on one screen.
///
/// This is the hub of the Day 6 workflow: open a student, issue their QR code,
/// link a parent, then look at their attendance. Each of those is a link to the
/// screen that already owns it, rather than a second implementation here.
class StudentDetailScreen extends StatefulWidget {
  const StudentDetailScreen({
    super.key,
    required this.student,
    this.schoolId,
    this.classLabel,
    this.qrRepository,
    this.parentsRepository,
    this.canManage = true,
  });

  final Student student;
  final String? schoolId;
  final String? classLabel;

  /// Injectable for tests.
  final QrRepository? qrRepository;
  final ParentsAdminRepository? parentsRepository;

  /// False for a teacher: no QR issuing, no parent linking, no deactivation.
  final bool canManage;

  @override
  State<StudentDetailScreen> createState() => _StudentDetailScreenState();
}

class _StudentDetailScreenState extends State<StudentDetailScreen> {
  late final QrRepository _qr;
  late final ParentsAdminRepository _parents;

  late Student _student;
  QrCredentialStatus? _qrStatus;
  List<LinkedParent> _linked = const <LinkedParent>[];
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _student = widget.student;
    _qr = widget.qrRepository ?? const QrRepository();
    _parents = widget.parentsRepository ?? const ParentsAdminRepository();
    _load();
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final results = await Future.wait<Object?>([
        _qr.fetchStatus(_student.id),
        widget.canManage
            ? _parents.listLinked(_student.id, schoolId: widget.schoolId)
            : Future<List<LinkedParent>>.value(const <LinkedParent>[]),
      ]);
      if (!mounted) {
        return;
      }
      setState(() {
        _qrStatus = results[0] as QrCredentialStatus;
        _linked = results[1] as List<LinkedParent>? ?? const <LinkedParent>[];
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = describeError(error);
        _loading = false;
      });
    }
  }

  Future<void> _openQrManagement() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => QrCredentialScreen(
          schoolId: widget.schoolId,
          initialStudentId: _student.id,
          repository: _qr,
        ),
      ),
    );
    if (mounted) {
      await _load();
    }
  }

  Future<void> _openParentLinking() async {
    final changed = await showParentLinkSheet(
      context,
      studentId: _student.id,
      schoolId: widget.schoolId,
      repository: _parents,
      existing: _linked,
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  Future<void> _openAttendance() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => StudentAttendanceScreen(
          studentId: _student.id,
          studentName: _student.fullName,
          admissionNumber: _student.admissionNumber,
          schoolId: widget.schoolId,
          repository: const AttendanceReportRepository(),
        ),
      ),
    );
  }

  Future<void> _deactivate() async {
    final confirmed = await confirmAction(
      context,
      title: 'Deactivate ${_student.fullName}?',
      message: 'The student stays in the system and their attendance history is '
          'kept, but they will no longer be counted in daily attendance and '
          'their QR code will stop working.',
      confirmLabel: 'Deactivate',
      destructive: true,
    );
    if (!confirmed || !mounted) {
      return;
    }

    setState(() => _busy = true);
    try {
      await const StudentsRepository()
          .deactivateStudent(_student.id, schoolId: widget.schoolId);
      // The endpoint returns no body, so re-read the record rather than
      // assuming the status changed.
      final fresh = await const StudentsRepository()
          .fetchStudent(_student.id, schoolId: widget.schoolId);
      if (!mounted) {
        return;
      }
      setState(() {
        _student = fresh;
        _busy = false;
      });
      showMessage(context, '${fresh.fullName} deactivated.');
      await _load();
    } on ApiException catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showMessage(context, describeError(error), isError: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(_student.fullName)),
      body: SafeArea(child: _body(theme)),
    );
  }

  Widget _body(ThemeData theme) {
    if (_loading) {
      return const LoadingView(message: 'Loading student');
    }
    if (_error != null) {
      return ErrorView(
        message: _error!,
        onRetry: _load,
        title: 'Could not load this student',
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _header(theme),
          const SizedBox(height: 24),
          const _SectionHeading('Attendance'),
          _actionTile(
            icon: Icons.history,
            title: 'Attendance history',
            subtitle: 'Days, times and derived status',
            onTap: _openAttendance,
          ),
          const SizedBox(height: 24),
          if (widget.canManage) ...[
            const _SectionHeading('QR code'),
            _actionTile(
              icon: Icons.qr_code_2,
              title: _qrTitle(),
              subtitle: _qrSubtitle(),
              onTap: _openQrManagement,
            ),
            const SizedBox(height: 24),
            const _SectionHeading('Parents'),
            if (_linked.isEmpty)
              _emptyParents()
            else
              ..._linked.map(_parentTile),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              // Always enabled: a student can have several linked parents,
              // so this must not lock out adding a second one.
              onPressed: _busy ? null : _openParentLinking,
              icon: const Icon(Icons.person_add_alt),
              label: Text(
                _linked.isEmpty ? 'Link a parent' : 'Link another parent',
              ),
            ),
            const SizedBox(height: 24),
          ],
          if (widget.canManage && _student.isActive) ...[
            TextButton.icon(
              onPressed: _busy ? null : _deactivate,
              style: TextButton.styleFrom(foregroundColor: theme.colorScheme.error),
              icon: _busy
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.person_off_outlined),
              label: const Text('Deactivate student'),
            ),
          ],
          if (!_student.isActive)
            Card(
              color: theme.colorScheme.errorContainer,
              child: const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'This student is inactive. They are not counted in daily '
                  'attendance and cannot be marked present by scanning.',
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _header(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_student.fullName, style: theme.textTheme.titleLarge),
            const SizedBox(height: 12),
            _detail('Admission number', _student.admissionNumber),
            _detail('Class', widget.classLabel ?? 'No class'),
            _detail(
              'Status',
              _student.isActive ? 'Active' : 'Inactive',
            ),
            if (_student.dateOfBirth != null && _student.dateOfBirth!.isNotEmpty)
              _detail('Date of birth', _student.dateOfBirth!),
          ],
        ),
      ),
    );
  }

  Widget _detail(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 130,
            child: Text(label, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  String _qrTitle() {
    switch (_qrStatus?.state) {
      case QrCodeState.active:
        return 'QR code active';
      case QrCodeState.revoked:
        return 'QR code revoked';
      default:
        return 'Generate QR code';
    }
  }

  String _qrSubtitle() {
    final status = _qrStatus;
    if (status == null) {
      return 'Tap to manage';
    }
    switch (status.state) {
      case QrCodeState.active:
        return 'Tap to view, regenerate or revoke';
      case QrCodeState.revoked:
        return 'The old code no longer works. Tap to issue a new one';
      case QrCodeState.notGenerated:
        return 'Tap to issue this student a code';
    }
  }

  Widget _actionTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }

  Widget _emptyParents() {
    return const Card(
      margin: EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Text(
          'No parents linked.\n\nLink a parent so they can see this student\'s '
          'attendance and receive arrival and departure notifications.',
        ),
      ),
    );
  }

  Widget _parentTile(LinkedParent parent) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.person_outline)),
        title: Text(parent.displayName),
        subtitle: Text(parent.subtitle),
        trailing: widget.canManage
            ? TextButton(
                onPressed: _busy ? null : () => _removeParent(parent),
                child: const Text('Remove'),
              )
            : null,
      ),
    );
  }

  Future<void> _removeParent(LinkedParent parent) async {
    final confirmed = await confirmAction(
      context,
      title: 'Remove ${parent.displayName}?',
      message: 'They will immediately lose access to this student\'s attendance '
          'and notifications. Notifications already sent to them are kept as a '
          'record.',
      confirmLabel: 'Remove parent',
      destructive: true,
    );
    if (!confirmed || !mounted) {
      return;
    }

    setState(() => _busy = true);
    try {
      await _parents.unlinkParent(_student.id, parent.userId, schoolId: widget.schoolId);
      if (!mounted) {
        return;
      }
      showMessage(context, '${parent.displayName} removed.');
      await _load();
    } on ApiException catch (error) {
      if (mounted) {
        showMessage(context, describeError(error), isError: true);
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
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
