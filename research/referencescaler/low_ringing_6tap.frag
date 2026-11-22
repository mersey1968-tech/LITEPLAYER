#version 300 es
precision highp float;

// ReferenceScaler research fragment shader, RGB SDR ONLY.
// Two-pass: render horizontal pass to an intermediate FBO, then vertical.
// Not for MediaCodec SurfaceView or protected HDR / Dolby Vision paths.
// This shader is intentionally not connected to LitePlayer playback.
uniform sampler2D uSource;
uniform vec2 uInputSize;      // texel resolution of this pass' source
uniform vec2 uOutputSize;     // texel resolution of this pass' destination
uniform vec2 uAxis;           // (1,0) horizontal or (0,1) vertical
uniform float uRingingClamp;  // 0: full windowed sinc, 1: clamp to adjacent sample extrema
in vec2 vTexCoord;
out vec4 fragColor;

const float PI = 3.141592653589793;
const float RADIUS = 3.0;      // 6 taps per axis
const float CUTOFF = 0.96;     // Slightly soften the ideal source Nyquist cutoff
const float KAISER_BETA = 7.5;

// Modified Bessel function I0, truncated series; good for beta <= 8.
float besselI0(float x) {
    float term = 1.0, sum = 1.0;
    for (int k = 1; k <= 14; ++k) {
        float t = x / (2.0 * float(k));
        term *= t*t;
        sum += term;
    }
    return sum;
}
float sinc(float x) {
    float p = PI*x;
    return abs(p) < 1e-5 ? 1.0 : sin(p)/p;
}
float kernel(float x) {
    float a = abs(x);
    if(a >= RADIUS) return 0.0;
    float z = a / RADIUS;
    float win = besselI0(KAISER_BETA*sqrt(max(0.0, 1.0-z*z))) / besselI0(KAISER_BETA);
    return CUTOFF*sinc(CUTOFF*x)*win;
}

void main() {
    // Coordinate of output pixel center expressed in source texel units.
    // uAxis selects whichever axis is actively resampled.
    vec2 sourcePixel = vTexCoord*uInputSize - vec2(0.5);
    vec2 base = floor(sourcePixel);
    float frac = dot(sourcePixel-base, uAxis);

    vec3 acc = vec3(0.0);
    float weightSum = 0.0;
    vec2 stepUV = uAxis / uInputSize;
    vec2 nearestUV = (base+vec2(0.5))/uInputSize;
    for(int i = -2; i <= 3; ++i) {
        float x = float(i) - frac;
        float w = kernel(x);
        vec3 c = texture(uSource, nearestUV + float(i)*stepUV).rgb;
        acc += c*w;
        weightSum += w;
    }
    vec3 filtered = acc / max(weightSum, 1e-8);

    // Optional strict overshoot containment relative to the two nearest samples.
    // It prevents new bright/dark extrema; it also reduces legitimate sinc detail.
    vec3 a = texture(uSource, nearestUV).rgb;
    vec3 b = texture(uSource, nearestUV+stepUV).rgb;
    vec3 contained = clamp(filtered, min(a,b), max(a,b));
    filtered = mix(filtered, contained, clamp(uRingingClamp,0.0,1.0));
    fragColor = vec4(filtered, 1.0);
}
