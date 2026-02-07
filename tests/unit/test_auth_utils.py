from __future__ import annotations

import hashlib

from services.auth.utils import AuthUtils
from services.vpn.subscriptions.utils import SubscriptionUtils


class TestAuthUtils:
    def test_hash_node_token_deterministic(self):
        h1 = AuthUtils.hash_node_token("my-token")
        h2 = AuthUtils.hash_node_token("my-token")
        assert h1 == h2

    def test_hash_node_token_sha256(self):
        expected = hashlib.sha256(b"test").hexdigest()
        assert AuthUtils.hash_node_token("test") == expected

    def test_hash_admin_api_key_deterministic(self):
        h1 = AuthUtils.hash_admin_api_key("key123")
        h2 = AuthUtils.hash_admin_api_key("key123")
        assert h1 == h2

    def test_hash_admin_api_key_sha256(self):
        expected = hashlib.sha256(b"secret").hexdigest()
        assert AuthUtils.hash_admin_api_key("secret") == expected

    def test_different_inputs_different_hashes(self):
        assert AuthUtils.hash_node_token("a") != AuthUtils.hash_node_token("b")


class TestSubscriptionUtils:
    def test_generate_returns_string(self):
        token = SubscriptionUtils.generate()
        assert isinstance(token, str)
        assert len(token) > 20

    def test_generate_unique(self):
        tokens = {SubscriptionUtils.generate() for _ in range(10)}
        assert len(tokens) == 10

    def test_hash_deterministic(self):
        h1 = SubscriptionUtils.hash("tok")
        h2 = SubscriptionUtils.hash("tok")
        assert h1 == h2

    def test_hash_sha256(self):
        expected = hashlib.sha256("tok".encode("utf-8")).hexdigest()
        assert SubscriptionUtils.hash("tok") == expected
