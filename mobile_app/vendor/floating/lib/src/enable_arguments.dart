part of '../floating.dart';

sealed class EnableArguments {
  final Rational aspectRatio;
  final Rectangle<int>? sourceRectHint;

  const EnableArguments({
    this.aspectRatio = const Rational.landscape(),
    this.sourceRectHint,
  });
}

class ImmediatePiP extends EnableArguments {
  const ImmediatePiP({
    super.aspectRatio = const Rational.landscape(),
    super.sourceRectHint,
  });
}

class OnLeavePiP extends EnableArguments {
  const OnLeavePiP({
    super.aspectRatio = const Rational.landscape(),
    super.sourceRectHint,
  });
}
