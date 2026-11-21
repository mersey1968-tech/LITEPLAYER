# Resolved dependency inventory — 2026-11-21

A GitHub Actions `License dependency inventory` run completed successfully: [run 44960601945](https://github.com/mersey1968-tech/LITEPLAYER/actions/runs/44960601945). The downloadable `LitePlayer-dependency-inventory` artifact contains `debugRuntimeClasspath.txt`, `releaseRuntimeClasspath.txt`, and the working Gradle build file.

## Confirmed direct runtime dependencies
- `eu.agno3.jcifs:jcifs-ng:2.1.10` — LGPL licensing review required; its graph brings in `org.slf4j:slf4j-api:1.7.36` and `org.bouncycastle:bcprov-jdk18on:1.76`.
- `androidx.activity:activity-ktx:1.9.3`
- `androidx.media3:media3-exoplayer:1.11.1`
- `androidx.media3:media3-ui:1.11.1`
- `io.github.anilbeesetti:nextlib-media3ext:1.7.1-0.9.0` — included as an actual resolved runtime dependency; references Media3 1.7.1 but resolves to 1.11.1 in this build.
- Kotlin standard library resolves to 2.2.10.

This is **dependency verification**, not a complete license inventory or software bill of materials. More AndroidX and transitive libraries are included. The AAR/APK's native files must be inspected to determine if software codecs and bundled assets change redistribution obligations.

## Conclusions
The suspected licensing combination is present in the dependency graph; it is not merely a stale comment. The independent GPL-2.0 IEC code provenance has also been checked against the patch. However, the exact compatibility/permissions question remains open at [upstream issue #1](https://github.com/backcountrymountains/fire-tv-jellyfin-dv-iec/issues/1). No reply was present when last checked on 2026-11-21.

**Public binary release remains blocked pending resolution.** None of these checks alters the source of the stable player.
