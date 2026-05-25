from uuid import uuid4

from services.probe.schemas import ProbeSyntheticDesiredBackends


class TestProbeSyntheticDesiredBackends:
    def test_groups_backend_ids_by_transport(self):
        first_backend_id = uuid4()
        second_backend_id = uuid4()

        desired_backends = ProbeSyntheticDesiredBackends()
        desired_backends.add_backend(transport_kind="reality", backend_id=first_backend_id)
        desired_backends.add_backend(transport_kind="reality", backend_id=second_backend_id)
        desired_backends.add_backend(transport_kind="ws", backend_id=second_backend_id)

        assert desired_backends.backend_ids_for("reality") == {first_backend_id, second_backend_id}
        assert desired_backends.backend_ids_for("ws") == {second_backend_id}
        assert desired_backends.is_empty() is False

    def test_returns_copy_for_missing_transport(self):
        desired_backends = ProbeSyntheticDesiredBackends()

        backend_ids = desired_backends.backend_ids_for("reality")
        backend_ids.add(uuid4())

        assert desired_backends.backend_ids_for("reality") == set()
        assert desired_backends.is_empty() is True
