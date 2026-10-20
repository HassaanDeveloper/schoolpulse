import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'attendance_report_repository.dart';
import 'student_attendance_screen.dart';

/// Read-only attendance dashboard for teachers and school admins.
///
/// The screen shows the school's local today. It never sends a date: the server
/// owns the timezone decision, and the client never writes attendance.
class AttendanceDashboardScreen extends StatefulWidget {
  const AttendanceDashboardScreen({
    super.key,
    this.schoolId,
    this.repository,
    this.pageSize = 20,
  });

  /// Which school to display. Required when the user belongs to more than one.
  final String? schoolId;

  /// Injectable for tests; defaults to the real API-backed repository.
  final AttendanceReportRepository? repository;

  final int pageSize;

  @override
  State<AttendanceDashboardScreen> createState() => _AttendanceDashboardScreenState();
}

class _AttendanceDashboardScreenState extends State<AttendanceDashboardScreen> {
  late final AttendanceReportRepository _repository;

  AttendanceSummary? _summary;
  TodayAttendancePage? _page;
  List<AttendanceClassOption> _classes = const <AttendanceClassOption>[];

  final TextEditingController _searchController = TextEditingController();
  Timer? _searchDebounce;

  int _pageNumber = 1;
  AttendanceStatus? _statusFilter;
  String? _classFilter;
  String _search = '';

  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  bool _filtersOpen = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const AttendanceReportRepository();
    unawaited(_load());
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController.dispose();
    super.dispose();
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
      // The class list is a convenience for the filter; a failure here must not
      // hide the attendance itself.
      final classesFuture = _loadClasses();

      final results = await Future.wait([
        _repository.fetchSummary(schoolId: widget.schoolId, classId: _classFilter),
        _repository.fetchToday(
          schoolId: widget.schoolId,
          classId: _classFilter,
          status: _statusFilter,
          search: _search,
          page: _pageNumber,
          pageSize: widget.pageSize,
        ),
      ]);

      await classesFuture;

      if (!mounted) {
        return;
      }
      setState(() {
        _summary = results[0] as AttendanceSummary;
        _page = results[1] as TodayAttendancePage;
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
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = 'Could not load attendance.';
        _loading = false;
      });
    }
  }

  Future<void> _loadClasses() async {
    try {
      final classes = await _repository.fetchFilterClasses(schoolId: widget.schoolId);
      if (mounted) {
        setState(() => _classes = classes);
      }
    } on ApiException {
      // The filter simply stays unavailable.
    }
  }

  /// Applies a filter from scratch, returning to page 1.
  void _applyFilter(VoidCallback update) {
    setState(update);
    _pageNumber = 1;
    unawaited(_load());
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 350), () {
      _applyFilter(() => _search = value);
    });
  }

  Future<void> _changePage(int next) async {
    if (_page == null || next < 1 || next > _page!.pageCount) {
      return;
    }

    setState(() {
      _loadingMore = true;
      _pageNumber = next;
    });

    try {
      final page = await _repository.fetchToday(
        schoolId: widget.schoolId,
        classId: _classFilter,
        status: _statusFilter,
        search: _search,
        page: next,
        pageSize: widget.pageSize,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _page = page;
        _loadingMore = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadingMore = false;
        _error = error.message;
      });
    }
  }

  Future<void> _refresh() => _load();

  void _openStudent(TodayAttendanceItem item) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => StudentAttendanceScreen(
          studentId: item.studentId,
          studentName: item.studentName,
          admissionNumber: item.admissionNumber,
          schoolId: widget.schoolId,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Attendance'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _refresh,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: 'Filters',
            onPressed: () => setState(() => _filtersOpen = !_filtersOpen),
            icon: Icon(_filtersOpen ? Icons.filter_alt : Icons.filter_alt_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null && _summary == null
                ? _ErrorView(message: _error!, onRetry: _refresh)
                : RefreshIndicator(
                    onRefresh: _refresh,
                    child: _buildBody(),
                  ),
      ),
    );
  }

  Widget _buildBody() {
    final summary = _summary;
    final page = _page;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      children: [
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: _ErrorBanner(message: _error!),
          ),
        if (summary != null) ...[
          _HeaderCard(summary: summary),
          const SizedBox(height: 12),
          _SummaryRow(summary: summary),
          const SizedBox(height: 20),
        ],
        _SearchField(
          controller: _searchController,
          onChanged: _onSearchChanged,
          onClear: () {
            _searchController.clear();
            _applyFilter(() => _search = '');
          },
        ),
        const SizedBox(height: 12),
        if (_filtersOpen) ...[
          _FilterPanel(
            classes: _classes,
            status: _statusFilter,
            classId: _classFilter,
            onStatusChanged: (value) => _applyFilter(() => _statusFilter = value),
            onClassChanged: (value) => _applyFilter(() => _classFilter = value),
          ),
          const SizedBox(height: 12),
        ],
        if (_hasActiveFilters)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () {
                _searchController.clear();
                _applyFilter(() {
                  _statusFilter = null;
                  _classFilter = null;
                  _search = '';
                });
              },
              icon: const Icon(Icons.clear),
              label: const Text('Clear filters'),
            ),
          ),
        if (page == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 48),
            child: Center(child: Text('No attendance data.')),
          )
        else if (page.items.isEmpty)
          _EmptyView(
            filtered: _hasActiveFilters,
            onClear: () {
              _searchController.clear();
              _applyFilter(() {
                _statusFilter = null;
                _classFilter = null;
                _search = '';
              });
            },
          )
        else ...[
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 10),
            child: Text(
              '${page.total} student${page.total == 1 ? '' : 's'}',
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          ...page.items.map(
            (item) => _StudentRow(
              item: item,
              timesLine: _timesLine(item),
              onTap: () => _openStudent(item),
            ),
          ),
          if (page.pageCount > 1)
            _Pager(
              page: page.page,
              pageCount: page.pageCount,
              loading: _loadingMore,
              onPrevious: () => _changePage(page.page - 1),
              onNext: () => _changePage(page.page + 1),
            ),
        ],
      ],
    );
  }

  bool get _hasActiveFilters =>
      _statusFilter != null || _classFilter != null || _search.trim().isNotEmpty;

  String _timesLine(TodayAttendanceItem item) {
    final arrival = _formatTime(item.arrivalAt);
    final departure = _formatTime(item.departureAt);

    if (arrival == null && departure == null) {
      return 'No scan yet today';
    }
    if (departure == null) {
      return 'Arrived $arrival';
    }
    return 'Arrived $arrival  \u00B7  Left $departure';
  }

  static String? _formatTime(DateTime? value) {
    if (value == null) {
      return null;
    }
    final String hour = value.hour.toString().padLeft(2, '0');
    final String minute = value.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }
}

