# Plex NFO Exporter

**Plex NFO Exporter** is a script that extracts metadata, posters, and background art from Plex and generates compatible files for use with other media servers like Jellyfin.  

---

## Features
- Extract media metadata from Plex into `.nfo` files.
- Export active poster images as `poster.jpg`.
- Export active background art as `fanart.jpg`.
- Save files in the media directory for easy use with other media servers.
- **Does not refresh Plex library metadata** during the export process.
- Flexible options:
  - Choose what metadata to export (e.g., title, tagline, plot, year, etc.).
  - Select specific libraries to process.
  - Export all metadata from Plex if needed.
- Support for path mapping between separate Plex and library servers.
- Compatible with **movies**, **TV shows**, and **music** libraries.
- Supports Plex's latest movie and TV agents, as well as [Hama agent](https://github.com/ZeroQI/Hama.bundle).  

---

## How to Use

1. **Download and Prepare the Script**  
   Clone or download the repository, ensuring the following files are included:  
   - `config.yml` (will create if not exists)
   - `.env` (will create if not exists)
   - `main.py`  
   - `requirements.txt`  

2. **Configure the Script**  
   Edit `config.yml` and `.env` to include your desired settings and credentials.

3. **Install Python**  
   Install Python (tested with Python 3.9–3.11).  

4. **Set Up the Environment**  
   Open a terminal and navigate to the script directory:  
   ```bash
   cd /your_directory/plex_nfo_exporter
   ```

   (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv env  
   env\Scripts\activate    # Windows  
   source env/bin/activate # macOS/Linux
   ```

5. **Install Dependencies**
   Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

6. **Run the Script**
   Execute the script:
   ```bash
   python main.py
   ```
   
## Features and Limitations

1. **Supported Plex Agents**
   - Compatible with Plex's new TV and movie agents.
   - Detects Hama agent and other agents to set metadata source IDs accordingly.

2. **Metadata Export Options**
   - Choose specific metadata fields to export.
   - Defaults include title, tagline, plot, year, and metadata agent IDs.

3. **File Organization**
   - Saves .nfo files as movie.nfo, tvshow.nfo, artist.nfo, album.nfo.
   - Exports active poster and fanart images as poster.jpg and fanart.jpg.

4. **Sync Across Servers**
   - Ensures that Plex and Jellyfin display the same library metadata, images, and media names.

5. **Docker Image**
   - Docker integration with cron jobs is planned but not yet fully implemented.

## Background

- About Me:
   I'm not a developer by trade, but I manage Plex and Jellyfin to enjoy both convenience and flexibility.
   My primary library is anime in Plex using the Hama agent with romaji names.

- Why This Script?
   I needed a tool to sync Plex and Jellyfin libraries, especially for anime with custom posters and art.
   Existing tools either require a full library refresh (e.g., Lambda) or work in reverse (e.g., XBMC Importer).

- Kometa Integration:
   I use Kometa to beautify posters, which works perfectly with this script.

## Future Plans

- Add Docker support with cron job automation.
- Enhance compatibility with more media servers.

## Contributions & Feedback

Feel free to open an issue or submit a pull request for improvements or feature requests.