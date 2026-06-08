from services.balancer.selection import BackendCandidate, choose_backend_tag


def candidate(tag: str, load: int, tiebreak: int = 0) -> BackendCandidate:
    return BackendCandidate(tag=tag, load=load, tiebreak=tiebreak)


def test_empty_returns_none():
    assert choose_backend_tag([], current_tag=None) is None


def test_picks_least_loaded_when_no_current():
    candidates = [candidate("backend-a", 10), candidate("backend-b", 3), candidate("backend-c", 7)]
    assert choose_backend_tag(candidates, current_tag=None) == "backend-b"


def test_tiebreak_breaks_equal_load():
    candidates = [candidate("backend-a", 5, tiebreak=2), candidate("backend-b", 5, tiebreak=1)]
    assert choose_backend_tag(candidates, current_tag=None) == "backend-b"


def test_keeps_current_within_absolute_gap():
    candidates = [candidate("backend-a", 3), candidate("backend-b", 5)]
    assert choose_backend_tag(candidates, current_tag="backend-b") == "backend-b"


def test_keeps_current_within_relative_gap():
    candidates = [candidate("backend-a", 80), candidate("backend-b", 100)]
    assert choose_backend_tag(candidates, current_tag="backend-b") == "backend-b"


def test_moves_off_current_when_gap_large():
    candidates = [candidate("backend-a", 2), candidate("backend-b", 100)]
    assert choose_backend_tag(candidates, current_tag="backend-b") == "backend-a"


def test_moves_off_when_current_not_a_candidate():
    candidates = [candidate("backend-a", 10), candidate("backend-b", 3)]
    assert choose_backend_tag(candidates, current_tag="backend-removed") == "backend-b"
