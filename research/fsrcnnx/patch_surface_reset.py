"""Isolate the surface-transition reset hypothesis.
Use Media3's public position-reset path at the current position, not a rewind.
No fixed latency offset; no audio or shader modifications.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a="""                    activePlayer.setVideoSurface(surface)
                    applyFrameRate()
                    if (resume1080AfterSurface) {"""
b="""                    activePlayer.setVideoSurface(surface)
                    applyFrameRate()
                    if (fmt.height > 800) {
                        // A position reset is queued after the new video surface.
                        // Preserve the current media position, not a guessed offset.
                        activePlayer.seekTo(activePlayer.currentPosition)
                    }
                    if (resume1080AfterSurface) {"""
assert s.count(a)==1,(a,s.count(a))
s=s.replace(a,b,1)
p.write_text(s)
print("1080p neural surface transition: Media3 position reset at current position.")
