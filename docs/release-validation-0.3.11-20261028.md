# VoiceFlow 0.3.11 validation handoff — 2026-10-28

Status: **not released**. The current installed candidate is build 261028.3, source commit `dfde0e2` (full commit recorded in its build provenance). The offline installer SHA-256 is `0b200ecb27eead9adba33cc63f53a0360aef497044a5c690bda73e5ca72b241a`. A public Release or website update must not be inferred from this candidate.

The speech indicator is anchored to the left edge; short text is centered within the region to its right as the capsule changes width. Width targets now track text continuously and animation follows successive targets. Prior user feedback noted excessive right space and uneven expansion; human verification of the final build remains pending at the time of this record.

The release verifier passed with 862 tests. Native Chinese text renders at four capsule widths were captured locally. The installed payload (493 files), seven model files and seven protected data files matched before application start. The same installer was uploaded as draft `v0.3.11-candidate.1.6`, and isolated Windows workflow run 40646034963 was dispatched. Inspect its result; dispatch is not a pass.

Do not publish until the exact artifact has passed required human speech and visual acceptance, isolated Windows installation/upgrade/uninstall, and complete artifact-bound license review/sign-off and all other release gates. The earlier 261028.1 candidate is superseded; its isolated run failed because its checksum asset was absent. The 261027.3 candidate passed its isolated workflow but is also superseded. Preserve these results.

Local-only evidence is under `E:/01_Projects/AI_core/release-evidence-20261027/`. The most recent pre-install user-data backup is `voice-data-before-right-center-upgrade.zip` in that directory. It contains private data; do not upload it. User speech content is not recorded here. The prior local state is preserved on branch `backup/local-20261027`; earlier installer candidates are retained in the local evidence directory.
