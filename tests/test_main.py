import argparse
import os
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

import main


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("The Godfather", "The Godfather"),
        ("Se7en: Se7en", "Se7en - Se7en"),
        ('Who: What/Where\\When*Why?"<>|', "Who - What-Where-When-Why---"),
        ("Trailing dot.", "Trailing dot"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert main.sanitize_filename(raw) == expected


# ---------------------------------------------------------------------------
# map_media_path
# ---------------------------------------------------------------------------

def test_map_media_path_no_mapping_returns_normalized_source():
    assert main.map_media_path("/data_media/Movies/Foo", []) == "/data_media/Movies/Foo"


def test_map_media_path_applies_matching_mapping():
    mapping = [{"plex": "/data_media", "local": "/volume1/data/media"}]
    result = main.map_media_path("/data_media/Movies/Foo", mapping)
    assert result == "/volume1/data/media/Movies/Foo"


def test_map_media_path_rejects_unmapped_path_when_mappings_configured():
    mapping = [{"plex": "/data_media", "local": "/volume1/data/media"}]
    with pytest.raises(ValueError):
        main.map_media_path("/other/Movies/Foo", mapping)


def test_map_media_path_rejects_relative_path():
    with pytest.raises(ValueError):
        main.map_media_path("relative/path", [])


def test_map_media_path_rejects_partial_prefix_false_positive():
    # "/data_media2" is NOT under "/data_media" even though it starts with
    # the same characters — must not be treated as a match.
    mapping = [{"plex": "/data_media", "local": "/volume1/data/media"}]
    with pytest.raises(ValueError):
        main.map_media_path("/data_media2/Movies/Foo", mapping)


def test_map_media_path_rejects_traversal_inside_matched_root(tmp_path):
    local_root = tmp_path / "media"
    local_root.mkdir()
    mapping = [{"plex": "/data_media", "local": str(local_root)}]
    with pytest.raises(ValueError):
        main.map_media_path("/data_media/../../etc/passwd", mapping)


# ---------------------------------------------------------------------------
# safe_output_path
# ---------------------------------------------------------------------------

def test_safe_output_path_joins_within_root(tmp_path):
    result = main.safe_output_path(str(tmp_path), "movie.nfo")
    assert result == str((tmp_path / "movie.nfo").resolve())


def test_safe_output_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        main.safe_output_path(str(tmp_path), "../escape.nfo")


def test_safe_output_path_rejects_absolute_escape(tmp_path):
    with pytest.raises(ValueError):
        main.safe_output_path(str(tmp_path), "/etc/passwd")


# ---------------------------------------------------------------------------
# get_file_path
# ---------------------------------------------------------------------------

def test_get_file_path_movie_default_naming(tmp_path):
    nfo, poster, fanart = main.get_file_path(
        "movie", "default", "default", str(tmp_path), "The Godfather", "/media/The Godfather (1972).mkv"
    )
    assert nfo == str((tmp_path / "movie.nfo").resolve())
    assert poster == str((tmp_path / "poster.jpg").resolve())
    assert fanart == str((tmp_path / "fanart.jpg").resolve())


def test_get_file_path_movie_title_naming(tmp_path):
    nfo, poster, fanart = main.get_file_path(
        "movie", "title", "title", str(tmp_path), "The Godfather", "/media/The Godfather (1972).mkv"
    )
    assert nfo == str((tmp_path / "The Godfather.nfo").resolve())
    assert poster == str((tmp_path / "The Godfather_poster.jpg").resolve())
    assert fanart == str((tmp_path / "The Godfather_fanart.jpg").resolve())


def test_get_file_path_movie_filename_naming(tmp_path):
    nfo, poster, fanart = main.get_file_path(
        "movie", "filename", "filename", str(tmp_path), "The Godfather", "/media/The Godfather (1972).mkv"
    )
    assert nfo == str((tmp_path / "The Godfather (1972).nfo").resolve())
    assert poster == str((tmp_path / "The Godfather (1972)_poster.jpg").resolve())
    assert fanart == str((tmp_path / "The Godfather (1972)_fanart.jpg").resolve())


def test_get_file_path_image_naming_independent_of_nfo_naming(tmp_path):
    # image naming mode should not be coupled to the NFO naming mode
    nfo, poster, fanart = main.get_file_path(
        "movie", "title", "filename", str(tmp_path), "The Godfather", "/media/The Godfather (1972).mkv"
    )
    assert nfo == str((tmp_path / "The Godfather.nfo").resolve())
    assert poster == str((tmp_path / "The Godfather (1972)_poster.jpg").resolve())


def test_get_file_path_artist_and_album(tmp_path):
    nfo, _, _ = main.get_file_path("artist", "default", "default", str(tmp_path), "Some Artist", None)
    assert nfo == str((tmp_path / "artist.nfo").resolve())

    nfo, _, _ = main.get_file_path("albums", "default", "default", str(tmp_path), "Some Album", None)
    assert nfo == str((tmp_path / "album.nfo").resolve())


def test_get_file_path_tvshow(tmp_path):
    nfo, poster, fanart = main.get_file_path("tvshow", "default", "default", str(tmp_path), "Some Show", None)
    assert nfo == str((tmp_path / "tvshow.nfo").resolve())
    assert poster == str((tmp_path / "poster.jpg").resolve())
    assert fanart == str((tmp_path / "fanart.jpg").resolve())


def test_get_image_paths_uses_custom_patterns_and_sanitized_values(tmp_path):
    paths = main.get_image_paths(
        "movie",
        "filename",
        str(tmp_path),
        "The Godfather",
        "/media/The Godfather (1972).mkv",
        {
            "Custom image names": {
                "poster": ["{filename}_poster.jpg", "{filename}-poster.jpg"],
                "fanart": ["{title}-fanart.jpg"],
            }
        },
    )

    assert paths["poster"] == [
        str((tmp_path / "The Godfather (1972)_poster.jpg").resolve()),
        str((tmp_path / "The Godfather (1972)-poster.jpg").resolve()),
    ]
    assert paths["fanart"] == [str((tmp_path / "The Godfather-fanart.jpg").resolve())]


def test_get_image_paths_falls_back_per_image_when_custom_entry_is_empty(tmp_path):
    paths = main.get_image_paths(
        "movie",
        "title",
        str(tmp_path),
        "The Godfather",
        "/media/The Godfather (1972).mkv",
        {"Custom image names": {"poster": ["{title}-poster.jpg"], "fanart": []}},
    )

    assert paths["poster"] == [str((tmp_path / "The Godfather-poster.jpg").resolve())]
    assert paths["fanart"] == [str((tmp_path / "The Godfather_fanart.jpg").resolve())]


def test_get_image_paths_uses_media_type_specific_patterns_for_tvshow(tmp_path):
    paths = main.get_image_paths(
        "tvshow",
        "default",
        str(tmp_path),
        "Some Show",
        None,
        {
            "Custom image names": {
                "poster": ["{filename}_poster.jpg"],
                "tvshow": {
                    "poster": ["{title}_poster.jpg", "test-poster.jpg"],
                },
            }
        },
    )

    assert paths["poster"] == [
        str((tmp_path / "Some Show_poster.jpg").resolve()),
        str((tmp_path / "test-poster.jpg").resolve()),
    ]


def test_get_image_paths_skips_unusable_flat_pattern_for_tvshow(tmp_path):
    paths = main.get_image_paths(
        "tvshow",
        "default",
        str(tmp_path),
        "Some Show",
        None,
        {"Custom image names": {"poster": ["{filename}_poster.jpg", "test-poster.jpg"]}},
    )

    assert paths["poster"] == [str((tmp_path / "test-poster.jpg").resolve())]


def test_get_image_paths_falls_back_to_configured_type_when_all_patterns_unusable(tmp_path):
    paths = main.get_image_paths(
        "tvshow",
        "default",
        str(tmp_path),
        "Some Show",
        None,
        {"Custom image names": {"poster": ["{filename}_poster.jpg", "{unknown}.jpg"]}},
    )

    assert paths["poster"] == [str((tmp_path / "poster.jpg").resolve())]


def test_sync_alternate_image_creates_hardlink(tmp_path):
    primary = tmp_path / "primary.jpg"
    alternate = tmp_path / "alternate.jpg"
    primary.write_bytes(b"image data")

    result = main.sync_alternate_image(str(primary), str(alternate))

    assert result == "hardlink"
    assert alternate.read_bytes() == b"image data"
    assert primary.stat().st_ino == alternate.stat().st_ino


def test_sync_alternate_image_falls_back_to_copy(monkeypatch, tmp_path):
    primary = tmp_path / "primary.jpg"
    alternate = tmp_path / "alternate.jpg"
    primary.write_bytes(b"image data")

    def fail_link(*args, **kwargs):
        raise OSError("cross-device link")

    monkeypatch.setattr(main.os, "link", fail_link)

    result = main.sync_alternate_image(str(primary), str(alternate))

    assert result == "copy"
    assert alternate.read_bytes() == b"image data"
    assert primary.stat().st_ino != alternate.stat().st_ino


# ---------------------------------------------------------------------------
# same_origin / get_request
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url, configured, expected",
    [
        ("http://plex.local:32400/library", "http://plex.local:32400", True),
        ("HTTP://PLEX.LOCAL:32400/library", "http://plex.local:32400", True),
        ("https://plex.local:32400/library", "http://plex.local:32400", False),
        ("http://evil.example/library", "http://plex.local:32400", False),
        ("http://plex.local:9999/library", "http://plex.local:32400", False),
    ],
)
def test_same_origin(url, configured, expected):
    assert main.same_origin(url, configured) == expected


