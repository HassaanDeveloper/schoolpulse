// Day 7: what a user sees when the backend cannot be reached.
//
// The school demonstration depends on the network working, so this is the one
// failure path that must degrade to a readable sentence rather than a crash or
// a raw socket error. These tests cover the mapping only; they do not claim the
// app was observed on a phone.
import 'package:flutter_test/flutter_test.dart';
import 'package:schoolpulse/core/network/api_client.dart';
import 'package:schoolpulse/core/widgets/state_views.dart';

void main() {
  group('describeError', () {
    test('network failure keeps the client sentence', () {
      // A SocketException is translated into ApiException(0, ...) by
      // ApiClient; describeError passes that message through untouched.
      final error = ApiException(0, 'Could not reach the SchoolPulse server.');
      expect(describeError(error), 'Could not reach the SchoolPulse server.');
    });

    test('timeout keeps the timeout sentence', () {
      final error = ApiException(0, 'The server took too long to respond.');
      expect(describeError(error), 'The server took too long to respond.');
    });

    test('expired session prompts a sign-in', () {
      expect(
        describeError(ApiException(401, 'Not authenticated.')),
        'Your session has expired. Please sign in again.',
      );
    });

    test('forbidden does not echo server internals', () {
      expect(
        describeError(ApiException(403, 'School administrator privileges are required.')),
        'You do not have permission to do this.',
      );
    });

    test('an unrecognised failure is generic', () {
      expect(
        describeError(ApiException(500, 'An internal error occurred.')),
        'Something went wrong. Please try again.',
      );
    });

    test('a non-API exception never leaks its text', () {
      expect(
        describeError(StateError('connection to 10.0.2.2:8000 refused')),
        'Something went wrong. Please try again.',
      );
    });

    test('a server stack trace is never shown to a user', () {
      const leaky = 'Traceback (most recent call last): File app/main.py';
      expect(describeError(ApiException(500, leaky)), isNot(contains('Traceback')));
    });
  });
}