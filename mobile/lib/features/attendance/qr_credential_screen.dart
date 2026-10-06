import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../core/network/api_client.dart';
import '../../core/widgets/state_views.dart';
import 'qr_repository.dart';

/// Lets a school admin issue, view, regenerate and revoke a student's QR
/// credential.
///
/// The plaintext credential is only ever held in memory for the lifetime of
/// this screen: it is not written to disk or logged, because the server stores
/// only its SHA-256 hash.
class QrCredentialScreen extends StatefulWidget {
  const QrCredentialScreen({
    super.key,
    this.schoolId,
    this.repository,
    this.initialStudentId,
  });

  final String? schoolId;

  /// Injectable for tests; defaults to the real API-backed repository.
  final QrRepository? repository;

  /// Opens the screen on this student instead of the first one. Used when an
  /// administrator arrives from a student's detail screen.
  final String? initialStudentId;

  @override
  State<QrCredentialScreen> createState() => _QrCredentialScreenState();
}

class _QrCredentialScreenState extends State<QrCredentialScreen> {
  late final QrRepository _repository;

  List<Student> _students = const <Student>[];
  bool _loadingStudents = true;
  String? _loadError;

  String? _selectedStudentId;
  QrCredential? _issued;
  String? _issuedForStudentId;
  bool _busy = false;

