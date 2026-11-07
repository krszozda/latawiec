import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.krszozda.latawiec"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.krszozda.latawiec.shell"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
        // Emulator loopback to a `uvicorn` on the host; override with -PserverUrl=http://...
        val serverUrl = providers.gradleProperty("serverUrl").getOrElse("http://10.0.2.2:8000")
        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // The libraries bundle ~80 translations; the shell itself has no strings.
        resourceConfigurations += listOf("en")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
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
    implementation("com.google.android.material:material:1.12.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.yandex.div:div:33.10.0")
    implementation("com.yandex.div:coil:33.10.0")

    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
}
