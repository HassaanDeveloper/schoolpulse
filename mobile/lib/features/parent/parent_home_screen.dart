import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../attendance/attendance_report_repository.dart';
import '../auth/auth_controller.dart';
import '../notifications/notification_repository.dart';
import '../notifications/notifications_screen.dart';
import 'child_attendance_screen.dart';
import 'parent_repository.dart';

/// Home screen for a parent account.
///
/// Shows the children a school has linked to this account and the unread
/// notification badge. Scanner, QR management and the staff dashboard are not
/// reachable from here, and this screen never offers them.
class ParentHomeScreen extends StatefulWidget {
  const ParentHomeScreen({
    super.key,
    this.auth,
    this.parentRepository,
    this.notificationRepository,
    this.schoolId,
  });

  /// When supplied, the screen offers a sign-out action.
  final AuthController? auth;

  /// Injectable for tests; defaults to the real API-backed repositories.
  final ParentRepository? parentRepository;
  final NotificationRepository? notificationRepository;

  /// Restricts the view to one school, when the parent belongs to several.
  final String? schoolId;

  @override
  State<ParentHomeScreen> createState() => _ParentHomeScreenState();
}

class _ParentHomeScreenState extends State<ParentHomeScreen> {
  late final ParentRepository _parents;
  late final NotificationRepository _notifications;

  List<ParentChild>? _children;
  int _unreadCount = 0;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _parents = widget.parentRepository ?? const ParentRepository();
    _notifications = widget.notificationRepository ?? const NotificationRepository();
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
      // Both are needed for the first frame, so fetch together rather than
      // showing a badge count that is briefly wrong.
      final results = await Future.wait([
        _parents.fetchChildren(schoolId: widget.schoolId),
        _notifications.fetchUnreadCount(schoolId: widget.schoolId),
      ]);
      if (!mounted) {
        return;
      }
      setState(() {
        _children = results[0] as List<ParentChild>;
        _unreadCount = results[1] as int;
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

  Future<void> _openNotifications() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => NotificationsScreen(
          repository: widget.notificationRepository,
          schoolId: widget.schoolId,
          onUnreadCountChanged: _onUnreadCountChanged,
        ),
      ),
    );
    // The badge is refreshed on return rather than polled while the app is open.
    if (mounted) {
      await _refreshUnreadCount();
    }
  }

  void _onUnreadCountChanged(int count) {
    if (mounted) {
      setState(() => _unreadCount = count);
    }
  }

  Future<void> _refreshUnreadCount() async {
    try {
      final count = await _notifications.fetchUnreadCount(schoolId: widget.schoolId);
      if (mounted) {
        setState(() => _unreadCount = count);
      }
    } on ApiException {
      // A badge that cannot be refreshed keeps its last known value rather
      // than blanking the whole screen.
    }
  }

  void _openChild(ParentChild child) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ChildAttendanceScreen(
          child: child,
          repository: widget.parentRepository,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Children'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _load,
            icon: const Icon(Icons.refresh),
          ),
          _NotificationBell(count: _unreadCount, onPressed: _openNotifications),
          if (widget.auth != null)
            IconButton(
              tooltip: 'Log out',
              onPressed: () => widget.auth!.signOut(),
              icon: const Icon(Icons.logout),
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
      // Scrollable even while loading: RefreshIndicator requires a scrollable
      // child, and a bare Center would break the pull-to-refresh gesture.
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
            'Could not load your children.',
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

    final children = _children ?? const <ParentChild>[];
    if (children.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 48),
          Icon(Icons.family_restroom_outlined, size: 56, color: theme.colorScheme.primary),
          const SizedBox(height: 16),
          Text(
            'No children linked yet',
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            'Ask your school administrator to link your account to your child.',
            textAlign: TextAlign.center,
          ),
        ],
      );
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      children: [
        if (_unreadCount > 0)
          _UpdatesBanner(count: _unreadCount, onTap: _openNotifications),
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 10),
          child: Text(
            'Today at school',
            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        ...children.map(
          (child) => _ChildCard(child: child, onTap: () => _openChild(child)),
        ),
      ],
    );
  }
}

class _Tone {
  const _Tone(this.color, this.icon);

  final Color color;
  final IconData icon;
}

/// Colour and icon for the status the server resolved for the school's today.
///
/// "Not marked present" is amber rather than red: early in the morning it is
/// the normal state, and a parent should not be alarmed by it.
_Tone _toneFor(String? wireStatus) {
  switch (wireStatus) {
    case 'present':
      return const _Tone(Color(0xFF1B873F), Icons.check_circle_rounded);
    case 'completed':
      return const _Tone(Color(0xFF1F6FEB), Icons.logout_rounded);
    default:
      return const _Tone(Color(0xFFB26A00), Icons.schedule_rounded);
  }
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

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return CircleAvatar(
      radius: 26,
      backgroundColor: scheme.primaryContainer,
      child: Text(
        _initials(name),
        style: TextStyle(
          color: scheme.onPrimaryContainer,
          fontWeight: FontWeight.w800,
          fontSize: 16,
        ),
      ),
    );
  }
}

class _ChildCard extends StatelessWidget {
  const _ChildCard({required this.child, required this.onTap});

  final ParentChild child;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final label = child.todayStatusLabel;
    final tone = _toneFor(child.todayStatus);
    final date = parseDateOnly(child.todayStatusDate);

    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      elevation: 0,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: theme.colorScheme.outlineVariant),
      ),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _Avatar(name: child.fullName),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          child.fullName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          child.classLabel.isEmpty
                              ? child.schoolName
                              : '${child.classLabel} - ${child.schoolName}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant),
                ],
              ),
              if (label != null) ...[
                const SizedBox(height: 14),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: tone.color.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: tone.color.withValues(alpha: 0.25)),
                  ),
                  child: Row(
                    children: [
                      Icon(tone.icon, color: tone.color, size: 26),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              label,
                              style: theme.textTheme.titleSmall?.copyWith(
                                color: tone.color,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            Text(
                              date == null ? 'Today' : 'Today - ${formatDateOnly(date)}',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _UpdatesBanner extends StatelessWidget {
  const _UpdatesBanner({required this.count, required this.onTap});

  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Material(
        color: scheme.primaryContainer,
        borderRadius: BorderRadius.circular(18),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: scheme.primary,
                  child: Icon(Icons.notifications_active_rounded, color: scheme.onPrimary),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        count == 1 ? '1 new update' : '$count new updates',
                        style: theme.textTheme.titleSmall?.copyWith(
                          color: scheme.onPrimaryContainer,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      Text(
                        'Arrival and departure times for your children',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: scheme.onPrimaryContainer.withValues(alpha: 0.85),
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: scheme.onPrimaryContainer),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Notification icon with an unread count, hidden entirely when there is none.
class _NotificationBell extends StatelessWidget {
  const _NotificationBell({required this.count, required this.onPressed});

  final int count;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    if (count <= 0) {
      return IconButton(
        tooltip: 'Notifications',
        onPressed: onPressed,
        icon: const Icon(Icons.notifications_none),
      );
    }

    return Stack(
      alignment: Alignment.center,
      children: [
        IconButton(
          tooltip: 'Notifications',
          onPressed: onPressed,
          icon: const Icon(Icons.notifications),
        ),
        Positioned(
          top: 8,
          right: 6,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.error,
              borderRadius: BorderRadius.circular(10),
            ),
            constraints: const BoxConstraints(minWidth: 16),
            child: Text(
              count > 99 ? '99+' : '$count',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onError,
                fontSize: 10,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
