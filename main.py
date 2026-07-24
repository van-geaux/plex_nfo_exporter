#!/usr/bin/env python3

from alive_progress import alive_bar
from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO
from pathlib import Path
from PIL import Image
from urllib.parse import urljoin, urlsplit
from textwrap import dedent

import argparse
import gzip
import logging
import os
import re
import requests
import sys
import xml.etree.ElementTree as ET
import yaml

REQUEST_TIMEOUT = (10, 60)
MAX_XML_RESPONSE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_RESPONSE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000

# Module-level so functions can log even when imported without set_logger()
# having run yet (e.g. under test or when reused as a library). logging.getLogger()
# is a singleton keyed by name, so set_logger() configuring the same logger later
# (handlers, level) applies to this exact object.
logger = logging.getLogger(__name__)

def same_origin(url, configured_url):
    requested = urlsplit(url)
    configured = urlsplit(configured_url)
    return (
        requested.scheme.lower() == configured.scheme.lower()
        and requested.hostname.lower() == configured.hostname.lower()
        and requested.port == configured.port
    )

def get_request(url, headers=None, **kwargs):
    """Perform a same-origin GET request with bounded times and no retries."""
    configured_url = globals().get('baseurl')
    if configured_url and not same_origin(url, configured_url):
        raise ValueError(f'Refusing request outside configured Plex origin: {url}')

    kwargs['allow_redirects'] = False
    return requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)

def response_content(response, max_bytes=MAX_XML_RESPONSE_BYTES):
    content_length = response.headers.get('Content-Length')
    try:
        if content_length is not None and int(content_length) > max_bytes:
            raise ValueError(f'Response exceeds {max_bytes} byte limit')
    except ValueError as exc:
        if str(exc).startswith('Response exceeds'):
            raise

    content = response.content
    if len(content) > max_bytes:
        raise ValueError(f'Response exceeds {max_bytes} byte limit')
    return content

def parse_xml_response(response):
    try:
        return ET.fromstring(response_content(response))
    except ET.ParseError as exc:
        raise ValueError('Invalid Plex XML response') from exc

def resolve_config_dir():
    if os.path.isdir('/app/config'):
        return '/app/config'
    else:
        return '.'

TYPE_MAP = {
    'movie': ('movie', 'Video'),
    'show': ('tvshow', 'Directory'),
}

class StoreTrueIfFlagPresent(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)

def set_logger(log_level, config_dir=None):
    if config_dir is None:
        config_dir = resolve_config_dir()

    if not os.path.exists('logs'):
        os.makedirs('logs')

    files = list(Path('logs/').iterdir())
    files = [f for f in files if f.is_file()]
    if len(files) > 10:
        files.sort(key=lambda f: f.stat().st_mtime)
        oldest_file = files[0]
        os.remove(oldest_file)
        print(f"Deleted: {oldest_file}")

    config_path = resolve_config_file_path(config_dir)
    with open(config_path, 'r', encoding='utf-8') as file:
        config_content = file.read()
        config = yaml.safe_load(config_content)

    # Add custom "DETAIL" log level
    VERBOSE_LEVEL = 15
    logging.VERBOSE = VERBOSE_LEVEL
    logging.addLevelName(VERBOSE_LEVEL, "VERBOSE")

    def verbose(self, message, *args, **kwargs):
        if self.isEnabledFor(VERBOSE_LEVEL):
            self._log(VERBOSE_LEVEL, message, args, **kwargs)

    logging.Logger.verbose = verbose  # Add method once

    log_level_str = log_level if log_level is not None else os.getenv("LOG_LEVEL") or config.get('log_level', 'INFO')
    if not isinstance(log_level_str, str):
        log_level_str = 'INFO'
    log_level_str = log_level_str.upper()

    log_level_console = getattr(logging, log_level_str, 'INFO')
    log_level_file = min(getattr(logging, log_level_str, 'VERBOSE'), 15)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level_console)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    log_count = 1
    while True:
        log_name = f'app-{datetime.now().date().isoformat().replace("-", "")}-{log_count}'
        if os.path.exists(f'logs/{log_name}.log'):
            log_count += 1
        else:
            break

    file_handler = logging.FileHandler(
        f"logs/{log_name}.log", encoding='utf-8'
    )
    file_handler.setLevel(log_level_file)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger, log_name

