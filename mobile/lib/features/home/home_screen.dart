import 'package:flutter/material.dart';

import '../auth/auth_controller.dart';
import 'account_repository.dart';

/// Basic role-aware home screen. This is deliberately not the full dashboard.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.auth});

  final AuthController auth;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final AccountRepository _repository = const AccountRepository();

  late Future<Me> _future;

  @override
  void initState() {
    super.initState();
    _future = _repository.fetchMe();
  }

  Future<void> _signOut() async {
    await widget.auth.signOut();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('SchoolPulse'),
        actions: [
          IconButton(
            tooltip: 'Log out',
            onPressed: _signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            setState(() => _future = _repository.fetchMe());
            await _future;
          },
          child: FutureBuilder<Me>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }

              if (snapshot.hasError) {
                return ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    const SizedBox(height: 48),
                    Icon(
                      Icons.cloud_off_outlined,
                      size: 48,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Could not load your account.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Check that the backend is running and try again.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                );
              }

              final me = snapshot.data!;
              if (me.memberships.isEmpty) {
                return ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    const SizedBox(height: 48),
                    Icon(
                      Icons.domain_add_outlined,
                      size: 48,
                      color: theme.colorScheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'No school yet',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'You are signed in but not a member of any school. '
                      'School setup is coming next.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                );
              }

              return ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  Text('Welcome,', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(
                    widget.auth.email ?? 'Signed in',
                    style: theme.textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 24),
                  ...me.memberships.map(
                    (m) => Card(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: ListTile(
                        leading: const Icon(Icons.school_outlined),
                        title: Text(m.schoolName),
                        subtitle: Text('Role: ${m.roleLabel}'),
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}