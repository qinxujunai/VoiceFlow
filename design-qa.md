# VoiceFlow v0.3.1 Design QA

## Selected direction and evidence

- Selected direction: the quiet command-center concept generated during the
  product-design exploration, not the first visual option.
- Reference: `docs/design-reference-v031.png`.
- Real implementation capture: `docs/design-implementation-v031.png`.
- Same-state comparison: `docs/design-comparison-v031.png`.
- Complete state capture manifest:
  `logs/ui-v031-command-center-final/manifest.json`.

The implementation deliberately keeps the reference's hierarchy instead of
copying its concept-only decoration: health first, one clear start action,
then recent work. It removes the ornamental status icons, extra bottom bar,
and duplicated settings glyph from the mock because those elements do not add
working capability in the shipped Qt application.

## Application review

- Shell: passed. Four task destinations remain: Status, Dictionary, History,
  and Settings. Diagnostics and About stay behind Help.
- Home hierarchy: passed. Readiness, one trial action, and recent dictation are
  visible without a dashboard of cards or implementation jargon.
- Product truth: passed. The screen says local processing is available only
  when runtime checks pass; it does not expose model downloads or claim an
  unmeasured accuracy advantage.
- Dictionary: passed. Bundled AI terms are read-only, user terms remain local,
  ASCII terms normalize spelling at token boundaries, and explicit correction
  pairs reload for the next dictation without semantic rewriting.
- Settings: passed. Language, microphone, autostart, privacy boundary, and
  trigger help are the only ordinary controls.
- History: passed. Each result owns Copy and Paste Again actions and translates
  internal delivery codes into short, truthful labels.
- Typography and density: passed at the captured Windows scale. System fonts,
  one blue action color, one-pixel borders, and a neutral full-height sidebar
  keep the hierarchy quiet and readable.
- Overlay: passed across recording, streaming, settling, final, clipboard-only,
  saved, error, and cancellation captures. Draft and authoritative text use one
  color; recording bars remain red; normal verified paste fades silently.
- Accessibility: passed by implementation review. Primary controls have
  accessible names, keyboard focus remains native, high-contrast mode can use
  system styling, and reduced motion removes decorative timing.

## Public presentation review

- The README and website use the real capsule animation rather than a static
  concept screen.
- The animation shows confirmed live text, an in-place final replacement, one
  cursor delivery, and a quiet dismissal. It contains no success check or
  `已完成` label that the normal product path no longer displays.
- Chinese and English descriptions match that same behavior.
- The website makes no natural-speech accuracy claim and states that the
  Windows installer is unsigned.

## Result

Passed for the v0.3.1 release candidate. The implementation preserves the
selected command-center direction while making every visible control and claim
traceable to shipped behavior.
