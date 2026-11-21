LitePlayer subtitle diagnostics trial

Changes limited to MainActivity.kt subtitle callbacks:
- Removes the SRT last-cue-only filter: displays all cues as supplied by Media3.
- Does not clear active cues during onTracksChanged.
- Logs selected subtitle MIME/language and changed cue groups to Android logcat
  using the LitePlayerDiagnostics tag, including a maximum 180-character excerpt
  of each cue's original text with newline escapes.
- Does not rewrite subtitle text or modify its styling/spans.

NOTE: Subtitle dialogue text is written to local Android logcat for diagnostics.
Do not publicly share an unredacted log if it contains private dialogue.

Separate application ID: com.example.liteplayer.subtitletrial
Build via the existing GitHub Actions workflow; no APK compiled here.
