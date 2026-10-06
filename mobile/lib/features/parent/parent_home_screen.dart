import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
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
          Icon(Icons.family_restroom_outlined, size: 48, color: theme.colorScheme.primary),
          const SizedBox(height: 16),
          Text(
            'No children linked yet',
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium,
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
      padding: const EdgeInsets.all(16),
      children: [
        if (_unreadCount > 0)
          Card(
            margin: const EdgeInsets.only(bottom: 12),
            color: theme.colorScheme.primaryContainer,
            child: ListTile(
              leading: const Icon(Icons.notifications_active_outlined),
              title: Text(
                _unreadCount == 1 ? '1 new update' : '$_unreadCount new updates',
              ),
              subtitle: const Text('Arrival and departure times for your children'),
              trailing: const Icon(Icons.chevron_right),
              onTap: _openNotifications,
            ),
          ),
        ...children.map(_childCard),
      ],
    );
  }

  Widget _childCard(ParentChild child) {
    final status = child.todayStatusLabel;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: const Icon(Icons.person_outline),
        title: Text(child.fullName),
        // Today's status sits above the class line: it is the reason a parent
        // opens this screen, and class/school is supporting detail.
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (status != null) ...[
              Text(
                status,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurface,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 2),
            ],
            Text(
              child.classLabel.isEmpty
                  ? child.schoolName
                  : '${child.classLabel} - ${child.schoolName}',
            ),
          ],
        ),
        isThreeLine: status != null,
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => ChildAttendanceScreen(
              child: child,
              repository: widget.parentRepository,
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