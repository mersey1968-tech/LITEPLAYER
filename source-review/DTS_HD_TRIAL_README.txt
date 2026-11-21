Shield DTS-HD passthrough experiment

This is NOT a Nova audio-engine port. It is a narrow Media3 trial: DTS core is removed from the forced passthrough capability list while DTS-HD remains enabled. This may prevent Media3 from falling back to DTS core, or it may cause PCM decoding / no audio. TrueHD capability and video renderer are unchanged.

Build from this ZIP using the existing GitHub Actions workflow. Check AVR front-panel indication with a DTS-HD MA sample. If the result is PCM or silence, revert to the previous ZIP. Not compiled or device-tested here.

Nova reference: aos-avos Source/audio_interface_audiotrack_java.c: WAVE_FORMAT_DTS_HD_MA uses AudioFormat.ENCODING_DTS_HD and conditional 7.1 HDMI channel mask. Media3's stock sink cannot be assumed to replicate that.
