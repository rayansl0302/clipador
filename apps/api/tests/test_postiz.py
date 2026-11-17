from app.integrations.postiz import platform_settings


def test_tiktok_settings_match_public_api() -> None:
    settings = platform_settings("tiktok", "Gancho")
    assert settings["__type"] == "tiktok"
    assert settings["privacy_level"] == "PUBLIC_TO_EVERYONE"
    assert settings["content_posting_method"] == "DIRECT_POST"


def test_youtube_title_has_minimum_length() -> None:
    settings = platform_settings("youtube", "A")
    assert settings["title"] == "Corte"
    assert settings["type"] == "public"