ENV_PLACEHOLDER = dedent("""
    PLEX_URL='http://192.168.1.2:32400'
    PLEX_TOKEN='very-long-token'
""").strip()
CONFIG_PLACEHOLDER = dedent("""
    # config.yml

    # change plex url and token here
    # you can ignore this if you are using PLEX_URL and PLEX_TOKEN environment variables in docker
    Base URL: ${PLEX_URL} # i.e http://192.168.1.1:32400 or if reverse proxied i.e. https://plex.yourdomain.tld or fill them in .env file and let this part be
    Token: ${PLEX_TOKEN} # how to get token https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/ or fill them in .env file and let this part be

    # input the libraries you want to export NFO/poster/fanart from
    # if the library type is music, input it TWICE CONSECUTIVELY. This is due to plex having 2 different roots for music library, each for artist and albums
    # You can do all libraries using Libraries: ['*']
    Libraries: ['Movies', 'TV Shows', 'Anime', 'Music', 'Music']
    Blacklist: ['Test Movies']

    # overwrite files without checking if they are up-to-date with server's metadata
    Force overwrite: false

    # true/false choose what to export
    Export NFO: true
    Export poster: true
    Export fanart: false
    Export season poster: false
    Export episode NFO: false

    # title, or filename
    # title will save as {media_title}.ext i.e. "The Godfather.nfo", "The Godfather_poster.jpg", "The Godfather_fanart.jpg"
    # filename will save as {media_file}.ext i.e. "The Godfather (1972) [imdb-tt0068646].nfo", "The Godfather (1972) [imdb-tt0068646]_poster.jpg", "The Godfather (1972) [imdb-tt0068646]_fanart.jpg"
    # anything other than that will save as {library_type}.ext i.e. "movie.nfo", "poster.jpg", "fanart.jpg"
    Movie NFO name type: default
    Movie Poster/art name type: default

    # Leave this fully empty (Path mapping: []) only if EVERY Plex library
    # root is mounted at the identical path inside this container.
    # Otherwise, list EVERY Plex library root here, one entry per root -
    # if a root is Plex-path == local-path already (e.g. because you mount
    # it the same way for both Plex and this container), still add it with
    # matching 'plex'/'local' values. Once this list has even one entry,
    # any Plex media path that doesn't match one of them is rejected
    # instead of silently passed through, to stop unmapped/unexpected
    # paths from being treated as safe write targets.
    Path mapping: [
        {
            'plex': '/data_media',
            'local': '/volume1/data/media'
        },
        {
            'plex': '/usb2',
            'local': '/volumeUSB2/usbshare/data'
        },
        {
            'plex': '/debrid',
            'local': '/volume2/debrid'
        }
    ]

    ################################ NFO options ################################

    # important
    # set to false if you know you don't want these metadata
    title: true
    agent_id: true # will export all available metadata agent ids
    tagline: true
    plot: true
    year: true

    # optionals
    studio: false
    mpaa: false
    criticrating: false
    customrating: false
    runtime: false
    releasedate: false
    genre: false
    country: false
    style: false
    ratings: false
    directors: false
    writers: false
    roles: false
    # producers: false # there's no equivalent in jellyfin metadata

    # log level defaults to info for console and warning for file
    log_level: 
""").strip()


def resolve_env_file_path(config_dir=None):
    if config_dir is None:
        config_dir = resolve_config_dir()
    return os.path.join(config_dir, '.env')

def resolve_config_file_path(config_dir=None):
    if config_dir is None:
        config_dir = resolve_config_dir()
    return os.path.join(config_dir, 'config.yml')

def required_file_specs(config_dir=None):
    return (
        {
            'path': resolve_env_file_path(config_dir),
            'name': '.env',
            'content': ENV_PLACEHOLDER,
            'env_vars': ('PLEX_URL', 'PLEX_TOKEN'),
        },
        {
            'path': resolve_config_file_path(config_dir),
            'name': 'config.yml',
            'content': CONFIG_PLACEHOLDER,
            'env_vars': (),
        },
    )

def missing_env_variables(spec):
    return any(not os.getenv(var) for var in spec.get('env_vars', ()))

def create_placeholder(spec):
    directory = os.path.dirname(spec['path'])
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    with open(spec['path'], 'w', encoding='utf-8') as handle:
        handle.write(spec['content'])

    print(f"{spec['path']} created. Please populate it and rerun the script.")
    sys.exit()

def ensure_files_exist(config_dir=None):
    for spec in required_file_specs(config_dir):
        if spec.get('env_vars') and not missing_env_variables(spec):
            continue

        if os.path.exists(spec['path']):
            print(f"{spec['path']} already exists.")
            continue

        create_placeholder(spec)

def env_var_constructor(loader, node):
    """
    Custom YAML constructor to replace environment variable placeholders in the YAML string.
    Replaces ${VAR_NAME} with the actual environment variable value.
    """
    value = loader.construct_scalar(node)
    pattern = re.compile(r'\$\{(\w+)\}')
    match = pattern.findall(value)
    for var in match:
        value = value.replace(f'${{{var}}}', os.getenv(var, ''))

    return value

def fallback_response(url, token):
    start = 0
    container_size = 1000
    full_root = None

    while True:
        fallback_headers = {
            'X-Plex-Token': token,
            'X-Plex-Container-Start': str(start),
            'X-Plex-Container-Size': str(container_size)
        }
        
        response = get_request(url, headers=fallback_headers)

        if response.status_code != 200:
            logger.error(f"Error: {response.status_code}")
            break
        
        root = parse_xml_response(response)

        if full_root is None:
            full_root = root
        else:
            library_contents = root.findall('Directory')
            for item in library_contents:
                full_root.append(item)

        if len(root.findall('Directory')) < container_size:
            break

        start += container_size

    return response

def get_library_details(plex_url:str, headers:dict, library_names:list, blacklists:list | None=None) -> list:
    """
    Get details about available libraries
    """
    library_details = []
    if plex_url:
        url = urljoin(plex_url, 'library/sections')
        response = get_request(url, headers=headers)

        if response.status_code == 200:
            root = parse_xml_response(response)
            directories = root.findall('Directory')

            if library_names[0] == '*':
                for library in directories:
                    if library.attrib.get('title') not in blacklists:
                        library_details.append({"key": library.attrib.get('key'), "type": library.attrib.get('type'), "name": library.attrib.get('title')})
                    
                    if library.attrib.get('title') in blacklists:
                        logger.warning(f'Skipping "{library.attrib.get("title")}" due to blacklist.')
            else:
                for search_library in library_names:
                    for library in directories:
                        if library.attrib.get('title') == search_library and library.attrib.get('title') not in blacklists:
                            library_details.append({"key": library.attrib.get('key'), "type": library.attrib.get('type'), "name": library.attrib.get('title')})
                            break

                        if library.attrib.get('title') == search_library and library.attrib.get('title') in blacklists:
                            logger.warning(f'Skipping "{library.attrib.get("title")}" due to blacklist.')

                # else:
                #     logger.warning(f'Library "{search_library}" not found in Plex.')

    return library_details

