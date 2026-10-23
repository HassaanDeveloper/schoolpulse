import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../attendance/attendance_report_repository.dart';
import 'parent_repository.dart';

/// Attendance history for one child, as the parent sees it.
///
/// Reads the parent's own endpoint rather than the staff one, so the response
/// carries no scanner identity and the server chooses the school-local range.
class ChildAttendanceScreen extends StatefulWidget {
  const ChildAttendanceScreen({
    super.key,
    required this.child,
    this.repository,
    this.pageSize = 30,
  });

  final ParentChild child;

  /// Injectable for tests; defaults to the real API-backed repository.
  final ParentRepository? repository;

  /// The parent list is unpaginated on the wire, so this is a display cap only.
  final int pageSize;

  @override
  State<ChildAttendanceScreen> createState() => _ChildAttendanceScreenState();
}

class _ChildAttendanceScreenState extends State<ChildAttendanceScreen> {
  static const int maxRangeDays = 90;

  late final ParentRepository _repository;

  ParentChildAttendance? _attendance;
  bool _loading = true;
  String? _error;
  int _days = 7;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const ParentRepository();
    _load();
  }

  Future<void> _load() async {
    if (!mounted) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      // No dates are sent: the server applies the school-local default window.
      final attendance = await _repository.fetchChildAttendance(
        studentId: widget.child.studentId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _attendance = attendance;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final initialStart = now.subtract(Duration(days: _days - 1));
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
      initialDateRange: DateTimeRange(start: initialStart, end: now),
    );
    if (picked == null || !mounted) {
      return;
    }

    final span = picked.end.difference(picked.start).inDays + 1;
    if (span > maxRangeDays) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(content: Text('Choose a range of $maxRangeDays days or fewer.')),
        );
      return;
    }

    setState(() {
      _days = span;
      _loading = true;
    });
    await _loadCustom(picked.start, picked.end);
  }

  Future<void> _loadCustom(DateTime start, DateTime end) async {
    try {
      final attendance = await _repository.fetchChildAttendance(
        studentId: widget.child.studentId,
        startDate: start,
        endDate: end,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _attendance = attendance;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.child.fullName),
        actions: [
          IconButton(
            tooltip: 'Choose dates',
            onPressed: _loading ? null : _pickRange,
            icon: const Icon(Icons.date_range),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: _buildBody(theme),
        ),
      ),
    );
  }

  Widget _buildBody(ThemeData theme) {
    if (_loading) {
      // Scrollable while loading, so pull-to-refresh keeps working.
      return ListView(
        children: const [
          SizedBox(height: 120),
          Center(child: CircularProgressIndicator()),
        ],
      );
    }

    if (_error != null) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 48),
          Icon(Icons.cloud_off_outlined, size: 48, color: theme.colorScheme.error),
          const SizedBox(height: 16),
          Text(
            'Could not load attendance.',
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          Center(
            child: FilledButton(onPressed: _load, child: const Text('Try again')),
          ),
        ],
      );
    }

    final attendance = _attendance;
    if (attendance == null || attendance.records.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 48),
          const Icon(Icons.event_busy_outlined, size: 48),
          const SizedBox(height: 16),
          Text(
            'No attendance recorded',
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'Nothing has been recorded for these dates yet.',
            textAlign: TextAlign.center,
          ),
        ],
      );
    }

    // The server's range ends on the school's local today, so that date is the
    // anchor for "Today". Comparing against DateTime.now() here would repeat
    // the Day 5 timezone bug on a phone in another timezone.
    final today = attendance.endDate;
    final anchor = today;
    final todayRecord = anchor == null
        ? null
        : attendance.records
            .where((record) => _sameDay(record.date, anchor))
            .firstOrNull;
    final history = anchor == null || todayRecord == null
        ? attendance.records
        : attendance.records.where((record) => !_sameDay(record.date, anchor));

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      children: [
        _ChildHeader(child: widget.child),
        const SizedBox(height: 16),
        _TodayCard(record: todayRecord, child: widget.child),
        const SizedBox(height: 16),
        _SummaryTiles(attendance: attendance),
        const SizedBox(height: 24),
        Text(
          'History',
          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 10),
        if (history.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('No earlier days in this range.'),
          )
        else
          ...history.take(widget.pageSize).map(
                (record) => _DayRow(record: record, today: today),
              ),
      ],
    );
  }

  static bool _sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

