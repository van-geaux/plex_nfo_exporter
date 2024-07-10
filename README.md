# What this do
1. Extract media info from Plex and put them into an NFO file
2. Extract active poster image from Plex
3. Extract active art (background art) from Plex
4. Put all of them in media directory as tvshow/movie.nfo, poster.jpg, and fanart.jpg to be use on other media server i.e. Jellyfin
5. Do it all without refreshing library metadata
6. Option to choose what to export
7. Option to choose which library to process
8. Support separated plex and library servers with path mapping

# How to use
1. Download the repo and put it anywhere you like
2. Make sure there are at least config.yml, main.py, and requirements.txt files in it
3. Fill in the details in config.yml
4. Install python on your system if haven't already (I use python 3.12 but I've confirmed it works with 3.8 also)
5. CD to the script directory
   ```cd /your_directory/plex_nfo_exporter```
6. (optional) Create a virtual environment
   ```python -m venv env``` 
8. (optional) Activate virtual environment
   ```env\Scripts\activate``` for windows or ```source env/bin/activate```
10. Install dependencies
    ```pip install -r requirements.txt``` 
12. Run the script
    ```python main.py```

# Features and limitations
1. It support the new plex's tv and movie agent and will set tvdb and imdb respectively for main identifier in NFO file
2. It will also detect [Hama agent](https://github.com/ZeroQI/Hama.bundle) and other agents and set their metadata source ids accordingly
3. The NFO file will only consist of what I think is the bare neccessity: metadata source id, title, summary, year
4. The NFO file only consist of that because when I tested it in jellyfin, it pull all other necessary data from metadata source anyway and still use whatever in the NFO as priority
5. For a mixed (tv and movie) library, it will save the NFO as tvshow.nfo
6. With the same reasoning, the images pulled as poster.jpg and fanart.jpg are the current active images in plex
7. That way plex and jellyfin should show practically the same library (in image and media names)
8. I tried to make a docker image with cron job for better convenience but still fails, I will learn more and hope I can do it in the near future

# A little background
1. I'm not a developer by trade
2. I run both Plex and Jellyfin because Plex is convenient and Jellyfin is flexible
3. My main library is anime in Plex using Hama agent using romaji names
4. I also use [Kometa](https://kometa.wiki/en/latest/) to beautify the posters
5. My library in plex and jellyfin looks very different because of that
6. I've searched a while for tools/scripts to export NFO and images from plex to be used in jellyfin but
7. [Lambda](https://github.com/ZeroQI/Lambda.bundle) needs to refresh the whole library the first time and doesn't work well with Kometa because for new media it will export whatever poster and art pulled from metadata because Kometa hasn't run
8. [XBMC importer](https://github.com/gboudreau/XBMCnfoMoviesImporter.bundle) only import things from NFO to plex AFAIK
9. [Googled it](https://www.google.com/search?q=github+plex+nfo+export&sca_esv=71668abf73626b35&sca_upv=1&sxsrf=ADLYWIK0jN_WTI2xC-noSKYKXW4ISmPJ4w%3A1720488444387&ei=_JGMZvywF5-gnesP6pMt) but I didn't find what I need