def test_get_request_rejects_cross_origin(monkeypatch):
    monkeypatch.setattr(main, "baseurl", "http://plex.local:32400", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("requests.get should not be called for a rejected origin")

    monkeypatch.setattr(main.requests, "get", fail_if_called)

    with pytest.raises(ValueError):
        main.get_request("http://evil.example/steal-token")


def test_get_request_disables_redirects_and_sets_timeout(monkeypatch):
    monkeypatch.setattr(main, "baseurl", "http://plex.local:32400", raising=False)
    captured = {}

    def fake_get(url, headers=None, timeout=None, **kwargs):
        captured.update(url=url, headers=headers, timeout=timeout, kwargs=kwargs)
        return "response"

    monkeypatch.setattr(main.requests, "get", fake_get)

    result = main.get_request("http://plex.local:32400/library", headers={"X-Plex-Token": "abc"})

    assert result == "response"
    assert captured["timeout"] == main.REQUEST_TIMEOUT
    assert captured["kwargs"]["allow_redirects"] is False


# ---------------------------------------------------------------------------
# response_content / parse_xml_response
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, content, content_length=None):
        self.content = content
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)


def test_response_content_within_limit():
    response = _FakeResponse(b"<a/>")
    assert main.response_content(response) == b"<a/>"


def test_response_content_rejects_oversized_content_length_header():
    response = _FakeResponse(b"<a/>", content_length=10**9)
    with pytest.raises(ValueError):
        main.response_content(response, max_bytes=100)


