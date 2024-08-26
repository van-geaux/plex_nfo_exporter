from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO
from pathlib import Path
from PIL import Image

import datetime
import logging
import os
import re
import requests
import xml.etree.ElementTree as ET
import yaml

# if logs folder not exist then create it
if not os.path.exists('logs/'):
    os.makedirs('logs/')

# check and delete oldest log
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

def env_var_constructor(loader, node):
    value = loader.construct_scalar(node)
    pattern = re.compile(r'\$\{(\w+)\}')
    match = pattern.findall(value)
    for var in match:
        value = value.replace(f'${{{var}}}', os.getenv(var, ''))
    return value

def get_library_details(plex_url,headers, library_names):
    if plex_url:
        url = f'{plex_url}/library/sections'
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

def download_image(url, headers, save_path):
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            image.save(save_path)
        else:
            logger.error(f"Failed to retrieve image. HTTP Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

def write_nfo(config, nfo_path, library_type, meta_root, media_title, meta_url, headers):
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
                nfo.write(f'  <mpaa>{episode_root.get('contentRating')}</mpaa>\n')

            if episode_root.get('rating'):
                nfo.write(f'  <userrating>{episode_root.get('rating')}</userrating>\n')

            if episode_root.get('originallyAvailableAt'):
                nfo.write(f'  <aired>{episode_root.get('originallyAvailableAt')}</aired>\n')

            nfo.write('</episodedetails>')

            logger.info(f'[SUCCESS] Episodic NFO for {media_title} successfully saved to {episode_nfo_path}')

    except Exception as e:
        logger.error(f'[FAILURE] Failed to write episodic NFO for {media_title} due to {e}')

def main():
    load_dotenv()
    yaml.SafeLoader.add_constructor('!env_var', env_var_constructor)

    with open('config.yml', 'r') as file:
        config_content = file.read()
        config_content = re.sub(r'\$\{(\w+)\}', lambda match: os.getenv(match.group(1), ''), config_content)
        config = yaml.safe_load(config_content)

    baseurl = config['baseurl']
    token = config['token']

    library_names = config['library_names']
    days_difference = config['days_difference']
    path_mapping = config['path_mapping']

    headers = {'X-Plex-Token': token}
    library_details = get_library_details(baseurl,headers, library_names)

    current_time = datetime.datetime.now()

    for library in library_details:
        if baseurl:
            url = f'{baseurl}/library/sections/{library.get("key")}/all'
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                if library.get('type') == 'movie':
                    library_type = 'movie'
                    library_root = 'Video'
                elif library.get('type') == 'show':
                    library_type = 'tvshow'
                    library_root = 'Directory'
                    
                library_contents = root.findall(library_root)
                for content in library_contents:
                    ratingkey = content.get('ratingKey')
                    meta_url = f'{baseurl}/library/metadata/{ratingkey}'
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
                                
                        nfo_path = media_path + f'{library_type}.nfo'
                        poster_path = media_path + 'poster.jpg'
                        fanart_path = media_path + 'fanart.jpg'

                        if config['export_nfo']:
                            if os.path.exists(nfo_path):
                                file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(nfo_path))
                                time_difference = current_time - file_mod_time

                                if time_difference.days < days_difference:
                                    write_nfo(config, nfo_path, library_type, meta_root, media_title, meta_url, headers)
                                else:
                                    logger.info(f'[SKIPPED] NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                            else:
                                write_nfo(config, nfo_path, library_type, meta_root, media_title, meta_url, headers)

                        if config['export_episode_nfo'] and (library_type == 'tvshow'):
                            try:
                                meta_season = meta_url + '/children'
                                meta_season_response = requests.get(meta_season, headers=headers)
                                if meta_season_response.status_code == 200:
                                    meta_season_root = ET.fromstring(meta_season_response.content).findall('Directory')

                                    for season in meta_season_root[1:]:
                                        season_key = season.get('ratingKey')

                                        season_url = meta_url[:meta_url.rfind('/')] + '/' + season_key + '/children'
                                        season_url_response = requests.get(season_url, headers=headers)
                                        if season_url_response.status_code == 200:
                                            season_root = ET.fromstring(season_url_response.content).findall('Video')

                                            for episode in season_root:
                                                episode_key = episode.get('ratingKey')

                                                episode_url = meta_url[:meta_url.rfind('/')] + '/' + episode_key
                                                episode_url_response = requests.get(episode_url, headers=headers)
                                                episode_root = ET.fromstring(episode_url_response.content).find('Video')

                                                episode_path = episode_root.find('Media').find('Part').get('file')
                                                episode_nfo_path = episode_path[:episode_path.rfind('.')] + '.nfo'

                                                for path_list in path_mapping:
                                                    episode_nfo_path = episode_nfo_path.replace(path_list.get('plex'), path_list.get('local'))

                                                if os.path.exists(episode_nfo_path):
                                                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(episode_nfo_path))
                                                    time_difference = current_time - file_mod_time

                                                    if time_difference.days < days_difference:
                                                        write_episode_nfo(episode_nfo_path, episode_root, media_title)
                                                    else:
                                                        logger.info(f'[SKIPPED] Episodic NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                                                else:
                                                    write_episode_nfo(episode_nfo_path, episode_root, media_title)

                            except Exception as e:
                                logger.error(f'[FAILURE] Failed to write episodic NFO for {media_title} due to {e}')

                        if config['export_poster']:
                            try:
                                url = baseurl+meta_root.get('thumb')
                                if os.path.exists(poster_path):
                                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(poster_path))
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

                        if config['export_fanart']:
                            try:
                                url = baseurl+meta_root.get('art')
                                if os.path.exists(fanart_path):
                                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(fanart_path))
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

if __name__ == '__main__':    
    main()