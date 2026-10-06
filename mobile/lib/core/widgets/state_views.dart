import 'package:flutter/material.dart';

import '../network/api_client.dart';

/// Turns an [ApiException] into something a school administrator can act on.
///
/// Screens must never show a status code, a raw exception or an internal
/// message, so every screen funnels failures through here instead of
/// displaying `error.message` directly.
String describeError(Object error) {
  if (error is! ApiException) {
    return 'Something went wrong. Please try again.';
  }

  switch (error.statusCode) {
    case 0:
      // Network failure, already phrased by the API client.
      return error.message;
    case 401:
      return 'Your session has expired. Please sign in again.';
    case 403:
      return 'You do not have permission to do this.';
    case 404:
      return error.message.isEmpty
          ? 'That item could not be found.'
          : _sentence(error.message);
    case 409:
      // Conflict details are written for staff, e.g. a class that still has
      // students. They are safe to show once phrased as a sentence.
      return _sentence(error.message);
    case 422:
      return _validationMessage(error);
    default:
      return 'Something went wrong. Please try again.';
  }
}

/// Pydantic sends `detail` as a list of field errors on a 422; this turns the
/// first one into a readable sentence.
String _validationMessage(ApiException error) {
  for (final line in error.message.split('\n')) {
    final trimmed = line.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
  }
  return 'Please check the details you entered.';
}

String _sentence(String message) {
  final trimmed = message.trim();
  if (trimmed.isEmpty) {
    return 'That could not be completed.';
  }
  final first = trimmed[0].toUpperCase();
  final body = trimmed.substring(1);
  return trimmed.endsWith('.') || trimmed.endsWith('!') || trimmed.endsWith('?')
      ? '$first$body'
      : '$first$body.';
}

/// A full-screen "we are working on it" state.
///
/// Scrollable, because these screens sit inside a `RefreshIndicator` and a
/// non-scrollable child breaks pull-to-refresh.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 120),
        Center(
          child: Column(
            children: [
              const CircularProgressIndicator(),
              if (message != null) ...[
                const SizedBox(height: 16),
                Text(message!, textAlign: TextAlign.center),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// A retryable failure state with a school-friendly explanation.
class ErrorView extends StatelessWidget {
  const ErrorView({
    super.key,
    required this.message,
    required this.onRetry,
    this.title = 'Something went wrong',
  });

  final String message;
  final Future<void> Function() onRetry;
  final String title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 72),
        Icon(Icons.cloud_off_outlined, size: 48, color: theme.colorScheme.error),
        const SizedBox(height: 16),
        Text(title, textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 24),
        Center(
          child: FilledButton.tonal(
            onPressed: () => onRetry(),
            child: const Text('Try again'),
          ),
        ),
      ],
    );
  }
}

/// "There is nothing here yet" — always with the next useful action.
class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  final String title;
  final String message;
  final IconData icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 72),
        Icon(icon, size: 48, color: theme.colorScheme.primary),
        const SizedBox(height: 16),
        Text(title, textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center),
        if (action != null) ...[
          const SizedBox(height: 24),
          Center(child: action),
        ],
      ],
    );
  }
}

/// Shows a short confirmation or failure at the bottom of the screen.
void showMessage(BuildContext context, String message, {bool isError = false}) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  if (messenger == null) {
    return;
  }
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
      ),
    );
}

/// Asks before doing something that cannot be undone.
///
/// Returns true only when the user actively confirms, so a dismissed dialog is
/// never treated as consent.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  required String confirmLabel,
  bool destructive = false,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: destructive
              ? FilledButton.styleFrom(
                  backgroundColor: Theme.of(dialogContext).colorScheme.error,
                  foregroundColor: Theme.of(dialogContext).colorScheme.onError,
                )
              : null,
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}
