from uuid import uuid4

from app.utils.unsubscribe import generate_unsubscribe_token, verify_unsubscribe_token


class TestUnsubscribeTokens:
    def test_roundtrip(self) -> None:
        cid, sid = uuid4(), uuid4()
        token = generate_unsubscribe_token(cid, sid)
        result = verify_unsubscribe_token(token)
        assert result is not None
        assert result == (cid, sid)

    def test_tampered_token_rejected(self) -> None:
        cid, sid = uuid4(), uuid4()
        token = generate_unsubscribe_token(cid, sid)
        # Flip last character
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert verify_unsubscribe_token(tampered) is None

    def test_malformed_token_rejected(self) -> None:
        assert verify_unsubscribe_token("not-a-token") is None
        assert verify_unsubscribe_token("") is None

    def test_token_with_wrong_uuid_format_rejected(self) -> None:
        assert verify_unsubscribe_token("bad:bad:1234567890abcdef") is None

    def test_different_ids_produce_different_tokens(self) -> None:
        cid1, sid1 = uuid4(), uuid4()
        cid2, sid2 = uuid4(), uuid4()
        token1 = generate_unsubscribe_token(cid1, sid1)
        token2 = generate_unsubscribe_token(cid2, sid2)
        assert token1 != token2
