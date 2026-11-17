from app.routes import removal_accepted


def test_removal_requires_the_exact_phrase() -> None:
    assert removal_accepted("eu aceito")
    assert removal_accepted("  eu aceito  ")
    assert not removal_accepted("Eu aceito")
    assert not removal_accepted("eu  aceito")
    assert not removal_accepted("eu aceito agora")
    assert not removal_accepted("")
