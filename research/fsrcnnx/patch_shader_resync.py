"""Test current-position resync after the first neural draw, not attachment."""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a="""                        gpu.onFirstNeuralFrame = { resume() }"""
b="""                        gpu.onFirstNeuralFrame = {
                            if (player === activePlayer && scalerView === gpu &&
                                referenceScalerEnabled && !isFinishing) {
                                activePlayer.seekTo(activePlayer.currentPosition)
                            }
                            resume()
                        }"""
assert s.count(a)==1,(a,s.count(a))
s=s.replace(a,b,1)
p.write_text(s)
print("Resync triggered by first neural draw; no fixed seek delay or rewind.")