def test_response_content_rejects_oversized_actual_body():
    response = _FakeResponse(b"x" * 200)
    with pytest.raises(ValueError):
        main.response_content(response, max_bytes=100)


def test_parse_xml_response_parses_valid_xml():
    response = _FakeResponse(b"<MediaContainer><Directory title='Movies'/></MediaContainer>")
    root = main.parse_xml_response(response)
    assert root.find("Directory").get("title") == "Movies"


def test_parse_xml_response_rejects_malformed_xml():
    response = _FakeResponse(b"<not-well-formed>")
    with pytest.raises(ValueError):
        main.parse_xml_response(response)


# ---------------------------------------------------------------------------
# resolve_library_type (movie/show/music alternation)
# ---------------------------------------------------------------------------

def test_resolve_library_type_movie():
    assert main.resolve_library_type("movie", 0) == ("movie", "Video", 0)


def test_resolve_library_type_show():
    assert main.resolve_library_type("show", 0) == ("tvshow", "Directory", 0)


def test_resolve_library_type_music_alternates_artist_then_albums():
    # Music libraries must be listed twice in config; each pass through
    # resolve_library_type should alternate between artist and albums roots.
    library_type, root, check_music = main.resolve_library_type("artist", 0)
    assert (library_type, root) == ("artist", "Directory")
    assert check_music == 1

    library_type, root, check_music = main.resolve_library_type("artist", check_music)
    assert (library_type, root) == ("albums", "Directory")
    assert check_music == 0


