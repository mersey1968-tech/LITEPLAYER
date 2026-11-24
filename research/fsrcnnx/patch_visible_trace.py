"""Expose sampled timing records on TV; no playback control changes."""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
(root/"ClockTrace.kt").write_text("""package com.example.liteplayer

object ClockTrace {
    private val latest = linkedMapOf<String, String>()
    private val snapshots = arrayOfNulls<String>(3)
    @Synchronized fun record(tag: String, value: String) {
        latest[value.substringBefore(' ')] = value
        android.util.Log.i(tag, value)
    }
    @Synchronized fun capture(slot: Int) {
        snapshots[slot] = latest.values.joinToString("\\n")
    }
    @Synchronized fun text(slot: Int): String = snapshots[slot] ?: "Not captured"
    @Synchronized fun reset() {
        latest.clear()
        snapshots.fill(null)
    }
}
""")
for name in ["MainActivity.kt","ReferenceScalerView.kt","audio/IecAudioOutput.kt"]:
    p=root/name
    s=p.read_text().replace('android.util.Log.i("RefliteClock",','com.example.liteplayer.ClockTrace.record("RefliteClock",').replace('Log.i("RefliteClock",','com.example.liteplayer.ClockTrace.record("RefliteClock",')
    p.write_text(s)
p=root/"MainActivity.kt"
s=p.read_text()
needle="    private fun showRefliteScalerDialog() {"
s=once(s,needle,"""    private fun showClockTraceDialog() {
        val labels = arrayOf("Capture original", "Capture neural out of sync",
            "Capture after rewind", "View captured results", "Clear captures")
        AlertDialog.Builder(this).setTitle("A/V Sync Diagnostics")
            .setItems(labels) { _, which ->
                when (which) {
                    0, 1, 2 -> {
                        ClockTrace.capture(which)
                        Toast.makeText(this, "Timing snapshot saved", Toast.LENGTH_SHORT).show()
                    }
                    3 -> showClockTraceResults()
                    4 -> ClockTrace.reset()
                }
            }.setNegativeButton("Close", null).show()
    }

    private fun showClockTraceResults() {
        val body = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(24, 12, 24, 12)
        }
        val names = arrayOf("1. ORIGINAL", "2. NEURAL OUT OF SYNC", "3. AFTER REWIND")
        for (i in names.indices) {
            body.addView(android.widget.TextView(this).apply {
                text = names[i] + "\\n" + ClockTrace.text(i)
                textSize = 14f
                setTextIsSelectable(true)
                setPadding(0, 0, 0, 12)
            })
        }
        val scroll = android.widget.ScrollView(this).apply {
            addView(body)
            isFocusable = true
        }
        val dialog = AlertDialog.Builder(this).setTitle("A/V Sync Diagnostics — photograph results")
            .setView(scroll).setPositiveButton("Close", null).create()
        dialog.show()
        dialog.window?.setLayout(android.view.ViewGroup.LayoutParams.MATCH_PARENT,
            android.view.ViewGroup.LayoutParams.MATCH_PARENT)
    }

"""+needle)
# Attach the option only to the scaler dialog, regardless of other dialogs.
start=s.index(needle)
end=s.index("    private fun applyRefliteScaler()",start)
part=s[start:end]
part=once(part,'.setNegativeButton("Cancel", null)', '.setNeutralButton("A/V Sync Diagnostics") { _, _ -> showClockTraceDialog() }\n            .setNegativeButton("Cancel", null)')
s=s[:start]+part+s[end:]
p.write_text(s)
print("Visible clock diagnostics added")
