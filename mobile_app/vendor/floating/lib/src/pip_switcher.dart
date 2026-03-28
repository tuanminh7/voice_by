part of '../floating.dart';

class PiPSwitcher extends StatefulWidget {
  @visibleForTesting
  final Floating? floating;

  final Widget childWhenEnabled;
  final Widget childWhenDisabled;
  final Duration duration;
  final Curve curve;

  const PiPSwitcher({
    super.key,
    required this.childWhenEnabled,
    required this.childWhenDisabled,
    this.duration = const Duration(milliseconds: 200),
    this.curve = Curves.easeOutCubic,
    this.floating,
  });

  @override
  State<PiPSwitcher> createState() => _PipAwareState();
}

class _PipAwareState extends State<PiPSwitcher> {
  late final Floating _floating = widget.floating ?? Floating();

  @override
  Widget build(BuildContext context) => StreamBuilder<PiPStatus>(
        stream: _floating.pipStatusStream,
        initialData: PiPStatus.unavailable,
        builder: (context, snapshot) => AnimatedSwitcher(
          duration: widget.duration,
          switchInCurve: widget.curve,
          switchOutCurve: widget.curve,
          child: snapshot.data == PiPStatus.enabled
              ? widget.childWhenEnabled
              : widget.childWhenDisabled,
        ),
      );
}