# ---------------------------------------------------------------------------
# add_xml_element
# ---------------------------------------------------------------------------

def test_add_xml_element_creates_element_with_text_and_attributes():
    root = ET.Element("movie")
    element = main.add_xml_element(root, "title", "The Godfather", {"lang": "en"})
    assert element is not None
    assert element.tag == "title"
    assert element.text == "The Godfather"
    assert element.get("lang") == "en"


def test_add_xml_element_rejects_invalid_tag_name():
    root = ET.Element("movie")
    assert main.add_xml_element(root, "not a valid tag!") is None
    assert list(root) == []


# ---------------------------------------------------------------------------
# NFO section writers
# ---------------------------------------------------------------------------

def _meta_root(**attrib):
    return ET.fromstring(
        "<Video "
        + " ".join(f'{key}="{value}"' for key, value in attrib.items())
        + "/>"
    )


def test_write_simple_fields_respects_config_flags():
    meta_root = _meta_root(title="The Godfather", year="1972", studio="Paramount")
    root = ET.Element("movie")
    main.write_simple_fields(root, {"title": True, "year": True, "studio": False}, meta_root)

    tags = {child.tag: child.text for child in root}
    assert tags == {"title": "The Godfather", "year": "1972"}


def test_write_tag_collections():
    meta_root = ET.fromstring(
        '<Video><Genre tag="Crime"/><Genre tag="Drama"/><Country tag="USA"/></Video>'
    )
    root = ET.Element("movie")
    main.write_tag_collections(root, {"genre": True, "country": False}, meta_root)

    genres = [child.text for child in root if child.tag == "genre"]
    assert genres == ["Crime", "Drama"]
    assert [child for child in root if child.tag == "country"] == []


def test_write_ratings_section():
    meta_root = ET.fromstring(
        '<Video><Rating type="imdb" value="9.2"/><Rating type="tmdb" value="8.7"/></Video>'
    )
    root = ET.Element("movie")
    main.write_ratings_section(root, {"ratings": True}, meta_root)

    ratings_element = root.find("ratings")
    assert ratings_element is not None
    assert ratings_element.find("imdb").text == "9.2"
    assert ratings_element.find("tmdb").text == "8.7"


def test_write_ratings_section_disabled_by_config():
    meta_root = ET.fromstring('<Video><Rating type="imdb" value="9.2"/></Video>')
    root = ET.Element("movie")
    main.write_ratings_section(root, {"ratings": False}, meta_root)
    assert root.find("ratings") is None


def test_write_people_sections():
    meta_root = ET.fromstring(
        '<Video><Director tag="Francis Ford Coppola" thumb="thumb-url"/></Video>'
    )
    root = ET.Element("movie")
    main.write_people_sections(root, {"directors": True, "writers": False}, meta_root)

    director = root.find("director")
    assert director.text == "Francis Ford Coppola"
    assert director.get("thumb") == "thumb-url"
    assert root.find("writer") is None


def test_write_roles_section():
    meta_root = ET.fromstring(
        '<Video><Role tag="Al Pacino" role="Michael Corleone" thumb="thumb-url"/></Video>'
    )
    root = ET.Element("movie")
    main.write_roles_section(root, {"roles": True}, meta_root)

    actor = root.find("actor")
    assert actor.text == "Al Pacino"
    assert actor.get("role") == "Michael Corleone"
    assert actor.get("thumb") == "thumb-url"


