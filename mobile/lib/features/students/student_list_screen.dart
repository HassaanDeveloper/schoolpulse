import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../core/widgets/state_views.dart';
import '../students/students_repository.dart';
import 'student_detail_screen.dart';

/// Lists a school's students with search, class filter and paging.
///
/// Opening a student leads to [StudentDetailScreen], which is where QR codes
/// and parents are managed.
class StudentListScreen extends StatefulWidget {
  const StudentListScreen({
    super.key,
    this.schoolId,
    this.repository,
    this.classesRepository,
    this.canManage = true,
  });

  final String? schoolId;
  final StudentsRepository? repository;
  final ClassesRepository? classesRepository;

  /// False for a teacher, who may look up students but not enrol or deactivate.
  final bool canManage;

  @override
  State<StudentListScreen> createState() => _StudentListScreenState();
}

class _StudentListScreenState extends State<StudentListScreen> {
  late final StudentsRepository _repository;
  late final ClassesRepository _classesRepository;

  final _search = TextEditingController();

  List<SchoolClass> _classes = const <SchoolClass>[];
  StudentPage? _page;
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;

  String? _classFilter;
  int _pageNumber = 1;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const StudentsRepository();
    _classesRepository = widget.classesRepository ?? const ClassesRepository();
    _load(reset: true);
    _loadClasses();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _loadClasses() async {
    try {
      final classes = await _classesRepository.listClasses(schoolId: widget.schoolId);
      if (mounted) {
        setState(() => _classes = classes);
      }
    } on ApiException {
      // The filter is a convenience; the list itself still works without it.
    }
  }

