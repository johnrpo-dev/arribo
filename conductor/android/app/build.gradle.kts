import java.util.Properties

plugins {
    id("com.android.application")
    // Firebase (push, 1a-14). Exige app/google-services.json, que no va al repositorio.
    id("com.google.gms.google-services")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "co.arribo.arribo_conductor"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "co.arribo.arribo_conductor"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = 26
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // Firma del APK que se instala a los conductores (1a-21). La llave y sus claves están en
    // android/key.properties y en un .jks fuera del repositorio (conductor/crear-llave.ps1). Sin ese
    // archivo, el release se firma con la llave de depuración: sirve para probar, no para repartir,
    // porque un APK firmado con otra llave no se instala encima del anterior.
    val propiedadesLlave = Properties()
    val archivoLlave = rootProject.file("key.properties")
    if (archivoLlave.exists()) {
        archivoLlave.inputStream().use { propiedadesLlave.load(it) }
    }
    signingConfigs {
        if (archivoLlave.exists()) {
            create("release") {
                storeFile = file(propiedadesLlave.getProperty("storeFile"))
                storePassword = propiedadesLlave.getProperty("storePassword")
                keyAlias = propiedadesLlave.getProperty("keyAlias")
                keyPassword = propiedadesLlave.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (archivoLlave.exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
