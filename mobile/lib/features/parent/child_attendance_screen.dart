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
      padding: const EdgeInsets.all(16),
      children: [
        _SummaryCard(attendance: attendance),
        const SizedBox(height: 16),
        _TodaySection(record: todayRecord, child: widget.child),
        const SizedBox(height: 16),
        Text('History', style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        if (history.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('No earlier days in this range.'),
          )
        else
          ...history.take(widget.pageSize).map((record) => _dayTile(record, today)),
      ],
    );
  }

  static bool _sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  Widget _dayTile(AttendanceHistoryRecord record, DateTime? today) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(_iconFor(record.status), color: _colorFor(context, record.status)),
        title: Text(_labelFor(record.date, today)),
        subtitle: Text(record.status.label),
        trailing: Text(
          _timesFor(record),
          textAlign: TextAlign.right,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ),
    );
  }

  static IconData _iconFor(AttendanceStatus status) => switch (status) {
        AttendanceStatus.present => Icons.check_circle_outline,
        AttendanceStatus.completed => Icons.done_all,
        AttendanceStatus.absent => Icons.cancel_outlined,
        AttendanceStatus.unknown => Icons.help_outline,
      };

  static Color _colorFor(BuildContext context, AttendanceStatus status) =>
      switch (status) {
        AttendanceStatus.present => Theme.of(context).colorScheme.primary,
        AttendanceStatus.completed => Theme.of(context).colorScheme.primary,
        AttendanceStatus.absent => Theme.of(context).colorScheme.error,
        AttendanceStatus.unknown => Theme.of(context).colorScheme.outline,
      };

  /// Labels relative to the server's today, not the device's.
  static String _labelFor(DateTime date, DateTime? today) {
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

  static String _timesFor(AttendanceHistoryRecord record) {
    final arrival = record.arrivalTime ?? _localTime(record.arrivalAt);
    final departure = record.departureTime ?? _localTime(record.departureAt);
    if (arrival == null && departure == null) {
      return 'No times';
    }
    if (departure == null) {
      return 'In $arrival';
    }
    return '$arrival - $departure';
  }

  /// Only used when the server did not send a preformatted time. The Day 5
  /// parent endpoint always does, so a scan time is never recomputed from the
  /// phone's clock on the parent screens.
  static String? _localTime(DateTime? value) {
    if (value == null) {
      return null;
    }
    final local = value.toLocal();
    final hour = local.hour % 12 == 0 ? 12 : local.hour % 12;
    final minute = local.minute.toString().padLeft(2, '0');
    final suffix = local.hour >= 12 ? 'PM' : 'AM';
    return '$hour:$minute $suffix';
  }
}

class _TodaySection extends StatelessWidget {
  const _TodaySection({required this.record, required this.child});

  final AttendanceHistoryRecord? record;
  final ParentChild child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final today = record;
    // Prefer the record from the range; fall back to the status the children
    // list resolved when the chosen range does not reach today.
    final wireStatus = child.todayStatus;
    final status = today?.status ??
        (wireStatus == null ? null : _statusFromWire(wireStatus));
    final date = today?.date ?? parseDateOnly(child.todayStatusDate);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Today', style: theme.textTheme.titleSmall),
                const Spacer(),
                if (date != null)
                  Text(formatDateOnly(date), style: theme.textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 12),
            if (status == null)
              const Text('Nothing recorded for today yet.')
            else ...[
              Row(
                children: [
                  Icon(
                    _iconFor(status),
                    color: _colorFor(context, status),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      status.label,
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: _colorFor(context, status),
                      ),
                    ),
                  ),
                ],
              ),
              if (today != null) ...[
                const SizedBox(height: 12),
                Text(_timesFor(today), style: theme.textTheme.bodyMedium),
              ],
            ],
          ],
        ),
      ),
    );
  }

  /// Falls back to the children-list status when the selected range does not
  /// reach today.
  static AttendanceStatus? _statusFromWire(String value) => switch (value) {
        'present' => AttendanceStatus.present,
        'completed' => AttendanceStatus.completed,
        'absent' => AttendanceStatus.absent,
        _ => null,
      };

  static IconData _iconFor(AttendanceStatus status) => switch (status) {
        AttendanceStatus.present => Icons.check_circle_outline,
        AttendanceStatus.completed => Icons.done_all,
        AttendanceStatus.absent => Icons.cancel_outlined,
        AttendanceStatus.unknown => Icons.help_outline,
      };

  static Color _colorFor(BuildContext context, AttendanceStatus status) =>
      switch (status) {
        AttendanceStatus.present => Theme.of(context).colorScheme.primary,
        AttendanceStatus.completed => Theme.of(context).colorScheme.primary,
        AttendanceStatus.absent => Theme.of(context).colorScheme.error,
        AttendanceStatus.unknown => Theme.of(context).colorScheme.outline,
      };

  static String _timesFor(AttendanceHistoryRecord record) {
    final arrival = record.arrivalTime ?? _localTime(record.arrivalAt);
    final departure = record.departureTime ?? _localTime(record.departureAt);
    if (arrival == null && departure == null) {
      return 'No times';
    }
    if (departure == null) {
      return 'In $arrival';
    }
    return '$arrival - $departure';
  }

  /// Only used when the server did not send a preformatted time. The parent
  /// endpoint always does, so scan times are never recomputed from the phone's
  /// clock.
  static String? _localTime(DateTime? value) {
    if (value == null) {
      return null;
    }
    final local = value.toLocal();
    final hour = local.hour % 12 == 0 ? 12 : local.hour % 12;
    final minute = local.minute.toString().padLeft(2, '0');
    final suffix = local.hour >= 12 ? 'PM' : 'AM';
    return '$hour:$minute $suffix';
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.attendance});

  final ParentChildAttendance attendance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Last ${attendance.records.length} school days', style: theme.textTheme.titleSmall),
            const SizedBox(height: 12),
            Row(
              children: [
                _Stat(label: 'On site', value: attendance.daysOnSite, color: theme.colorScheme.primary),
                _Stat(label: 'Absent', value: attendance.absentDays, color: theme.colorScheme.error),
                _Stat(label: 'Days shown', value: attendance.records.length, color: theme.colorScheme.outline),
              ],
            ),
            if (attendance.latest != null) ...[
              const SizedBox(height: 12),
              Text(
                'Most recent: ${attendance.latest!.status.label}',
                style: theme.textTheme.bodyMedium,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value, required this.color});

  final String label;
  final int value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$value', style: theme.textTheme.headlineSmall?.copyWith(color: color)),
          Text(label, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}