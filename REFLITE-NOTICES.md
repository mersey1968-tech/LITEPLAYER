# Third-party credits — preliminary inventory

This is a working inventory, not a complete license notice or a grant of rights.

- FSRCNNX shaders and trained coefficients: igv, LGPL-3.0-or-later as identified in bundled shader headers. Upstream: https://github.com/igv/FSRCNN-TensorFlow . Verify exact provenance of both models, preserve copyright, supply applicable license texts and corresponding source.
- AndroidX Media3: Apache-2.0. https://github.com/androidx/media
- jcifs-ng: LGPL-2.1-or-later (verify exact dependency version and notices). https://github.com/AgNO3/jcifs-ng
- NextLib Media3 extension: GPL-3.0 per upstream/source-review dependency declaration; confirm exact packaged artifact, FFmpeg build flags and corresponding source obligations. https://github.com/anilbeesetti/nextlib
- Nova Video Player SMB compatibility settings: adapted from aos-FileCoreLibrary JcifsUtils.java; verify upstream file license and copyright before distribution. https://github.com/nova-video-player/aos-FileCoreLibrary

Review IEC audio implementation and all remaining code, assets and transitive dependencies for provenance and licenses. GPL-3.0-compatible distribution is a proposed approach, not a completed licensing decision. Dolby, DTS and NVIDIA names are used descriptively; no affiliation or certification is claimed.

## Verified upstream references (2026-11-27)

- JCIFS-NG 2.1.10 exact version metadata: https://central.sonatype.com/artifact/eu.agno3.jcifs/jcifs-ng/2.1.10 ; source tag: https://github.com/AgNO3/jcifs-ng/tree/jcifs-ng-2.1.10 ; license: https://github.com/AgNO3/jcifs-ng/blob/master/LICENSE .
- NextLib repository declares GPL-3.0: https://github.com/anilbeesetti/nextlib . The exact AAR version and its native build inputs must still be extracted and verified; the current upstream README is not evidence of the historical AAR configuration.
- Nova FileCoreLibrary repository: https://github.com/nova-video-player/aos-FileCoreLibrary ; Apache-2.0 repository license, exact adapted file revision and copyright still to be checked.
- FSRCNN-TensorFlow repository: https://github.com/igv/FSRCNN-TensorFlow . The bundled GLSL files identify LGPL-3.0-or-later, but the original trained model and generation scripts require separate provenance verification; do not assume all upstream files share that license.

## License text references

GNU GPL v3: https://www.gnu.org/licenses/gpl-3.0.txt
GNU LGPL v3: https://www.gnu.org/licenses/lgpl-3.0.txt
GNU LGPL v2.1: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt
Apache 2.0: https://www.apache.org/licenses/LICENSE-2.0.txt

These references are not a substitute for the complete license texts and notices required with distribution.
