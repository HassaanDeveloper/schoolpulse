import '../../core/network/api_client.dart';
import '../attendance/attendance_report_repository.dart';

/// Which attendance event a notice is about.
enum NotificationType {
  arrival,
  departure,
  unknown;

  static NotificationType parse(String? value) => switch (value) {
        'arrival' => NotificationType.arrival,
        'departure' => NotificationType.departure,
        _ => NotificationType.unknown,
      };

  String get label => switch (this) {
        NotificationType.arrival => 'Arrival',
        NotificationType.departure => 'Departure',
        NotificationType.unknown => 'Update',
      };
}

/// Delivery state as reported by the server.
///
/// [sent] means the notice was created in SchoolPulse. It does not mean any
/// external channel delivered anything.
enum NotificationStatus {
  queued,
  sent,
  failed,
  unknown;

  static NotificationStatus parse(String? value) => switch (value) {
        'queued' => NotificationStatus.queued,
        'sent' => NotificationStatus.sent,
        'failed' => NotificationStatus.failed,
        _ => NotificationStatus.unknown,
      };
}

/// Treats a blank string as absent, so an unresolved school shows nothing
/// rather than an empty label.
String? _nonEmpty(String? value) {
  if (value == null) {
    return null;
  }
  final trimmed = value.trim();
  return trimmed.isEmpty ? null : trimmed;
}

/// One in-app notice, from `GET /api/v1/me/notifications`.
///
/// The payload carries no parent id, no student id and no staff identity: the
/// list is already scoped to the caller, so there is nothing to identify the
/// recipient or the scanning teacher.
class AppNotification {
  const AppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.message,
    required this.status,
    required this.occurredAt,
    this.occurredTime,
    required this.readAt,
    required this.createdAt,
  });

  final String id;
  final NotificationType type;
  final String title;
  final String message;
  final NotificationStatus status;

  /// When the attendance event happened, as reported by the server.
  final DateTime? occurredAt;

  /// [occurredAt] already rendered in the school's own timezone, e.g. `8:04 AM`.
  ///
  /// Shown instead of a device-converted time: a parent travelling abroad must
  /// still see the time the school recorded. Null when the server could not
  /// resolve the school, so the app can stay silent rather than guess.
  final String? occurredTime;

  final DateTime? readAt;
  final DateTime? createdAt;

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: '${json['id']}',
      type: NotificationType.parse(json['type'] as String?),
      title: json['title'] as String? ?? '',
      message: json['message'] as String? ?? '',
      status: NotificationStatus.parse(json['status'] as String?),
      occurredAt: parseInstant(json['occurred_at']),
      occurredTime: _nonEmpty(json['occurred_time'] as String?),
      readAt: parseInstant(json['read_at']),
      createdAt: parseInstant(json['created_at']),
    );
  }

  bool get isRead => readAt != null;

  /// Unread failed notices are surfaced rather than hidden, so a broken
  /// channel cannot silently deprive a parent of an attendance event.
  bool get needsAttention => status == NotificationStatus.failed;
}

/// The inbox plus its badge count, from `GET /api/v1/me/notifications`.
class NotificationPage {
  const NotificationPage({
    required this.notifications,
    required this.unreadCount,
  });

  final List<AppNotification> notifications;
  final int unreadCount;

  factory NotificationPage.fromJson(Map<String, dynamic> json) {
    return NotificationPage(
      notifications: parseList(json['notifications'], AppNotification.fromJson),
      unreadCount: json['unread_count'] is num
          ? (json['unread_count'] as num).toInt()
          : 0,
    );
  }

  bool get isEmpty => notifications.isEmpty;
}

/// Reads and updates the parent's notifications.
///
/// There is no create endpoint on purpose: notices are produced only by a scan.
class NotificationRepository {
  const NotificationRepository();

  Future<NotificationPage> fetchNotifications({
    String? schoolId,
    bool unreadOnly = false,
    int limit = 50,
    int offset = 0,
  }) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/me/notifications',
      <String, dynamic>{
        if (schoolId != null) 'school_id': schoolId,
        if (unreadOnly) 'unread_only': true,
        'limit': limit,
        'offset': offset,
      },
    );
    return NotificationPage.fromJson(json);
  }

  Future<int> fetchUnreadCount({String? schoolId}) async {
    final Map<String, dynamic> json = await ApiClient.instance.get(
      '/api/v1/me/notifications/unread-count',
      <String, dynamic>{if (schoolId != null) 'school_id': schoolId},
    );
    final dynamic value = json['unread_count'];
    return value is num ? value.toInt() : 0;
  }

  /// Marks one notice read. The endpoint is idempotent, so a double tap is safe.
  Future<AppNotification> markRead(String notificationId) async {
    final Map<String, dynamic> json = await ApiClient.instance.patch(
      '/api/v1/me/notifications/$notificationId/read',
      const <String, dynamic>{},
    );
    return AppNotification.fromJson(json);
  }
}