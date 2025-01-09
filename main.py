#!/usr/bin/env python3

from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO
from pathlib import Path
from PIL import Image
from urllib.parse import urljoin

import logging
import os
import re
import requests
import sys
import xml.etree.ElementTree as ET
import yaml

def set_logger():
    if not os.path.exists('/logs'):
        os.makedirs('/logs')

    files = list(Path('logs/').iterdir())
    files = [f for f in files if f.is_file()]
    if len(files) > 10:
        files.sort(key=lambda f: f.stat().st_mtime)
        oldest_file = files[0]
        os.remove(oldest_file)
        print(f"Deleted: {oldest_file}")
    else:
        pass

    with open('config.yml', 'r') as file:
        config_content = file.read()
        config = yaml.safe_load(config_content)
    try:
        log_level_str = config.get('log_level').upper()
    except:
        log_level_str = 'other'

    log_level_console = getattr(logging, log_level_str, logging.INFO)
    log_level_file = getattr(logging, log_level_str, logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(f"logs/app-{str(datetime.now().date()).replace('-', '')}.log", encoding='utf-8')

    console_handler.setLevel(log_level_console)
    file_handler.setLevel(log_level_file)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

def ensure_env_file_exists() -> None:
    """
    Create .env with placeholder if not exist
    """
    default_content = "PLEX_URL='http://192.168.1.2:32400'\nPLEX_TOKEN='very-long-token'"
    file_path = '.env'
    if not os.path.exists(file_path):
        with open(file_path, 'w') as env_file:
            env_file.write(default_content)
        print(f"{file_path} created, if you haven't put your Plex's url and token in the config then please put them in the .env")
        sys.exit()
    else:
        print(f"{file_path} already exists.")

def ensure_config_file_exists() -> None:
    default_content = """# config.yml

# change plex url and token here
Base URL: ${PLEX_URL} # i.e http://192.168.1.1:32400 or if reverse proxied i.e. https://plex.yourdomain.tld or fill them in .env file and let this part be
Token: ${PLEX_TOKEN} # how to get token https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/ or fill them in .env file and let this part be

# input the libraries you want to export NFO/poster/fanart from
# if the library type is music, input it TWICE. This is due to plex have 2 different roots for music library, each for artist and albums
Libraries: ['Movies', 'TV Shows', 'Anime', 'Music', 'Music']

# minimum age (days) for NFO/poster/art not to be replaced
# i.e setting 15 means any NFO/poster/art file older than 15 days will not be replaced
# !!!!!!! set lower than how often you plan to run the script !!!!!!!
days_difference: 4

# true/false choose what to export
Export NFO: true
Export poster: false
Export fanart: false
Export season poster: false
Export episode NFO: false

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

# change this to true only if you put all your media files inside one media folder
# this option will put media title on files, i.e. movietitle.nfo instead of movie.nfo and movietitle_poster.jpg instead of poster.jpg
Unified Media Path: false

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
"""
    file_path = 'config.yml'
    if not os.path.exists(file_path):
        with open(file_path, 'w') as env_file:
            env_file.write(default_content)
        print(f"{file_path} created, if you haven't set your config then please put them in the config.yml")
        sys.exit()
    else:
        print(f"{file_path} already exists.")

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


def get_library_details(plex_url:str, headers:dict, library_names:list) -> list:
    """
    Get details about available libraries
    """
    if plex_url:
        url = urljoin(plex_url, '/library/sections')
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            root = ET.fromstring(response.content)

            library_details = []

            for search_library in library_names:
                directories = root.findall('Directory')
                for library in directories:
                    if library.attrib.get('title') == search_library:
                        library_details.append({"key": library.attrib.get('key'), "type": library.attrib.get('type')})

    return library_details

def download_image(url:str, headers:dict, save_path:str) -> None:
    """
    Download image from provided url, also convert RGBA to RGB
    """
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))

            if image.mode == "RGBA":
                image = image.convert("RGB")

            image.save(save_path)
        else:
            logger.error(f"Failed to retrieve image. HTTP Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

def write_nfo(config:dict, nfo_path:str, library_type:str, meta_root:str, media_title:str) -> None:
    try:
        with open(nfo_path, 'w', encoding='utf-8') as nfo:
            nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            nfo.write(f'<{library_type} xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')
                
            if config['agent_id'] and meta_root.get('guid'):
                guid = meta_root.get('guid')
                if 'themoviedb' in guid:
                    nfo.write(f'  <tmdbid>{guid[guid.rfind("//")+2:(guid.rfind("?") if "?" in guid else len(guid))]}</tmdbid>\n')

                if 'agents.hama' in guid:
                    nfo.write(f'  <{guid[guid.rfind("//")+2:guid.rfind("-")]}id>{guid[guid.rfind("-")+1:(guid.rfind("?") if "?" in guid else len(guid))]}</{guid[guid.rfind("//")+2:guid.rfind("-")]}id>\n')

                for agent in meta_root.findall('Guid'):
                    agent_name = agent.get('id')[:agent.get('id').rfind(':')]+'id'
                    agent_id = agent.get('id')[agent.get('id').find('//')+2:]
                    nfo.write(f'  <{agent_name}>{agent_id}</{agent_name}>\n')
                                                    
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

            logger.info(f'[SUCCESS] NFO for {media_title} successfully saved to {nfo_path}')

    except Exception as e:
        logger.error(f'[FAILURE] Failed to write NFO for {media_title} due to {e}')

def write_episode_nfo(episode_nfo_path, episode_root, media_title):
    try:
        with open(episode_nfo_path, 'w', encoding='utf-8') as nfo:
            nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            nfo.write('<episodedetails xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')

            if episode_root.findall('Guid'):
                for guid in episode_root.findall('Guid'):
                    if 'imdb' in guid.get('id'):
                        utype = 'imdb'
                    elif 'tmdb' in guid.get('id'):
                        utype = 'tmdb'
                    elif 'tvdb' in guid.get('id'):
                        utype = 'tvdb'
                                            
                    nfo.write(f'  <uniqueid type="{utype}">{guid.get("id")[guid.get("id").rfind("/")+1:]}</uniqueid>\n')

            if episode_root.get('parentIndex'):
                nfo.write(f'  <season>{episode_root.get("parentIndex")}</season>\n')

            if episode_root.get('index'):
                nfo.write(f'  <episode>{episode_root.get("index")}</episode>\n')

            if episode_root.get('title'):
                nfo.write(f'  <title>{episode_root.get("title")}</title>\n')

            if episode_root.get('summary'):
                nfo.write(f'  <plot>{episode_root.get("summary")}</plot>\n')

            if episode_root.get('contentRating'):
                nfo.write(f'  <mpaa>{episode_root.get("contentRating")}</mpaa>\n')

            if episode_root.get('rating'):
                nfo.write(f'  <userrating>{episode_root.get("rating")}</userrating>\n')

            if episode_root.get('originallyAvailableAt'):
                nfo.write(f'  <aired>{episode_root.get("originallyAvailableAt")}</aired>\n')

            nfo.write('</episodedetails>')

            logger.info(f'[SUCCESS] Episodic NFO for {media_title} successfully saved to {episode_nfo_path}')

    except Exception as e:
        logger.error(f'[FAILURE] Failed to write episodic NFO for {media_title} due to {e}')

def sanitize_filename(filename):
    filename = filename.replace(": ", " - ").replace(":", "-").replace("/", "-").replace("\\", "-")
    filename = filename.replace("*", "-").replace("?", "").replace('"', "")
    filename = filename.replace("<", "-").replace(">", "-").replace("|", "-")
    filename = filename.rstrip('.')
    return filename

def main():
    load_dotenv()
    yaml.SafeLoader.add_constructor('!env_var', env_var_constructor)

    with open('config.yml', 'r') as file:
        config_content = file.read()
        config_content = re.sub(r'\$\{(\w+)\}', lambda match: os.getenv(match.group(1), ''), config_content)
        config = yaml.safe_load(config_content)

    baseurl = config['Base URL']
    token = config['Token']

    library_names = config['Libraries']
    days_difference = config['days_difference']
    path_mapping = config['Path mapping']

    headers = {'X-Plex-Token': token}
    library_details = get_library_details(baseurl, headers, library_names)

    current_time = datetime.now()
    check_music = 0

    for library in library_details:
        if baseurl:
            if check_music == 0:
                url = urljoin(baseurl, f'/library/sections/{library.get("key")}/all')
            else:
                url = urljoin(baseurl, f'/library/sections/{library.get("key")}/albums')

            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                if library.get('type') == 'movie':
                    library_type = 'movie'
                    library_root = 'Video'
                elif library.get('type') == 'show':
                    library_type = 'tvshow'
                    library_root = 'Directory'
                elif library.get('type') and check_music == 0:
                    library_type = 'artist'
                    library_root = 'Directory'
                    check_music += 1
                elif check_music == 1:
                    library_type = 'albums'
                    library_root = 'Directory'
                    check_music -= 1
                    
                library_contents = root.findall(library_root)
                for content in library_contents:
                    ratingkey = content.get('ratingKey')  
                    meta_url = urljoin(baseurl, f'/library/metadata/{ratingkey}')  
                    meta_response = requests.get(meta_url, headers=headers)
                    if meta_response.status_code == 200:
                        meta_root = ET.fromstring(meta_response.content).find(library_root)

                        media_title = meta_root.get('title')
                        if library_type == 'movie':
                            media_path = meta_root.find('Media').find('Part').get('file')
                            media_path = media_path[:media_path.rfind("/")]+"/"
                            for path_list in path_mapping:
                                media_path = media_path.replace(path_list.get('plex'), path_list.get('local'))
                        elif library_type == 'tvshow':
                            media_path = meta_root.find('Location').get('path')+'/'
                            for path_list in path_mapping:
                                media_path = media_path.replace(path_list.get('plex'), path_list.get('local'))
                        elif library_type == 'artist':
                            media_path = meta_root.find('Location').get('path')+'/'
                            for path_list in path_mapping:
                                media_path = media_path.replace(path_list.get('plex'), path_list.get('local'))
                        elif library_type == 'albums':
                            track_url = urljoin(meta_url, '/children')
                            track_response = requests.get(track_url, headers=headers)
                            track0_path = ET.fromstring(track_response.content).findall('Track')[0].find('Media').find('Part').get('file')
                            media_path = track0_path[:track0_path.rfind('/')]+'/'
                            for path_list in path_mapping:
                                media_path = media_path.replace(path_list.get('plex'), path_list.get('local'))
                        
                        
                        if library_type == 'artist':
                            nfo_path = os.path.join(media_path, 'artist.nfo')
                        elif library_type == 'albums':
                            nfo_path = os.path.join(media_path, 'album.nfo')
                        elif config.get('Unified Media Path'):
                            sanitized_title = sanitize_filename(media_title)
                            nfo_path = os.path.join(media_path, f'{sanitized_title}.nfo')
                        else:
                            nfo_path = os.path.join(media_path, f'{library_type}.nfo')

                        if config.get('Unified Media Path'):
                            poster_path = os.path.join(media_path, f'{sanitized_title}_poster.jpg')
                            fanart_path = os.path.join(media_path, f'{sanitized_title}_fanart.jpg')
                        else:
                            poster_path = os.path.join(media_path, 'poster.jpg')
                            fanart_path = os.path.join(media_path, 'fanart.jpg')

                        if config['Export NFO']:
                            if os.path.exists(nfo_path):
                                file_mod_time = datetime.fromtimestamp(os.path.getmtime(nfo_path))
                                time_difference = current_time - file_mod_time

                                if time_difference.days < days_difference:
                                    write_nfo(config, nfo_path, library_type, meta_root, media_title)
                                else:
                                    logger.info(f'[SKIPPED] NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                            else:
                                write_nfo(config, nfo_path, library_type, meta_root, media_title)

                        if config['Export episode NFO'] and (library_type == 'tvshow'):
                            try:
                                meta_season = urljoin(meta_url, '/children')
                                meta_season_response = requests.get(meta_season, headers=headers)
                                if meta_season_response.status_code == 200:
                                    meta_season_root = ET.fromstring(meta_season_response.content).findall('Directory')

                                    for season in meta_season_root[1:]:
                                        season_key = season.get('ratingKey')

                                        season_url = urljoin(meta_url[:meta_url.rfind('/')], f'{season_key}/children')
                                        season_url_response = requests.get(season_url, headers=headers)
                                        if season_url_response.status_code == 200:
                                            season_root = ET.fromstring(season_url_response.content).findall('Video')

                                            for episode in season_root:
                                                episode_key = episode.get('ratingKey')

                                                episode_url = urljoin(meta_url[:meta_url.rfind('/')], episode_key)
                                                episode_url_response = requests.get(episode_url, headers=headers)
                                                episode_root = ET.fromstring(episode_url_response.content).find('Video')

                                                episode_path = episode_root.find('Media').find('Part').get('file')
                                                episode_nfo_path = episode_path[:episode_path.rfind('.')] + '.nfo'

                                                for path_list in path_mapping:
                                                    episode_nfo_path = episode_nfo_path.replace(path_list.get('plex'), path_list.get('local'))

                                                if os.path.exists(episode_nfo_path):
                                                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(episode_nfo_path))
                                                    time_difference = current_time - file_mod_time

                                                    if time_difference.days < days_difference:
                                                        write_episode_nfo(episode_nfo_path, episode_root, media_title)
                                                    else:
                                                        logger.info(f'[SKIPPED] Episodic NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                                                else:
                                                    write_episode_nfo(episode_nfo_path, episode_root, media_title)

                            except Exception as e:
                                logger.error(f'[FAILURE] Failed to write episodic NFO for {media_title} due to {e}')

                        if config['Export poster']:
                            try:
                                url = urljoin(baseurl, meta_root.get('thumb'))
                                if os.path.exists(poster_path):
                                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(poster_path))
                                    time_difference = current_time - file_mod_time
                                                        
                                    if time_difference.days < days_difference:
                                        download_image(url, headers, poster_path)
                                        logger.info(f'[SUCCESS] Poster for {media_title} successfully saved to {poster_path}')

                                    else:
                                        logger.info(f'[SKIPPED] Poster for {media_title} skipped because there is poster file older than {days_difference} days')
                                else:
                                    download_image(url, headers, poster_path)
                                    logger.info(f'[SUCCESS] Poster for {media_title} successfully saved to {poster_path}')
                            except:
                                logger.info(f'[FAILURE] Poster for {media_title} not found')

                        if config['Export fanart']:
                            try:
                                url = urljoin(baseurl, meta_root.get('art'))
                                if os.path.exists(fanart_path):
                                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(fanart_path))
                                    time_difference = current_time - file_mod_time
                                                        
                                    if time_difference.days < days_difference:
                                        download_image(url, headers, fanart_path)
                                        logger.info(f'[SUCCESS] Art for {media_title} successfully saved to {fanart_path}')

                                    else:
                                        logger.info(f'[SKIPPED] Art for {media_title} skipped because there is fanart file older than {days_difference} days')
                                else:
                                    download_image(url, headers, fanart_path)
                                    logger.info(f'[SUCCESS] Art for {media_title} successfully saved to {fanart_path}')
                            except:
                                logger.info(f'[FAILURE] Art for {media_title} not found')

                        if config['Export season poster'] and library_type == 'tvshow':
                            try:
                                season_url = urljoin(f'{meta_url}/', 'children')
                                season_response = requests.get(season_url, headers=headers)
                                if season_response.status_code == 200:
                                    season_root = ET.fromstring(season_response.content).findall('Directory')
                                    for season_dir in season_root:
                                        if not season_dir.get('title') or season_dir.get('title') == 'All episodes':
                                            continue

                                        season_title = season_dir.get('title').lower().replace(' ', '')
                                        if season_title == 'Specials':
                                            season_path = os.path.join(media_path, f'season-{season_title}-cover.jpg')
                                        elif season_title == 'Miniseries':
                                            season_path = os.path.join(media_path, f"season1-cover.jpg")
                                        else:
                                            season_path = os.path.join(media_path, f"{season_title}-cover.jpg")
                                        
                                        url = urljoin(baseurl, season_dir.get('thumb'))
                                        if os.path.exists(season_path):
                                            file_mod_time = datetime.fromtimestamp(os.path.getmtime(season_path))
                                            time_difference = current_time - file_mod_time

                                            if time_difference.days < days_difference:
                                                download_image(url, headers, season_path)
                                                logger.info(f'[SUCCESS] {season_title} poster for {media_title} successfully saved to {season_path}')

                                            else:
                                                logger.info(f'[SKIPPED] {season_title} poster skipped because there is fanart file older than {days_difference} days')

                                        else:
                                            download_image(url, headers, season_path)
                                            logger.info(f'[SUCCESS] {season_title} poster for {media_title} successfully saved to {season_path}')

                            except:
                                logger.info(f'[FAILURE] Season poster for {media_title} not found')

if __name__ == '__main__':
    ensure_config_file_exists()
    ensure_env_file_exists()  
    logger = set_logger()
    main()