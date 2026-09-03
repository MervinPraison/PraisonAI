# Consumer rules: applied to the APP that depends on this library, not to the
# library itself. Empty on purpose -- the only class here is @TauriPlugin
# annotated and reached by name from Rust (register_android_plugin), and
# tauri-android's own consumer rules already keep those.
#
# The FILE, however, is not optional: `android/build.gradle.kts` names it in
# consumerProguardFiles, and AGP fails the library build if a file named there
# is missing. It has to exist even with nothing in it.