def test_write_agent_ids_section_tmdb_and_guid_children():
    meta_root = ET.fromstring(
        '<Video guid="com.plexapp.agents.themoviedb://238?lang=en">'
        '<Guid id="tvdb://81189"/>'
        "</Video>"
    )
    root = ET.Element("movie")
    main.write_agent_ids_section(root, {"agent_id": True}, meta_root)

    tags = {child.tag: child.text for child in root}
    assert tags["tmdbid"] == "238"
    assert tags["tvdbid"] == "81189"


def test_write_agent_ids_section_disabled_by_config():
    meta_root = ET.fromstring('<Video guid="com.plexapp.agents.themoviedb://238"/>')
    root = ET.Element("movie")
    main.write_agent_ids_section(root, {"agent_id": False}, meta_root)
    assert list(root) == []


# ---------------------------------------------------------------------------
# write_episode_nfo
# ---------------------------------------------------------------------------

class _FakeLogger:
    def verbose(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


def test_write_episode_nfo_guid_missing_id_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "logger", _FakeLogger(), raising=False)
    episode_root = ET.fromstring(
        '<Video parentIndex="1" index="2" title="Ep">'
        '<Guid/>'
        '<Guid id="imdb://tt0000001"/>'
        "</Video>"
    )
    nfo_path = tmp_path / "episode.nfo"

    result = main.write_episode_nfo(str(nfo_path), episode_root, "Ep")

    assert result is True
    written = nfo_path.read_text(encoding="utf-8")
    root = ET.fromstring(written)
    uniqueids = root.findall("uniqueid")
    assert len(uniqueids) == 1
    assert uniqueids[0].get("type") == "imdb"
    assert uniqueids[0].text == "tt0000001"


def test_write_episode_nfo_unknown_agent_guid_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "logger", _FakeLogger(), raising=False)
    episode_root = ET.fromstring(
        '<Video parentIndex="1" index="2" title="Ep">'
        '<Guid id="anidb://12345"/>'
        "</Video>"
    )
    nfo_path = tmp_path / "episode.nfo"

    result = main.write_episode_nfo(str(nfo_path), episode_root, "Ep")

    assert result is True
    root = ET.fromstring(nfo_path.read_text(encoding="utf-8"))
    assert root.findall("uniqueid") == []


# ---------------------------------------------------------------------------
# process_content — defensive Media/Part handling for movies
# ---------------------------------------------------------------------------

class _FakeResponse200:
    status_code = 200


def test_process_content_movie_without_media_part_does_not_raise(monkeypatch):
    monkeypatch.setattr(main, "logger", _FakeLogger(), raising=False)
    monkeypatch.setattr(main, "get_request", lambda *a, **k: _FakeResponse200())

    meta_root = ET.fromstring('<Video ratingKey="1" title="No Media Part"/>')

    class _Wrapper:
        def find(self, path):
            return meta_root

    monkeypatch.setattr(main, "parse_xml_response", lambda response: _Wrapper())
    monkeypatch.setattr(main, "get_media_path", lambda *a, **k: ["/movies/No Media Part"])

    captured_file_titles = []

    def fake_get_file_path(library_type, movie_filename_type, image_filename_type, media_path, media_title, file_title):
        captured_file_titles.append(file_title)
        return ("nfo.nfo", "poster.jpg", "fanart.jpg")

    monkeypatch.setattr(main, "get_file_path", fake_get_file_path)

    content = ET.Element("Video", {"ratingKey": "1"})
    args = argparse.Namespace(title=None)
    exports = {
        "export_nfo": False,
        "export_episode_nfo": False,
        "export_poster": False,
        "export_fanart": False,
        "export_season_poster": False,
    }
    summary = {}

    main.process_content(
        content, "Video", "movie", args, {}, [], exports,
        "default", "default", False, False, summary,
        "http://plex.local", {},
    )

    assert captured_file_titles == [None]


