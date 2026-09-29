from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st

from bananame.mutate import Edit, _newline_adapt, _resolve_file_edits


@given(st.text())
def test_newline_adaptation_is_idempotent_for_lf(text: str) -> None:
    once = _newline_adapt(text, "\n")
    assert _newline_adapt(once, "\n") == once


@given(st.text())
def test_newline_adaptation_is_idempotent_for_crlf(text: str) -> None:
    once = _newline_adapt(text, "\r\n")
    assert _newline_adapt(once, "\r\n") == once


@given(
    prefix=st.text(alphabet=st.characters(blacklist_characters="XY"), max_size=20),
    middle=st.text(alphabet=st.characters(blacklist_characters="XY"), max_size=20),
    suffix=st.text(alphabet=st.characters(blacklist_characters="XY"), max_size=20),
    repl_x=st.text(max_size=10),
    repl_y=st.text(max_size=10),
)
def test_disjoint_same_file_edits_are_order_independent(prefix: str, middle: str, suffix: str, repl_x: str, repl_y: str) -> None:
    source = prefix + "X" + middle + "Y" + suffix
    guard = "0" * 64
    x = Edit(path="a.txt", search="X", replace=repl_x, expected_sha256=guard)
    y = Edit(path="a.txt", search="Y", replace=repl_y, expected_sha256=guard)
    xy, _ = _resolve_file_edits("a.txt", [x, y], source, "\n")
    yx, _ = _resolve_file_edits("a.txt", [y, x], source, "\n")
    assert xy == yx
