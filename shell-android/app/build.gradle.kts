import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.krszozda.latawiec"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.krszozda.latawiec.shell"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
        // Emulator loopback to a `uvicorn` on the host; override with -PserverUrl=http://...
        val serverUrl = providers.gradleProperty("serverUrl").getOrElse("http://10.0.2.2:8000")
        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.yandex.div:div:32.6.0")
    implementation("com.yandex.div:picasso:32.6.0")
}
