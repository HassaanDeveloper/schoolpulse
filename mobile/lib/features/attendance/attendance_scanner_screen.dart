import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/network/api_client.dart';
import 'attendance_repository.dart';

/// Camera scanner that turns student QR codes into attendance.
///
/// The scanner only forwards the opaque credential to the API. Who gets marked
/// present, and whether the scan counts as arrival or departure, is decided
/// entirely by the server. The screen adds two safeguards on top:
///
/// * a card that was just scanned stays locked while it is held in front of the
///   camera, so one card can never be read twice by accident;
/// * a card that was marked as arrived in the last few minutes needs an
///   explicit confirmation before the app sends it again (which the server
///   would record as a departure).
class AttendanceScannerScreen extends StatefulWidget {
  const AttendanceScannerScreen({super.key, this.repository});

  /// Injectable for tests; defaults to the real API-backed repository.
  final AttendanceRepository? repository;

  @override
  State<AttendanceScannerScreen> createState() => _AttendanceScannerScreenState();
}

enum _ScanKind { arrival, departure, already, error }

_ScanKind _kindOf(ScanResult result) {
  final label = result.status.label.toLowerCase();
  if (label.contains('arrival')) {
    return _ScanKind.arrival;
  }
  if (label.contains('departure')) {
    return _ScanKind.departure;
  }
  return _ScanKind.already;
}

class _FlashStyle {
  const _FlashStyle(this.color, this.icon);

  final Color color;
  final IconData icon;
}

_FlashStyle _styleOf(_ScanKind kind, ColorScheme scheme) {
  switch (kind) {
    case _ScanKind.arrival:
      return const _FlashStyle(Color(0xFF2E7D32), Icons.check_circle_rounded);
    case _ScanKind.departure:
      return const _FlashStyle(Color(0xFF1565C0), Icons.logout_rounded);
    case _ScanKind.already:
      return const _FlashStyle(Color(0xFFEF6C00), Icons.info_rounded);
    case _ScanKind.error:
      return _FlashStyle(scheme.error, Icons.error_rounded);
  }
}

class _Flash {
  const _Flash({
    required this.id,
    required this.kind,
    required this.title,
    required this.subtitle,
  });

  final int id;
  final _ScanKind kind;
  final String title;
  final String subtitle;
}

class _RecentScan {
  const _RecentScan({required this.name, required this.kind, required this.at});

  final String name;
  final _ScanKind kind;
  final DateTime at;
}

class _AttendanceScannerScreenState extends State<AttendanceScannerScreen> {
  final MobileScannerController _controller = MobileScannerController();
  late final AttendanceRepository _repository;

  List<_ScanOutcome> _history = <_ScanOutcome>[];

  bool _submitting = false;
  bool _dialogOpen = false;

  _Flash? _flash;
  int _flashCounter = 0;
  Timer? _flashTimer;

  /// A scanned code stays locked until it has been out of view for this long.
  /// Every sighting of a locked code extends the lock, so holding a card steady
  /// can never trigger a second scan.
  final Map<String, DateTime> _lockedUntil = <String, DateTime>{};
  static const Duration _holdLockout = Duration(seconds: 6);

  /// Codes recently marked in this session, used to ask before a departure.
  final Map<String, _RecentScan> _recent = <String, _RecentScan>{};
  static const Duration _confirmWindow = Duration(minutes: 15);

  static const Duration _flashDuration = Duration(milliseconds: 2500);

