import hashlib


class AuthUtils:
    @staticmethod
    def hash_node_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def hash_admin_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()
