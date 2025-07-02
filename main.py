#!/usr/bin/env python3

from alive_progress import alive_bar
from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO
from pathlib import Path
from PIL import Image
from urllib.parse import urljoin

import argparse
import gzip
import logging
import os
import re
import requests
import sys
import xml.etree.ElementTree as ET
import yaml

if os.path.isdir('/app/config'):
    config_path = '/app/config/config.yml'
else:
    config_path = 'config.yml'

class StoreTrueIfFlagPresent(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)

def set_logger(log_level):
    if not os.path.exists('logs'):
        os.makedirs('logs')

    files = list(Path('logs/').iterdir())
    files = [f for f in files if f.is_file()]
    if len(files) > 10:
        files.sort(key=lambda f: f.stat().st_mtime)
        oldest_file = files[0]
        os.remove(oldest_file)
        print(f"Deleted: {oldest_file}")

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

def ensure_files_exist():
    """
    Ensure required .env and config.yml files exist with placeholder content.
    """
    files = [
        {
            "path": "/app/config/.env" if os.path.isdir("/app/config") else ".env",
            "content": "PLEX_URL='http://192.168.1.2:32400'\nPLEX_TOKEN='very-long-token'",
            "name": ".env",
            "env_vars": ["PLEX_URL", "PLEX_TOKEN"]
        },
        {
            "path": "/app/config/config.yml" if os.path.isdir("/app/config") else "config.yml",
            "content": """# config.yml

# change plex url and token here
# you can ignore this if you are using PLEX_URL and PLEX_TOKEN environment variables in docker
Base URL: ${PLEX_URL} # i.e http://192.168.1.1:32400 or if reverse proxied i.e. https://plex.yourdomain.tld or fill them in .env file and let this part be
Token: ${PLEX_TOKEN} # how to get token https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/ or fill them in .env file and let this part be

# input the libraries you want to export NFO/poster/fanart from
# if the library type is music, input it TWICE CONSECUTIVELY. This is due to plex having 2 different roots for music library, each for artist and albums
Libraries: ['Movies', 'TV Shows', 'Anime', 'Music', 'Music']

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

# Leave this empty if you use docker volume mapping i.e. Path mapping: []
# change/add path mapping if plex path is different from local (script) path
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
""",
            "name": "config.yml"
        }
    ]

    for file in files:
        if file["name"] == ".env":
            if all(os.getenv(var) for var in file["env_vars"]):
                continue
        if not os.path.exists(file["path"]):
            with open(file["path"], "w", encoding="utf-8") as f:
                f.write(file["content"])
            print(f"{file['path']} created. Please populate it and rerun the script.")
            sys.exit()
        else:
            print(f"{file['path']} already exists.")

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
        
        response = requests.get(url, headers=fallback_headers)

        if response.status_code != 200:
            logger.error(f"Error: {response.status_code}")
            break
        
        root = ET.fromstring(response.content)

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

def get_library_details(plex_url:str, headers:dict, library_names:list) -> list:
    """
    Get details about available libraries
    """
    library_details = []
    if plex_url:
        url = urljoin(plex_url, 'library/sections')
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            root = ET.fromstring(response.content)
            directories = root.findall('Directory')

            for search_library in library_names:
                for library in directories:
                    if library.attrib.get('title') == search_library:
                        library_details.append({"key": library.attrib.get('key'), "type": library.attrib.get('type'), "name": library.attrib.get('title')})
                        break
                else:
                    logger.warning(f'"Library {search_library}" not found in Plex.')

    if not library_details:
        logger.warning(f'None of the specified libraries were found in Plex. Exiting...')
        sys.exit()

    return library_details