  bool get _busy => _submitting || _dialogOpen;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const AttendanceRepository();
  }

  @override
  void dispose() {
    _flashTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    final now = DateTime.now();
    String? candidate;

    for (final barcode in capture.barcodes) {
      final raw = barcode.rawValue?.trim();
      if (raw == null || raw.isEmpty) {
        continue;
      }

      final until = _lockedUntil[raw];
      if (until != null && now.isBefore(until)) {
        // Still in front of the camera: keep it locked.
        _lockedUntil[raw] = now.add(_holdLockout);
        continue;
      }

      // Only claim a code when we can act on it right now. While busy it stays
      // unlocked, so the next student's card is scanned as soon as we are free.
      if (!_busy && candidate == null) {
        candidate = raw;
        _lockedUntil[raw] = now.add(_holdLockout);
      }
    }

    _lockedUntil.removeWhere((_, until) => now.isAfter(until));

    if (candidate != null) {
      unawaited(_handleCredential(candidate));
    }
  }

  Future<void> _handleCredential(String credential) async {
    final recent = _recent[credential];
    if (recent != null &&
        recent.kind == _ScanKind.arrival &&
        DateTime.now().difference(recent.at) < _confirmWindow) {
      setState(() => _dialogOpen = true);
      final confirmed = await _confirmDeparture(recent);
      if (!mounted) {
        return;
      }
      setState(() => _dialogOpen = false);
      _lockedUntil[credential] = DateTime.now().add(_holdLockout);
      if (!confirmed) {
        return;
      }
    }

    await _submit(credential);
  }

  Future<bool> _confirmDeparture(_RecentScan recent) async {
    final minutes = DateTime.now().difference(recent.at).inMinutes;
    final when = minutes < 1 ? 'less than a minute ago' : '$minutes min ago';

    final confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.logout_rounded),
        title: const Text('Mark departure?'),
        content: Text(
          '${recent.name} arrived $when. '
          'Do you want to mark them as leaving school now?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Not now'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Yes, mark departure'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  Future<void> _submit(String credential) async {
    setState(() => _submitting = true);

    try {
      final result = await _repository.scan(credential);
      if (!mounted) {
        return;
      }
      final kind = _kindOf(result);
      if (result.status.isNew) {
        _recent[credential] = _RecentScan(
          name: result.student.name,
          kind: kind,
          at: DateTime.now(),
        );
      }
      setState(() {
        _history.insert(0, _ScanOutcome.success(result));
        _history = _history.take(_historyLimit).toList();
      });
      _showFlash(kind, result.student.name, result.status.label);
      if (result.status.isNew) {
        HapticFeedback.mediumImpact();
      }
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _history.insert(0, _ScanOutcome.failure(error.message));
        _history = _history.take(_historyLimit).toList();
      });
      _showFlash(_ScanKind.error, 'Scan rejected', error.message);
      HapticFeedback.heavyImpact();
    } finally {
      // The lock now runs from the moment the request finished.
      _lockedUntil[credential] = DateTime.now().add(_holdLockout);
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  void _showFlash(_ScanKind kind, String title, String subtitle) {
    _flashTimer?.cancel();
    setState(() {
      _flash = _Flash(
        id: ++_flashCounter,
        kind: kind,
        title: title,
        subtitle: subtitle,
      );
    });
    _flashTimer = Timer(_flashDuration, () {
      if (mounted) {
        setState(() => _flash = null);
      }
    });
  }

  Future<void> _toggleTorch() async {
    await _controller.toggleTorch();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final flash = _flash;
    final style = flash == null ? null : _styleOf(flash.kind, theme.colorScheme);

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
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: 250,
                        height: 250,
                        decoration: BoxDecoration(
                          color: style?.color.withValues(alpha: 0.18),
                          border: Border.all(
                            color: style?.color ?? Colors.white,
                            width: style == null ? 3 : 8,
                          ),
                          borderRadius: BorderRadius.circular(20),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: 16,
                    left: 16,
                    right: 16,
                    child: IgnorePointer(
                      child: AnimatedSwitcher(
                        duration: const Duration(milliseconds: 200),
                        child: flash == null || style == null
                            ? const SizedBox.shrink(key: ValueKey<int>(0))
                            : _ResultBanner(
                                key: ValueKey<int>(flash.id),
                                flash: flash,
                                style: style,
                              ),
                      ),
                    ),
                  ),
                  const IgnorePointer(
                    child: Align(
                      alignment: Alignment.bottomCenter,
                      child: Padding(
                        padding: EdgeInsets.only(bottom: 16, left: 16, right: 16),
                        child: Text(
                          'Hold the code in the frame. When it turns green, '
                          'move on to the next student.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: Colors.white,
                            shadows: [Shadow(blurRadius: 4, color: Colors.black)],
                          ),
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

class _ResultBanner extends StatelessWidget {
  const _ResultBanner({super.key, required this.flash, required this.style});

  final _Flash flash;
  final _FlashStyle style;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      liveRegion: true,
      child: Material(
        color: style.color,
        elevation: 6,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(style.icon, size: 40, color: Colors.white),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      flash.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      flash.subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyLarge?.copyWith(color: Colors.white),
                    ),
                  ],
                ),
              ),
            ],
          ),
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
