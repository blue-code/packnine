"""비밀번호 목록(자동 시도) 테스트.

같은 비밀번호를 쓰는 아카이브를 여러 개 다룰 때 매번 입력하는 번거로움을 줄이는 기능이다.
비밀번호는 민감 정보라 두 가지를 반드시 지킨다.

1) 기본은 '이번 실행 동안만'이다 - 디스크에 남기려면 호출자가 명시적으로 켜야 한다.
2) 디스크에 남길 때도 평문으로 보이지 않게 한다(파일을 열어본 사람이 바로 읽을 수 없게).
"""
from __future__ import annotations

from packnine.application.password_book import PasswordBook


def test_remembers_in_order_of_most_recent_first():
    book = PasswordBook()

    book.remember("first")
    book.remember("second")

    assert book.candidates() == ["second", "first"]


def test_remembering_again_moves_it_to_front_without_duplicating():
    book = PasswordBook()

    book.remember("a")
    book.remember("b")
    book.remember("a")

    assert book.candidates() == ["a", "b"]


def test_empty_password_is_ignored():
    book = PasswordBook()

    book.remember("")
    book.remember(None)

    assert book.candidates() == []


def test_list_is_capped():
    book = PasswordBook()
    for index in range(PasswordBook.MAX_ENTRIES + 5):
        book.remember(f"pw{index}")

    assert len(book.candidates()) == PasswordBook.MAX_ENTRIES
    assert book.candidates()[0] == f"pw{PasswordBook.MAX_ENTRIES + 4}"


def test_try_each_returns_first_password_that_works():
    book = PasswordBook()
    book.remember("wrong1")
    book.remember("correct")
    book.remember("wrong2")
    tried: list[str] = []

    def attempt(password: str) -> bool:
        tried.append(password)
        return password == "correct"

    assert book.try_each(attempt) == "correct"
    # 맞는 것을 찾으면 더 시도하지 않는다.
    assert tried[-1] == "correct"


def test_try_each_returns_none_when_nothing_matches():
    book = PasswordBook()
    book.remember("a")
    book.remember("b")

    assert book.try_each(lambda password: False) is None


def test_try_each_on_empty_book_does_not_call_attempt():
    book = PasswordBook()
    calls: list[str] = []

    assert book.try_each(lambda password: calls.append(password) or True) is None
    assert calls == []


def test_saving_and_loading_round_trip(tmp_path):
    store = tmp_path / "passwords.dat"
    book = PasswordBook(store_path=store)
    book.remember("첫번째")
    book.remember("두번째")

    book.save()
    reloaded = PasswordBook(store_path=store)
    reloaded.load()

    assert reloaded.candidates() == ["두번째", "첫번째"]


def test_saved_file_does_not_contain_plain_text_password(tmp_path):
    # 파일을 열어본 사람이 바로 읽을 수 있으면 안 된다(강한 암호화는 아니지만 평문은 금지).
    store = tmp_path / "passwords.dat"
    book = PasswordBook(store_path=store)
    book.remember("평문비밀번호")
    book.save()

    raw = store.read_bytes()
    assert "평문비밀번호".encode("utf-8") not in raw


def test_load_without_file_leaves_book_empty(tmp_path):
    book = PasswordBook(store_path=tmp_path / "없는파일.dat")
    book.load()

    assert book.candidates() == []


def test_corrupted_store_is_ignored(tmp_path):
    store = tmp_path / "passwords.dat"
    store.write_bytes(b"\x00\x01" + "망가진내용".encode("utf-8"))

    book = PasswordBook(store_path=store)
    book.load()

    assert book.candidates() == []


def test_forget_all_clears_memory_and_disk(tmp_path):
    store = tmp_path / "passwords.dat"
    book = PasswordBook(store_path=store)
    book.remember("a")
    book.save()

    book.forget_all()

    assert book.candidates() == []
    reloaded = PasswordBook(store_path=store)
    reloaded.load()
    assert reloaded.candidates() == []
