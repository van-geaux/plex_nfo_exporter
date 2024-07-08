from PIL import Image
from io import BytesIO
from plexapi.server import PlexServer

import os
import datetime
import requests
import yaml

with open('config.yml', 'r') as file:
    config = yaml.safe_load(file)

plex_root = config['plex_root']
baseurl = config['baseurl']
token = config['token']
plex = PlexServer(baseurl, token)

libraries_names = config['libraries_names']
days_difference = config['days_difference']
path_mapping = config['path_mapping']

current_time = datetime.datetime.now()

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

def write_nfo(title, nfo_path, library_type, media_title):
    with open(nfo_path, 'w', encoding='utf-8') as nfo:
        nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        nfo.write(f'<{library_type} xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')

        try:
            # for plex's own new agents
            if isinstance(title.guids, list) and len(title.guids) > 0:
                for guid in title.guids:
                    if library_type == 'tvshow':
                        if 'tvdb' not in guid.id:
                            continue
                        else:
                            nfo.write(f'  <uniqueid default="true" type="tvdb">{guid.id[guid.id.rfind("//")+2:]}</uniqueid>\n')
                            break
                    elif library_type == 'Movie':
                        if 'imdb' not in guid.id:
                            continue
                        else:
                            nfo.write(f'  <uniqueid default="true" type="imdb">{guid.id[guid.id.rfind("//")+2:]}</uniqueid>\n')
                            break
            # for other agents
            else:
                guid = title.guid
                if 'agents.hama' in guid:
                    nfo.write(f'  <uniqueid default="true" type="{guid[guid.rfind("//")+2:guid.rfind("-")]}">{guid[guid.rfind("-")+1:]}</uniqueid>\n')
                elif 'themoviedb' in title.guid:
                    nfo.write(f'  <uniqueid default="true" type="tmdb">{guid[guid.rfind("//")+2:]}</uniqueid>\n')
                elif 'tvdb' in title.guid:
                    nfo.write(f'  <uniqueid default="true" type="tvdb">{guid[guid.rfind("//")+2:]}</uniqueid>\n')
                elif 'imdb' in title.guid:
                    nfo.write(f'  <uniqueid default="true" type="imdb">{guid[guid.rfind("//")+2:]}</uniqueid>\n')
                elif 'anidb' in title.guid:
                    nfo.write(f'  <uniqueid default="true" type="anidb">{guid[guid.rfind("//")+2:]}</uniqueid>\n')
                else:
                    print(f'[FAILURE] No uniqueid detected for {media_title}')
                    pass

        except:
            print(f'[FAILURE] No uniqueid detected for {media_title}')
            pass

        try:
            nfo.write(f'  <title>{media_title}</title>\n')
        except:
            pass

        try:
            nfo.write(f'  <plot>{title.summary}</plot>\n')
        except:
            pass

        try:
            nfo.write(f'  <studio>{title.studio}</studio>\n')
        except:
            pass

        try:
            nfo.write(f'  <year>{title.year}</year>\n')
        except:
            pass

        try:
            nfo.write(f'  <mpaa>{title.contentRating}</mpaa>\n')
        except:
            pass

        try:
            nfo.write('  <ratings>\n')
            nfo.write('    <rating default="" max="10" Name="">\n')
            nfo.write(f'      <value>{title.rating}</value>\n')
        except:
            pass
        finally:
            nfo.write('    </rating>\n')
            nfo.write('  </ratings>\n')

        nfo.write(f'</{library_type}')

    print(f'[SUCCESS] NFO successfully saved to {nfo_path}')

def main():
    for name in libraries_names:
        for library in plex.library.sections():
            if name.lower() == library.title.lower():
                for title in library.search():
                    media_title = title.title

                    if 'Show' in type(library).__name__:
                        nfo_path = title.locations[0] + '/' + 'tvshow.nfo'
                        poster_path = title.locations[0] + '/' + 'poster.jpg'
                        fanart_path = title.locations[0] + '/' + 'fanart.jpg'
                        library_type = 'tvshow'
                    else:
                        nfo_path = title.locations[0][:title.locations[0].rfind('/')+1] + 'movie.nfo'
                        poster_path = title.locations[0][:title.locations[0].rfind('/')+1] + 'poster.jpg'
                        fanart_path = title.locations[0][:title.locations[0].rfind('/')+1] + 'fanart.jpg'
                        library_type = 'Movie'

                    for path_list in path_mapping:
                        nfo_path = nfo_path.replace(path_list.get('plex'), path_list.get('local'))
                        poster_path = poster_path.replace(path_list.get('plex'), path_list.get('local'))
                        fanart_path = fanart_path.replace(path_list.get('plex'), path_list.get('local'))

                    if os.path.exists(nfo_path):
                        file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(nfo_path))
                        time_difference = current_time - file_mod_time

                        if time_difference.days < days_difference:
                            write_nfo(title, nfo_path, library_type, media_title)
                        else:
                            print(f'[SKIPPED] NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                    else:
                        write_nfo(title, nfo_path, library_type, media_title)

                    try:
                        if os.path.exists(poster_path):
                            file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(poster_path))
                            time_difference = current_time - file_mod_time
                                        
                            if time_difference.days < days_difference:
                                url = title.posterUrl
                                download_image(url, poster_path)
                                print(f'[SUCCESS] Poster for {media_title} successfully saved to {poster_path}')

                            else:
                                print(f'[SKIPPED] Poster for {media_title} skipped because there is poster file older than {days_difference} days')
                        else:
                            url = title.posterUrl
                            download_image(url, poster_path)
                            print(f'[SUCCESS] Poster for {media_title} successfully saved to {poster_path}')
                    except:
                        print(f'[FAILURE] Poster for {media_title} not found')

                    try:
                        if os.path.exists(fanart_path):
                            file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(fanart_path))
                            time_difference = current_time - file_mod_time
                                        
                            if time_difference.days < days_difference:
                                url = title.artUrl
                                download_image(url, fanart_path)
                                print(f'[SUCCESS] Fanart successfully saved to {fanart_path}')

                            else:
                                print(f'[SKIPPED] Fanart for {media_title} skipped because there is fanart file older than {days_difference} days')
                        else:
                            url = title.artUrl
                            download_image(url, fanart_path)
                            print(f'[SUCCESS] Fanart for {media_title} successfully saved to {fanart_path}')
                    except:
                        print(f'[FAILURE] Fanart for {media_title} not found')

if __name__ == '__main__':    
    main()