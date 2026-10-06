import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'attendance_dashboard_screen.dart';
import 'attendance_report_repository.dart';

/// One student's attendance over a date range, for teachers and school admins.
///
/// Days with no attendance record are shown as ABSENT rather than hidden, which
/// is why the list is driven by the requested range and not by scan events.
class StudentAttendanceScreen extends StatefulWidget {
  const StudentAttendanceScreen({
    super.key,
    required this.studentId,
    required this.studentName,
    this.admissionNumber,
    this.schoolId,
    this.repository,
    this.pageSize = 20,
    this.today,
  });

  final String studentId;
  final String studentName;
  final String? admissionNumber;
  final String? schoolId;

  /// Injectable for tests; defaults to the real API-backed repository.
  final AttendanceReportRepository? repository;

  final int pageSize;

  /// Overrides "today" when picking the default range, so the default range is
  /// anchored to the school's local date rather than the device's.
  final DateTime? today;

  @override
  State<StudentAttendanceScreen> createState() => _StudentAttendanceScreenState();
}

class _StudentAttendanceScreenState extends State<StudentAttendanceScreen> {
  /// Mirrors the server's own limit so the UI cannot request an invalid range.
  static const int maxRangeDays = 90;

  late final AttendanceReportRepository _repository;
  late DateTime _startDate;
  late DateTime _endDate;

  StudentAttendanceDetail? _detail;
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  int _pageNumber = 1;
  bool _rangeOpen = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const AttendanceReportRepository();
    final today = _today();
    _endDate = today;
    _startDate = today.subtract(const Duration(days: 6));
    _load();
  }

  /// The device's today, or the injected value. The server still decides the
  /// real school-local date when no range is sent.
  DateTime _today() {
    final now = DateTime.now();
    final provided = widget.today;
    if (provided == null) {
      return DateTime(now.year, now.month, now.day);
    }
    return DateTime(provided.year, provided.month, provided.day);
  }

  Future<void> _load({bool append = false}) async {
    if (!mounted) {
      return;
    }
    setState(() {
      if (append) {
        _loadingMore = true;
      } else {
        _loading = true;
      }
      _error = null;
    });

    try {
      final detail = await _repository.fetchStudentDetail(
        studentId: widget.studentId,
        schoolId: widget.schoolId,
        startDate: _startDate,
        endDate: _endDate,
        page: _pageNumber,
        pageSize: widget.pageSize,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _detail = detail;
        _loading = false;
        _loadingMore = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.message;
        _loading = false;
        _loadingMore = false;
      });
    }
  }

  void _applyPreset(int days) {
    setState(() {
      _endDate = _today();
      _startDate = _endDate.subtract(Duration(days: days - 1));
      _pageNumber = 1;
    });
    _load();
  }

  /// Applies an explicit range, rejecting the ones the server would refuse.
  void _applyCustomRange(DateTime start, DateTime end) {
    final days = end.difference(start).inDays + 1;

    if (start.isAfter(end)) {
      _showMessage('The start date must be on or before the end date.');
      return;
    }
    if (days > maxRangeDays) {
      _showMessage('Choose a range of $maxRangeDays days or fewer.');
      return;
    }

    setState(() {
      _startDate = start;
      _endDate = end;
      _pageNumber = 1;
    });
    _load();
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _changePage(int next) async {
    final detail = _detail;
    if (detail == null || next < 1 || next > detail.pageCount) {
      return;
    }
    setState(() {
      _pageNumber = next;
      _loadingMore = true;
    });
    await _load(append: true);
  }

  Future<void> _pickRange() async {
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: _today().add(const Duration(days: 365)),
      initialDateRange: DateTimeRange(start: _startDate, end: _endDate),
    );

    if (picked != null) {
      _applyCustomRange(picked.start, picked.end);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Student attendance'),
        actions: [
          IconButton(
            tooltip: 'Date range',
            onPressed: _loading ? null : () => setState(() => _rangeOpen = !_rangeOpen),
            icon: Icon(_rangeOpen ? Icons.date_range : Icons.date_range_outlined),
          ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null && _detail == null
                ? _DetailError(message: _error!, onRetry: _load)
                : RefreshIndicator(onRefresh: _load, child: _buildBody()),
      ),
    );
  }

  Widget _buildBody() {
    final detail = _detail;
    if (detail == null) {
      return const Center(child: Text('No attendance history.'));
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      children: [
        Text(widget.studentName, style: Theme.of(context).textTheme.headlineSmall),
        Text(
          [
            if (widget.admissionNumber != null && widget.admissionNumber!.isNotEmpty)
              widget.admissionNumber!,
            if (detail.student.className.isNotEmpty) detail.student.classLabel,
          ].join(' - '),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        _RangeBar(
          start: _startDate,
          end: _endDate,
          open: _rangeOpen,
          onPreset: _applyPreset,
          onCustom: _pickRange,
        ),
        if (_rangeOpen)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text('Ranges are limited to 90 days.'),
          ),
        const SizedBox(height: 16),
        _SummaryStrip(summary: detail.summary),
        const SizedBox(height: 20),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (detail.records.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 48),
            child: Center(child: Text('No days in this range.')),
          )
        else ...[
          Text(
            '${detail.total} day${detail.total == 1 ? '' : 's'}',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(height: 8),
          ...detail.records.map((record) => _HistoryTile(record: record)),
          if (detail.pageCount > 1)
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton.icon(
                  onPressed: detail.hasPreviousPage && !_loadingMore
                      ? () => _changePage(detail.page - 1)
                      : null,
                  icon: const Icon(Icons.chevron_left),
                  label: const Text('Previous'),
                ),
                Text('Page ${detail.page} of ${detail.pageCount}'),
                TextButton.icon(
                  onPressed: detail.hasNextPage && !_loadingMore
                      ? () => _changePage(detail.page + 1)
                      : null,
                  icon: const Icon(Icons.chevron_right),
                  iconAlignment: IconAlignment.end,
                  label: const Text('Next'),
                ),
              ],
            ),
        ],
      ],
    );
  }
}

