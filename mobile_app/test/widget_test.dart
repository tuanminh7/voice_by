import 'package:flutter_test/flutter_test.dart';

import 'package:ut_nguyen_mobile/src/models/app_models.dart';

void main() {
  test('BootstrapState parses authenticated payload', () {
    final state = BootstrapState.fromJson({
      'authenticated': true,
      'pin_configured': true,
      'user': {
        'id': 12,
        'full_name': 'Ba Nguyen',
      },
    });

    expect(state.authenticated, isTrue);
    expect(state.pinConfigured, isTrue);
    expect(state.user?.fullName, 'Ba Nguyen');
  });

  test('CallSession parses call metadata', () {
    final session = CallSession.fromJson({
      'call_session_id': 8,
      'room_id': 'room-8',
      'provider': 'zegocloud',
      'status': 'ringing',
      'trigger_source': 'voice_intent',
      'relationship_key': 'son',
      'relationship_label': 'Con trai',
      'ring_timeout_seconds': 25,
      'caller': {
        'id': 2,
        'full_name': 'Ong Nguyen',
      },
      'accepted_by': {
        'id': 5,
        'full_name': 'Anh Nam',
      },
      'current_target': {
        'id': 5,
        'full_name': 'Anh Nam',
      },
      'targets': [
        {
          'target_user_id': 5,
          'full_name': 'Anh Nam',
          'relationship_key': 'son',
          'priority_order': 1,
          'status': 'ringing',
        },
      ],
      'transcript_text': 'Goi con trai',
      'detected_intent': 'call_family',
      'created_at': '2026-03-25T20:00:00',
    });

    expect(session.provider, 'zegocloud');
    expect(session.caller?.fullName, 'Ong Nguyen');
    expect(session.acceptedBy?.id, 5);
    expect(session.targets, hasLength(1));
    expect(session.isFinished, isFalse);
  });
}
