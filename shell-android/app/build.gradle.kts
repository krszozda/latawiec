import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.krszozda.latawiec"
    compileSdk = 36

    defaultConfig {
        // Shipping your own app overrides these: see docs/shipping.md.
        applicationId =
            providers.gradleProperty("appId").getOrElse("io.github.krszozda.latawiec.shell")
        minSdk = 26
        targetSdk = 36
        versionCode = providers.gradleProperty("versionCode").getOrElse("1").toInt()
        versionName = providers.gradleProperty("versionName").getOrElse("0.1")
        resValue(
            "string",
            "app_name",
            providers.gradleProperty("appName").getOrElse("Latawiec"),
        )
        // Emulator loopback to a `uvicorn` on the host; override with -PserverUrl=http://...
        val serverUrl = providers.gradleProperty("serverUrl").getOrElse("http://10.0.2.2:8000")
        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
        manifestPlaceholders["deepLinkScheme"] =
            providers.gradleProperty("deepLinkScheme").getOrElse("latawiec")
        // The generic try-it-out APK passes -Pcleartext so a typed LAN http
        // URL works; store builds keep the platform default (https only).
        manifestPlaceholders["cleartext"] =
            if (providers.gradleProperty("cleartext").isPresent) "true" else "false"
        // Push rides on Firebase and is branded like everything else: pass
        // the three values from your Firebase project's Android app (see
        // docs/shipping.md). Without them the shell runs push-free.
        for ((field, property) in mapOf(
            "FIREBASE_PROJECT_ID" to "firebaseProjectId",
            "FIREBASE_APP_ID" to "firebaseAppId",
            "FIREBASE_API_KEY" to "firebaseApiKey",
        )) {
            buildConfigField(
                "String",
                field,
                "\"${providers.gradleProperty(property).getOrElse("")}\"",
            )
        }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // The libraries bundle ~80 translations; the shell itself has no strings.
        resourceConfigurations += listOf("en")
    }

    buildFeatures {
        buildConfig = true
    }

    // Store uploads need a signed bundle; local builds stay unsigned when
    // the four properties are absent.
    val storeFile = providers.gradleProperty("releaseStoreFile").orNull
    if (storeFile != null) {
        signingConfigs.create("release") {
            this.storeFile = file(storeFile)
            storePassword = providers.gradleProperty("releaseStorePassword").get()
            keyAlias = providers.gradleProperty("releaseKeyAlias").get()
            keyPassword = providers.gradleProperty("releaseKeyPassword").get()
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            if (storeFile != null) {
                signingConfig = signingConfigs.getByName("release")
            } else if (providers.gradleProperty("debugSign").isPresent) {
                // The generic try-it-out APK: a real release build (so the
                // debug-only serverUrl extra stays dead) that still installs
                // anywhere without a keystore.
                signingConfig = signingConfigs.getByName("debug")
            }
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
    implementation("com.google.firebase:firebase-messaging:26.0.1")

    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
}
