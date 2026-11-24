from pathlib import Path
root=Path("proj/app/src/main")
p=root/"res/layout/activity_main.xml"
s=p.read_text()
needle='<Button android:id="@+id/refliteScalerButton"'
assert s.count(needle)==1
s=s.replace(needle,'''<Button android:id="@+id/refliteSyncButton"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="A/V Sync" />
        '''+needle,1)
p.write_text(s)
p=root/"java/com/example/liteplayer/MainActivity.kt"
s=p.read_text()
needle='findViewById<Button>(R.id.refliteScalerButton).setOnClickListener { showRefliteScalerDialog() }'
assert s.count(needle)==1
s=s.replace(needle,needle+'\n        findViewById<Button>(R.id.refliteSyncButton).setOnClickListener { showClockTraceDialog() }',1)
assert 'showAudioTracksDialog' in s or 'setTitle("Audio tracks")' in s
p.write_text(s)
print("Dedicated diagnostic control added; audio selection unchanged.")