def test_process_content_syncs_custom_poster_alternates_after_primary_success(monkeypatch):
    monkeypatch.setattr(main, "logger", _FakeLogger(), raising=False)
    monkeypatch.setattr(main, "get_request", lambda *a, **k: _FakeResponse200())

    meta_root = ET.fromstring('<Video ratingKey="1" title="Movie"/>')

    class _Wrapper:
        def find(self, path):
            return meta_root

    monkeypatch.setattr(main, "parse_xml_response", lambda response: _Wrapper())
    monkeypatch.setattr(main, "get_media_path", lambda *a, **k: ["/movies/Movie"])

    processed = []
    synced = []

    def fake_process_media(kind, config, file_path, *args, **kwargs):
        processed.append((kind, file_path))
        return "success"

    monkeypatch.setattr(main, "process_media", fake_process_media)
    monkeypatch.setattr(main, "sync_alternate_image", lambda primary, alternate, force=False: synced.append((primary, alternate, force)))

    content = ET.Element("Video", {"ratingKey": "1"})
    args = argparse.Namespace(title=None)
    exports = {
        "export_nfo": False,
        "export_episode_nfo": False,
        "export_poster": True,
        "export_fanart": False,
        "export_season_poster": False,
    }
    summary = {"poster_new": 0}

    main.process_content(
        content,
        "Video",
        "movie",
        args,
        {"Custom image names": {"poster": ["poster.jpg", "poster-alt.jpg"]}},
        [],
        exports,
        "default",
        "default",
        False,
        False,
        summary,
        "http://plex.local",
        {},
    )

    assert processed == [("Poster", "/movies/Movie/poster.jpg")]
    assert synced == [
        ("/movies/Movie/poster.jpg", "/movies/Movie/poster-alt.jpg", True)
    ]


# ---------------------------------------------------------------------------
# resolve_config_dir
# ---------------------------------------------------------------------------

def test_resolve_config_dir_prefers_app_config_when_present(monkeypatch):
    monkeypatch.setattr(main.os.path, "isdir", lambda path: path == "/app/config")
    assert main.resolve_config_dir() == "/app/config"


def test_resolve_config_dir_falls_back_to_cwd(monkeypatch):
    monkeypatch.setattr(main.os.path, "isdir", lambda path: False)
    assert main.resolve_config_dir() == "."


# ---------------------------------------------------------------------------
# str_to_bool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("", False),
        ("no", False),
    ],
)
def test_str_to_bool(value, expected):
    assert main.str_to_bool(value) is expected


# ---------------------------------------------------------------------------
# load_configuration — env substitution and .env loading
# ---------------------------------------------------------------------------

def test_load_configuration_substitutes_env_vars_in_config_yml(tmp_path, monkeypatch):
    monkeypatch.setenv("PLEX_TOKEN", "secret-token-123")
    (tmp_path / "config.yml").write_text(
        "Base URL: http://plex.local:32400\nToken: ${PLEX_TOKEN}\n",
        encoding="utf-8",
    )

    config = main.load_configuration(str(tmp_path))

    assert config["Token"] == "secret-token-123"
    assert config["Base URL"] == "http://plex.local:32400"


def test_load_configuration_missing_env_var_substitutes_empty_string(tmp_path, monkeypatch):
    monkeypatch.delenv("UNSET_VAR_FOR_TEST", raising=False)
    (tmp_path / "config.yml").write_text("Token: ${UNSET_VAR_FOR_TEST}\n", encoding="utf-8")

    config = main.load_configuration(str(tmp_path))

    # An empty substitution leaves the YAML value blank, which PyYAML parses as None.
    assert config["Token"] is None


def test_load_configuration_loads_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("PLEX_URL_FROM_DOTENV_TEST", raising=False)
    (tmp_path / ".env").write_text("PLEX_URL_FROM_DOTENV_TEST=http://from-dotenv\n", encoding="utf-8")
    (tmp_path / "config.yml").write_text("Base URL: ${PLEX_URL_FROM_DOTENV_TEST}\n", encoding="utf-8")

    config = main.load_configuration(str(tmp_path))

    assert config["Base URL"] == "http://from-dotenv"
    assert os.getenv("PLEX_URL_FROM_DOTENV_TEST") == "http://from-dotenv"


