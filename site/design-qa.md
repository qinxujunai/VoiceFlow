# VoiceFlow product site design QA

## Direction

The selected direction is a quiet command center: editorial typography,
generous whitespace, restrained blue, real product screenshots, and no
decorative illustrations. It extends the desktop application's compact,
local-first visual language instead of presenting VoiceFlow as a generic AI
tool.

## Verified states

- Desktop viewport: 1280 x 720, no console errors.
- Mobile viewport: 390 x 844, no horizontal overflow.
- Simplified Chinese is the default language.
- English switch updates the document language, title, navigation, and product
  copy without reloading.
- Primary download and source links are real links.
- The macOS card is intentionally unavailable; it does not imitate a download.
- Keyboard focus is visible and reduced-motion preferences are respected.
- All product imagery is captured from the current VoiceFlow build.

## Release truth

The site identifies the Windows artifact as an unsigned public Beta and directs
users to verify its SHA-256. It does not claim a signed Windows build or a
macOS package before those artifacts have passed their platform-specific gates.

## Result

Passed local browser QA on 2026-07-27. The production deployment remains gated
on a matching GitHub Release asset at the download URL.
