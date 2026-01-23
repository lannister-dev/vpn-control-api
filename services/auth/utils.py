import hashlib


class AuthUtils:
    @staticmethod
    def hash_node_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()