  QrCredentialStatus? _status;
  bool _loadingStatus = false;
  String? _statusError;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const QrRepository();
    _loadStudents();
  }

  Future<void> _loadStudents() async {
    setState(() {
      _loadingStudents = true;
      _loadError = null;
    });

    try {
      final students = await _repository.listStudents(schoolId: widget.schoolId);
      if (!mounted) {
        return;
      }
      // Honour a preselected student when it is still on the list, otherwise
      // fall back to the first one.
      final requestedId = widget.initialStudentId;
      final preselected = requestedId == null
          ? null
          : students.where((student) => student.id == requestedId).firstOrNull;
      setState(() {
        _students = students;
        _selectedStudentId = students.isEmpty
            ? null
            : (preselected?.id ?? students.first.id);
        _loadingStudents = false;
      });
      _loadStatus();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadError = describeError(error);
        _loadingStudents = false;
      });
    }
  }

  /// Reads the credential state so the screen can say Active, Revoked or Not
  /// generated, rather than only showing a code it happens to have issued.
  Future<void> _loadStatus() async {
    final studentId = _selectedStudentId;
    if (studentId == null) {
      return;
    }

    try {
      final status = await _repository.fetchStatus(studentId);
      if (!mounted) {
        return;
      }
      setState(() {
        _status = status;
        _loadingStatus = false;
      });
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _statusError = describeError(error);
          _loadingStatus = false;
        });
      }
    }
  }

  Future<void> _selectStudent(String? studentId) async {
    setState(() {
      _selectedStudentId = studentId;
      _status = null;
      _statusError = null;
      _loadingStatus = true;
    });
    await _loadStatus();
  }

  Student? get _selectedStudent {
    for (final student in _students) {
      if (student.id == _selectedStudentId) {
        return student;
      }
    }
    return null;
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) {
        _showSnack(describeError(error), isError: true);
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _generate() async {
    final studentId = _selectedStudentId;
    if (studentId == null) {
      return;
    }

    final confirmed = await _confirmRegeneration(studentId);
    if (!confirmed) {
      return;
    }

    await _run(() async {
      final credential = await _repository.generateCredential(studentId);
      if (!mounted) {
        return;
      }
      setState(() {
        _issued = credential;
        _issuedForStudentId = studentId;
      });
      if (credential.revokedPrevious) {
        _showSnack('Previous QR code revoked. The old code no longer works.');
      }
      await _loadStatus();
    });
  }

  Future<bool> _confirmRegeneration(String studentId) async {
    final student = _selectedStudent;
    final name = student?.fullName ?? 'this student';

    final bool alreadyIssued = _issuedForStudentId == studentId;
    if (!alreadyIssued) {
      return true;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Replace existing QR code?'),
        content: Text(
          '$name already has an active QR code. Generating a new one revokes '
          'the old code immediately.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Replace'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  Future<void> _revoke() async {
    final studentId = _issuedForStudentId;
    if (studentId == null) {
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Revoke QR code?'),
        content: const Text(
          'The student will not be able to be scanned until a new QR code is '
          'generated.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton.tonal(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Revoke'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }

    await _run(() async {
      await _repository.revokeCredential(studentId);
      if (!mounted) {
        return;
      }
      setState(() {
        _issued = null;
        _issuedForStudentId = null;
      });
      _showSnack('QR code revoked.');
      await _loadStatus();
    });
  }

  void _showSnack(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
        ),
      );
  }

  /// Tells the administrator whether the selected student can be scanned right
  /// now, which is the question they actually have.
  Widget _statusBanner(ThemeData theme) {
    if (_loadingStatus) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(8),
          child: SizedBox(
            height: 18,
            width: 18,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }
    if (_statusError != null) {
      return Text(
        'Could not read the QR status.',
        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
      );
    }

    final status = _status;
    if (status == null) {
      return const SizedBox.shrink();
    }

    final (String label, IconData icon, Color colour) = switch (status.state) {
      QrCodeState.active => (
          'Active — this student can be scanned',
          Icons.check_circle_outline,
          Colors.green.shade700,
        ),
      QrCodeState.revoked => (
          'Revoked — the old code no longer works',
          Icons.block,
          theme.colorScheme.error,
        ),
      QrCodeState.notGenerated => (
          'Not generated yet',
          Icons.info_outline,
          theme.colorScheme.onSurfaceVariant,
        ),
    };

    return Row(
      children: [
        Icon(icon, size: 18, color: colour),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(color: colour),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Student QR codes')),
      body: SafeArea(
        child: _loadingStudents
            ? const Center(child: CircularProgressIndicator())
            : _loadError != null
                ? _ErrorView(message: _loadError!, onRetry: _loadStudents)
                : _students.isEmpty
                    ? const _EmptyView(
                        message: 'No students yet. Add students to issue QR codes.',
                      )
                    : ListView(
                        padding: const EdgeInsets.all(16),
                        children: [
                          DropdownButtonFormField<String>(
                            initialValue: _selectedStudentId,
                            decoration: const InputDecoration(
                              labelText: 'Student',
                              border: OutlineInputBorder(),
                            ),
                            items: [
                              for (final student in _students)
                                DropdownMenuItem<String>(
                                  value: student.id,
                                  child: Text(
                                    '${student.fullName} (${student.admissionNumber})',
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                            ],
                            onChanged: _busy
                                ? null
                                : (value) => _selectStudent(value),
                          ),
                          if (_selectedStudent != null &&
                              !_selectedStudent!.isActive) ...[
                            const SizedBox(height: 8),
                            Text(
                              'This student is inactive and cannot be marked '
                              'present by scanning.',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.error,
                              ),
                            ),
                          ],
                          const SizedBox(height: 16),
                          _statusBanner(theme),
                          const SizedBox(height: 16),
                          FilledButton.icon(
                            onPressed: _busy ? null : _generate,
                            icon: _busy
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Icon(Icons.qr_code_2),
                            label: Text(
                              _issuedForStudentId == _selectedStudentId
                                  ? 'Regenerate QR code'
                                  : 'Generate QR code',
                            ),
                          ),
                          const SizedBox(height: 24),
                          if (_issued != null)
                            _IssuedCredential(
                              credential: _issued!,
                              student: _selectedStudent,
                              onRevoke: _busy ? null : _revoke,
                            ),
                        ],
                      ),
            ),
    );
  }
}

class _IssuedCredential extends StatelessWidget {
  const _IssuedCredential({
    required this.credential,
    required this.student,
    required this.onRevoke,
  });

  final QrCredential credential;
  final Student? student;
  final VoidCallback? onRevoke;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              student?.fullName ?? 'Student',
              style: theme.textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            Center(
              child: QrImageView(
                data: credential.credential,
                size: 220,
                backgroundColor: Colors.white,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Scan this code to mark attendance.',
              style: theme.textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'This code is shown only once. Store it somewhere safe, and '
              'generate a new one if it is lost.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.error,
              ),
              textAlign: TextAlign.center,
            ),
            if (credential.revokedPrevious) ...[
              const SizedBox(height: 8),
              Text(
                'The previous code for this student was revoked.',
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: onRevoke,
              icon: const Icon(Icons.block),
              label: const Text('Revoke this QR code'),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyView extends StatelessWidget {
  const _EmptyView({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.people_outline,
              size: 48,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 16),
            Text(message, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_outlined, size: 48, color: theme.colorScheme.error),
            const SizedBox(height: 16),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: () => onRetry(),
              child: const Text('Try again'),
            ),
          ],
        ),
      ),
    );
  }
}