def get_media_path(library_type, meta_root, meta_url, path_mapping, headers):
    if library_type == 'movie':
        media_path_parts = meta_root.findall('.//Part')
        media_paths = []
        for media_part in media_path_parts:
            media_path = media_part.get('file')
            if media_path:
                media_paths.append(os.path.dirname(media_path))
        media_path_final = [map_media_path(path_member, path_mapping) for path_member in set(media_paths)]

        return media_path_final

    elif library_type in ('tvshow', 'artist'):
        media_path_parts = meta_root.findall('.//Location')
        media_paths = []
        for media_part in media_path_parts:
            media_path = media_part.get('path')
            if media_path:
                media_paths.append(media_path)
        media_path_final = [map_media_path(path_member, path_mapping) for path_member in media_paths]

        return media_path_final
    
    elif library_type == 'albums':
        track_url = urljoin(meta_url, '/children')
        track_response = get_request(track_url, headers=headers)
        tracks = parse_xml_response(track_response).findall('Track')
        if not tracks:
            raise ValueError('Album response has no tracks')
        track_part = tracks[0].find('Media/Part')
        track0_path = track_part.get('file') if track_part is not None else None
        if not track0_path:
            raise ValueError('Album track has no media path')
        return [map_media_path(os.path.dirname(track0_path), path_mapping)]
    
def get_file_path(library_type, movie_filename_type, image_filename_type, media_path, media_title, file_title):
    sanitized_title = sanitize_filename(media_title or '')
    file_name = sanitize_filename(os.path.basename(file_title or '').rsplit('.', 1)[0])
    if library_type == 'artist':
        nfo_path = safe_output_path(media_path, 'artist.nfo')
    elif library_type == 'albums':
        nfo_path = safe_output_path(media_path, 'album.nfo')
    elif library_type == 'movie':
        if movie_filename_type == 'title':
            nfo_path = safe_output_path(media_path, f'{sanitized_title}.nfo')
        elif movie_filename_type == 'filename':
            nfo_path = safe_output_path(media_path, f'{file_name}.nfo')
        else:
            nfo_path = safe_output_path(media_path, 'movie.nfo')
    else:
        nfo_path = safe_output_path(media_path, f'{library_type}.nfo')

    if library_type == 'movie':
        if image_filename_type == 'title':
            poster_path = safe_output_path(media_path, f'{sanitized_title}_poster.jpg')
            fanart_path = safe_output_path(media_path, f'{sanitized_title}_fanart.jpg')
        elif image_filename_type == 'filename':
            poster_path = safe_output_path(media_path, f'{file_name}_poster.jpg')
            fanart_path = safe_output_path(media_path, f'{file_name}_fanart.jpg')
        else:
            poster_path = safe_output_path(media_path, 'poster.jpg')
            fanart_path = safe_output_path(media_path, 'fanart.jpg')
    else:
        poster_path = safe_output_path(media_path, 'poster.jpg')
        fanart_path = safe_output_path(media_path, 'fanart.jpg')

    return nfo_path, poster_path, fanart_path

def download_image(url:str, headers:dict, save_path:str) -> None:
    """
    Download image from provided url, also convert RGBA to RGB
    """
    try:
        headers = headers.copy()
        headers["Accept-Encoding"] = "gzip"

        response = get_request(url, headers=headers, stream=True)

        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                # Save raw content for debugging
                # with open("debug_response.bin", "wb") as f:
                #     for chunk in response.iter_content(8192):
                #         f.write(chunk)
                logger.verbose(f"[ERROR] Invalid content type: {content_type}, URL: {url}")
                return False

            content_length = response.headers.get("Content-Length")
            try:
                if content_length is not None and int(content_length) > MAX_IMAGE_RESPONSE_BYTES:
                    raise ValueError(f"Image response exceeds {MAX_IMAGE_RESPONSE_BYTES} byte limit")
            except ValueError as exc:
                if str(exc).startswith("Image response exceeds"):
                    raise

            raw_content = response.raw.read(MAX_IMAGE_RESPONSE_BYTES + 1)
            if len(raw_content) > MAX_IMAGE_RESPONSE_BYTES:
                raise ValueError(f"Image response exceeds {MAX_IMAGE_RESPONSE_BYTES} byte limit")

            if response.headers.get("Content-Encoding") == "gzip":
                decompressed = gzip.GzipFile(fileobj=BytesIO(raw_content)).read(MAX_IMAGE_RESPONSE_BYTES + 1)
                if len(decompressed) > MAX_IMAGE_RESPONSE_BYTES:
                    raise ValueError(f"Decompressed image exceeds {MAX_IMAGE_RESPONSE_BYTES} byte limit")
                image_data = BytesIO(decompressed)
            else:
                image_data = BytesIO(raw_content)

            image = Image.open(image_data)
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError(f"Decoded image exceeds {MAX_IMAGE_PIXELS} pixel limit")
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            image.save(save_path)
            return True

        elif response.status_code == 404:
            logger.verbose('[FAILURE] Image does not exist')
            return False
        else:
            logger.verbose(f"[FAILURE] Download Image HTTP Response: {response.status_code}")
            return False

    except Exception as e:
        logger.verbose(f"[FAILURE] Download Image failed: {e}")
        return False

