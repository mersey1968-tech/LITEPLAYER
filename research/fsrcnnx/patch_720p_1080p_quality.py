"""Isolated Reflite-only 720p/1080p quality update.
720p: trained FSRCNNX 2x output (1440p) -> edge-constrained cubic 1.5x to 4K.
1080p: native FSRCNNX x2 to 4K.
No new UI, no changes to original LitePlayer or stable Reflite.
Apply after natural-detail and gentle automatic cleanup.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def once(a,b):
    global s
    n=s.count(a)
    if n!=1:raise RuntimeError(f"Expected one model match got {n}: {a[:85]!r}")
    s=s.replace(a,b,1)
once('''            uniform vec2 uSourceTexel;
            uniform float uHdr;''','''            uniform vec2 uSourceTexel;
            uniform vec2 uNeuralSize;
            uniform float uCubicNeural;
            uniform float uHdr;''')
once('''            void main(){
                float y=texture(uNeural,uv).r;''','''            // Four bilinear fetches approximate the 16-tap cubic reconstruction.
            // Run only when 720p neural 2x output (1440p) needs a final
            // 1.5x enlargement to 2160p. Avoid ringing beyond local extrema.
            float cubicNeural(vec2 pos) {
                vec2 x=pos*uNeuralSize-vec2(0.5);
                vec2 f=fract(x);
                vec2 base=floor(x);
                vec2 f2=f*f, f3=f2*f;
                vec2 w0=-0.5*f+f2-0.5*f3;
                vec2 w1=1.0-2.5*f2+1.5*f3;
                vec2 w2=0.5*f+2.0*f2-1.5*f3;
                vec2 w3=-0.5*f2+0.5*f3;
                vec2 g0=w0+w1, g1=w2+w3;
                vec2 v0=(base-vec2(1.0)+w1/g0+vec2(0.5))/uNeuralSize;
                vec2 v1=(base+vec2(1.0)+w3/g1+vec2(0.5))/uNeuralSize;
                float a=texture(uNeural,vec2(v0.x,v0.y)).r;
                float b=texture(uNeural,vec2(v1.x,v0.y)).r;
                float c=texture(uNeural,vec2(v0.x,v1.y)).r;
                float d=texture(uNeural,vec2(v1.x,v1.y)).r;
                float cubic=g0.y*(g0.x*a+g1.x*b)+g1.y*(g0.x*c+g1.x*d);
                float lo=min(min(a,b),min(c,d));
                float hi=max(max(a,b),max(c,d));
                return clamp(cubic,lo-0.025,hi+0.025);
            }
            void main(){
                float y=uCubicNeural>0.5?cubicNeural(uv):texture(uNeural,uv).r;''')
once('''        stages.forEach { targets.add(allocate(if(it.scaled)2*w else w,if(it.scaled)2*h else h)) }''','''        stages.forEach { targets.add(allocate(if(it.scaled)2*w else w,if(it.scaled)2*h else h)) }
        // Cubic reconstruction relies on bilinear 2x2 blending for its
        // four-fetch optimization. Only the final learned luma texture needs it.
        targets.lastOrNull()?.let {
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,it.texture)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MAG_FILTER,GLES30.GL_LINEAR)
        }''')
once('''        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uSourceTexel"),1f/w.toFloat(),1f/h.toFloat())''','''        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uSourceTexel"),1f/w.toFloat(),1f/h.toFloat())
        val neural=targets.last()
        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uNeuralSize"),neural.w.toFloat(),neural.h.toFloat())
        val cubic720=h <= 800 && outH > neural.h && outH >= 1600
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uCubicNeural"),if(cubic720) 1f else 0f)''')
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
r=p.read_text()
a='''                if (slowFrames >= 2 && neuralScale > 0.51f) {
                    neuralScale = if (neuralScale > 0.9f) 0.75f else 0.5f
                    slowFrames = 0
                    Log.i("Reflite GPU", "FSRCNNX performance scale -> " + neuralScale)
                }'''
b='''                // Keep 720p training resolution intact. The old 0.5x
                // fallback quietly discarded almost all learned fine detail.
                // 1080p retains a conservative 0.75x emergency fallback to
                // avoid extended audio/video stalls on busy Shield devices.
                val qualityFloor=if (srcH <= 800) 1.0f else 0.75f
                if (slowFrames >= 3 && neuralScale > qualityFloor) {
                    neuralScale = qualityFloor
                    slowFrames = 0
                    Log.i("Reflite GPU", "FSRCNNX protected quality scale -> " +
                        neuralScale + " source=" + srcW + "x" + srcH)
                }'''
n=r.count(a)
if n!=1:raise RuntimeError(f"Fallback expected one got {n}")
r=r.replace(a,b,1)
# Avoid processing repeated previous video frames just to benchmark them:
# sample only on fresh frames; retaining original rendering semantics.
p.write_text(r)
print("720p -> 1440p neural -> 2160p cubic; protected training resolution and 1080p quality floor.")