/// Quick ranges plus a custom picker.
class _RangeBar extends StatelessWidget {
  const _RangeBar({
    required this.start,
    required this.end,
    required this.open,
    required this.onPreset,
    required this.onCustom,
  });

  final DateTime start;
  final DateTime end;
  final bool open;
  final ValueChanged<int> onPreset;
  final VoidCallback onCustom;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${formatDateOnly(start)}  to  ${formatDateOnly(end)}',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                ActionChip(label: const Text('Last 7 days'), onPressed: () => onPreset(7)),
                ActionChip(label: const Text('Last 30 days'), onPressed: () => onPreset(30)),
                ActionChip(
                  label: Text(open ? 'Hide range' : 'Custom range'),
                  onPressed: onCustom,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryStrip extends StatelessWidget {
  const _SummaryStrip({required this.summary});

  final StudentAttendanceSummary summary;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _Metric(label: 'On site', value: '${summary.daysOnSite}'),
            _Metric(label: 'Absent', value: '${summary.absentDays}'),
            _Metric(label: 'Days', value: '${summary.totalDays}'),
            _Metric(
              label: 'Rate',
              value: '${(summary.attendanceRate * 100).round()}%',
              valueStyle: theme.textTheme.titleMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, this.valueStyle});

  final String label;
  final String value;
  final TextStyle? valueStyle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      children: [
        Text(value, style: valueStyle ?? theme.textTheme.titleMedium),
        const SizedBox(height: 2),
        Text(label, style: theme.textTheme.labelSmall),
      ],
    );
  }
}

class _HistoryTile extends StatelessWidget {
  const _HistoryTile({required this.record});

  final AttendanceHistoryRecord record;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        dense: true,
        leading: StatusDot(status: record.status),
        title: Text(formatDateOnly(record.date)),
        subtitle: Text(_times(record)),
        trailing: Text(
          record.status.label,
          style: TextStyle(color: statusColor(context, record.status)),
        ),
      ),
    );
  }

  static String _times(AttendanceHistoryRecord record) {
    final arrival = _clock(record.arrivalAt);
    final departure = _clock(record.departureAt);

    if (arrival == null) {
      return 'No record';
    }
    if (departure == null) {
      return 'Arrived $arrival';
    }
    return 'Arrived $arrival - left $departure';
  }

  static String? _clock(DateTime? value) {
    if (value == null) {
      return null;
    }
    final String hour = value.hour.toString().padLeft(2, '0');
    final String minute = value.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }
}

class _DetailError extends StatelessWidget {
  const _DetailError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 48),
        Icon(Icons.person_off_outlined, size: 48, color: theme.colorScheme.error),
        const SizedBox(height: 16),
        Text(
          'Could not load this student.',
          textAlign: TextAlign.center,
          style: theme.textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        Center(
          child: FilledButton.tonal(onPressed: onRetry, child: const Text('Try again')),
        ),
      ],
    );
  }
}
