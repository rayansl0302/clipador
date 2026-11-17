from app.security import create_token, hash_password, read_token, verify_password
from app.config import Settings


def test_password_roundtrip() -> None:
    hashed = hash_password("segredo-forte")
    assert verify_password(hashed, "segredo-forte")
    assert not verify_password(hashed, "outra")


def test_jwt_roundtrip() -> None:
    settings = Settings(jwt_secret="teste-secreto")
    token = create_token("user-1", settings)
    assert read_token(token, settings) == "user-1"
    assert read_token(token, Settings(jwt_secret="outro")) is None
