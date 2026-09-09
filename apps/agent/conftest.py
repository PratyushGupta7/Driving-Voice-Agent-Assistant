import sys
from types import ModuleType

try:
    import livekit.local_inference  # noqa: F401
except Exception:
    fake_native = ModuleType("livekit.local_inference._native")
    fake_native.EOT = type("EOT", (), {})
    fake_native.VAD = type("VAD", (), {})
    fake_native.VAD_WINDOW_SAMPLES = 512
    sys.modules["livekit.local_inference._native"] = fake_native
    fake_local = ModuleType("livekit.local_inference")
    fake_local.EOT = fake_native.EOT
    fake_local.VAD = fake_native.VAD
    fake_local.VAD_WINDOW_SAMPLES = 512
    sys.modules["livekit.local_inference"] = fake_local