SIMPLE_FIELD_MAP = [
    ('studio', 'studio', 'studio'),
    ('title', 'title', 'title'),
    ('mpaa', 'contentRating', 'mpaa'),
    ('plot', 'summary', 'plot'),
    ('criticrating', 'rating', 'criticrating'),
    ('customrating', 'userRating', 'customrating'),
    ('year', 'year', 'year'),
    ('tagline', 'tagline', 'tagline'),
    ('runtime', 'duration', 'runtime'),
    ('releasedate', 'originallyAvailableAt', 'releasedate'),
]

TAG_COLLECTION_MAP = [
    ('genre', 'Genre', 'genre'),
    ('country', 'Country', 'country'),
    ('style', 'Style', 'style'),
]

PEOPLE_MAP = [
    ('directors', 'Director', 'director'),
    ('writers', 'Writer', 'writer'),
]















XML_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]*$')

def add_xml_element(parent, tag, text=None, attributes=None):
    if not XML_NAME_PATTERN.fullmatch(tag):
        return None
    element = ET.SubElement(parent, tag, attributes or {})
    if text is not None:
        element.text = str(text)
    return element

def write_agent_ids_section(root, config, meta_root):
    if not config.get('agent_id'):
        return

    guid = meta_root.get('guid')
    if not guid:
        return

    if 'themoviedb' in guid:
        add_xml_element(root, 'tmdbid', guid.split('//')[-1].split('?')[0])

    if 'agents.hama' in guid:
        prefix = guid.split('//')[-1].split('-')[0]
        id_part = guid.split('-')[-1].split('?')[0]
        add_xml_element(root, f'{prefix}id', id_part)

    for agent in meta_root.findall('Guid'):
        aid = agent.get('id', '')
        if not aid:
            continue
        tag = aid.split(':')[0] + 'id'
        value = aid.split('//')[-1]
        add_xml_element(root, tag, value)


def write_simple_fields(root, config, meta_root):
    for config_key, attribute, tag in SIMPLE_FIELD_MAP:
        if config.get(config_key) and meta_root.get(attribute):
            add_xml_element(root, tag, meta_root.get(attribute))


def write_tag_collections(root, config, meta_root):
    for config_key, element_name, tag_name in TAG_COLLECTION_MAP:
        if not config.get(config_key):
            continue
        for element in meta_root.findall(element_name):
            value = element.get('tag')
            if value:
                add_xml_element(root, tag_name, value)


def write_ratings_section(root, config, meta_root):
    if not config.get('ratings'):
        return

    ratings = list(meta_root.findall('Rating'))
    if not ratings:
        return

    ratings_root = add_xml_element(root, 'ratings')
    for rating in ratings:
        rating_type = rating.get('type')
        value = rating.get('value')
        if ratings_root is not None and rating_type and value:
            add_xml_element(ratings_root, rating_type, value)


def write_people_sections(root, config, meta_root):
    for config_key, element_name, tag_name in PEOPLE_MAP:
        if not config.get(config_key):
            continue
        for person in meta_root.findall(element_name):
            label = person.get('tag')
            if not label:
                continue
            attributes = {}
            thumb = person.get('thumb')
            if thumb:
                attributes['thumb'] = thumb
            add_xml_element(root, tag_name, label, attributes)


def write_roles_section(root, config, meta_root):
    if not config.get('roles'):
        return

    for role in meta_root.findall('Role'):
        label = role.get('tag')
        if not label:
            continue
        attributes = {}
        thumb = role.get('thumb')
        if thumb:
            attributes['thumb'] = thumb
        role_name = role.get('role')
        if role_name:
            attributes['role'] = role_name
        add_xml_element(root, 'actor', label, attributes)


def write_nfo(config:dict, nfo_path:str, library_type:str, meta_root:str, media_title:str) -> None:
    try:
        with open(nfo_path, 'w', encoding='utf-8') as nfo:
            root = ET.Element(library_type, {
                'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                'xsd': 'http://www.w3.org/2001/XMLSchema',
            })

            write_agent_ids_section(root, config, meta_root)
            write_simple_fields(root, config, meta_root)
            write_tag_collections(root, config, meta_root)
            write_ratings_section(root, config, meta_root)
            write_people_sections(root, config, meta_root)
            write_roles_section(root, config, meta_root)

            nfo.write(ET.tostring(root, encoding='unicode', xml_declaration=True))

            return True

    except Exception as e:
        logger.verbose(f"[FAILURE] Failed to write NFO for {media_title} due to {e}")
        if os.path.exists(nfo_path):
            try:
                os.remove(nfo_path)
                logger.verbose(f"[CLEANUP] Incomplete NFO at {nfo_path} has been removed")
            except Exception as rm_err:
                logger.verbose(f"[CLEANUP] Failed to remove incomplete NFO at {nfo_path}: {rm_err}")
        return False

def write_episode_nfo(episode_nfo_path, episode_root, media_title):
    try:
        with open(episode_nfo_path, 'w', encoding='utf-8') as nfo:
            root = ET.Element('episodedetails', {
                'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                'xsd': 'http://www.w3.org/2001/XMLSchema',
            })

            if episode_root.findall('Guid'):
                for guid in episode_root.findall('Guid'):
                    gid = guid.get("id")
                    if not gid:
                        continue
                    utype = None
                    if 'imdb' in gid:
                        utype = 'imdb'
                    elif 'tmdb' in gid:
                        utype = 'tmdb'
                    elif 'tvdb' in gid:
                        utype = 'tvdb'

                    if utype:
                        add_xml_element(root, 'uniqueid', gid.rsplit('/', 1)[-1], {'type': utype})

            fields = {
                'parentIndex': 'season',
                'index': 'episode',
                'title': 'title',
                'summary': 'plot',
                'contentRating': 'mpaa',
                'rating': 'userrating',
                'originallyAvailableAt': 'aired',
            }

            for attr, tag in fields.items():
                value = episode_root.get(attr)
                if value:
                    add_xml_element(root, tag, value)

            nfo.write(ET.tostring(root, encoding='unicode', xml_declaration=True))

            return True

    except Exception as e:
        logger.verbose(f'[ERROR] Failed to write episode NFO for {media_title} due to {e}')
        if os.path.exists(episode_nfo_path):
            try:
                os.remove(episode_nfo_path)
                logger.verbose(f'[CLEANUP] Incomplete Episode NFO at {episode_nfo_path} has been removed')
            except Exception as rm_err:
                logger.verbose(f'[CLEANUP] Failed to remove incomplete Episode NFO at {episode_nfo_path}: {rm_err}')

        return False
    