/// Plain-language words for each status, used everywhere on this screen.
String _statusWord(AttendanceStatus status) {
  return switch (status) {
    AttendanceStatus.present => 'In school',
    AttendanceStatus.completed => 'Went home',
    AttendanceStatus.absent => 'Absent',
    AttendanceStatus.unknown => 'Unknown',
  };
}

IconData _statusIcon(AttendanceStatus status) {
  return switch (status) {
    AttendanceStatus.present => Icons.check_circle_outline,
    AttendanceStatus.completed => Icons.logout_rounded,
    AttendanceStatus.absent => Icons.person_off_outlined,
    AttendanceStatus.unknown => Icons.help_outline,
  };
}

/// The initials shown in a student's avatar, for example "Ali Khan" -> "AK".
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

/// The school, the local date, and how much of the school has arrived.
class _HeaderCard extends StatelessWidget {
  const _HeaderCard({required this.summary});

  final AttendanceSummary summary;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final onColor = scheme.onPrimaryContainer;
    final date = summary.date;

    final total = summary.present + summary.completed + summary.absent;
    final arrived = summary.present + summary.completed;
    final rate = total == 0 ? 0.0 : arrived / total;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: scheme.primaryContainer,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            summary.schoolName,
            style: theme.textTheme.titleLarge?.copyWith(
              color: onColor,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            date == null ? 'Today' : '${_weekday(date)}, ${formatDateOnly(date)}',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: onColor.withValues(alpha: 0.8),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${(rate * 100).round()}%',
                style: theme.textTheme.displaySmall?.copyWith(
                  color: onColor,
                  fontWeight: FontWeight.w800,
                  height: 1,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    total == 0
                        ? 'No students enrolled yet'
                        : '$arrived of $total students have arrived',
                    style: theme.textTheme.bodyMedium?.copyWith(color: onColor),
                  ),
                ),
              ),
            ],
          ),
          if (total > 0) ...[
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: rate,
                minHeight: 8,
                backgroundColor: onColor.withValues(alpha: 0.15),
                valueColor: AlwaysStoppedAnimation<Color>(scheme.primary),
              ),
            ),
          ],
        ],
      ),
    );
  }

  static String _weekday(DateTime value) {
    const names = <String>[
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ];
    return names[value.weekday - 1];
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({required this.summary});

  final AttendanceSummary summary;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _SummaryCard(
            label: 'In school',
            value: summary.present,
            status: AttendanceStatus.present,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SummaryCard(
            label: 'Went home',
            value: summary.completed,
            status: AttendanceStatus.completed,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SummaryCard(
            label: 'Absent',
            value: summary.absent,
            status: AttendanceStatus.absent,
          ),
        ),
      ],
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({
    required this.label,
    required this.value,
    required this.status,
  });

  final String label;
  final int value;
  final AttendanceStatus status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = statusColor(context, status);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        children: [
          Icon(_statusIcon(status), color: color, size: 22),
          const SizedBox(height: 6),
          Text(
            '$value',
            style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: theme.textTheme.labelMedium,
          ),
        ],
      ),
    );
  }
}

/// One student: initials, name, class, today's times and a status chip.
class _StudentRow extends StatelessWidget {
  const _StudentRow({
    required this.item,
    required this.timesLine,
    required this.onTap,
  });

