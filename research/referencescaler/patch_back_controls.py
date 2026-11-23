"""Back closes visible Reflite playback controls before returning to Plezy.
No changes to intent result, next-episode, audio, or upscaling.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a='''        if (event.keyCode == KeyEvent.KEYCODE_BACK) {
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) exitToCaller()
            return true
        }'''
b='''        if (event.keyCode == KeyEvent.KEYCODE_BACK) {
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
                if (controlPanel.visibility == View.VISIBLE) {
                    concealControls("Back: hide playback controls")
                } else {
                    exitToCaller()
                }
            }
            return true
        }'''
assert s.count(a)==1, "Back dispatcher changed"
s=s.replace(a,b,1)
a='''    override fun onBackPressed() {
        exitToCaller()
    }'''
b='''    override fun onBackPressed() {
        if (controlPanel.visibility == View.VISIBLE) concealControls("Back")
        else exitToCaller()
    }'''
assert s.count(a)==1, "Activity back handler changed"
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite Back: dismiss visible controls first; subsequent Back exits to Plezy")
