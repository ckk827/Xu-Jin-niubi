"""Preview configuration defaults; platform-specific expiry policies stay independent.

These values are implementation defaults, not measured optimal thresholds.
Windows members may override observation windows through their existing settings.
Android heartbeat validation uses the fixed protocol defaults below.
"""

DEFAULT_ACTIVE_SECONDS = 60
DEFAULT_REST_SECONDS = 1200
WINDOWS_POLL_SECONDS = 3
WINDOWS_STALE_SECONDS = 15
ANDROID_HEARTBEAT_SECONDS = 15
ANDROID_STALE_SECONDS = 90
ANDROID_CLOCK_SKEW_SECONDS = 30
PAIR_CODE_LIFETIME_SECONDS = 300
MANUAL_STATE_LIFETIME_SECONDS = 1800
