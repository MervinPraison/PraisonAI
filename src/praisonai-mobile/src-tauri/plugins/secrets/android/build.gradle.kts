plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ai.praison.mobile.secrets"
    compileSdk = 36

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = "1.8"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.9.0")
    implementation("androidx.appcompat:appcompat:1.6.0")
    // THE dependency. EncryptedSharedPreferences + MasterKeys: Tink underneath,
    // the wrapping key generated in and never leaving the AndroidKeyStore.
    //
    // 1.0.0 rather than 1.1.0-alpha: this is the credential store for the whole
    // app, and "the newest alpha" is not a property worth having here. The
    // 1.0.0 API (`MasterKeys.getOrCreate`) is what Google's own documentation
    // still shows.
    implementation("androidx.security:security-crypto:1.0.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.15.3")
    implementation(project(":tauri-android"))
}