class _Tone {
  const _Tone(this.color, this.icon);

  final Color color;
  final IconData icon;
}

/// One colour and icon per status. Today's "absent" is amber (the normal state
/// early in the day); an absent day in the past is red.
_Tone _toneOf(BuildContext context, AttendanceStatus status, {required bool today}) {
  final scheme = Theme.of(context).colorScheme;
  switch (status) {
    case AttendanceStatus.present:
      return const _Tone(Color(0xFF1B873F), Icons.check_circle_rounded);
    case AttendanceStatus.completed:
      return const _Tone(Color(0xFF1F6FEB), Icons.logout_rounded);
    case AttendanceStatus.absent:
      return today
          ? const _Tone(Color(0xFFB26A00), Icons.schedule_rounded)
          : _Tone(scheme.error, Icons.cancel_rounded);
    case AttendanceStatus.unknown:
      return _Tone(scheme.outline, Icons.help_outline);
  }
}

String _todayText(AttendanceStatus status) {
  return switch (status) {
    AttendanceStatus.present => 'Arrived today',
    AttendanceStatus.completed => 'Arrived and left today',
    AttendanceStatus.absent => 'Not marked present today',
    AttendanceStatus.unknown => 'No update yet',
  };
}

String _dayWord(AttendanceStatus status) {
  return switch (status) {
    AttendanceStatus.present => 'Arrived',
    AttendanceStatus.completed => 'Arrived and left',
    AttendanceStatus.absent => 'Absent',
    AttendanceStatus.unknown => 'Unknown',
  };
}

AttendanceStatus? _statusFromWire(String? value) => switch (value) {
      'present' => AttendanceStatus.present,
      'completed' => AttendanceStatus.completed,
      'absent' => AttendanceStatus.absent,
      _ => null,
    };

String? _arrivalOf(AttendanceHistoryRecord record) =>
    record.arrivalTime ?? _localTime(record.arrivalAt);

String? _departureOf(AttendanceHistoryRecord record) =>
    record.departureTime ?? _localTime(record.departureAt);

String _timesFor(AttendanceHistoryRecord record) {
  final arrival = _arrivalOf(record);
  final departure = _departureOf(record);
  if (arrival == null && departure == null) {
    return 'No times';
  }
  if (departure == null) {
    return 'In $arrival';
  }
  return '$arrival - $departure';
}

/// Only used when the server did not send a preformatted time. The parent
/// endpoint always does, so a scan time is never recomputed from the phone's
/// clock on the parent screens.
String? _localTime(DateTime? value) {
  if (value == null) {
    return null;
  }
  final local = value.toLocal();
  final hour = local.hour % 12 == 0 ? 12 : local.hour % 12;
  final minute = local.minute.toString().padLeft(2, '0');
  final suffix = local.hour >= 12 ? 'PM' : 'AM';
  return '$hour:$minute $suffix';
}

/// Labels relative to the server's today, not the device's.
String _labelFor(DateTime date, DateTime? today) {
  if (today == null) {
    return formatDateOnly(date);
  }
  final day = DateTime(date.year, date.month, date.day);
  final anchor = DateTime(today.year, today.month, today.day);
  final difference = anchor.difference(day).inDays;
  if (difference == 0) {
    return 'Today';
  }
  if (difference == 1) {
    return 'Yesterday';
  }
  return formatDateOnly(day);
}

String _initials(String name) {
  final parts = name
      .trim()
      .split(RegExp(r'\s+'))
      .where((part) => part.isNotEmpty)
      .toList();
  if (parts.isEmpty) {
    return '?';
  }
  String first(String text) => String.fromCharCode(text.runes.first);
  if (parts.length == 1) {
    return first(parts.first).toUpperCase();
  }
  return (first(parts.first) + first(parts.last)).toUpperCase();
}

// ---------------------------------------------------------------------------
// Widgets
// ---------------------------------------------------------------------------

class _ChildHeader extends StatelessWidget {
  const _ChildHeader({required this.child});