def process_media(type, config, file_path, library_type, media_root, media_title, dry_run, force_overwrite, season_dir='', season_path='', baseurl=None, headers=None):
    file_exists = os.path.exists(season_path or file_path)
    if not os.path.exists(os.path.dirname(season_path or file_path)):
        logger.verbose(f'[FAILURE] {type} for {media_title} skipped because {os.path.dirname(season_path or file_path)} is not exist')
        return 'not_exist'
    elif dry_run:
        status = 'checked and rewritten' if file_exists else f'saved to {season_path or file_path}'
        logger.info(f'[DRY RUN] {type} for {media_title} will be {status}')
        return 'dry_run'
    else:
        try:
            if file_exists:
                file_mod_time = int(os.path.getmtime(season_path or file_path))
                server_mod_time = int(media_root.get('updatedAt') or 0)
                if (file_mod_time < server_mod_time) or force_overwrite:
                    if type == 'NFO':
                        file_status = write_nfo(config, file_path, library_type, media_root, media_title)
                    elif type == 'Episode NFO':
                        file_status = write_episode_nfo(file_path, media_root, media_title)
                    elif type in ('Poster', 'Season Poster', 'Art'):
                        if type == 'Poster':
                            url = urljoin(baseurl, media_root.get('thumb'))
                        elif type == 'Season Poster':
                            url = urljoin(baseurl, season_dir.get('thumb'))
                        else:
                            url = urljoin(baseurl, media_root.get('art'))
                        file_status = download_image(url, headers, season_path or file_path)

                    if file_status:
                        logger.verbose(f'[UPDATED] {type} for {media_title} successfully saved to {season_path or file_path}')
                        return 'updated'
                    else:
                        return 'failure'
                else:
                    logger.verbose(f'[SKIPPED] {type} for {media_title} skipped because file is not older than last updated metadata')
                    return 'skipped'
            else:
                if type == 'NFO':
                    file_status = write_nfo(config, file_path, library_type, media_root, media_title)
                elif type == 'Episode NFO':
                    file_status = write_episode_nfo(file_path, media_root, media_title)
                elif type in ('Poster', 'Season Poster', 'Art'):
                    if type == 'Poster':
                        url = urljoin(baseurl, media_root.get('thumb'))
                    elif type == 'Season Poster':
                        url = urljoin(baseurl, season_dir.get('thumb'))
                    else:
                        url = urljoin(baseurl, media_root.get('art'))
                    file_status = download_image(url, headers, season_path or file_path)

                if file_status:
                    logger.verbose(f'[ADDED] {type} for {media_title} successfully saved to {season_path or file_path}')
                    return 'success'
                else:
                    return 'failure'
        except Exception as e:
            logger.verbose(f'[FAILURE] {type} for {media_title} failed: {e}')
            return 'failure'

def sanitize_filename(filename):
    filename = filename.replace(": ", " - ")
    filename = filename.translate(str.maketrans({
        ":": "-"
        , "/": "-"
        , "\\": "-"
        , "*": "-"
        , "?": ""
        , '"': ""
        , "<": "-"
        , ">": "-"
        , "|": "-"
    })).rstrip('.')
    return filename

def map_media_path(path, path_mapping):
    if not isinstance(path, str) or not path or not os.path.isabs(path):
        raise ValueError(f'Invalid Plex media path: {path!r}')

    source_path = os.path.normpath(path)
    for mapping in path_mapping or []:
        plex_root = mapping.get('plex')
        local_root = mapping.get('local')
        if not isinstance(plex_root, str) or not isinstance(local_root, str):
            raise ValueError('Path mappings must define string plex and local roots')
        if not os.path.isabs(plex_root) or not os.path.isabs(local_root):
            raise ValueError('Path mapping roots must be absolute paths')

        plex_root = os.path.normpath(plex_root)
        local_root = os.path.abspath(os.path.normpath(local_root))
        relative_path = os.path.relpath(source_path, plex_root)
        if relative_path == os.curdir or not relative_path.startswith(os.pardir + os.sep):
            mapped_path = os.path.normpath(os.path.join(local_root, relative_path))
            if os.path.commonpath((os.path.realpath(local_root), os.path.realpath(mapped_path))) != os.path.realpath(local_root):
                raise ValueError(f'Mapped media path escapes local root: {path!r}')
            return mapped_path

    if path_mapping:
        raise ValueError(f'Plex media path is outside configured mappings: {path!r}')
    return source_path

def safe_output_path(media_path, filename):
    root = os.path.realpath(media_path)
    candidate = os.path.realpath(os.path.join(media_path, filename))
    if os.path.commonpath((root, candidate)) != root:
        raise ValueError(f'Output path escapes media root: {filename!r}')
    return candidate

def str_to_bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")

