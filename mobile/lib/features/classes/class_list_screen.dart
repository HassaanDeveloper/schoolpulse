import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../core/widgets/state_views.dart';
import '../students/students_repository.dart';

/// Lists a school's classes and lets an administrator add or remove one.
///
/// Read-only for teachers, who reach this screen through the staff home; the
/// add and delete actions are hidden for them and refused by the server.
class ClassListScreen extends StatefulWidget {
  const ClassListScreen({
    super.key,
    this.schoolId,
    this.repository,
    this.canManage = true,
  });

  final String? schoolId;
  final ClassesRepository? repository;

  /// False for a teacher, who may look at classes but not change them.
  final bool canManage;

  @override
  State<ClassListScreen> createState() => _ClassListScreenState();
}

class _ClassListScreenState extends State<ClassListScreen> {
  late final ClassesRepository _repository;

  List<SchoolClass>? _classes;
  bool _loading = true;
  String? _error;
  String? _deletingId;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const ClassesRepository();
    _load();
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final classes = await _repository.listClasses(schoolId: widget.schoolId);
      if (!mounted) {
        return;
      }
      setState(() {
        _classes = classes;
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

  Future<void> _createClass() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => ClassFormScreen(
          schoolId: widget.schoolId,
          repository: _repository,
        ),
      ),
    );
    if (created != true || !mounted) {
      return;
    }
    showMessage(context, 'Class created.');
    await _load();
  }

  Future<void> _deleteClass(SchoolClass schoolClass) async {
    final confirmed = await confirmAction(
      context,
      title: 'Delete ${schoolClass.label}?',
      message: 'This removes the class. Students already in it must be moved '
          'first. Attendance history is not affected.',
      confirmLabel: 'Delete class',
      destructive: true,
    );
    if (!confirmed || !mounted) {
      return;
    }

    setState(() => _deletingId = schoolClass.id);
    try {
      await _repository.deleteClass(schoolClass.id, schoolId: widget.schoolId);
      if (!mounted) {
        return;
      }
      showMessage(context, '${schoolClass.label} deleted.');
      await _load();
    } on ApiException catch (error) {
      // A class that still has students answers 409; describeError turns that
      // into "This class cannot be deleted because students are assigned to it."
      if (mounted) {
        showMessage(context, describeError(error), isError: true);
      }
    } finally {
      if (mounted) {
        setState(() => _deletingId = null);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Classes')),
      floatingActionButton: widget.canManage
          ? FloatingActionButton.extended(
              onPressed: _loading ? null : _createClass,
              icon: const Icon(Icons.add),
              label: const Text('Add class'),
            )
          : null,
      body: SafeArea(child: _body()),
    );
  }

  Widget _body() {
    if (_loading) {
      return const LoadingView(message: 'Loading classes');
    }
    if (_error != null) {
      return ErrorView(
        message: _error!,
        onRetry: _load,
        title: 'Could not load classes',
      );
    }

    final classes = _classes ?? const <SchoolClass>[];
    if (classes.isEmpty) {
      return EmptyView(
        icon: Icons.school_outlined,
        title: 'No classes yet',
        message: widget.canManage
            ? 'Add a class so students can be enrolled.'
            : 'This school has not added any classes yet.',
        action: widget.canManage
            ? FilledButton.icon(
                onPressed: _createClass,
                icon: const Icon(Icons.add),
                label: const Text('Add class'),
              )
            : null,
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
        itemCount: classes.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final schoolClass = classes[index];
          final busy = _deletingId == schoolClass.id;

          return Card(
            child: ListTile(
              leading: const Icon(Icons.groups_outlined),
              title: Text(schoolClass.name),
              subtitle: Text(
                schoolClass.section == null && schoolClass.academicYear == null
                    ? 'No section or year set'
                    : schoolClass.label,
              ),
              trailing: widget.canManage
                  ? (busy
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : IconButton(
                          tooltip: 'Delete class',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _deleteClass(schoolClass),
                        ))
                  : null,
            ),
          );
        },
      ),
    );
  }
}

/// Creates one class.
///
/// Only a name is required; section and academic year are optional because a
/// school may not use them.
class ClassFormScreen extends StatefulWidget {
  const ClassFormScreen({super.key, this.schoolId, this.repository});

  final String? schoolId;
  final ClassesRepository? repository;

  @override
  State<ClassFormScreen> createState() => _ClassFormScreenState();
}

class _ClassFormScreenState extends State<ClassFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _section = TextEditingController();
  final _year = TextEditingController();

  late final ClassesRepository _repository;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const ClassesRepository();
  }

  @override
  void dispose() {
    _name.dispose();
    _section.dispose();
    _year.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    setState(() => _saving = true);

    try {
      await _repository.createClass(
        name: _name.text.trim(),
        section: _section.text.trim(),
        academicYear: _year.text.trim(),
        schoolId: widget.schoolId,
      );
      if (mounted) {
        Navigator.of(context).pop(true);
      }
    } on ApiException catch (error) {
      if (mounted) {
        showMessage(context, describeError(error), isError: true);
      }
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Add class')),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              TextFormField(
                controller: _name,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Class name',
                  hintText: 'Grade 5',
                  border: OutlineInputBorder(),
                ),
                validator: (value) => (value == null || value.trim().isEmpty)
                    ? 'Enter a class name'
                    : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _section,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: 'Section (optional)',
                  hintText: 'B',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _year,
                decoration: const InputDecoration(
                  labelText: 'Academic year (optional)',
                  hintText: '2026-27',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _saving ? null : _save,
                child: _saving
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Save class'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
