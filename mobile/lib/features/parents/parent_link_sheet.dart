import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../core/widgets/state_views.dart';
import 'parents_admin_repository.dart';

/// Lets an administrator link a parent account to one student.
///
/// The list comes from `GET /api/v1/parents`, a read-only directory of accounts
/// that already hold a parent membership in this administrator's school. There
/// is deliberately no "create parent" action here: SchoolPulse has no public
/// parent registration, and adding one would be a backdoor into the identity
/// system.
///
/// Returns true when a link was added, so the caller can refresh.
Future<bool?> showParentLinkSheet(
  BuildContext context, {
  required String studentId,
  required ParentsAdminRepository repository,
  required List<LinkedParent> existing,
  String? schoolId,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => ParentLinkSheet(
      studentId: studentId,
      repository: repository,
      existing: existing,
      schoolId: schoolId,
    ),
  );
}

class ParentLinkSheet extends StatefulWidget {
  const ParentLinkSheet({
    super.key,
    required this.studentId,
    required this.repository,
    required this.existing,
    this.schoolId,
  });

  final String studentId;
  final ParentsAdminRepository repository;
  final List<LinkedParent> existing;
  final String? schoolId;

  @override
  State<ParentLinkSheet> createState() => _ParentLinkSheetState();
}

class _ParentLinkSheetState extends State<ParentLinkSheet> {
  final _search = TextEditingController();

  List<ParentAccount>? _accounts;
  bool _loading = true;
  bool _linking = false;
  String? _error;
  bool _changed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final accounts = await widget.repository.listAccounts(
        schoolId: widget.schoolId,
        search: _search.text,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _accounts = accounts;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = describeError(error);
        _loading = false;
      });
    }
  }

  void _onSearchChanged(String _) {
    Future<void>.delayed(const Duration(milliseconds: 350), () {
      if (mounted) {
        _load();
      }
    });
  }

  bool _isAlreadyLinked(String userId) =>
      widget.existing.any((parent) => parent.userId == userId);

  Future<void> _link(ParentAccount account) async {
    setState(() => _linking = true);
    try {
      await widget.repository.linkParent(
        widget.studentId,
        account.userId,
        schoolId: widget.schoolId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _linking = false;
        _changed = true;
      });
      showMessage(context, '${account.displayName} linked to this student.');
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (mounted) {
        setState(() => _linking = false);
        showMessage(context, describeError(error), isError: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accounts = _accounts ?? const <ParentAccount>[];
    final available = accounts.where((a) => !_isAlreadyLinked(a.userId)).toList();

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: FractionallySizedBox(
        heightFactor: 0.85,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Link a parent', style: theme.textTheme.titleMedium),
                        const SizedBox(height: 2),
                        Text(
                          'Only parent accounts already registered at this school '
                          'are listed.',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.of(context).pop(_changed),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                controller: _search,
                onChanged: _onSearchChanged,
                decoration: const InputDecoration(
                  labelText: 'Search by name or email',
                  prefixIcon: Icon(Icons.search),
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(child: _list(theme, available, accounts)),
          ],
        ),
      ),
    );
  }

  Widget _list(ThemeData theme, List<ParentAccount> available, List<ParentAccount> all) {
    if (_loading) {
      return const LoadingView(message: 'Loading parent accounts');
    }
    if (_error != null) {
      return ErrorView(message: _error!, onRetry: _load, title: 'Could not load parents');
    }
    if (all.isEmpty) {
      return EmptyView(
        icon: Icons.person_search_outlined,
        title: _search.text.trim().isEmpty
            ? 'No parent accounts at this school'
            : 'No matching parent accounts',
        message: _search.text.trim().isEmpty
            ? 'A parent account has to exist before it can be linked. Ask the '
                'school office to add one, then search for it here.'
            : 'Try a different name or email address.',
      );
    }
    if (available.isEmpty) {
      return EmptyView(
        icon: Icons.check_circle_outline,
        title: 'Everyone here is already linked',
        message: 'All ${all.length} parent account(s) at this school are '
            'already linked to this student.',
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: available.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final account = available[index];
        return ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const CircleAvatar(child: Icon(Icons.person_outline)),
          title: Text(account.displayName),
          subtitle: Text(account.subtitle),
          trailing: _linking
              ? const SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : FilledButton.tonal(
                  onPressed: () => _link(account),
                  child: const Text('Link'),
                ),
        );
      },
    );
  }
}