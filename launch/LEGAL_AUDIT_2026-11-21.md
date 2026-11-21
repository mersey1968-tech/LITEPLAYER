# LitePlayer redistribution and legal compliance audit
**Date:** 2026-11-21  
**Scope:** GitHub repository `mersey1968-tech/LITEPLAYER`, public-launch-prep branch, Android build workflow and checked-in source.  
**Status:** **BLOCKED FOR PUBLIC BINARY DISTRIBUTION** until the items below are resolved.  
**Nature:** Preliminary technical open-source compliance assessment, **not legal advice or a legal clearance opinion**.

## Executive assessment
The build includes GPL-3.0 NextLib (`io.github.anilbeesetti:nextlib-media3ext:1.7.1-0.9.0`) and source adapted from the `backcountrymountains/fire-tv-jellyfin-dv-iec` GPL-2.0 project. A GPL-2.0-only/GPL-3.0-only combination may be incompatible. The applicable licensing to the specific adapted files needs a provenance check and rights clarification or technical separation/reimplementation. No LitePlayer project-wide license or full third-party notices are in the current release source tree. **Do not put a public release APK on GitHub yet.**

## Actual build topology
`.github/workflows/main.yml` unzips `LitePlayer.zip`, overlays `source-review/.../MainActivity.kt`, `audio/IecAudioOutput.kt`, `activity_main.xml`, and `SmbAccess.kt`, and inserts `jcifs-ng:2.1.10` into Gradle. The other audio files `IecPacker.kt` and `IecAudioOutputProvider.kt` exist within the ZIP; confirm their exact binary/source hash against the overlays before release. `LitePlayer.zip` uses NextLib's Media3 extension dependency. A public GitHub repository is not by itself a complete corresponding-source distribution.

## Component compliance matrix

| Component | Evidence | License / issue | Action before release |
|---|---|---|---|
| AndroidX Media3 1.11.1 | Gradle dependency | Apache-2.0; retain licenses/attribution; trademarks not granted | Include license and applicable notices |
| jcifs-ng 2.1.10 | Workflow injection, SMB code | LGPL-2.1; binary/library source, modification and replacement/relinking compliance must be evaluated | Supply exact notices, source and appropriate replacement mechanism/source compliance |
| NextLib media3ext 1.7.1-0.9.0 | ZIP Gradle file | NextLib repository GPL-3.0. GPL copyleft potentially reaches distributed combined Android application, and corresponding source/build scripts must be provided | Examine exact artifact POM/AAR, bundled native FFmpeg, exact source and transitive licenses; determine distribution license |
| IEC packer | `IecPacker.kt` header and `IEC_SOURCE_ATTRIBUTION.txt` | Derivative of FFmpeg `libavformat/spdifenc.c`, LGPL-2.1-or-later; attribution already included in comment | Include LGPL license, copyright text, modified source and source availability; comply with any GPL combinations |
| IEC audio output/provider | `IecAudioOutput*.kt`, attribution file | Attribution says adapted from `backcountrymountains/fire-tv-jellyfin-dv-iec`, whose repo is GPL-2.0. Exact file provenance and GPL-2.0-only versus GPL-2.0-or-later permissions are NOT confirmed | Review upstream git/file headers and compare adapted lines. Obtain relicensing permission, replace incompatible code, or establish legal compatibility before combining with GPL-3.0 |
| Android build plugins, Kotlin, transitive artifacts | Gradle | Multiple Apache/MIT/BSD and potentially other licenses; transitive inventory not yet run | Generate resolved runtime dependency graph/SBOM and exact license/notice list |
| LitePlayer project code | No root `LICENSE` found | Ownership, author contributions and intended outbound license not documented | Confirm owner rights and choose compatible license; publish complete source if GPL-required |
| Demo screenshots/videos | Launch plan | Footage and film clips can be copyrighted | Use own original screen captures and licensed test media |
| Dolby / DTS / HDR / NVIDIA product names | Marketing copy | Descriptive compatibility claims differ from certification/endorsement or trademark-logo rights | Use factual plain-text names, no corporate logos or certification marks without permission; verify capabilities with actual files/hardware |
| Decoder patents | Dolby/FFmpeg/codec tech | Copyright licenses do not necessarily grant patent rights; hardware-decoded/bitstream-only versus bundled software decoding matters | Review target jurisdictions, exact codecs and native libraries; obtain specialist advice if needed |
| Privacy | Android manifest has INTERNET, network discovery and SMB connections; SMB credentials appear held in RAM; local preferences store connection context | Full network/data audit not yet completed | Verify all networking/endpoints/telemetry and user storage, then publish an accurate privacy notice; do not promise zero data collection before verification |

## Potential license incompatibility — highest priority
- Source `backcountrymountains/fire-tv-jellyfin-dv-iec/LICENSE` contains GNU GPL version 2 text, and its README calls the repository GPL-2.0. Whether code included here is GPL-2.0-only, GPL-2.0-or-later, independently owned, or separately available under another license is not established.
- `anilbeesetti/nextlib/LICENSE` contains GNU GPL version 3; its README identifies GPL-3.0.
- A GPL-2.0-only and GPL-3.0-only work generally cannot be combined into a distributed derivative unless an exception or further permission applies. **Do not assume copying an attribution notice resolves this.**
- Need verify exact audio source provenance, not infer it solely from project's README. If incompatible, preferred options: get written compatible licenses from rights holders, replace/reimplement affected code with compatible provenance, or remove one component after testing its impact on audio. Do **not** alter the tested player's playback engine without regression testing.

## Third-party compliance work still to do
1. Extract the *actual APK* or build ZIP and produce a dependency inventory including native libraries and exact versions; do not trust only `source-review/app/build.gradle.kts` because workflow builds the unpacked `LitePlayer.zip`.
2. Compare IEC source to the upstream patches and inspect file-level copyright/license terms, revision and dates.
3. Determine all GPL/LGPL obligations for a statically packaged Android APK, including complete corresponding source, scripts, necessary notices, and any relinking/replacement requirements.
4. Decide the application-level license in light of included copyleft code; prepare `LICENSE`, `NOTICE`, third-party license files, source archive, and a source correspondence manifest.
5. Check branded claims, distribution patent implications, privacy policies, copyright of publicity assets and user-facing disclaimers.
6. Have legally competent reviewer resolve uncertain copyleft combination and patent/trademark questions before publishing broadly.

## References (verified 2026-11-21)
- https://github.com/backcountrymountains/fire-tv-jellyfin-dv-iec ; `LICENSE` = GPL version 2.
- https://github.com/anilbeesetti/nextlib ; `LICENSE` = GPL version 3.
- https://github.com/AgNO3/jcifs-ng/blob/master/LICENSE ; LGPL 2.1.
- https://central.sonatype.com/artifact/eu.agno3.jcifs/jcifs-ng/2.1.10
- https://github.com/androidx/media/blob/release/LICENSE ; Apache 2.0.
- https://ffmpeg.org/legal.html and https://ffmpeg.org/doxygen/trunk/spdifenc_8c_source.html ; LGPL 2.1+, codec patent caution.
- https://professional.dolby.com/licensing ; licensing/branding context.

**Do not label the project legally cleared solely on the basis of successful private playback tests.**
