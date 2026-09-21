import usage_cache


def _point_cache_at(tmp_path, monkeypatch):
    cache_path = tmp_path / "usage_cache.json"
    monkeypatch.setattr(usage_cache, "CACHE_PATH", cache_path)
    monkeypatch.setattr(usage_cache, "APP_DIR", tmp_path)
    return cache_path


def test_load_cache_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    assert usage_cache.load_cache() == {}


def test_load_cache_corrupt_json_returns_empty_dict(tmp_path, monkeypatch):
    cache_path = _point_cache_at(tmp_path, monkeypatch)
    cache_path.write_text("{not valid json", encoding="utf-8")
    assert usage_cache.load_cache() == {}


def test_save_then_load_round_trip(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    data = {"2026-09-01": 100.0, "2026-09-02": 250.5}
    usage_cache.save_cache(data)

    loaded = usage_cache.load_cache()

    assert loaded == data


def test_save_cache_creates_parent_dir(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "dir"
    monkeypatch.setattr(usage_cache, "CACHE_PATH", nested / "usage_cache.json")
    monkeypatch.setattr(usage_cache, "APP_DIR", nested)

    usage_cache.save_cache({"2026-09-01": 1.0})

    assert (nested / "usage_cache.json").exists()


def test_set_day_mutates_in_place():
    cache: dict = {}
    usage_cache.set_day(cache, "2026-09-01", 42.0)
    usage_cache.set_day(cache, "2026-09-02", 7.0)
    usage_cache.set_day(cache, "2026-09-01", 99.0)  # overwrite

    assert cache == {"2026-09-01": 99.0, "2026-09-02": 7.0}
