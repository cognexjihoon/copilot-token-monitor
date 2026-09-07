import config
from config import AppConfig


def _point_config_at(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    return config_path


def test_default_config_is_invalid_without_cookie():
    cfg = AppConfig()
    assert not cfg.is_valid()


def test_config_with_cookie_is_valid():
    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    assert cfg.is_valid()


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    _point_config_at(tmp_path, monkeypatch)
    cfg = AppConfig.load()
    assert cfg.poll_interval_min == 30
    assert cfg.cookie() == ""


def test_load_corrupt_json_returns_defaults(tmp_path, monkeypatch):
    config_path = _point_config_at(tmp_path, monkeypatch)
    config_path.write_text("{broken", encoding="utf-8")
    cfg = AppConfig.load()
    assert cfg.poll_interval_min == 30


def test_save_then_load_round_trips_cookie_without_dpapi(tmp_path, monkeypatch):
    # on non-Windows _HAS_DPAPI is False, so the cookie is stored with a
    # "plain:" prefix rather than encrypted -- this test locks in that
    # fallback behavior still round-trips correctly.
    monkeypatch.setattr(config, "_HAS_DPAPI", False)
    _point_config_at(tmp_path, monkeypatch)

    cfg = AppConfig(poll_interval_min=15)
    cfg.set_cookie("user_session=abc; _gh_sess=def")
    cfg.save()

    loaded = AppConfig.load()

    assert loaded.cookie() == "user_session=abc; _gh_sess=def"
    assert loaded.poll_interval_min == 15


def test_save_never_writes_plaintext_cookie_field(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_HAS_DPAPI", False)
    config_path = _point_config_at(tmp_path, monkeypatch)

    cfg = AppConfig()
    cfg.set_cookie("user_session=super-secret")
    cfg.save()

    raw = config_path.read_text(encoding="utf-8")
    assert "_cookie_plain" not in raw
    assert "cookie_enc" in raw


def test_empty_cookie_round_trips_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_HAS_DPAPI", False)
    _point_config_at(tmp_path, monkeypatch)

    AppConfig().save()

    loaded = AppConfig.load()
    assert loaded.cookie() == ""


def test_teams_fields_default_to_disabled():
    cfg = AppConfig()
    assert cfg.teams_webhook_url == ""
    assert cfg.teams_threshold_pct == 80.0
    assert cfg.teams_notified_month == ""


def test_teams_fields_round_trip(tmp_path, monkeypatch):
    _point_config_at(tmp_path, monkeypatch)

    cfg = AppConfig()
    cfg.teams_webhook_url = "https://example.com/webhook"
    cfg.teams_threshold_pct = 90.0
    cfg.teams_notified_month = "2026-09"
    cfg.save()

    loaded = AppConfig.load()
    assert loaded.teams_webhook_url == "https://example.com/webhook"
    assert loaded.teams_threshold_pct == 90.0
    assert loaded.teams_notified_month == "2026-09"
