# IEC audio provenance verification — 2026-11-21

## Verified finding

The custom IEC audio implementation in LitePlayer is materially adapted from the IEC patch in `backcountrymountains/fire-tv-jellyfin-dv-iec`:

- `IecAudioOutput.kt`: 55 identical long lines to upstream patch (including implementation-specific documentation and logic)
- `IecAudioOutputProvider.kt`: 64 matching long lines
- `IecPacker.kt`: 122 matching long lines

Matching counts compare normalized full lines longer than 40 characters, and are evidence of substantial shared implementation, **not a legal originality analysis or a full percentage similarity measurement**. `IecPacker.kt` explicitly credits FFmpeg's `spdifenc.c` under LGPL-2.1-or-later. The upstream project README explicitly describes the patch collection as GPL-2.0, with a repository GPL version 2 license file. The specific new IEC adaptation files have no separately observed GPL-2.0-or-later permission notice; do not presume a blanket GPL-2.0-or-later grant based solely on Jellyfin Android TV's project license.

## Other component

`io.github.anilbeesetti:nextlib-media3ext:1.7.1-0.9.0` is in the actual Gradle source ZIP and is published under GPL-3.0 according to Maven artifact metadata. GPL-2.0-only and GPL-3.0-only are incompatible for a combined distributed work, unless additional permission or an exception applies. Verify exact adaptation's grants with copyright holders and confirm the Android binary really contains the relevant library before making a final finding.

## Immediate next action (nontechnical, preserving working audio)

Seek clarification from the IEC patch author on whether the three **new** IEC audio implementation files are available under GPL-2.0-or-later or GPL-3.0-compatible terms. The existing upstream project GPL-2.0 labeling leaves this uncertain. Any permission should be explicit, in writing and attributable to appropriate rights holders. The FFmpeg-derived IecPacker portion must continue to retain its LGPL obligations.

**Draft permission request (not sent):**

Subject: License clarification for IEC 61937 audio implementation

Hello,

I'm preparing an open-source release of LitePlayer, an Android TV player using adapted versions of the IEC 61937 audio implementation in your `fire-tv-jellyfin-dv-iec` patch.

The three affected files are `IecAudioOutput.kt`, `IecAudioOutputProvider.kt`, and `IecPacker.kt` (the latter explicitly credits FFmpeg LGPL-2.1-or-later code). Your project currently states GPL-2.0. Our build also includes a GPL-3.0-licensed third-party media extension.

Could you confirm whether you own the relevant changes and can license the original IEC adapter portions under **GPL-2.0-or-later** or another GPL-3.0-compatible license? If the terms cannot be changed, please let us know. We will preserve all required notices and attribution.

Thank you for your contribution.

## Status

**Distribution hold remains in effect** until the license compatibility questions, full dependency inventory, source availability and notices are addressed. No playback code changes have been made.

### Source references
- https://github.com/backcountrymountains/fire-tv-jellyfin-dv-iec/blob/main/patches/iec/0001-Add-IEC-61937-packing-for-DTS-and-TrueHD-bitstreamin.patch
- https://github.com/backcountrymountains/fire-tv-jellyfin-dv-iec/blob/main/README.md
- https://github.com/backcountrymountains/fire-tv-jellyfin-dv-iec/blob/main/LICENSE
- https://mvnrepository.com/artifact/io.github.anilbeesetti/nextlib-media3ext/1.7.1-0.9.0
- https://www.gnu.org/licenses/gpl-faq.html#v2v3Compatibility