  final TodayAttendanceItem item;
  final String timesLine;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              _Avatar(name: item.studentName),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.studentName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${item.admissionNumber} - ${item.classLabel}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      timesLine,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              _StatusChip(status: item.status),
            ],
          ),
        ),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return CircleAvatar(
      radius: 24,
      backgroundColor: scheme.secondaryContainer,
      child: Text(
        _initials(name),
        style: TextStyle(
          color: scheme.onSecondaryContainer,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final AttendanceStatus status;

  @override
  Widget build(BuildContext context) {
    final color = statusColor(context, status);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_statusIcon(status), size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            _statusWord(status),
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w700,
                ),
          ),
        ],
      ),
    );
  }
}

/// Coloured dot for a derived status.
class StatusDot extends StatelessWidget {
  const StatusDot({super.key, required this.status});

  final AttendanceStatus status;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(color: statusColor(context, status), shape: BoxShape.circle),
    );
  }
}

/// One consistent colour per status across the whole app.
Color statusColor(BuildContext context, AttendanceStatus status) {
  final scheme = Theme.of(context).colorScheme;
  return switch (status) {
    AttendanceStatus.present => const Color(0xFF1B873F),
    AttendanceStatus.completed => const Color(0xFF1F6FEB),
    AttendanceStatus.absent => scheme.error,
    AttendanceStatus.unknown => scheme.outline,
  };
}

/// Round badge showing the status as an icon in the status colour.
class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.status});

  final AttendanceStatus status;

  @override
  Widget build(BuildContext context) {
    final color = statusColor(context, status);

    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Icon(_statusIcon(status), color: color, size: 22),
    );
  }
}

class _SearchField extends StatelessWidget {
  const _SearchField({
    required this.controller,
    required this.onChanged,
    required this.onClear,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        prefixIcon: const Icon(Icons.search),
        hintText: 'Search name or admission number',
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        suffixIcon: ValueListenableBuilder<TextEditingValue>(
          valueListenable: controller,
          builder: (context, value, _) {
            if (value.text.isEmpty) {
              return const SizedBox.shrink();
            }
            return IconButton(
              tooltip: 'Clear search',
              onPressed: onClear,
              icon: const Icon(Icons.close),
            );
          },
        ),
      ),
    );
  }
}

class _FilterPanel extends StatelessWidget {
  const _FilterPanel({
    required this.classes,
    required this.status,
    required this.classId,
    required this.onStatusChanged,
    required this.onClassChanged,
  });

  final List<AttendanceClassOption> classes;
  final AttendanceStatus? status;
  final String? classId;
  final ValueChanged<AttendanceStatus?> onStatusChanged;
  final ValueChanged<String?> onClassChanged;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Status', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                ChoiceChip(
                  label: const Text('All'),
                  selected: status == null,
                  onSelected: (_) => onStatusChanged(null),
                ),
                for (final option in AttendanceStatus.values.where((s) => s != AttendanceStatus.unknown))
                  ChoiceChip(
                    label: Text(_statusWord(option)),
                    selected: status == option,
                    onSelected: (_) => onStatusChanged(status == option ? null : option),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Class', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            if (classes.isEmpty)
              const Text('No classes available to filter.')
            else
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  ChoiceChip(
                    label: const Text('All classes'),
                    selected: classId == null,
                    onSelected: (_) => onClassChanged(null),
                  ),
                  for (final option in classes)
                    ChoiceChip(
                      label: Text(option.label),
                      selected: classId == option.id,
                      onSelected: (_) => onClassChanged(classId == option.id ? null : option.id),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _Pager extends StatelessWidget {
  const _Pager({
    required this.page,
    required this.pageCount,
    required this.loading,
    required this.onPrevious,
    required this.onNext,
  });

  final int page;
  final int pageCount;
  final bool loading;
  final VoidCallback onPrevious;
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        TextButton.icon(
          onPressed: page > 1 && !loading ? onPrevious : null,
          icon: const Icon(Icons.chevron_left),
          label: const Text('Previous'),
        ),
        Text('Page $page of $pageCount'),
        TextButton.icon(
          onPressed: page < pageCount && !loading ? onNext : null,
          icon: const Icon(Icons.chevron_right),
          iconAlignment: IconAlignment.end,
          label: const Text('Next'),
        ),
      ],
    );
  }
}

class _EmptyView extends StatelessWidget {
  const _EmptyView({required this.filtered, required this.onClear});

  final bool filtered;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Column(
        children: [
          const Icon(Icons.inbox_outlined, size: 48),
          const SizedBox(height: 12),
          Text(
            filtered
                ? 'No students match these filters.'
                : 'No students to show yet.',
            textAlign: TextAlign.center,
          ),
          if (filtered) ...[
            const SizedBox(height: 8),
            TextButton(onPressed: onClear, child: const Text('Clear filters')),
          ],
        ],
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_outlined, color: theme.colorScheme.onErrorContainer),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: theme.colorScheme.onErrorContainer),
            ),
          ),
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

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
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        Center(
          child: FilledButton.tonal(onPressed: onRetry, child: const Text('Try again')),
        ),
      ],
    );
  }
}
