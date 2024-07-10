from io import BytesIO
from PIL import Image
from plexapi.server import PlexServer

import os
import datetime
import requests
import yaml

with open('config.yml', 'r') as file:
    config = yaml.safe_load(file)

# plex_root = config['plex_root']
baseurl = config['baseurl']
token = config['token']
plex = PlexServer(baseurl, token)

library_names = config['library_names']
days_difference = config['days_difference']
path_mapping = config['path_mapping']

export_nfo = config['export_nfo']
export_poster = config['export_poster']
export_fanart = config['export_fanart']

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
    try:
        other_ids = []

        # get metadata agent id for plex's own new agents
        if title.guids:
            for guid in title.guids:
                if library_type == 'tvshow':
                    if 'imdb' in guid.id:
                        other_ids.append({'id_tag': 'imdb_id', 'id_number': guid.id[guid.id.rfind("//")+2:]})
                    elif 'tvdb' in guid.id:
                        id_number = guid.id[guid.id.rfind("//")+2:]
                        other_ids.append({'id_tag': 'tvdbid', 'id_number': guid.id[guid.id.rfind("//")+2:]})
                    else:
                        other_ids.append({'id_tag': guid.id[:guid.id.rfind(':')]+'id', 'id_number': guid.id[guid.id.rfind("//")+2:]})

                elif library_type == 'Movie':
                    if 'imdb' in guid.id:
                        id_number = guid.id[guid.id.rfind("//")+2:]
                        other_ids.append({'id_tag': 'imdbid', 'id_number': guid.id[guid.id.rfind("//")+2:]})
                    else:
                        other_ids.append({'id_tag': guid.id[:guid.id.rfind(':')]+'id', 'id_number': guid.id[guid.id.rfind("//")+2:]})
        # get metadata agent id for other metadata agents
        else:
            guid = title.guid

            if 'imdb:' in guid:
                other_ids.append({'id_tag': 'imdbid', 'id_number': guid[guid.rfind("//")+2:(guid.rfind("?") if "?" in guid else len(guid))]})
            elif 'tvdb:' in guid:
                other_ids.append({'id_tag': 'tvdbid', 'id_number': guid[guid.rfind("//")+2:(guid.rfind("?") if "?" in guid else len(guid))]})
            elif 'themoviedb:' in guid:
                other_ids.append({'id_tag': 'tmdbid', 'id_number': guid[guid.rfind("//")+2:(guid.rfind("?") if "?" in guid else len(guid))]})
            elif 'imdb' in guid:
                id_number = guid[guid.rfind("-")+1:(guid.rfind("?") if "?" in guid else len(guid))]
                other_ids.append({'id_tag': 'imdbid', 'id_number': id_number})
            elif 'tvdb' in guid:
                id_number = guid[guid.rfind("-")+1:(guid.rfind("?") if "?" in guid else len(guid))]
                other_ids.append({'id_tag': 'tvdb', 'id_number': id_number})
            elif 'anidb' in guid:
                other_ids.append({'id_tag': 'anidbid', 'id_number': guid[guid.rfind("-")+1:(guid.rfind("?") if "?" in guid else len(guid))]})
            elif 'themoviedb' in guid:
                other_ids.append({'id_tag': 'tmdbid', 'id_number': guid[guid.rfind("-")+1:(guid.rfind("?") if "?" in guid else len(guid))]})            

        with open(nfo_path, 'w', encoding='utf-8') as nfo:
            nfo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            nfo.write(f'<{library_type} xsi="http://www.w3.org/2001/XMLSchema-instance" xsd="http://www.w3.org/2001/XMLSchema">\n')

            try:
                nfo.write(f'  <id>{id_number}</id>\n')
            except:
                pass

            if other_ids:
                for other_id in other_ids:
                    nfo.write(f'  <{other_id.get("id_tag")}>{other_id.get("id_number")}</{other_id.get("id_tag")}>\n')

            nfo.write(f'  <title>{media_title}</title>\n')

            try:
                nfo.write(f'  <plot>{title.summary}</plot>\n')
            except:
                pass

            try:
                nfo.write(f'  <year>{title.year}</year>\n')
            except:
                pass

            # try:
            #     nfo.write(f'  <mpaa>{title.contentRating}</mpaa>\n')
            # except:
            #     pass

            nfo.write(f'</{library_type}>')

            print(f'[SUCCESS] NFO successfully saved to {nfo_path}')

    except Exception as e:
        print(f'[FAILURE] Failed to write NFO for {media_title} due to {e}')

def main():
    for name in library_names:
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

                    if export_nfo is True:
                        if os.path.exists(nfo_path):
                            file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(nfo_path))
                            time_difference = current_time - file_mod_time

                            if time_difference.days < days_difference:
                                write_nfo(title, nfo_path, library_type, media_title)
                            else:
                                print(f'[SKIPPED] NFO for {media_title} skipped because there is NFO file older than {days_difference} days')

                        else:
                            write_nfo(title, nfo_path, library_type, media_title)

                    if export_poster is True:
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

                    if export_fanart is True:
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