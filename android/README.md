# 📱 SmartPanda Android App

Android companion app for SmartPanda (Phase 3 of the roadmap): remote control and live telemetry of the Fiat Panda 169, talking to the middleware running on the Raspberry Pi (Phase 2, not built yet).

## Stack

- **Language:** Kotlin
- **UI:** Jetpack Compose (Material 3)
- **Build:** Gradle (Kotlin DSL) with version catalog (`gradle/libs.versions.toml`)
- **Min SDK:** 26 (Android 8.0) — **Target SDK:** 35

## Getting started

Open **this folder** (`android/`, not the repo root) in Android Studio:

1. `File → Open…` → select `SmartPanda/android`
2. Android Studio will generate the Gradle wrapper JAR and `local.properties` (both git-ignored) on first sync.
3. Run the `app` configuration on an emulator or device.

The project currently shows a placeholder home screen. Real features depend on the Pi middleware exposing an API (WebSocket/REST) — see the roadmap in the root [README](../README_EN.md).

## Planned structure

```
app/src/main/java/com/smartpanda/app/
├── MainActivity.kt        # entry point (Compose)
├── ui/                    # screens & components (to come)
├── data/                  # Pi middleware client, telemetry models (to come)
└── ...
```

> No launcher icon yet — the system default is used until assets from `../assets/logos/` are converted to adaptive icons.
