## 1. Implementation
- [x] 1.1 Add a unit test that extracts a tar layer containing an executable file and confirms the execute bit is preserved in Android mode.
- [x] 1.2 Update _safe_extract_tar permission normalization so files with execute bits keep execute permissions on Android.
- [x] 1.3 Update any related logging or comments to reflect the executable-bit preservation behavior.
- [x] 1.4 Run tests: pytest -k "android_permissions".
