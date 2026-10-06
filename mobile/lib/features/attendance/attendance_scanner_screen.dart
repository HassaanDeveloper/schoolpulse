import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/network/api_client.dart';
import 'attendance_repository.dart';

/// Camera scanner that turns student QR codes into attendance.
///
/// The scanner only forwards the opaque credential to the API. Who gets marked
/// present, and whether the scan counts as arrival or departure, is decided
/// entirely by the server.
class AttendanceScannerScreen extends StatefulWidget {
  const AttendanceScannerScreen({super.key, this.repository});

  /// Injectable for tests; defaults to the real API-backed repository.
  final AttendanceRepository? repository;

  @override
  State<AttendanceScannerScreen> createState() => _AttendanceScannerScreenState();
}

class _AttendanceScannerScreenState extends State<AttendanceScannerScreen> {
  final MobileScannerController _controller = MobileScannerController();
  late final AttendanceRepository _repository;

  List<_ScanOutcome> _history = <_ScanOutcome>[];

  bool _scanning = true;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const AttendanceRepository();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (!_scanning || _submitting) {
      return;
    }

    for (final barcode in capture.barcodes) {
      final raw = barcode.rawValue;
      if (raw == null || raw.trim().isEmpty) {
        continue;
      }
      _submit(raw.trim());
      return;
    }
  }

  Future<void> _submit(String credential) async {
    // Pause while the request is in flight so one code cannot be scanned twice.
    setState(() {
      _submitting = true;
      _scanning = false;
    });

    try {
      final result = await _repository.scan(credential);
      if (!mounted) {
        return;
      }
      setState(() {
        _history.insert(0, _ScanOutcome.success(result));
        _history = _history.take(_historyLimit).toList();
      });
      _feedback(result);
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _history.insert(0, _ScanOutcome.failure(error.message));
        _history = _history.take(_historyLimit).toList();
      });
      _showMessage(error.message, isError: true);
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
          _scanning = true;
        });
      }
    }
  }

  void _feedback(ScanResult result) {
    if (!result.status.isNew) {
      return;
    }
    _showMessage('${result.student.name}: ${result.status.label}');
  }

  void _showMessage(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
        ),
      );
  }

  Future<void> _toggleTorch() async {
    await _controller.toggleTorch();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan attendance'),
        actions: [
          IconButton(
            tooltip: 'Toggle torch',
            onPressed: _toggleTorch,
            icon: const Icon(Icons.flashlight_on_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  MobileScanner(
                    controller: _controller,
                    onDetect: _onDetect,
                    errorBuilder: (context, error, child) => _CameraError(error: error),
                  ),
                  IgnorePointer(
                    child: Center(
                      child: Container(
                        width: 240,
                        height: 240,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.white, width: 3),
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                    ),
                  ),
                  if (_submitting)
                    const ColoredBox(
                      color: Color(0x66000000),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                ],
              ),
            ),
            if (_history.isNotEmpty)
              Container(
                width: double.infinity,
                constraints: const BoxConstraints(maxHeight: 180),
                color: theme.colorScheme.surfaceContainerHighest,
                child: ListView.builder(
                  shrinkWrap: true,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  itemCount: _history.length,
                  itemBuilder: (context, index) => _HistoryTile(outcome: _history[index]),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

const int _historyLimit = 20;

class _ScanOutcome {
  const _ScanOutcome.success(this.result)
      : errorMessage = null,
        isError = false;

  const _ScanOutcome.failure(this.errorMessage)
      : result = null,
        isError = true;

  final ScanResult? result;
  final String? errorMessage;
  final bool isError;

  String get headline {
    final scan = result;
    if (scan == null) {
      return 'Scan rejected';
    }
    return '${scan.student.name} - ${scan.status.label}';
  }
}

class _HistoryTile extends StatelessWidget {
  const _HistoryTile({required this.outcome});

  final _ScanOutcome outcome;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        outcome.isError ? Icons.error_outline : Icons.check_circle_outline,
        color: outcome.isError ? theme.colorScheme.error : theme.colorScheme.primary,
      ),
      title: Text(outcome.headline),
      subtitle: Text(
        outcome.isError
            ? outcome.errorMessage!
            : 'Date ${outcome.result!.attendanceDate?.toIso8601String().split('T').first ?? '-'}',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

class _CameraError extends StatelessWidget {
  const _CameraError({required this.error});

  final MobileScannerException error;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ColoredBox(
      color: theme.colorScheme.surface,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.no_photography_outlined, size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 16),
              Text(
                'The camera could not be started.',
                style: theme.textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                error.errorDetails?.message ??
                    'Grant camera permission and try again.',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}