def load_configuration(config_dir=None):
    if config_dir is None:
        config_dir = resolve_config_dir()

    env_path = resolve_env_file_path(config_dir)
    if os.path.exists(env_path):
        load_dotenv(env_path)

    yaml.SafeLoader.add_constructor('!env_var', env_var_constructor)

    config_path = resolve_config_file_path(config_dir)
    with open(config_path, 'r', encoding='utf-8') as file:
        config_content = file.read()
        config_content = re.sub(r'\$\{(\w+)\}', lambda match: os.getenv(match.group(1), ''), config_content)

    return yaml.safe_load(config_content)

def resolve_base_settings(args, config):
    global baseurl
    baseurl = (args.url or os.getenv('PLEX_URL') or config.get('Base URL', '')).strip("'\"")
    if not baseurl:
        logger.warning('Failed to read Plex url, please check config/variables')
        sys.exit()
    logger.debug(f'baseurl: {baseurl}')
    token_source = args.token or os.getenv('PLEX_TOKEN') or config.get('Token')
    token = (token_source or '').strip("'\"")
    if not token:
        logger.warning('Failed to read Plex token, please check config/variables')
        sys.exit()

    library_names = args.library or config.get('Libraries', [])
    logger.debug(f'library_names: {library_names}')

    blacklists = config.get('Blacklist', None)
    path_mapping = config.get('Path mapping', [])
    logger.debug(f'path_mapping: {path_mapping}')

    return baseurl, token, library_names, blacklists, path_mapping

def build_export_flags(args, config):
    option_map = {
        'export_nfo': ('Export NFO', args.export_nfo),
        'export_episode_nfo': ('Export episode NFO', args.export_episode_nfo),
        'export_poster': ('Export poster', args.export_poster),
        'export_fanart': ('Export fanart', args.export_fanart),
        'export_season_poster': ('Export season poster', args.export_season_poster),
    }

    exports = {}
    for key, (config_key, arg_value) in option_map.items():
        value = arg_value if arg_value is not None else config.get(config_key, False)
        source = 'command-line argument' if arg_value is not None else 'config file'
        logger.debug(f'{key} is set to {value} by {source}.')
        exports[key] = value

    return exports

def determine_force_overwrite(args, config):
    if args.force_overwrite:
        logger.debug('force_overwrite is set to True by command-line argument.')
        return True

    if str_to_bool(os.getenv('FORCE_OVERWRITE', 'false')):
        logger.debug('force_overwrite is set to True by environment variable.')
        return True

    force_overwrite = config.get('Force overwrite', False)
    if force_overwrite:
        logger.debug('force_overwrite is set to True by config file.')
    else:
        logger.debug('force_overwrite is set to False.')

    return force_overwrite

def determine_dry_run(args):
    if args.dry_run:
        logger.debug('dry_run is set to True by command-line argument.')
        return True

    if str_to_bool(os.getenv('DRY_RUN', 'false')):
        logger.debug('dry_run is set to True by environment variable.')
        return True

    logger.debug('dry_run is set to False.')
    return False

def create_library_result():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    return {
        'start': timestamp,
        'finish': '',
        'nfo_new': 0,
        'nfo_updated': 0,
        'nfo_skipped': 0,
        'nfo_failure': 0,
        'poster_new': 0,
        'poster_updated': 0,
        'poster_skipped': 0,
        'poster_failure': 0,
        'art_new': 0,
        'art_updated': 0,
        'art_skipped': 0,
        'art_failure': 0,
        'season_poster_new': 0,
        'season_poster_updated': 0,
        'season_poster_skipped': 0,
        'season_poster_failure': 0,
        'episode_nfo_new': 0,
        'episode_nfo_updated': 0,
        'episode_nfo_skipped': 0,
        'episode_nfo_failure': 0,
    }

def resolve_library_type(library_type, check_music):
    if library_type in TYPE_MAP:
        processed_type, root = TYPE_MAP[library_type]
        return processed_type, root, check_music

    if check_music == 0:
        return 'artist', 'Directory', check_music + 1

    if check_music == 1:
        return 'albums', 'Directory', check_music - 1

    return library_type, 'Directory', check_music

def fetch_library_root(library, library_root, check_music_state, baseurl, headers):
    suffix = 'all' if check_music_state == 0 else 'albums'
    url = urljoin(baseurl, f"/library/sections/{library.get('key')}/{suffix}")
    response = get_request(url, headers=headers)

    if response.status_code == 400:
        response = fallback_response(url, headers['X-Plex-Token'])

    if response.status_code != 200:
        logger.error(f"Failed to get library info with error code {response.status_code}: {response.text}")
        sys.exit()

    return parse_xml_response(response)

def update_summary(summary, category, status):
    if status == 'success':
        key = f'{category}_new'
    elif status == 'updated':
        key = f'{category}_updated'
    elif status == 'skipped':
        key = f'{category}_skipped'
    elif status in ('not_exist', 'failure'):
        key = f'{category}_failure'
    else:
        return

    summary[key] += 1

