DTS-HD-only IEC61937 experimental trial

Based on the last working LitePlayer source (back_exit_fix).
Media3 upgraded 1.7.1 -> 1.11.1 to use AudioOutputProvider.
Only DTS-HD MIME format is intercepted; TrueHD, AC3, EAC3, and other formats delegate to stock Media3.
The IEC AudioTrack uses 192 kHz and 7.1 carrier; DTS-HD is packed into type IV bursts.
This is uncompiled and untested on NVIDIA Shield. It may fail to compile or play.
No fallback guarantee: if IEC AudioTrack initialization fails, DTS-HD playback may fail.
Do not replace your known-working source until tested.