def get_media_path(library_type, meta_root, meta_url, path_mapping, headers):
    if library_type == 'movie':
        media_path_parts = meta_root.findall('.//Part')
        media_paths = []
        for media_part in media_path_parts:
            media_paths.append(media_part.get('file'))
        media_path_dirty = {path_member[:path_member.rfind("/")]+"/" for path_member in media_paths}
        media_path_final = []
        for path_member in media_path_dirty:
            for path_list in path_mapping:
                path_member = path_member.replace(path_list.get('plex'), path_list.get('local'))
            media_path_final.append(path_member)

        return media_path_final
    
    elif library_type in ('tvshow', 'artist'):
        media_path_parts = meta_root.findall('.//Location')
        media_paths = []
        for media_part in media_path_parts:
            media_paths.append(media_part.get('path')+'/')
        media_path_final = []
        for path_member in media_paths:
            for path_list in path_mapping:
                path_member = path_member.replace(path_list.get('plex'), path_list.get('local'))
            media_path_final.append(path_member)

        return media_path_final
    
    elif library_type == 'albums':
        track_url = urljoin(meta_url, '/children')
        track_response = requests.get(track_url, headers=headers)
        track0_path = ET.fromstring(track_response.content).findall('Track')[0].find('Media/Part').get('file')
        media_path = track0_path[:track0_path.rfind('/')]+'/'
        media_path_final = []
        for path_list in path_mapping:
            media_path = media_path.replace(path_list.get('plex'), path_list.get('local'))
        media_path_final.append(media_path)

        return media_path_final
    
def get_file_path(library_type, movie_filename_type, image_filename_type, media_path, media_title, file_title):
    if library_type == 'artist':
        nfo_path = os.path.join(media_path, 'artist.nfo')
    elif library_type == 'albums':
        nfo_path = os.path.join(media_path, 'album.nfo')
    elif library_type == 'movie':
        if movie_filename_type == 'title':
            sanitized_title = sanitize_filename(media_title)
            nfo_path = os.path.join(media_path, f'{sanitized_title}.nfo')
        elif movie_filename_type == 'filename':
            file_name = file_title[file_title.rfind('/')+1:file_title.rfind('.')]
            nfo_path = os.path.join(media_path, f'{file_name}.nfo')
        else:
            nfo_path = os.path.join(media_path, 'movie.nfo')
    else:
        nfo_path = os.path.join(media_path, f'{library_type}.nfo')

    if library_type == 'movie':
        if image_filename_type == 'title':
            poster_path = os.path.join(media_path, f'{sanitized_title}_poster.jpg')
            fanart_path = os.path.join(media_path, f'{sanitized_title}_fanart.jpg')
        elif image_filename_type == 'filename':
            poster_path = os.path.join(media_path, f'{file_name}_poster.jpg')
            fanart_path = os.path.join(media_path, f'{file_name}_fanart.jpg')
        else:
            poster_path = os.path.join(media_path, 'poster.jpg')
            fanart_path = os.path.join(media_path, 'fanart.jpg')
    else:
        poster_path = os.path.join(media_path, 'poster.jpg')
        fanart_path = os.path.join(media_path, 'fanart.jpg')

    return nfo_path, poster_path, fanart_path

def download_image(url:str, headers:dict, save_path:str) -> None:
    """
    Download image from provided url, also convert RGBA to RGB
    """
    try:
        headers = headers.copy()
        headers["Accept-Encoding"] = "gzip"

        response = requests.get(url, headers=headers, stream=True)

        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                # Save raw content for debugging
                # with open("debug_response.bin", "wb") as f:
                #     for chunk in response.iter_content(8192):
                #         f.write(chunk)
                logger.verbose(f"[ERROR] Invalid content type: {content_type}, URL: {url}")
                return False

            # Manually decompress if needed
            if response.headers.get("Content-Encoding") == "gzip":
                buffer = BytesIO(response.raw.read())
                decompressed = gzip.GzipFile(fileobj=buffer).read()
                image_data = BytesIO(decompressed)
            else:
                image_data = BytesIO(response.content)

            image = Image.open(image_data)
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

