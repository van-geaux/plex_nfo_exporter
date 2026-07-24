import xml.etree.ElementTree as ET

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
