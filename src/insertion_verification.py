"""Read-only, bounded confirmation for known native editor offset profiles."""

from delivery import TargetSnapshot, inspect_current_target, inspect_foreground_target


MAX_VERIFIABLE_CHARACTERS = 4096


def _normalize_lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def replacement_matches(before: TargetSnapshot, after: TargetSnapshot, text: str,
                        *, encoding: str, line_ending: str) -> bool:
    if not text or not after.paste_decision_from(None).allowed:
        return False
    for name in ("window_handle", "process_id", "focus_window_handle"):
        if not getattr(before, name) or getattr(before, name) != getattr(after, name):
            return False
    for name in ("document_id", "runtime_id"):
        expected = getattr(before, name)
        if expected and getattr(after, name) != expected:
            return False
    values = (before.selection_start, before.selection_end, before.document_length,
              after.selection_start, after.selection_end, after.document_length)
    if any(value is None for value in values):
        return False
    start, end, length, caret, selection_end, new_length = values
    if not 0 <= start <= end <= length or caret != selection_end:
        return False
    if encoding not in {"utf-16-le", "utf-8"} or line_ending not in {"\r\n", "\n", "\r", "preserve"}:
        return False
    inserted = text if line_ending == "preserve" else _normalize_lines(text).replace("\n", line_ending)
    units = len(inserted.encode(encoding)) // (2 if encoding == "utf-16-le" else 1)
    return caret == start + units and new_length == length - (end - start) + units


def _read_inserted_span(expected, text):
    import uiautomation as automation

    control = automation.GetFocusedControl()
    if control is None or int(control.ProcessId) != expected.process_id:
        return False
    runtime = ".".join(str(int(value)) for value in control.GetRuntimeId())
    if not expected.runtime_id or runtime != expected.runtime_id:
        return False
    if bool(control.IsPassword) or not bool(control.IsEnabled):
        return False
    pattern = control.GetPattern(automation.PatternId.TextPattern)
    selections = pattern.GetSelection() if pattern is not None else []
    if len(selections) != 1:
        return False
    caret = selections[0]
    start = automation.TextPatternRangeEndpoint.Start
    end = automation.TextPatternRangeEndpoint.End
    if caret.CompareEndpoints(start, caret, end) != 0:
        return False
    span = caret.Clone()
    count = len(_normalize_lines(text))
    moved = span.MoveEndpointByUnit(start, automation.TextUnit.Character, -count, waitTime=0)
    if moved != -count or span.CompareEndpoints(end, caret, end) != 0:
        return False
    # One extra UTF-16 unit exposes an overlong range rather than accepting a
    # truncated matching prefix. Never read DocumentRange or an unlimited span.
    maximum = len(text.encode("utf-16-le")) // 2 + text.count("\n") + 1
    actual = span.GetText(maximum)
    return _normalize_lines(actual) == _normalize_lines(text)


def verify_native_insertion(expected: TargetSnapshot, text: str) -> bool:
    """Called only on the existing MTA worker; COM ranges never leave it."""
    if (not text or len(text) > MAX_VERIFIABLE_CHARACTERS
            or not expected.text_encoding or not expected.line_ending):
        return False
    after = inspect_current_target()
    if (after.text_encoding, after.line_ending) != (expected.text_encoding, expected.line_ending):
        return False
    if not replacement_matches(expected, after, text, encoding=expected.text_encoding,
                               line_ending=expected.line_ending):
        return False
    if not _read_inserted_span(after, text):
        return False
    latest = inspect_foreground_target()
    # The final cheap check catches a focus or edit change during the UIA read.
    return latest.same_input_context(after)