def write_nfo(config:dict, nfo_path:str, library_type:str, meta_root:str, media_title:str) -> None:
    try:
        with open(nfo_path, 'w', encoding='utf-8') as nfo:
            nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            nfo.write(f'<{library_type} xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')
                
            guid = meta_root.get('guid')
            if config['agent_id'] and guid:
                if 'themoviedb' in guid:
                    nfo.write(f'  <tmdbid>{guid.split("//")[-1].split("?")[0]}</tmdbid>\n')

                if 'agents.hama' in guid:
                    prefix = guid.split("//")[-1].split("-")[0]
                    id_part = guid.split("-")[-1].split("?")[0]
                    nfo.write(f'  <{prefix}id>{id_part}</{prefix}id>\n')

                for agent in meta_root.findall('Guid'):
                    aid = agent.get('id', '')
                    tag = aid.split(':')[0] + 'id'
                    value = aid.split('//')[-1]
                    nfo.write(f'  <{tag}>{value}</{tag}>\n')
                                                    
            if config['studio'] and meta_root.get('studio'):
                nfo.write(f'  <studio>{meta_root.get("studio")}</studio>\n')

            if config['title'] and meta_root.get('title'):
                nfo.write(f'  <title>{meta_root.get("title")}</title>\n')
                                                    
            if config['mpaa'] and meta_root.get('contentRating'):
                nfo.write(f'  <mpaa>{meta_root.get("contentRating")}</mpaa>\n')
                                                    
            if config['plot'] and meta_root.get('summary'):
                nfo.write(f'  <plot>{meta_root.get("summary")}</plot>\n')
                                                    
            if config['criticrating'] and meta_root.get('rating'):
                nfo.write(f'  <criticrating>{meta_root.get("rating")}</criticrating>\n')
                                                    
            if config['customrating'] and meta_root.get('userRating'):
                nfo.write(f'  <customrating>{meta_root.get("userRating")}</customrating>\n')
                                                    
            if config['year'] and meta_root.get('year'):
                nfo.write(f'  <year>{meta_root.get("year")}</year>\n')
                                                    
            if config['tagline'] and meta_root.get('tagline'):
                nfo.write(f'  <tagline>{meta_root.get("tagline")}</tagline>\n')
                                                
            if config['runtime'] and meta_root.get('duration'):
                nfo.write(f'  <runtime>{meta_root.get("duration")}</runtime>\n')
                                                
            if config['releasedate'] and meta_root.get('originallyAvailableAt'):
                nfo.write(f'  <releasedate>{meta_root.get("originallyAvailableAt")}</releasedate>\n')

            if config['genre'] and meta_root.findall('Genre'):
                for genre in meta_root.findall('Genre'):
                    nfo.write(f'  <genre>{genre.get("tag")}</genre>\n')

            if config['country'] and meta_root.findall('Country'):
                for country in meta_root.findall('Country'):
                    nfo.write(f'  <country>{country.get("tag")}</country>\n')

            if config['style'] and meta_root.findall('Style'):
                for style in meta_root.findall('Style'):
                    nfo.write(f'  <style>{style.get("tag")}</style>\n')

            if config['ratings'] and meta_root.findall('Rating'):
                nfo.write('  <ratings>\n')
                for rating in meta_root.findall('Rating'):
                    nfo.write(f'    <{rating.get("type")}>{rating.get("value")}</{rating.get("type")}>\n')
                nfo.write('  </ratings>\n')

            if config['directors'] and meta_root.findall('Director'):
                for director in meta_root.findall('Director'):
                    tags = '  <director'
                    if director.get("thumb"):
                        tags += f' thumb="{director.get("thumb")}"'
                    tags += f'>{director.get("tag")}</director>\n'
                    nfo.write(tags)

            if config['writers'] and meta_root.findall('Writer'):
                for writer in meta_root.findall('Writer'):
                    tags = '  <writer'
                    if writer.get("thumb"):
                        tags += f' thumb="{writer.get("thumb")}"'
                    tags += f'>{writer.get("tag")}</writer>\n'
                    nfo.write(tags)

            if config['roles'] and meta_root.findall('Role'):
                for role in meta_root.findall('Role'):
                    tags = '  <actor'
                    if role.get("thumb"):
                        tags += f' thumb="{role.get("thumb")}"'
                    if role.get("role"):
                        tags += f' role="{role.get("role")}"'
                    tags += f'>{role.get("tag")}</actor>\n'
                    nfo.write(tags)

            nfo.write(f'</{library_type}>')

            return True

    except Exception as e:
        logger.verbose(f'[FAILURE] Failed to write NFO for {media_title} due to {e}')
        if os.path.exists(nfo_path):
            try:
                os.remove(nfo_path)
                logger.verbose(f'[CLEANUP] Incomplete NFO at {nfo_path} has been removed')
            except Exception as rm_err:
                logger.verbose(f'[CLEANUP] Failed to remove incomplete NFO at {nfo_path}: {rm_err}')
        return False

