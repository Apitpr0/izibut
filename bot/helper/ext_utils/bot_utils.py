import psutil
import logging
import re
import threading
import time

from bot import download_dict, download_dict_lock

LOGGER = logging.getLogger(__name__)

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"


class MirrorStatus:
    STATUS_UPLOADING = "Uploading...📤"
    STATUS_DOWNLOADING = "Downloading...📥"
    STATUS_WAITING = "Queued⛓️"
    STATUS_FAILED = "Failed. Cleaning download😢"
    STATUS_CANCELLED = "Cancelled❌"
    STATUS_ARCHIVING = "Archiving📩"
    STATUS_EXTRACTING = "Extracting🤐"

PROGRESS_MAX_SIZE = 100 // 8
PROGRESS_INCOMPLETE = ['▣', '▣', '▣', '▣', '▣', '▣', '▣']

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = threading.Event()
        thread = threading.Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time.time() + self.interval
        while not self.stopEvent.wait(nextTime - time.time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()


def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'


def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor


def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in download_dict.values():
            status = dl.status()
            if status != MirrorStatus.STATUS_UPLOADING and status != MirrorStatus.STATUS_ARCHIVING\
                    and status != MirrorStatus.STATUS_EXTRACTING:
                if dl.gid() == gid:
                    return dl
    return None


def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    if total == 0:
        p = 0
    else:
        p = round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    cPart = p % 8 - 1
    p_str = '▣' * cFull
    if cPart >= 0:
        p_str += PROGRESS_INCOMPLETE[cPart]
    p_str += '▢' * (PROGRESS_MAX_SIZE - cFull)
    p_str = f"[{p_str}]"
    return p_str


def get_readable_message():
    with download_dict_lock:
        msg = ""
        for download in list(download_dict.values()):
            msg += f"<b>📇Filename:</b> <code>{download.name()}</code>" \
                   f"\n<b>📊Status:</b> <i>{download.status()}</i>"
            if download.status() != MirrorStatus.STATUS_ARCHIVING and download.status() != MirrorStatus.STATUS_EXTRACTING:
                msg += f"\n{get_progress_bar_string(download)} {download.progress()}" \
                       f"\n💾<b>Total Size:</b> <code>{download.size()}</code>" \
                       f"\n💨<b>Speed:</b> <code>{download.speed()}</code>" \
                       f"\n⏳<b>ETA:</b> <code>{download.eta()}</code>"
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if hasattr(download, 'is_torrent'):
                    msg += f"\n<b>🌱Seeders:</b> <code>{download.aria_download().num_seeders}</code>" \
                           f"\n<b>🙂Peers:</b> <code>{download.aria_download().connections}</code>"
                msg += f"\n<b>🌚GID:</b> <code>{download.gid()}</code>"
            # CPU
            cpufreq = psutil.cpu_freq()
            cpuUsage = psutil.cpu_percent()
            # RAM
            svmem = psutil.virtual_memory()
            mu = get_size(svmem.used)
            mp = svmem.percent
            msg += f"\n\n<b>📊Usage📊</b>" \
                   f"\n<b>😯CPU:</b> <code>{cpufreq.current:.2f}Mhz ({cpuUsage}%)</code>" \
                   f"\n<b>😋RAM:</b> <code>{mu} ({mp}%)</code>"
        return msg


def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result


def is_url(url: str):
    url = re.findall(URL_REGEX, url)
    if url:
        return True
    return False


def is_magnet(url: str):
    magnet = re.findall(MAGNET_REGEX, url)
    if magnet:
        return True
    return False


def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper
