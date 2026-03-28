part of '../floating.dart';

enum PiPStatus {
  enabled,
  disabled,
  automatic,
  unavailable,
}

class Floating {
  @visibleForTesting
  EnableArguments? lastEnableArguments;

  static final Floating _singleton = Floating._internal();

  factory Floating() => _singleton;

  Floating._internal();

  void reset() {
    lastEnableArguments = null;
  }

  Future<bool> get isPipAvailable async => false;

  Future<PiPStatus> get pipStatus async => PiPStatus.unavailable;

  Stream<PiPStatus> get pipStatusStream =>
      Stream<PiPStatus>.value(PiPStatus.unavailable).asBroadcastStream();

  Future<PiPStatus> enable(EnableArguments arguments) async {
    lastEnableArguments = arguments;
    return PiPStatus.unavailable;
  }

  Future<void> cancelOnLeavePiP() async {
    lastEnableArguments = null;
  }
}

class Rational {
  final int numerator;
  final int denominator;

  const Rational(this.numerator, this.denominator);

  const Rational.square()
      : numerator = 1,
        denominator = 1;

  const Rational.landscape()
      : numerator = 16,
        denominator = 9;

  const Rational.vertical()
      : numerator = 9,
        denominator = 16;

  @override
  String toString() =>
      'Rational(numerator: $numerator, denominator: $denominator)';

  Map<String, dynamic> toMap() => {
        'numerator': numerator,
        'denominator': denominator,
      };
}

class RationalNotMatchingAndroidRequirementsException implements Exception {
  final Rational rational;

  RationalNotMatchingAndroidRequirementsException(this.rational);

  @override
  String toString() => 'RationalNotMatchingAndroidRequirementsException('
      '${rational.numerator}/${rational.denominator} does not fit into '
      'Android-supported aspect ratios. Boundaries: '
      'min: 1/2.39, max: 2.39/1.'
      ')';
}