def write_episode_nfo(episode_nfo_path, episode_root, media_title):
    try:
        with open(episode_nfo_path, 'w', encoding='utf-8') as nfo:
            nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            nfo.write('<episodedetails xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')

            if episode_root.findall('Guid'):
                for guid in episode_root.findall('Guid'):
                    gid = guid.get("id")
                    if 'imdb' in guid.get('id'):
                        utype = 'imdb'
                    elif 'tmdb' in guid.get('id'):
                        utype = 'tmdb'
                    elif 'tvdb' in guid.get('id'):
                        utype = 'tvdb'
                                            
                    nfo.write(f'  <uniqueid type="{utype}">{gid.rsplit("/", 1)[-1]}</uniqueid>\n')

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
                    nfo.write(f'  <{tag}>{value}</{tag}>\n')

            nfo.write('</episodedetails>')

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
    
def process_media(type, config, file_path, library_type, media_root, media_title, dry_run, force_overwrite, season_dir='', season_path=''):
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

def str_to_bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")

def main(args, log_name):
    if os.path.exists('/app/config/.env'):
        load_dotenv('/app/config/.env')
    else:
        load_dotenv()

    yaml.SafeLoader.add_constructor('!env_var', env_var_constructor)

    with open(config_path, 'r', encoding='utf-8') as file:
        config_content = file.read()
        config_content = re.sub(r'\$\{(\w+)\}', lambda match: os.getenv(match.group(1), ''), config_content)
        config = yaml.safe_load(config_content)

    global baseurl
    baseurl = (args.url or os.getenv("PLEX_URL") or config.get("Base URL")).strip("'\"")
    if not baseurl:
        logger.warning('Failed to read Plex url, please check config/variables')
        sys.exit()
    logger.debug(f'baseurl: f{baseurl}')

    token = (args.token or os.getenv("PLEX_TOKEN") or config['Token']).strip("'\"")
    if not token:
        logger.warning('Failed to read Plex token, please check config/variables')
        sys.exit()

    library_names = args.library or config['Libraries']
    if not library_names:
        logger.warning('No library name is provided, please check config/variables')
        sys.exit()
    logger.debug(f'library_names: f{library_names}')

    path_mapping = config['Path mapping']
    logger.debug(f'path_mapping: f{path_mapping}')

    global headers
    headers = {'X-Plex-Token': token}
    library_details = get_library_details(baseurl, headers, library_names)

    check_music = 0

    type_map = {
        'movie': ('movie', 'Video'),
        'show': ('tvshow', 'Directory'),
    }

    library_result = {}

    export_options = {
        'export_nfo': ('Export NFO', args.export_nfo),
        'export_episode_nfo': ('Export episode NFO', args.export_episode_nfo),
        'export_poster': ('Export poster', args.export_poster),
        'export_fanart': ('Export fanart', args.export_fanart),
        'export_season_poster': ('Export season poster', args.export_season_poster),
    }

    exports = {}

    for key, (config_key, arg_value) in export_options.items():
        value = arg_value if arg_value is not None else config.get(config_key, False)
        logger.debug(f'{key} is set to {value} by {"command-line argument" if arg_value is not None else "config file"}.')
        exports[key] = value

    export_nfo = exports['export_nfo']
    export_episode_nfo = exports['export_episode_nfo']
    export_poster = exports['export_poster']
    export_fanart = exports['export_fanart']
    export_season_poster = exports['export_season_poster']

    movie_filename_type = (args.nfo_name_type or config.get('Movie NFO name type') or 'default').lower()
    image_filename_type = (args.image_name_type or config.get('Movie Poster/art name type') or 'default').lower()

    if args.force_overwrite:
        force_overwrite = True
        logger.debug(f'force_overwrite is set to True by command-line argument.')
    elif str_to_bool(os.getenv("FORCE_OVERWRITE", "false")):
        force_overwrite = True
        logger.debug(f'force_overwrite is set to True by environment variable.')
    elif config.get('Force overwrite', False):
        force_overwrite = config.get('Force overwrite', False)
        logger.debug(f'force_overwrite is set to True by config file.')
    else:
        force_overwrite = False
        logger.debug(f'force_overwrite is set to False.')

    if args.dry_run:
        dry_run = args.dry_run
        logger.debug(f'dry_run is set to True by command-line argument.')
    elif str_to_bool(os.getenv("DRY_RUN", "false")):
        dry_run = str_to_bool(os.getenv("DRY_RUN", "false"))
        logger.debug(f'dry_run is set to True by environment variable.')
    else:
        dry_run = False
        logger.debug(f'dry_run is set to False.')

    print('')
    for library in library_details:
        library_name = library.get("name")

        library_result[f'{library_name}'] = {
            'start': datetime.now().strftime("%Y-%m-%d %H:%M")
            , 'finish': ''
            , 'nfo_new': 0
            , 'nfo_updated': 0
            , 'nfo_skipped': 0
            , 'nfo_failure': 0
            , 'poster_new': 0
            , 'poster_updated': 0
            , 'poster_skipped': 0
            , 'poster_failure': 0
            , 'art_new': 0
            , 'art_updated': 0
            , 'art_skipped': 0
            , 'art_failure': 0
            , 'season_poster_new': 0
            , 'season_poster_updated': 0
            , 'season_poster_skipped': 0
            , 'season_poster_failure': 0
            , 'episode_nfo_new': 0
            , 'episode_nfo_updated': 0
            , 'episode_nfo_skipped': 0
            , 'episode_nfo_failure': 0
        }

        lib_type = library.get('type')
        if lib_type in type_map:
            library_type, library_root = type_map[lib_type]
        elif check_music == 0:
            library_type, library_root = 'artist', 'Directory'
            check_music += 1
        elif check_music == 1:
            library_type, library_root = 'albums', 'Directory'
            check_music -= 1

        if check_music == 0:
            url = urljoin(baseurl, f'/library/sections/{library.get("key")}/all')
        else:
            url = urljoin(baseurl, f'/library/sections/{library.get("key")}/albums')

        response = requests.get(url, headers=headers)

        if response.status_code == 400:
            response = fallback_response(url, token)

        elif response.status_code == 200:
            full_root = ET.fromstring(response.content)
        else:
            logger.error(f'Failed to get library info with error code {response.status_code}: {response.text}')
            sys.exit()
                
        library_contents = full_root.findall(library_root)
        
        with alive_bar(len(library_contents), monitor=True, elapsed=True, stats=False, receipt_text=True) as bar:
            bar.text(f'for {library.get("name")}')
            for content in library_contents:
                ratingkey = content.get('ratingKey')  
                meta_url = urljoin(baseurl, f'/library/metadata/{ratingkey}')
                meta_response = requests.get(meta_url, headers=headers)
                if meta_response.status_code == 200:
                    meta_root = ET.fromstring(meta_response.content).find(library_root)

                    media_title = meta_root.get('title')

                    if args.title:
                        if media_title not in args.title:
                            continue

                    if library_type == 'movie':
                        file_title = meta_root.find('Media/Part').get('file')
                    else:
                        file_title = None
                    

                    media_path_final = get_media_path(library_type, meta_root, meta_url, path_mapping, headers)

                    for media_path in media_path_final:
                        logger.debug(f'media_path: {media_path}')
                        nfo_path, poster_path, fanart_path = get_file_path(library_type, movie_filename_type, image_filename_type, media_path, media_title, file_title)

                        if export_nfo:
                            nfo_status = process_media('NFO', config, nfo_path, library_type, meta_root, media_title, dry_run, force_overwrite)

                            if nfo_status == 'success':
                                library_result[f'{library_name}']['nfo_new'] += 1
                            elif nfo_status == 'updated':
                                library_result[f'{library_name}']['nfo_updated'] += 1
                            elif nfo_status == 'skipped':
                                library_result[f'{library_name}']['nfo_skipped'] += 1
                            elif nfo_status == 'not_exist':
                                library_result[f'{library_name}']['nfo_failure'] += 1
                            elif nfo_status == 'failure':
                                library_result[f'{library_name}']['nfo_failure'] += 1

                        if export_episode_nfo and library_type == 'tvshow':
                            try:
                                meta_season_url = urljoin(meta_url + '/', 'children')
                                season_resp = requests.get(meta_season_url, headers=headers)

                                if season_resp.status_code == 200:
                                    for season in ET.fromstring(season_resp.content).findall('Directory'):
                                        season_key = season.get('ratingKey')
                                        episodes_url = urljoin(meta_url[:meta_url.rfind('/')] + '/', f'{season_key}/children')
                                        episodes_resp = requests.get(episodes_url, headers=headers)

                                        if episodes_resp.status_code == 200:
                                            for episode in ET.fromstring(episodes_resp.content).findall('Video'):
                                                episode_key = episode.get('ratingKey')
                                                episode_url = urljoin(meta_url[:meta_url.rfind('/')] + '/', episode_key)
                                                episode_data = requests.get(episode_url, headers=headers)
                                                episode_root = ET.fromstring(episode_data.content).find('Video')

                                                episode_path = episode_root.find('Media/Part').get('file')
                                                episode_nfo_path = episode_path[:episode_path.rfind('.')] + '.nfo'
                                                for path in path_mapping:
                                                    episode_nfo_path = episode_nfo_path.replace(path['plex'], path['local'])

                                                episode_nfo_status = process_media('Episode NFO', config, episode_nfo_path, library_type, episode_root, media_title, dry_run, force_overwrite)

                                                if episode_nfo_status == 'success':
                                                    library_result[f'{library_name}']['episode_nfo_new'] += 1
                                                elif episode_nfo_status == 'updated':
                                                    library_result[f'{library_name}']['episode_nfo_updated'] += 1
                                                elif episode_nfo_status == 'skipped':
                                                    library_result[f'{library_name}']['episode_nfo_skipped'] += 1
                                                elif episode_nfo_status == 'not_exist':
                                                    library_result[f'{library_name}']['episode_nfo_failure'] += 1
                                                elif episode_nfo_status == 'failure':
                                                    library_result[f'{library_name}']['episode_nfo_failure'] += 1

                            except Exception as e:
                                logger.verbose(f'[FAILURE] Episode NFO for {media_title} failed: {e}')
                                library_result[f'{library_name}']['episode_nfo_failure'] += 1

                        if export_poster:
                            poster_status = process_media('Poster', config, poster_path, library_type, meta_root, media_title, dry_run, force_overwrite)

                            if poster_status == 'success':
                                library_result[f'{library_name}']['poster_new'] += 1
                            elif poster_status == 'updated':
                                library_result[f'{library_name}']['poster_updated'] += 1
                            elif poster_status == 'skipped':
                                library_result[f'{library_name}']['poster_skipped'] += 1
                            elif poster_status == 'not_exist':
                                library_result[f'{library_name}']['poster_failure'] += 1
                            elif poster_status == 'failure':
                                library_result[f'{library_name}']['poster_failure'] += 1

                        if export_fanart:
                            fanart_status = process_media('Art', config, fanart_path, library_type, meta_root, media_title, dry_run, force_overwrite)

                            if fanart_status == 'success':
                                library_result[f'{library_name}']['art_new'] += 1
                            elif fanart_status == 'updated':
                                library_result[f'{library_name}']['art_updated'] += 1
                            elif fanart_status == 'skipped':
                                library_result[f'{library_name}']['art_skipped'] += 1
                            elif fanart_status == 'not_exist':
                                library_result[f'{library_name}']['art_failure'] += 1
                            elif fanart_status == 'failure':
                                library_result[f'{library_name}']['art_failure'] += 1

                        if export_season_poster and library_type == 'tvshow':
                            try:
                                season_url = urljoin(f'{meta_url}/', 'children')
                                season_response = requests.get(season_url, headers=headers)
                                
                                if season_response.status_code == 200:
                                    season_root = ET.fromstring(season_response.content).findall('Directory')
                                    for season_dir in season_root:
                                        if not season_dir.get('title') or season_dir.get('title') == 'All episodes':
                                            continue

                                        season_title = season_dir.get('title').lower().replace(' ', '')
                                        season_path = os.path.join(media_path, f'{season_title}-cover.jpg' if season_title != 'specials' and season_title != 'miniseries' else f"season1-cover.jpg")
                                        
                                        if season_title == 'specials':
                                            season_path = os.path.join(media_path, f'season-{season_title}-cover.jpg')

                                        season_poster_status = process_media('Season Poster', config, fanart_path, library_type, meta_root, media_title, dry_run, force_overwrite, season_dir, season_path)

                                        if season_poster_status == 'success':
                                            library_result[f'{library_name}']['season_poster_new'] += 1
                                        elif season_poster_status == 'updated':
                                            library_result[f'{library_name}']['season_poster_updated'] += 1
                                        elif season_poster_status == 'skipped':
                                            library_result[f'{library_name}']['season_poster_skipped'] += 1
                                        elif season_poster_status == 'not_exist':
                                            library_result[f'{library_name}']['season_poster_failure'] += 1
                                        elif season_poster_status == 'failure':
                                            library_result[f'{library_name}']['season_poster_failure'] += 1

                            except Exception as e:
                                logger.info(f'[FAILURE] Season poster for {media_title} failed: {e}')
                                library_result[f'{library.get("name")}']['season_poster_failure'] += 1

                bar()

            library_result[f'{library.get("name")}']['finish'] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not dry_run:
        for key in library_result.keys():
            print(f'\n============================ {key.upper()} PROCESSING SUMMARY ============================')
            print(f'''
Start       : {library_result[f'{library.get("name")}']['start']}
Finished    : {library_result[f'{library.get("name")}']['finish']}''')

            if export_nfo and not dry_run:
                print(f'''
NFO Files
  - Added     : {library_result[key]['nfo_new']} NFO(s)
  - Updated   : {library_result[key]['nfo_updated']} NFO(s)
  - Skipped   : {library_result[key]['nfo_skipped']} NFO(s)
  - Failed    : {library_result[key]['nfo_failure']} NFO(s)''')
                    
            if export_poster and not dry_run:
                print(f'''
Poster Images
  - Added     : {library_result[key]['poster_new']} poster(s)
  - Updated   : {library_result[key]['poster_updated']} poster(s)
  - Skipped   : {library_result[key]['poster_skipped']} poster(s)
  - Failed    : {library_result[key]['poster_failure']} poster(s)''')
                    
            if export_fanart and not dry_run:
                print(f'''
Art Images
  - Added     : {library_result[key]['art_new']} art(s)
  - Updated   : {library_result[key]['art_updated']} art(s)
  - Skipped   : {library_result[key]['art_skipped']} art(s)
  - Failed    : {library_result[key]['art_failure']} art(s)''')
                    
            if export_season_poster and not dry_run:
                print(f'''
Season Poster Images
  - Added     : {library_result[key]['season_poster_new']} season poster(s)
  - Updated   : {library_result[key]['season_poster_updated']} season poster(s)
  - Skipped   : {library_result[key]['season_poster_skipped']} season poster(s)
  - Failed    : {library_result[key]['season_poster_failure']} season poster(s)''')
                    
            if export_episode_nfo and not dry_run:
                print(f'''
Episode NFO Files
  - Added     : {library_result[key]['episode_nfo_new']} episode NFO(s)
  - Updated   : {library_result[key]['episode_nfo_updated']} episode NFO(s)
  - Skipped   : {library_result[key]['episode_nfo_skipped']} episode NFO(s)
  - Failed    : {library_result[key]['episode_nfo_failure']} episode NFO(s)''')
                
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

    args = parser.parse_args()
    log_level = args.log_level

    ensure_files_exist() 
    logger, log_name = set_logger(log_level)
    main(args, log_name)