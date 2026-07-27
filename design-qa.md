# VoiceFlow Application and Product Site Design QA

## Source and implementation

- Ambient visual asset:
  `site/assets/voiceflow-ambient-v2.png`
- Real product asset:
  `site/assets/voiceflow-app-home-v2.png`
- Local implementation: `http://localhost:4173/`
- Primary comparison viewport: 1280 × 720 CSS pixels, Chinese, light mode,
  page top.
- Responsive verification viewport: 390 × 844 CSS pixels, Chinese, light
  mode, page top.

## Comparison history

1. The earlier hero used a composite editor scene that competed with the actual
   product. It was removed.
2. The current hero uses a generated near-white acoustic field only as
   atmosphere, then places the real VoiceFlow settings screen and real overlay
   capture above it. No fake editor, transcript, model state, or platform asset
   is shown.
3. The mobile pass found a grid intrinsic-width defect that made the Chinese
   headline wider than its section. Grid children now use `minmax(0, 1fr)` and
   `min-width: 0`; the final 390 px viewport has no horizontal overflow.
4. The desktop pass found that the short Chinese hero title wrapped at the
   selected viewport. The hero allocation and title sizing were corrected; the
   final title is one line without reducing mobile legibility.

## Visual checks

- Header: passed. Brand, navigation, and language switch share one quiet
  baseline; the sticky blur does not obscure content.
- Hero hierarchy: passed. “开口。文字就位。” remains the entry point, followed
  by the offline promise, one primary download, compatibility, then product
  proof.
- Product truth: passed. The hero uses the real VoiceFlow window and overlay;
  the generated asset contains no text, controls, or fictitious state.
- Typography: passed. System display fonts, tight headline tracking, and
  restrained body measure remain legible in Chinese and English.
- Spacing and rhythm: passed. Sections use deliberate whitespace and avoid a
  dashboard-style card grid.
- Privacy section: passed. It explains the real tradeoff: cloud models may do
  more, while offline input avoids accounts, quotas, upload, and server state.
- Reliability section: passed. P95 figures disclose machine and sample limits;
  model copy does not turn a two-sample benchmark into a broad accuracy claim.
- Download section: passed. Windows is the only available artifact; macOS is
  explicitly unavailable instead of presenting a placeholder download.
- Mobile: passed at 390 × 844. No horizontal overflow; the headline, CTA,
  language switch, and product image remain usable.
- Reduced motion and focus: passed by implementation review. The page honors
  `prefers-reduced-motion`, and links, buttons, and disclosure controls have
  visible focus states.

## Functional checks

- Chinese/English switch updates document language, title, metadata, body copy,
  image alt text, URL query, and persisted preference.
- Both primary CTAs resolve to the versioned
  `VoiceFlow-0.2.0-Windows-x64.exe` asset.
- Navigation anchors, GitHub links, release notes, privacy notes, licenses, and
  issue links are real destinations.
- All visible images loaded with non-zero natural dimensions.
- Browser console contained no warnings or errors.

## Application checks

- Home: passed. The task order is value, readiness, trial, then recent result;
  it no longer opens as a wall of settings.
- Navigation: passed. Six focused destinations remain: Home, History,
  Dictation, Dictionary, Diagnostics, and About. Hotkey setup is kept in
  Dictation instead of occupying a standalone page.
- Dictation: passed. SenseVoice is described as the daily default. Unqualified
  alternative models are not exposed as customer-facing choices.
- Dictionary: passed. Proper nouns, reusable phrases, and deterministic
  corrections are separate, editable sections with explicit behavior.
- Diagnostics: passed. Microphone, model, hotkeys, local storage, and runtime
  checks use structured status rows rather than a raw text dump.
- About: passed. Version, offline boundary, licenses, and the user-data
  location are visible without exposing a real username.
- History: passed. Preview length increased from 90 to 180 characters with
  wrapping, while complete text remains available.
- Overlay: passed. The stable prefix remains fixed and only confirmed suffixes
  reveal at a 24 ms rhythm with a 420 ms catch-up ceiling. Final and processing
  states cancel the animation.
- Capture safety: passed. Product screenshots default to an isolated temporary
  data directory populated with neutral fixtures; private history is never
  included unless `--live-data` is explicitly supplied.

## Final result

Passed for publication. The implementation follows the selected Apple-inspired
direction without turning the page into a concept poster: the product story,
download path, platform availability, privacy proof, and bilingual experience
remain functional and truthful.
