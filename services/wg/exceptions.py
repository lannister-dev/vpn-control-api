class WgMeshError(Exception):
    pass


class WgMeshAddressPoolExhaustedError(WgMeshError):
    pass


class WgMeshUnknownNodeError(WgMeshError):
    pass
