# Reflite — isolated experimental Android TV build

Reflite is the working name for the new optional video-scaling research app. It installs beside LitePlayer, never overwrites the production player, and is NOT ready to replace it.

Current build stage:
- Original stable LitePlayer playback behavior and media engine.
- Separate package ID: com.example.reflite.experimental
- Separate home-screen label: Reflite
- Included low-ringing SDR research shader in APK assets, but **not connected** to the decoder or display pipeline yet.
- No added sharpening; native 4K, HDR and audio passthrough are unchanged.

Next stage: implement an independently selectable 1080p SDR OpenGL ES rendering path and compare timing, ringing, colour accuracy, audio passthrough and frame matching. Do not enable the experimental GPU route for HDR10 or Dolby Vision.

This project deliberately does not merge into the LitePlayer stable branch.
