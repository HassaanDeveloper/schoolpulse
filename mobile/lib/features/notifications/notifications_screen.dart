import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import 'notification_repository.dart';

/// The parent's notification inbox.
///
/// Refreshes only on open, on pull-to-refresh and when a notice is marked read.
/// There is no polling, no stream and no push: this is Day 5, in-app only.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({
    super.key,
    this.repository,
    this.schoolId,
    this.onUnreadCountChanged,
  });

  /// Injectable for tests; defaults to the real API-backed repository.
  final NotificationRepository? repository;

  /// Restricts the inbox to one school, when the parent belongs to several.
  final String? schoolId;

  /// Reports the badge count back to the caller so the home screen can update.
  final ValueChanged<int>? onUnreadCountChanged;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late final NotificationRepository _repository;

  NotificationPage? _page;
  bool _loading = true;
  bool _unreadOnly = false;
  String? _error;
  final Set<String> _marking = <String>{};

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const NotificationRepository();
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
      final page = await _repository.fetchNotifications(
        schoolId: widget.schoolId,
        unreadOnly: _unreadOnly,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _page = page;
        _loading = false;
      });
      widget.onUnreadCountChanged?.call(page.unreadCount);
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

  Future<void> _toggleRead(AppNotification notification) async {
    if (_marking.contains(notification.id)) {
      return;
    }

    setState(() => _marking.add(notification.id));

    try {
      final updated = await _repository.markRead(notification.id);
      if (!mounted) {
        return;
      }

      final current = _page;
      if (current == null) {
        return;
      }

      final notifications = current.notifications
          .map((item) => item.id == updated.id ? updated : item)
          .toList(growable: false);
      final unread = notifications.where((item) => !item.isRead).length;

      setState(() {
        _page = NotificationPage(notifications: notifications, unreadCount: unread);
        _marking.remove(notification.id);
      });
      widget.onUnreadCountChanged?.call(unread);
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _marking.remove(notification.id));
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Row(
              children: [
                FilterChip(
                  label: const Text('Unread only'),
                  selected: _unreadOnly,
                  onSelected: (value) {
                    setState(() => _unreadOnly = value);
                    _load();
                  },
                ),
                const SizedBox(width: 12),
                if (_page != null)
                  Text(
                    '${_page!.unreadCount} unread',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
          ),
        ),
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: _buildBody(),
        ),
      ),
    );
  }

  Widget _buildBody() {
    final theme = Theme.of(context);

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
            'Could not load notifications.',
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

    final page = _page;
    if (page == null || page.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 48),
          Icon(Icons.notifications_none, size: 48, color: theme.colorScheme.primary),
          const SizedBox(height: 16),
          Text(
            _unreadOnly ? 'Nothing unread' : 'No notifications yet',
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'You will be notified here when attendance is recorded.',
            textAlign: TextAlign.center,
          ),
        ],
      );
    }

    return ListView(
      padding: const EdgeInsets.all(12),
      children: page.notifications.map(_tile).toList(),
    );
  }

  Widget _tile(AppNotification notification) {
    final theme = Theme.of(context);
    final busy = _marking.contains(notification.id);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      color: notification.isRead ? null : theme.colorScheme.surfaceContainerHighest,
      child: ListTile(
        leading: Icon(
          notification.type == NotificationType.departure
              ? Icons.logout
              : Icons.login,
          color: theme.colorScheme.primary,
        ),
        title: Text(
          notification.title,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: notification.isRead ? FontWeight.normal : FontWeight.bold,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 2),
            Text(notification.message),
            const SizedBox(height: 4),
            Text(
              _metaLabel(notification),
              style: theme.textTheme.bodySmall,
            ),
            if (notification.needsAttention)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  'Could not be delivered to this device channel. The attendance '
                  'record is unaffected.',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                ),
              ),
          ],
        ),
        isThreeLine: true,
        trailing: busy
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : TextButton(
                onPressed: notification.isRead ? null : () => _toggleRead(notification),
                child: Text(notification.isRead ? 'Read' : 'Mark read'),
              ),
        onTap: notification.isRead ? null : () => _toggleRead(notification),
      ),
    );
  }

  /// Builds the small line under the message: the type, plus the time the event
/// was recorded.
  ///
  /// [AppNotification.occurredTime] is already rendered by the server in the
  /// school's timezone. Formatting `occurredAt` on the device would re-express
  /// that instant in the phone's timezone and show a family a time the school
  /// never recorded, which is the bug fixed in Day 5.
  static String _metaLabel(AppNotification notification) {
    final type = notification.type.label;
    final time = notification.occurredTime;
    if (time == null) {
      return type;
    }
    return '$type - $time';
  }
}