  Future<void> _load({bool reset = false}) async {
    if (mounted) {
      setState(() {
        if (reset) {
          _loading = true;
          _pageNumber = 1;
        } else {
          _loadingMore = true;
        }
        _error = null;
      });
    }

    try {
      final page = await _repository.listStudents(
        schoolId: widget.schoolId,
        classId: _classFilter,
        search: _search.text,
        page: reset ? 1 : _pageNumber,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _page = page;
        _loading = false;
        _loadingMore = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = describeError(error);
        _loading = false;
        _loadingMore = false;
      });
    }
  }

  void _onSearchChanged(String _) {
    // Debounced so a search does not fire a request per keystroke.
    Future<void>.delayed(const Duration(milliseconds: 350), () {
      if (mounted) {
        _load(reset: true);
      }
    });
  }

  Future<void> _loadNextPage() async {
    final page = _page;
    if (page == null || !page.hasNextPage || _loadingMore) {
      return;
    }
    setState(() => _pageNumber = page.page + 1);
    await _load();
  }

  Future<void> _createStudent() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => StudentFormScreen(
          schoolId: widget.schoolId,
          repository: _repository,
          classes: _classes,
        ),
      ),
    );
    if (created != true || !mounted) {
      return;
    }
    showMessage(context, 'Student added.');
    await _load(reset: true);
  }

  Future<void> _openStudent(Student student) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => StudentDetailScreen(
          student: student,
          schoolId: widget.schoolId,
          classLabel: _classLabelFor(student),
        ),
      ),
    );
    if (mounted) {
      await _load(reset: true);
    }
  }

  String _classLabelFor(Student student) {
    for (final schoolClass in _classes) {
      if (schoolClass.id == student.classId) {
        return schoolClass.label;
      }
    }
    return 'No class';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Students')),
      floatingActionButton: widget.canManage
          ? FloatingActionButton.extended(
              onPressed: _loading ? null : _createStudent,
              icon: const Icon(Icons.person_add_alt),
              label: const Text('Add student'),
            )
          : null,
      body: SafeArea(child: _body()),
    );
  }

  Widget _body() {
    if (_loading) {
      return const LoadingView(message: 'Loading students');
    }
    if (_error != null) {
      return ErrorView(
        message: _error!,
        onRetry: () => _load(reset: true),
        title: 'Could not load students',
      );
    }

    final page = _page;
    if (page == null || page.items.isEmpty) {
      final searching = _search.text.trim().isNotEmpty || _classFilter != null;
      return EmptyView(
        icon: Icons.groups_outlined,
        title: searching ? 'No students found' : 'No students yet',
        message: searching
            ? 'Try a different name, admission number or class.'
            : widget.canManage
                ? 'Add a student to issue a QR code and link a parent.'
                : 'This school has not enrolled any students yet.',
        action: widget.canManage && !searching
            ? FilledButton.icon(
                onPressed: _createStudent,
                icon: const Icon(Icons.person_add_alt),
                label: const Text('Add student'),
              )
            : null,
      );
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
        itemCount: page.items.length + 2,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          if (index == 0) {
            return _filters();
          }
          if (index == page.items.length + 1) {
            return _pager(page);
          }

          final student = page.items[index - 1];
          return Card(
            child: ListTile(
              leading: CircleAvatar(
                child: Text(
                  student.firstName.isEmpty
                      ? '?'
                      : student.firstName.characters.first.toUpperCase(),
                ),
              ),
              title: Text(student.fullName),
              subtitle: Text(
                '${student.admissionNumber}  •  ${_classLabelFor(student)}',
              ),
trailing: student.isActive
                  ? const Icon(Icons.chevron_right)
                  // Inactive is called out rather than hidden: their history
                  // still matters, and the reason must be visible.
                  : const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Chip(
                          label: Text('Inactive'),
                          visualDensity: VisualDensity.compact,
                        ),
                        Icon(Icons.chevron_right),
                      ],
                    ),
              onTap: () => _openStudent(student),
            ),
          );
        },
      ),
    );
  }

  Widget _filters() {
    return Column(
      children: [
        TextField(
          controller: _search,
          onChanged: _onSearchChanged,
          textInputAction: TextInputAction.search,
          decoration: InputDecoration(
            labelText: 'Search students',
            hintText: 'Name or admission number',
            prefixIcon: const Icon(Icons.search),
            border: const OutlineInputBorder(),
            suffixIcon: _search.text.isEmpty
                ? null
                : IconButton(
                    tooltip: 'Clear search',
                    icon: const Icon(Icons.clear),
                    onPressed: () {
                      _search.clear();
                      _load(reset: true);
                    },
                  ),
          ),
        ),
        if (_classes.isNotEmpty) ...[
          const SizedBox(height: 12),
          DropdownButtonFormField<String?>(
            initialValue: _classFilter,
            decoration: const InputDecoration(
              labelText: 'Class',
              border: OutlineInputBorder(),
            ),
            items: [
              const DropdownMenuItem<String?>(value: null, child: Text('All classes')),
              for (final schoolClass in _classes)
                DropdownMenuItem<String?>(
                  value: schoolClass.id,
                  child: Text(schoolClass.label, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (value) {
              setState(() => _classFilter = value);
              _load(reset: true);
            },
          ),
        ],
        const SizedBox(height: 8),
      ],
    );
  }

  Widget _pager(StudentPage page) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            'Page ${page.page} of ${page.pageCount}  •  ${page.total} students',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          Row(
            children: [
              IconButton(
                tooltip: 'Previous page',
                icon: const Icon(Icons.chevron_left),
                onPressed: page.hasPreviousPage
                    ? () {
                        setState(() => _pageNumber = page.page - 1);
                        _load();
                      }
                    : null,
              ),
              if (_loadingMore)
                const SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                IconButton(
                  tooltip: 'Next page',
                  icon: const Icon(Icons.chevron_right),
                  onPressed: page.hasNextPage ? _loadNextPage : null,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Enrols one student.
///
/// Collects only what a school needs to identify a child: name, admission
/// number and class. Date of birth and gender are optional and left blank by
/// default — the app should not push a school into collecting more than it
/// needs.
class StudentFormScreen extends StatefulWidget {
  const StudentFormScreen({
    super.key,
    this.schoolId,
    this.repository,
    this.classes = const <SchoolClass>[],
  });

  final String? schoolId;
  final StudentsRepository? repository;
  final List<SchoolClass> classes;

  @override
  State<StudentFormScreen> createState() => _StudentFormScreenState();
}

class _StudentFormScreenState extends State<StudentFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _firstName = TextEditingController();
  final _lastName = TextEditingController();
  final _admissionNumber = TextEditingController();
  final _dateOfBirth = TextEditingController();

  String? _classId;
  String? _gender;
  bool _saving = false;

  late final StudentsRepository _repository;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? const StudentsRepository();
    if (widget.classes.isNotEmpty) {
      _classId = widget.classes.first.id;
    }
  }

  @override
  void dispose() {
    _firstName.dispose();
    _lastName.dispose();
    _admissionNumber.dispose();
    _dateOfBirth.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    if (_classId == null) {
      showMessage(context, 'Choose a class for this student.', isError: true);
      return;
    }

    setState(() => _saving = true);
    try {
      await _repository.createStudent(
        firstName: _firstName.text.trim(),
        lastName: _lastName.text.trim(),
        admissionNumber: _admissionNumber.text.trim(),
        classId: _classId!,
        dateOfBirth: _dateOfBirth.text.trim(),
        gender: _gender,
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
    final classes = widget.classes;

    return Scaffold(
      appBar: AppBar(title: const Text('Add student')),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (classes.isEmpty)
                const Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'Add a class first — every student belongs to one.',
                    ),
                  ),
                )
              else
                DropdownButtonFormField<String>(
                  initialValue: _classId,
                  decoration: const InputDecoration(
                    labelText: 'Class',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final schoolClass in classes)
                      DropdownMenuItem<String>(
                        value: schoolClass.id,
                        child: Text(
                          schoolClass.label,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (value) => setState(() => _classId = value),
                ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _firstName,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'First name',
                  border: OutlineInputBorder(),
                ),
                validator: (value) => (value == null || value.trim().isEmpty)
                    ? 'Enter a first name'
                    : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _lastName,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Last name',
                  border: OutlineInputBorder(),
                ),
                validator: (value) => (value == null || value.trim().isEmpty)
                    ? 'Enter a last name'
                    : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _admissionNumber,
                decoration: const InputDecoration(
                  labelText: 'Admission number',
                  hintText: 'ADM-101',
                  border: OutlineInputBorder(),
                ),
                validator: (value) => (value == null || value.trim().isEmpty)
                    ? 'Enter an admission number'
                    : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _dateOfBirth,
                readOnly: true,
                decoration: const InputDecoration(
                  labelText: 'Date of birth (optional)',
                  border: OutlineInputBorder(),
                ),
                onTap: _pickDateOfBirth,
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String?>(
                initialValue: _gender,
                decoration: const InputDecoration(
                  labelText: 'Gender (optional)',
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem<String?>(value: null, child: Text('Not specified')),
                  DropdownMenuItem<String?>(value: 'female', child: Text('Female')),
                  DropdownMenuItem<String?>(value: 'male', child: Text('Male')),
                ],
                onChanged: (value) => setState(() => _gender = value),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _saving || classes.isEmpty ? null : _save,
                child: _saving
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Save student'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pickDateOfBirth() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime(now.year - 30),
      lastDate: now,
      initialDate: DateTime(now.year - 10),
      helpText: 'Select date of birth',
    );
    if (picked != null) {
      final month = picked.month.toString().padLeft(2, '0');
      final day = picked.day.toString().padLeft(2, '0');
      _dateOfBirth.text = '${picked.year}-$month-$day';
    }
  }
}
