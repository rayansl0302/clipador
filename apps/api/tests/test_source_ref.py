from app.pipeline.source_ref import reference_from_oembed


def test_oembed_keeps_title_and_channel() -> None:
    parsed = reference_from_oembed(
        {
            "title": "União Europeia",
            "author_name": "Peter Turgniev",
            "thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        }
    )
    assert parsed == ("União Europeia", "Peter Turgniev", "https://i.ytimg.com/vi/abc/hqdefault.jpg")


def test_oembed_without_title_is_ignored() -> None:
    assert reference_from_oembed({"author_name": "Canal"}) is None
    assert reference_from_oembed("texto") is None
