plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.example.liteplayer"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.example.liteplayer"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.1"
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") } // keep APK small
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {\n    implementation("eu.agno3.jcifs:jcifs-ng:2.1.10")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.media3:media3-exoplayer:1.11.1")
    implementation("androidx.media3:media3-ui:1.11.1")
    // FFmpeg software decoders for Media3 (GPL-3.0): ALAC, TrueHD/MLP, FLAC, lossless H.264/HEVC/VP9 fallback
    implementation("io.github.anilbeesetti:nextlib-media3ext:1.7.1-0.9.0")
}
