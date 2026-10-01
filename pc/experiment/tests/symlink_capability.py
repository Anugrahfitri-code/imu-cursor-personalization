"""Runtime probe for hosts that cannot create filesystem symlinks."""
import os
import tempfile

__all__ = ["can_create_symlinks"]


def can_create_symlinks() -> bool:
    """Return True when this process is allowed to create a real symlink.

    Non-elevated Windows sessions without Developer Mode reject symlink
    creation with a privilege error (WinError 1314).  Tests that rely on
    genuine symlinks skip themselves on such hosts; capable hosts still
    run them in full.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "target.txt")
        link = os.path.join(tmp, "link.txt")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("probe")
        try:
            os.symlink(target, link)
        except OSError:
            return False
    return True