def export_episode_nfos(meta_url, path_mapping, config, media_title, dry_run, force_overwrite, summary, headers):
    try:
        meta_season_url = urljoin(meta_url + '/', 'children')
        season_resp = get_request(meta_season_url, headers=headers)

        if season_resp.status_code != 200:
            return

        for season in parse_xml_response(season_resp).findall('Directory'):
            season_key = season.get('ratingKey')
            episodes_url = urljoin(meta_url[:meta_url.rfind('/')] + '/', f'{season_key}/children')
            episodes_resp = get_request(episodes_url, headers=headers)

            if episodes_resp.status_code != 200:
                continue

            for episode in parse_xml_response(episodes_resp).findall('Video'):
                episode_key = episode.get('ratingKey')
                episode_url = urljoin(meta_url[:meta_url.rfind('/')] + '/', episode_key)
                episode_data = get_request(episode_url, headers=headers)
                episode_root = parse_xml_response(episode_data).find('Video')

                if episode_root is None:
                    continue

                episode_part = episode_root.find('Media/Part')
                episode_path = episode_part.get('file') if episode_part is not None else None
                if not episode_path:
                    logger.verbose(f'[FAILURE] Episode NFO for {media_title} skipped because media path is missing')
                    continue
                episode_nfo_path = map_media_path(os.path.splitext(episode_path)[0] + '.nfo', path_mapping)

                status = process_media('Episode NFO', config, episode_nfo_path, 'tvshow', episode_root, media_title, dry_run, force_overwrite, headers=headers)
                update_summary(summary, 'episode_nfo', status)
    except Exception as exc:
        logger.verbose(f'[FAILURE] Episode NFO for {media_title} failed: {exc}')
        summary['episode_nfo_failure'] += 1

def export_season_posters(meta_url, media_path, fanart_path, config, meta_root, media_title, dry_run, force_overwrite, summary, baseurl, headers):
    try:
        season_url = urljoin(f'{meta_url}/', 'children')
        season_response = get_request(season_url, headers=headers)

        if season_response.status_code != 200:
            return

        season_root = parse_xml_response(season_response).findall('Directory')
        for season_dir in season_root:
            title = season_dir.get('title')
            if not title or title == 'All episodes':
                continue

            season_title = title.lower().replace(' ', '')
            if season_title not in ('specials', 'miniseries'):
                season_filename = f'{season_title}-cover.jpg'
            else:
                season_filename = 'season1-cover.jpg'
            if season_title == 'specials':
                season_filename = f'season-{season_title}-cover.jpg'

            season_path = safe_output_path(media_path, season_filename)
            status = process_media('Season Poster', config, fanart_path, 'tvshow', meta_root, media_title, dry_run, force_overwrite, season_dir, season_path, baseurl, headers)
            update_summary(summary, 'season_poster', status)
    except Exception as exc:
        logger.info(f'[FAILURE] Season poster for {media_title} failed: {exc}')
        summary['season_poster_failure'] += 1

def process_content(content, library_root, library_type, args, config, path_mapping, exports, movie_filename_type, image_filename_type, dry_run, force_overwrite, summary, baseurl, headers):
    ratingkey = content.get('ratingKey')
    meta_url = urljoin(baseurl, f"/library/metadata/{ratingkey}")
    meta_response = get_request(meta_url, headers=headers)
    if meta_response.status_code != 200:
        return

    meta_root = parse_xml_response(meta_response).find(library_root)
    if meta_root is None:
        return

    media_title = meta_root.get('title')

    if args.title and media_title not in args.title:
        return

    if library_type == 'movie':
        movie_part = meta_root.find('Media/Part')
        file_title = movie_part.get('file') if movie_part is not None else None
    else:
        file_title = None
    media_paths = get_media_path(library_type, meta_root, meta_url, path_mapping, headers)

    for media_path in media_paths:
        logger.debug(f'media_path: {media_path}')
        nfo_path, poster_path, fanart_path = get_file_path(library_type, movie_filename_type, image_filename_type, media_path, media_title, file_title)

        if exports['export_nfo']:
            status = process_media('NFO', config, nfo_path, library_type, meta_root, media_title, dry_run, force_overwrite)
            update_summary(summary, 'nfo', status)

        if exports['export_episode_nfo'] and library_type == 'tvshow':
            export_episode_nfos(meta_url, path_mapping, config, media_title, dry_run, force_overwrite, summary, headers)

        if exports['export_poster']:
            status = process_media('Poster', config, poster_path, library_type, meta_root, media_title, dry_run, force_overwrite, baseurl=baseurl, headers=headers)
            update_summary(summary, 'poster', status)

        if exports['export_fanart']:
            status = process_media('Art', config, fanart_path, library_type, meta_root, media_title, dry_run, force_overwrite, baseurl=baseurl, headers=headers)
            update_summary(summary, 'art', status)

        if exports['export_season_poster'] and library_type == 'tvshow':
            export_season_posters(meta_url, media_path, fanart_path, config, meta_root, media_title, dry_run, force_overwrite, summary, baseurl, headers)

