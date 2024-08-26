from datetime import datetime
from pathlib import Path

import logging
import os
import shutil
import yaml

# if logs folder not exist then create it


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
