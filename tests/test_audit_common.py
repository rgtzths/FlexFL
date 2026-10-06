import audit_common
import pytest


@pytest.mark.parametrize(
    "clf,value,reference,expected",
    [
        (True, 0.6, 0.5, True),
        (True, 0.4, 0.5, False),
        (True, 0.5, 0.5, False),
        (False, 0.4, 0.5, True),
        (False, 0.6, 0.5, False),
        (False, 0.5, 0.5, False),
    ],
)
def test_better_is_strict_in_the_task_direction(clf, value, reference, expected):
    assert audit_common.better(clf, value, reference) is expected


def test_score_keys():
    assert audit_common.score_key("clip", 1e-4) == "clip_lr0.0001"
    assert audit_common.HEADLINE_KEY == "standard_lr0.001"


def test_sha256_file_matches_known_digest(tmp_path):
    path = tmp_path / "abc.txt"
    path.write_bytes(b"abc")
    assert audit_common.sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_read_lines_skips_blank_lines_and_accepts_str(tmp_path):
    path = tmp_path / "names.txt"
    path.write_text("a\n\n   \n b \nc\n")
    assert audit_common.read_lines(path) == ["a", "b", "c"]
    assert audit_common.read_lines(str(path)) == ["a", "b", "c"]