def process_library(library, args, config, path_mapping, exports, movie_filename_type, image_filename_type, dry_run, force_overwrite, check_music, library_result, baseurl, headers):
    library_name = library.get('name')
    summary = create_library_result()
    library_result[library_name] = summary

    lib_type = library.get('type')
    library_type, library_root, updated_check_music = resolve_library_type(lib_type, check_music)

    full_root = fetch_library_root(library, library_root, updated_check_music, baseurl, headers)
    library_contents = full_root.findall(library_root)

    with alive_bar(len(library_contents), monitor=True, elapsed=True, stats=False, receipt_text=True) as bar:
        bar.text(f'for {library_name}')
        for content in library_contents:
            try:
                process_content(content, library_root, library_type, args, config, path_mapping, exports, movie_filename_type, image_filename_type, dry_run, force_overwrite, summary, baseurl, headers)
            except Exception as exc:
                logger.verbose(f"[FAILURE] Skipping item (ratingKey={content.get('ratingKey')}) in {library_name} due to incomplete or unexpected Plex metadata: {exc}")
            bar()

    summary['finish'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return updated_check_music

def print_library_summary(library_result, exports):
    for library_name, summary in library_result.items():
        print(f"\n============================ {library_name.upper()} PROCESSING SUMMARY ============================")
        print(f"\nStart       : {summary['start']}\nFinished    : {summary['finish']}")

        if exports['export_nfo']:
            print(
                f"\nNFO Files\n  - Added     : {summary['nfo_new']} NFO(s)\n  - Updated   : {summary['nfo_updated']} NFO(s)\n  - Skipped   : {summary['nfo_skipped']} NFO(s)\n  - Failed    : {summary['nfo_failure']} NFO(s)"
            )

        if exports['export_poster']:
            print(
                f"\nPoster Images\n  - Added     : {summary['poster_new']} poster(s)\n  - Updated   : {summary['poster_updated']} poster(s)\n  - Skipped   : {summary['poster_skipped']} poster(s)\n  - Failed    : {summary['poster_failure']} poster(s)"
            )

        if exports['export_fanart']:
            print(
                f"\nArt Images\n  - Added     : {summary['art_new']} art(s)\n  - Updated   : {summary['art_updated']} art(s)\n  - Skipped   : {summary['art_skipped']} art(s)\n  - Failed    : {summary['art_failure']} art(s)"
            )

        if exports['export_season_poster']:
            print(
                f"\nSeason Poster Images\n  - Added     : {summary['season_poster_new']} season poster(s)\n  - Updated   : {summary['season_poster_updated']} season poster(s)\n  - Skipped   : {summary['season_poster_skipped']} season poster(s)\n  - Failed    : {summary['season_poster_failure']} season poster(s)"
            )

        if exports['export_episode_nfo']:
            print(
                f"\nEpisode NFO Files\n  - Added     : {summary['episode_nfo_new']} episode NFO(s)\n  - Updated   : {summary['episode_nfo_updated']} episode NFO(s)\n  - Skipped   : {summary['episode_nfo_skipped']} episode NFO(s)\n  - Failed    : {summary['episode_nfo_failure']} episode NFO(s)"
            )

def main(args, log_name, config_dir=None):
    config = load_configuration(config_dir)

    baseurl, token, library_names, blacklists, path_mapping = resolve_base_settings(args, config)

    headers = {'X-Plex-Token': token}
    library_details = get_library_details(baseurl, headers, library_names, blacklists)

    exports = build_export_flags(args, config)
    movie_filename_type = (args.nfo_name_type or config.get('Movie NFO name type') or 'default').lower()
    image_filename_type = (args.image_name_type or config.get('Movie Poster/art name type') or 'default').lower()

    force_overwrite = determine_force_overwrite(args, config)
    dry_run = determine_dry_run(args)

    library_result = {}
    check_music = 0

    print('')

    for library in library_details:
        check_music = process_library(
            library,
            args,
            config,
            path_mapping,
            exports,
            movie_filename_type,
            image_filename_type,
            dry_run,
            force_overwrite,
            check_music,
            library_result,
            baseurl,
            headers,
        )

    if not dry_run:
        print_library_summary(library_result, exports)

    print(f'\nLog file: {log_name}.log')
    print('Check the log file for entries marked [ADDED], [UPDATED], [SKIPPED], and [FAILED].')
    print('To display those in the terminal instead, set "LOG_LEVEL" to "VERBOSE" in your config.yml or as an environment variable.\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Export metadata and poster/art from plex to NFO and image files.")
    parser.add_argument("--url", "-u", help="Plex server base url")
    parser.add_argument("--token", help="Plex token")
    parser.add_argument("--library", "-l", nargs='+', help="Library name(s) to process.")
    parser.add_argument("--title", "-t", nargs='+', help="Media title(s) to process.")

    parser.add_argument("--nfo-name-type", choices=["default", "title", "filename"], default=None)
    parser.add_argument("--image-name-type", choices=["default", "title", "filename"], default=None)

    parser.add_argument("--export-nfo", dest="export_nfo", action="store_true", help="Export NFO files; overrides config.yml setting", default=None)
    parser.add_argument("--no-export-nfo", dest="export_nfo", action="store_false", help="Do not export NFO files")

    parser.add_argument("--export-poster", dest="export_poster", action="store_true", help="Export posters; overrides config.yml setting", default=None)
    parser.add_argument("--no-export-poster", dest="export_poster", action="store_false")

    parser.add_argument("--export-fanart", dest="export_fanart", action="store_true", help="Export fanarts; overrides config.yml setting", default=None)
    parser.add_argument("--no-export-fanart", dest="export_fanart", action="store_false")

    parser.add_argument("--export-season-poster", dest="export_season_poster", action="store_true", help="Export season poster; overrides config.yml setting", default=None)
    parser.add_argument("--no-export-season-poster", dest="export_season_poster", action="store_false")

    parser.add_argument("--export-episode-nfo", dest="export_episode_nfo", action="store_true", help="Export episode NFO files; overrides config.yml setting", default=None)
    parser.add_argument("--no-export-episode-nfo", dest="export_episode_nfo", action="store_false")

    parser.add_argument("--force-overwrite", "-f", dest="force_overwrite", action=StoreTrueIfFlagPresent, nargs=0, help="Overwrite files without checking server metadata; overrides config.yml setting", default=None)

    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without making any changes")

    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "CRITICAL", "VERBOSE"], type=str.upper, default=None)

    parser.add_argument("--config", "-c", help="Path to config directory containing config.yml and .env (optional, defaults to auto-detect)")

    args = parser.parse_args()
    log_level = args.log_level

    resolved_config_dir = args.config if args.config is not None else resolve_config_dir()

    ensure_files_exist(resolved_config_dir) 
    logger, log_name = set_logger(log_level, resolved_config_dir)
    main(args, log_name, resolved_config_dir)