  final ParentChild child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return Row(
      children: [
        CircleAvatar(
          radius: 28,
          backgroundColor: scheme.primaryContainer,
          child: Text(
            _initials(child.fullName),
            style: TextStyle(
              color: scheme.onPrimaryContainer,
              fontWeight: FontWeight.w800,
              fontSize: 18,
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                child.fullName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
              ),
              Text(
                child.classLabel.isEmpty
                    ? child.schoolName
                    : '${child.classLabel} - ${child.schoolName}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _TodayCard extends StatelessWidget {
  const _TodayCard({required this.record, required this.child});

  final AttendanceHistoryRecord? record;
  final ParentChild child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final today = record;
    // Prefer the record from the range; fall back to the status the children
    // list resolved when the chosen range does not reach today.
    final status = today?.status ?? _statusFromWire(child.todayStatus);
    final date = today?.date ?? parseDateOnly(child.todayStatusDate);
    final tone = status == null ? null : _toneOf(context, status, today: true);
    final accent = tone?.color ?? theme.colorScheme.outline;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: accent.withValues(alpha: 0.28)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                'Today',
                style: theme.textTheme.labelLarge?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              if (date != null)
                Text(formatDateOnly(date), style: theme.textTheme.bodySmall),
            ],
          ),
          const SizedBox(height: 14),
          if (status == null || tone == null)
            const Text('Nothing recorded for today yet.')
          else ...[
            Row(
              children: [
                Icon(tone.icon, color: tone.color, size: 40),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    _todayText(status),
                    style: theme.textTheme.titleLarge?.copyWith(
                      color: tone.color,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            if (today != null) ...[
              const SizedBox(height: 18),
              _TimelineRow(
                label: 'Arrived',
                time: _arrivalOf(today),
                color: tone.color,
                showLine: true,
              ),
              _TimelineRow(
                label: 'Left school',
                time: _departureOf(today),
                color: tone.color,
                showLine: false,
              ),
            ],
          ],
        ],
      ),
    );
  }
}

/// One step of the arrival/departure timeline. The dot is filled once the event
/// has happened and hollow while it is still to come.
class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.label,
    required this.time,
    required this.color,
    required this.showLine,
  });

  final String label;
  final String? time;
  final Color color;
  final bool showLine;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final done = time != null;

    return SizedBox(
      height: showLine ? 44 : 24,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 16,
            child: Column(
              children: [
                Container(
                  width: 14,
                  height: 14,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: done ? color : Colors.transparent,
                    border: Border.all(color: color, width: 2),
                  ),
                ),
                if (showLine)
                  Expanded(
                    child: Container(width: 2, color: color.withValues(alpha: 0.35)),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Row(
              children: [
                Text(label, style: theme.textTheme.bodyLarge),
                const Spacer(),
                Text(
                  time ?? '-',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: done ? null : theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SummaryTiles extends StatelessWidget {
  const _SummaryTiles({required this.attendance});

  final ParentChildAttendance attendance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Last ${attendance.records.length} school days',
          style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _StatTile(
                label: 'On site',
                value: attendance.daysOnSite,
                color: const Color(0xFF1B873F),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _StatTile(
                label: 'Absent',
                value: attendance.absentDays,
                color: theme.colorScheme.error,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _StatTile(
                label: 'Days shown',
                value: attendance.records.length,
                color: theme.colorScheme.outline,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({required this.label, required this.value, required this.color});

  final String label;
  final int value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$value',
            style: theme.textTheme.headlineSmall?.copyWith(
              color: color,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _DayRow extends StatelessWidget {
  const _DayRow({required this.record, required this.today});

  final AttendanceHistoryRecord record;
  final DateTime? today;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tone = _toneOf(context, record.status, today: false);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: tone.color.withValues(alpha: 0.12),
            child: Icon(tone.icon, color: tone.color, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _labelFor(record.date, today),
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
                Text(
                  _dayWord(record.status),
                  style: theme.textTheme.bodySmall?.copyWith(color: tone.color),
                ),
              ],
            ),
          ),
          Text(
            _timesFor(record),
            textAlign: TextAlign.right,
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
