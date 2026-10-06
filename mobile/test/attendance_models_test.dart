import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/features/attendance/attendance_repository.dart';
import 'package:schoolpulse/features/attendance/qr_repository.dart';

void main() {
  group('ScanStatus', () {
    test('parses the three server statuses', () {
      expect(ScanStatus.parse('ARRIVAL_RECORDED'), ScanStatus.arrivalRecorded);
      expect(ScanStatus.parse('DEPARTURE_RECORDED'), ScanStatus.departureRecorded);
      expect(ScanStatus.parse('ALREADY_RECORDED'), ScanStatus.alreadyRecorded);
    });

    test('falls back to unknown for unrecognised values', () {
      expect(ScanStatus.parse('SOMETHING_NEW'), ScanStatus.unknown);
      expect(ScanStatus.parse(null), ScanStatus.unknown);
    });

    test('only arrival and departure count as new records', () {
      expect(ScanStatus.arrivalRecorded.isNew, isTrue);
      expect(ScanStatus.departureRecorded.isNew, isTrue);
      expect(ScanStatus.alreadyRecorded.isNew, isFalse);
      expect(ScanStatus.unknown.isNew, isFalse);
    });

    test('has a human readable label for every status', () {
      expect(ScanStatus.arrivalRecorded.label, 'Arrival recorded');
      expect(ScanStatus.departureRecorded.label, 'Departure recorded');
      expect(ScanStatus.alreadyRecorded.label, 'Already recorded');
      expect(ScanStatus.unknown.label, 'Recorded');
    });
  });

  group('ScanResult.fromJson', () {
    test('parses a successful arrival scan', () {
      final result = ScanResult.fromJson(<String, dynamic>{
        'status': 'ARRIVAL_RECORDED',
        'student': <String, dynamic>{
          'id': 'student-1',
          'name': 'Ayesha Khan',
          'admission_number': 'ADM-001',
        },
        'attendance_date': '2026-03-02',
        'arrival_at': '2026-03-02T09:00:00Z',
        'departure_at': null,
        'timestamp': '2026-03-02T09:00:00Z',
      });

      expect(result.status, ScanStatus.arrivalRecorded);
      expect(result.student.name, 'Ayesha Khan');
      expect(result.student.admissionNumber, 'ADM-001');
      expect(result.attendanceDate, DateTime(2026, 3, 2));
      expect(result.arrivalAt, isNotNull);
      expect(result.departureAt, isNull);
      expect(result.timestamp, result.arrivalAt);
    });

    test('parses a completed departure scan', () {
      final result = ScanResult.fromJson(<String, dynamic>{
        'status': 'DEPARTURE_RECORDED',
        'student': <String, dynamic>{
          'id': 'student-1',
          'name': 'Ayesha Khan',
          'admission_number': 'ADM-001',
        },
        'attendance_date': '2026-03-02',
        'arrival_at': '2026-03-02T09:00:00Z',
        'departure_at': '2026-03-02T14:00:00Z',
        'timestamp': '2026-03-02T14:00:00Z',
      });

      expect(result.status, ScanStatus.departureRecorded);
      expect(result.departureAt, isNotNull);
      expect(result.timestamp, result.departureAt);
      expect(result.timestamp!.isAfter(result.arrivalAt!), isTrue);
    });

    test('tolerates a missing student block', () {
      final result = ScanResult.fromJson(<String, dynamic>{'status': 'ALREADY_RECORDED'});

      expect(result.status, ScanStatus.alreadyRecorded);
      expect(result.student.id, 'null');
      expect(result.student.name, '');
      expect(result.attendanceDate, isNull);
    });
  });

  group('Student.fromJson', () {
    test('parses a student and derives the display name', () {
      final student = Student.fromJson(<String, dynamic>{
        'id': 'student-1',
        'admission_number': 'ADM-001',
        'first_name': 'Ayesha',
        'last_name': 'Khan',
        'status': 'active',
      });

      expect(student.fullName, 'Ayesha Khan');
      expect(student.isActive, isTrue);
    });

    test('falls back to the admission number when no name is set', () {
      final student = Student.fromJson(<String, dynamic>{
        'id': 'student-1',
        'admission_number': 'ADM-001',
        'first_name': '',
        'last_name': '',
        'status': 'inactive',
      });

      expect(student.fullName, 'ADM-001');
      expect(student.isActive, isFalse);
    });
  });

  group('QrCredential.fromJson', () {
    test('reads the one-time plaintext credential', () {
      final credential = QrCredential.fromJson(<String, dynamic>{
        'student_id': 'student-1',
        'credential': 'opaque-token-value',
        'created_at': '2026-03-02T09:00:00Z',
        'revoked_previous': true,
      });

      expect(credential.studentId, 'student-1');
      expect(credential.credential, 'opaque-token-value');
      expect(credential.revokedPrevious, isTrue);
      expect(credential.createdAt, isNotNull);
    });

    test('defaults revoked_previous to false', () {
      final credential = QrCredential.fromJson(<String, dynamic>{
        'student_id': 'student-1',
        'credential': 'token',
      });

      expect(credential.revokedPrevious, isFalse);
      expect(credential.createdAt, isNull);
    });

    test('never exposes a stored hash', () {
      final credential = QrCredential.fromJson(<String, dynamic>{
        'student_id': 'student-1',
        'credential': 'token',
        'token_hash': 'should-not-be-parsed',
      });

      expect(
        credential.credential,
        isNot(contains('should-not-be-parsed')),
      );
    });
  });

  group('QrCredentialStatus.fromJson', () {
    test('reads the active flag without a secret', () {
      final status = QrCredentialStatus.fromJson(<String, dynamic>{
        'student_id': 'student-1',
        'has_active_credential': true,
        'created_at': '2026-03-02T09:00:00Z',
      });

      expect(status.studentId, 'student-1');
      expect(status.hasActiveCredential, isTrue);
    });

    test('defaults to no active credential', () {
      final status = QrCredentialStatus.fromJson(<String, dynamic>{
        'student_id': 'student-1',
      });

      expect(status.hasActiveCredential, isFalse);
    });
  });
}