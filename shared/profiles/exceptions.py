class ProfileRegistryError(RuntimeError):
    pass


class ProfilesBootstrapError(RuntimeError):
    """Fatal error during profiles registry bootstrap."""


class ProfileBuildError(RuntimeError):
    """Fatal error during profile build process."""


class ProfileRegionMismatchError(RuntimeError):
    """Fatal error during profile region mismatch."""
