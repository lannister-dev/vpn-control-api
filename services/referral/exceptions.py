class ReferralError(Exception):
    pass


class ReferralCodeNotFound(ReferralError):
    pass


class SelfReferralNotAllowed(ReferralError):
    pass


class AlreadyReferred(ReferralError):
    pass


class ReferralNotEnabled(ReferralError):
    pass
