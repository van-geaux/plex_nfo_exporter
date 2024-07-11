from PIL import Image
from io import BytesIO

import os
import datetime
import requests
import xml.etree.ElementTree as ET
import yaml

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

def download_image(url, save_path):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            image.save(save_path)
        else:
            print(f"[ERROR] Failed to retrieve image. HTTP Status Code: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")

def write_nfo(config, nfo_path, library_type, meta_root, media_title):
    try:
        with open(nfo_path, 'w', encoding='utf-8') as nfo:
            nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            nfo.write(f'<{library_type} xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')

            if config['agent_id'] and meta_root.get('guid'):
                guid = meta_root.get('guid')
                if 'themoviedb' in guid:
                    nfo.write(f'  <tmdbid>{guid[guid.rfind("//")+2:(guid.rfind("?") if "?" in guid else len(guid))]}</tmdbid>\n')

                if 'anidb' in guid:
                    nfo.write(f'  <anidbid>{guid[guid.rfind("-")+1:(guid.rfind("?") if "?" in guid else len(guid))]}</anidbid>\n')

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

            if config['ratings'] and meta_root.findall('Country'):
                nfo.write('  <ratings>\n')
                for rating in meta_root.findall('Rating'):
                    nfo.write(f'    <{rating.get("type")}>{rating.get("value")}</{rating.get("type")}>\n')
                nfo.write('  </ratings>\n')

            if config['directors'] and meta_root.findall('Director'):
                for director in meta_root.findall('Director'):
                    nfo.write(f'  <director thumb={director.get("thumb")}>{director.get("tag")}</director>\n')

            if config['writers'] and meta_root.findall('Writer'):
                for writer in meta_root.findall('Writer'):
                    nfo.write(f'  <writer thumb={writer.get("thumb")}>{writer.get("tag")}</writer>\n')

            if config['roles'] and meta_root.findall('Role'):
                for role in meta_root.findall('Role'):
                    nfo.write(f'  <actor thumb={role.get("thumb")} role={role.get("role")}>{role.get("tag")}</actor>\n')

            nfo.write(f'</{library_type}>')

            print(f'[SUCCESS] NFO for {media_title} successfully saved to {nfo_path}')

    except Exception as e:
        print(f'[FAILURE] Failed to write NFO for {media_title} due to {e}')

def main():
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)

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
                                    write_nfo(config, nfo_path, library_type, meta_root, media_title)
                                else:
                                    print(f'[SKIPPED] NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                            else:
                                write_nfo(config, nfo_path, library_type, meta_root, media_title)

                        if config['export_poster']:
                            try:
                                url = baseurl+meta_root.get('thumb')
                                if os.path.exists(poster_path):
                                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(poster_path))
                                    time_difference = current_time - file_mod_time
                                                        
                                    if time_difference.days < days_difference:
                                        download_image(url, poster_path)
                                        print(f'[SUCCESS] Poster for {media_title} successfully saved to {poster_path}')

                                    else:
                                        print(f'[SKIPPED] Poster for {media_title} skipped because there is poster file older than {days_difference} days')
                                else:
                                    download_image(url, poster_path)
                                    print(f'[SUCCESS] Poster for {media_title} successfully saved to {poster_path}')
                            except:
                                print(f'[FAILURE] Poster for {media_title} not found')

                        if config['export_poster']:
                            try:
                                url = baseurl+meta_root.get('art')
                                if os.path.exists(fanart_path):
                                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(fanart_path))
                                    time_difference = current_time - file_mod_time
                                                        
                                    if time_difference.days < days_difference:
                                        download_image(url, fanart_path)
                                        print(f'[SUCCESS] Art for {media_title} successfully saved to {fanart_path}')

                                    else:
                                        print(f'[SKIPPED] Art for {media_title} skipped because there is fanart file older than {days_difference} days')
                                else:
                                    download_image(url, fanart_path)
                                    print(f'[SUCCESS] Art for {media_title} successfully saved to {fanart_path}')
                            except:
                                print(f'[FAILURE] Art for {media_title} not found')

if __name__ == '__main__':    
    main()