# ---------------------------------------------------------------------------
# resolve_base_settings — precedence and validation
# ---------------------------------------------------------------------------

def _args(**overrides):
    base = {"url": None, "token": None, "library": None}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_resolve_base_settings_prefers_args_over_env_and_config(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)
    monkeypatch.setenv("PLEX_URL", "http://from-env")
    monkeypatch.setenv("PLEX_TOKEN", "env-token")

    args = _args(url="http://from-args", token="args-token")
    config = {"Base URL": "http://from-config", "Token": "config-token"}

    baseurl, token, library_names, blacklists, path_mapping = main.resolve_base_settings(args, config)

    assert baseurl == "http://from-args"
    assert token == "args-token"


def test_resolve_base_settings_falls_back_to_env_then_config(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)
    monkeypatch.delenv("PLEX_URL", raising=False)
    monkeypatch.delenv("PLEX_TOKEN", raising=False)

    args = _args()
    config = {"Base URL": "'http://from-config'", "Token": '"config-token"'}

    baseurl, token, *_ = main.resolve_base_settings(args, config)

    assert baseurl == "http://from-config"
    assert token == "config-token"


def test_resolve_base_settings_exits_when_url_missing(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)
    monkeypatch.delenv("PLEX_URL", raising=False)

    args = _args()
    config = {"Token": "config-token"}

    with pytest.raises(SystemExit):
        main.resolve_base_settings(args, config)


def test_resolve_base_settings_exits_when_token_missing(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)
    monkeypatch.delenv("PLEX_TOKEN", raising=False)

    args = _args(url="http://from-args")
    config = {}

    with pytest.raises(SystemExit):
        main.resolve_base_settings(args, config)


# ---------------------------------------------------------------------------
# build_export_flags / determine_force_overwrite / determine_dry_run
# ---------------------------------------------------------------------------

def test_build_export_flags_prefers_cli_args_over_config(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)
    args = argparse.Namespace(
        export_nfo=True,
        export_episode_nfo=None,
        export_poster=False,
        export_fanart=None,
        export_season_poster=None,
    )
    config = {
        "Export NFO": False,
        "Export episode NFO": True,
        "Export poster": True,
        "Export fanart": False,
        "Export season poster": True,
    }

    exports = main.build_export_flags(args, config)

    assert exports["export_nfo"] is True  # CLI overrides config
    assert exports["export_episode_nfo"] is True  # falls back to config
    assert exports["export_poster"] is False  # explicit CLI False overrides config True
    assert exports["export_fanart"] is False  # falls back to config
    assert exports["export_season_poster"] is True  # falls back to config


def test_determine_force_overwrite_precedence(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)

    monkeypatch.delenv("FORCE_OVERWRITE", raising=False)
    assert main.determine_force_overwrite(_args(force_overwrite=True), {}) is True

    monkeypatch.setenv("FORCE_OVERWRITE", "true")
    assert main.determine_force_overwrite(_args(force_overwrite=False), {}) is True

    monkeypatch.delenv("FORCE_OVERWRITE", raising=False)
    assert main.determine_force_overwrite(_args(force_overwrite=False), {"Force overwrite": True}) is True
    assert main.determine_force_overwrite(_args(force_overwrite=False), {}) is False


def test_determine_dry_run_precedence(monkeypatch):
    monkeypatch.setattr(main, "logger", MagicMock(), raising=False)

    monkeypatch.delenv("DRY_RUN", raising=False)
    assert main.determine_dry_run(_args(dry_run=True)) is True

    monkeypatch.setenv("DRY_RUN", "true")
    assert main.determine_dry_run(_args(dry_run=False)) is True

    monkeypatch.delenv("DRY_RUN", raising=False)
    assert main.determine_dry_run(_args(dry_run=False)) is False
