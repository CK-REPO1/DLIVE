'''
**********************************************************
*@license GNU General Public License, version 3 (GPL-3.0)*
**********************************************************
'''

import re
import os
import sys
import json
import html
from urllib.parse import urlencode, quote, unquote, parse_qsl, quote_plus, urlparse
from datetime import datetime, timedelta, timezone
import time
import requests
import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
import xbmcaddon
import base64
import xml.etree.ElementTree as ET
import gzip
import io

addon_url = sys.argv[0]
addon_handle = int(sys.argv[1])
params = dict(parse_qsl(sys.argv[2][1:]))
addon = xbmcaddon.Addon(id='plugin.video.daddylivehd')

mode = addon.getSetting('mode')
baseurl = addon.getSetting('baseurl').strip()
schedule_path = addon.getSetting('schedule_path').strip()
schedule_url = baseurl + schedule_path
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
FANART = addon.getAddonInfo('fanart')
ICON = addon.getAddonInfo('icon')

# Cache
schedule_cache = None
cache_timestamp = 0
livetv_cache = None
livetv_cache_timestamp = 0
cache_duration = 600  # 10 minutes

# EPG setup
epg_url = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"

# Channel Matches will be inserted in Part 2/3

def log(msg):
    LOGPATH = xbmcvfs.translatePath('special://logpath/')
    FILENAME = 'daddylivehd.log'
    LOG_FILE = os.path.join(LOGPATH, FILENAME)
    try:
        if isinstance(msg, str):
            _msg = f'\n    {msg}'
        else:
            raise TypeError('log() msg not of type str!')
        if not os.path.exists(LOG_FILE):
            f = open(LOG_FILE, 'w', encoding='utf-8')
            f.close()
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            line = ('[{} {}]: {}').format(datetime.now().date(), str(datetime.now().time())[:8], _msg)
            f.write(line.rstrip('\r\n') + '\n')
    except Exception as e:
        try:
            xbmc.log(f'[ Daddylive ] Logging Failure: {e}', 2)
        except:
            pass

def preload_cache():
    global schedule_cache, cache_timestamp
    global livetv_cache, livetv_cache_timestamp
    now = time.time()
    try:
        hea = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': baseurl,
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-GPC': '1'
        }
        response = requests.get(schedule_url, headers=hea, timeout=10)
        if response.status_code == 200:
            schedule_cache = response.json()
            cache_timestamp = now
    except Exception as e:
        log(f"Failed to preload LIVE SPORTS schedule: {e}")
    try:
        livetv_cache = channels(fetch_live=True)
        livetv_cache_timestamp = now
    except Exception as e:
        log(f"Failed to preload LIVE TV channels: {e}")

def clean_category_name(name):
    if isinstance(name, str):
        name = html.unescape(name).strip()
    return name

def get_local_time(utc_time_str):
    time_format = addon.getSetting('time_format')
    if not time_format:
        time_format = '12h'
    try:
        event_time_utc = datetime.strptime(utc_time_str, '%H:%M')
    except TypeError:
        event_time_utc = datetime(*(time.strptime(utc_time_str, '%H:%M')[0:6]))
    user_timezone = addon.getSetting('epg_timezone')
    if not user_timezone:
        user_timezone = 0
    else:
        user_timezone = int(user_timezone)
    dst_enabled = addon.getSettingBool('dst_enabled')
    if dst_enabled:
        user_timezone += 1
    timezone_offset_minutes = user_timezone * 60
    event_time_local = event_time_utc + timedelta(minutes=timezone_offset_minutes)
    if time_format == '12h':
        local_time_str = event_time_local.strftime('%I:%M %p').lstrip('0')
    else:
        local_time_str = event_time_local.strftime('%H:%M')
    return local_time_str

def build_url(query):
    return addon_url + '?' + urlencode(query)

def addDir(title, dir_url, is_folder=True):
    li = xbmcgui.ListItem(title)
    labels = {'title': title, 'plot': title, 'mediatype': 'video'}
    kodiversion = getKodiversion()
    if kodiversion < 20:
        li.setInfo("video", labels)
    else:
        infotag = li.getVideoInfoTag()
        infotag.setMediaType(labels.get("mediatype", "video"))
        infotag.setTitle(labels.get("title", "Daddylive"))
        infotag.setPlot(labels.get("plot", labels.get("title", "Daddylive")))
    li.setArt({'thumb': '', 'poster': '', 'banner': '', 'icon': ICON, 'fanart': FANART})
    if is_folder:
        li.setProperty("IsPlayable", 'false')
    else:
        li.setProperty("IsPlayable", 'true')
    xbmcplugin.addDirectoryItem(handle=addon_handle, url=dir_url, listitem=li, isFolder=is_folder)

def closeDir():
    xbmcplugin.endOfDirectory(addon_handle)

def getKodiversion():
    return int(xbmc.getInfoLabel("System.BuildVersion")[:2])

def get_now_next_later(epg_url, channel_id):
    try:
        response = requests.get(epg_url, timeout=30)
        response.raise_for_status()
        compressed_file = io.BytesIO(response.content)
        decompressed_file = gzip.GzipFile(fileobj=compressed_file)
        tree = ET.parse(decompressed_file)
        root = tree.getroot()
        now = datetime.utcnow()
        upcoming_programs = []
        for program in root.findall("programme"):
            if program.get("channel") != channel_id:
                continue
            start = datetime.strptime(program.get("start")[:14], "%Y%m%d%H%M%S")
            stop = datetime.strptime(program.get("stop")[:14], "%Y%m%d%H%M%S")
            if start >= now:
                title = program.findtext("title", default="Unknown Title")
                desc = program.findtext("desc", default="No Description Available")
                upcoming_programs.append({
                    "title": title.strip(),
                    "start": start.strftime("%I:%M %p"),
                    "desc": desc.strip()
                })
            if len(upcoming_programs) == 3:
                break
        return upcoming_programs
    except Exception as e:
        log(f"Error fetching or parsing EPG: {e}")
        return []
# --- CHANNEL MATCHES ---

CHANNEL_MATCHES = {
    "ABC News USA": "us-abcnews",
    "ABC USA": "us-abc",
    "AMC USA": "us-amc",
    "Animal Planet USA": "us-animalplanet",
    "BBC America USA": "us-bbcamerica",
    "BBC News UK": "uk-bbcnews",
    "BBC One UK": "uk-bbcone",
    "BBC Two UK": "uk-bbctwo",
    "beIN Sports 1 USA": "us-beinsports1",
    "beIN Sports 2 USA": "us-beinsports2",
    "beIN Sports 3 USA": "us-beinsports3",
    "beIN Sports USA": "us-beinsports",
    "BET USA": "us-bet",
    "Bloomberg USA": "us-bloomberg",
    "BT Sport 1 UK": "uk-btsport1",
    "BT Sport 2 UK": "uk-btsport2",
    "BT Sport 3 UK": "uk-btsport3",
    "BT Sport ESPN UK": "uk-btsportespen",
    "Cartoon Network USA": "us-cartoonnetwork",
    "CBS News USA": "us-cbsnews",
    "CBS Sports Network USA": "us-cbssportsnetwork",
    "CBS USA": "us-cbs",
    "CNBC USA": "CNBC.USA.us",
    "CNN USA": "us-cnn",
    "Comedy Central": "Comedy.Central.za",
    "Discovery Channel USA": "Discovery.Channel.tr",
    "Disney Channel USA": "Disney.Channel.za",
    "Disney Junior USA": "DISNEY.JR.uy",
    "Disney XD USA": "Disney.XD.pl",
    "E! USA": "us-eentertainment",
    "ESPN 2 USA": "us-espn2",
    "ESPN Deportes": "ESPN.Deportes.us",
    "ESPN USA": "us-espn",
    "Food Network USA": "us-foodnetwork",
    "FOX Business USA": "Fox.Business.us",
    "FOX News USA": "Fox.News.us",
    "FOX Sports 1 USA": "us-foxsports1",
    "FOX Sports 2 USA": "us-foxsports2",
    "FOX USA": "us-fox",
    "Fight Network": "plex.tv.Fight.Network.plex",
    "Golf Channel USA": "Golf.Channel.USA.us",
    "HBO USA": "us-hbo",
    "HGTV": "HGTV.uy",
    "History Channel USA": "us-history",
    "Investigation Discovery USA": "us-investigationdiscovery",
    "Lifetime USA": "us-lifetime",
    "MSNBC": "MSNBC.au",
    "MTV USA": "us-mtv",
    "Nat Geo Wild USA": "us-natgeowild",
    "National Geographic USA": "us-nationalgeographic",
    "NBC News USA": "us-nbcnews",
    "NBC Sports USA": "us-nbcsports",
    "NBC USA": "us-nbc",
    "NFL Network": "NFL.Network.us",
    "NHL Network USA": "NHL.Network.USA.us",
    "Nickelodeon USA": "us-nickelodeon",
    "PBS USA": "us-pbs",
    "SEC Network USA": "us-secnetwork",
    "Showtime USA": "us-showtime",
    "Sky News UK": "uk-skynews",
    "Sky Sports Football UK": "uk-skysportsfootball",
    "Sky Sports Main Event": "Sky.Sports.Main.Event.ie",
    "Sky Sports Premier League": "Sky.Sports.Premier.League.ie",
    "Starz USA": "us-starz",
    "Syfy USA": "us-syfy",
    "TBS USA": "us-tbs",
    "Tennis Channel USA": "us-tennischannel",
    "TLC": "TLC.tr",
    "TNT USA": "us-tnt",
    "Travel Channel": "Travel.Channel.za",
    "truTV USA": "us-trutv",
    "USA Network USA": "us-usanetwork",
    "VH1 USA": "us-vh1",
    "Weather Channel USA": "The.Weather.Channel.us",
    "YES Network USA": "us-yesnetwork",
    "WWE Network": "WWE.Network.us",
    "DAZN LaLiga": "DAZN.LALIGA.es",
    "DAZN LaLiga 2": "DAZN.LALIGA.2.es",
    "TSN1": "TSN1.mt",
    "TSN2": "TSN2.mt",
    "TSN3": "TSN3.mt",
    "TSN4": "TSN4.mt",
    "TSN5": "TSN5.mt",
    "Sportsnet One": "Sportsnet.One.ca",
    "Sportsnet 360": "Sportsnet.360.ca",
    "Sportsnet World": "Sportsnet.World.ca",
    "TVA Sports": "TVA.Sports.ca",
    "TVA Sports 2": "TVA.Sports.2.ca",
    "Telemundo": "TELEMUNDO.uy",
    "Destination America": "Destination.America.us",
    "Prima Sport 1": "Prima.Sport.1.ro",
    "Prima Sport 2": "Prima.Sport.2.ro",
    "Prima Sport 3": "Prima.Sport.3.ro",
    "Prima Sport 4": "Prima.Sport.4.ro",
    "Animal Planet": "ANIMAL.PLANET.uy",
    "Astro Cricket": "Astro.Cricket.my",
    "Boomerang": "Boomerang.vn",
    "Cleo TV": "CLEO.TV.us",
    "Fox Cricket": "FoxCricket.alt.au",
    "Nick Music": "Nick.Music.nz",
    "Nicktoons": "NickTOONS.za",
    "Oxygen True Crime": "Oxygen.True.Crime.ca",
    "Smithsonian Channel": "Smithsonian.Channel.my",
    "Sky Sport Bundesliga 1 HD": "Sky.Sport.Bundesliga.1.HD.at",
    "Sky Sport Austria 1 HD": "Sky.Sport.Austria.1.HD.de",
    "Sky Crime": "Sky.Crime.it",
    "Sky History": "Sky.History.ie",
    "Sky Witness HD": "Sky.Witness.HD.uk",
    "Sky Atlantic": "Sky.Atlantic.it",
    "SportDigital Fussball": "SPORTDIGITAL.FUSSBALL.ch",
    "Fashion TV": "Fashion.TV.tr",
    "Dave": "Dave.ch",
    "5 USA": "5.USA.uk",
    "V Film Premiere": "V.Film.Premiere.se",
    "V Film Family": "V.Film.Family.se",
    "TeenNick": "TeenNick.ro",
    "TV2 Zulu": "TV2.Zulu.se",
    "TVP INFO": "TVP.Info.pl",
    "Sundance TV": "Sundance.TV.pl",
    "Paramount Network": "Paramount.Network.se",
    "Marquee Sports Network": "Marquee.Sports.Network.us",
    "Motor Trend": "Motor.Trend.it",
    "GOLF Channel USA": "Golf.Channel.USA.us",
    "Discovery Life Channel": "Discovery.Life.Channel.us",
    "FOX Soccer Plus": "FOX.Soccer.Plus.us",
    "Willow XTRA": "Willow.Xtra.us"
}

# --- END CHANNEL MATCHES ---
def Main_Menu():
    addDir('LIVE SPORTS', build_url({'mode': 'menu', 'serv_type': 'sched'}))
    addDir('LIVE TV (All)', build_url({'mode': 'menu', 'serv_type': 'live_tv'}))
    addDir('Settings', build_url({'mode': 'open_settings'}))
    addDir('USA TV', build_url({'mode': 'country', 'country': 'USA'}))
    addDir('UK TV', build_url({'mode': 'country', 'country': 'UK'}))
    addDir('Spain TV', build_url({'mode': 'country', 'country': 'Spain'}))
    addDir('Canada TV', build_url({'mode': 'country', 'country': 'Canada'}))
    addDir('Australia TV', build_url({'mode': 'country', 'country': 'Australia'}))
    addDir('Mexico TV', build_url({'mode': 'country', 'country': 'Mexico'}))
    addDir('Germany TV', build_url({'mode': 'country', 'country': 'Germany'}))
    addDir('India TV', build_url({'mode': 'country', 'country': 'India'}))
    addDir('France TV', build_url({'mode': 'country', 'country': 'France'}))
    addDir('Portugal TV', build_url({'mode': 'country', 'country': 'Portugal'}))
    addDir('Italy TV', build_url({'mode': 'country', 'country': 'Italy'}))
    addDir('Arabic TV', build_url({'mode': 'country', 'country': 'Arabic'}))
    addDir('Miscellaneous TV', build_url({'mode': 'country', 'country': 'Misc'}))
    closeDir()

def getCategTrans():
    global schedule_cache, cache_timestamp
    hea = {'User-Agent': UA}
    categs = []
    now = time.time()
    try:
        if schedule_cache and (now - cache_timestamp) < cache_duration:
            schedule = schedule_cache
        else:
            response = requests.get(schedule_url, headers=hea, timeout=10)
            if response.status_code == 200:
                schedule = response.json()
                schedule_cache = schedule
                cache_timestamp = now
            else:
                xbmcgui.Dialog().ok("Error", f"Failed to fetch data: {response.status_code}")
                return []
    except Exception as e:
        xbmcgui.Dialog().ok("Error", f"Error fetching category: {e}")
        return []
    try:
        for date_key, events in schedule.items():
            for categ, events_list in events.items():
                categ = clean_category_name(categ)
                categs.append((categ, json.dumps(events_list)))
    except Exception as e:
        log(f"Error parsing schedule: {e}")
    return categs

def Menu_Trans():
    categs = getCategTrans()
    if not categs:
        return
    for categ_name, events_list in categs:
        addDir(categ_name, build_url({'mode': 'showChannels', 'trType': categ_name}))
    closeDir()

def ShowChannels(categ, channels_list):
    if categ.lower() == 'basketball':
        nba_channels = []
        for item in channels_list:
            title = item.get('title')
            if 'NBA' in title.upper():
                nba_channels.append(item)
        if nba_channels:
            addDir('[NBA]', build_url({'mode': 'showNBA', 'trType': categ, 'nba_channels': json.dumps(nba_channels)}), True)
    for item in channels_list:
        title = item.get('title')
        addDir(title, build_url({'mode': 'trList', 'trType': categ, 'channels': json.dumps(item.get('channels'))}), True)
    closeDir()

def getTransData(categ):
    trns = []
    categs = getCategTrans()
    for categ_name, events_list_json in categs:
        if categ_name == categ:
            events_list = json.loads(events_list_json)
            for item in events_list:
                event = item.get('event')
                time_str = item.get('time')
                event_time_local = get_local_time(time_str)
                title = f'{event_time_local} {event}'
                channels = item.get('channels')
                if isinstance(channels, dict):
                    channels = list(channels.values())
                if isinstance(channels, list) and all(isinstance(channel, dict) for channel in channels):
                    trns.append({
                        'title': title,
                        'channels': [{'channel_name': channel.get('channel_name'), 'channel_id': channel.get('channel_id')} for channel in channels]
                    })
                else:
                    log(f"Unexpected data structure in 'channels'")
    return trns

def TransList(categ, channels):
    for channel in channels:
        channel_title = html.unescape(channel.get('channel_name'))
        channel_id = channel.get('channel_id')
        addDir(channel_title, build_url({'mode': 'trLinks', 'trData': json.dumps({'channels': [{'channel_name': channel_title, 'channel_id': channel_id}]})}), False)
    closeDir()

def getSource(trData):
    data = json.loads(unquote(trData))
    channels_data = data.get('channels')
    if channels_data is not None and isinstance(channels_data, list):
        url_stream = f'{baseurl}stream/stream-{channels_data[0]["channel_id"]}.php'
        xbmcplugin.setContent(addon_handle, 'videos')
        PlayStream(url_stream)

def PlayStream(link):
    try:
        stream_path = addon.getSetting('stream_path').strip()
        headers = {'Referer': baseurl, 'user-agent': UA}
        resp = requests.post(link, headers=headers).text
        url_1 = re.findall('iframe src="([^"]*)', resp)[0]
        parsed_url = urlparse(url_1)
        referer_base = f"{parsed_url.scheme}://{parsed_url.netloc}"
        referer = quote_plus(referer_base)
        user_agent = quote_plus(UA)
        resp2 = requests.post(url_1, headers=headers).text
        stream_id = re.findall('fetch\(\'([^\']*)', resp2)[0]
        url_2 = re.findall('var channelKey = "([^"]*)', resp2)[0]
        m3u8 = re.findall('(\/mono\.m3u8)', resp2)[0]
        resp3 = referer_base + stream_id + url_2
        url_3 = requests.post(resp3, headers=headers).text
        key = re.findall(':"([^"]*)', url_3)[0]
        final_link = f'https://{key}{stream_path}/{key}/{url_2}{m3u8}|Referer={referer}/&Origin={referer}&Keep-Alive=true&User-Agent={user_agent}'
        if final_link.startswith("http"):
            liz = xbmcgui.ListItem('Daddylive', path=final_link)
            liz.setProperty('inputstream', 'inputstream.ffmpegdirect')
            liz.setMimeType('application/x-mpegURL')
            liz.setProperty('inputstream.ffmpegdirect.is_realtime_stream', 'true')
            liz.setProperty('inputstream.ffmpegdirect.stream_mode', 'timeshift')
            liz.setProperty('inputstream.ffmpegdirect.manifest_type', 'hls')
            xbmcplugin.setResolvedUrl(addon_handle, True, liz)
        else:
            xbmcgui.Dialog().ok("Playback Error", "Invalid stream link.")
    except Exception as e:
        log(f"Error in PlayStream: {e}")

def list_gen():
    addon_url = baseurl
    chData = channels()
    for c in chData:
        addDir(c[1], build_url({'mode': 'play', 'url': addon_url + c[0]}), False)
    closeDir()

def channels(fetch_live=False):
    global livetv_cache, livetv_cache_timestamp
    if not fetch_live:
        now = time.time()
        if livetv_cache and (now - livetv_cache_timestamp) < cache_duration:
            return livetv_cache
    url = baseurl + '/24-7-channels.php'
    do_adult = xbmcaddon.Addon().getSetting('adult_pw')
    hea = {'Referer': baseurl + '/', 'user-agent': UA}
    resp = requests.post(url, headers=hea).text
    ch_block = re.compile('<center><h1(.+?)tab-2', re.MULTILINE | re.DOTALL).findall(str(resp))
    chan_data = re.compile('href=\"(.*)\" target(.*)<strong>(.*)</strong>').findall(ch_block[0])
    channels = []
    for c in chan_data:
        if not "18+" in c[2]:
            channels.append([c[0], c[2]])
        if do_adult == 'lol' and "18+" in c[2]:
            channels.append([c[0], c[2]])
    return channels

def show_country_channels(country_name):
    all_channels = channels()
    for c in all_channels:
        channel_name = c[1]
        if country_name.lower() in channel_name.lower():
            addDir(channel_name, build_url({'mode': 'play', 'url': baseurl + c[0]}), False)
    closeDir()

kodiversion = getKodiversion()
mode = params.get('mode', None)

if not mode:
    preload_cache()
    Main_Menu()
else:
    if mode == 'menu':
        servType = params.get('serv_type')
        if servType == 'sched':
            Menu_Trans()
        if servType == 'live_tv':
            list_gen()
    if mode == 'showChannels':
        transType = params.get('trType')
        channels = getTransData(transType)
        ShowChannels(transType, channels)
    if mode == 'trList':
        transType = params.get('trType')
        channels = json.loads(params.get('channels'))
        TransList(transType, channels)
    if mode == 'trLinks':
        trData = params.get('trData')
        getSource(trData)
    if mode == 'play':
        link = params.get('url')
        PlayStream(link)
    if mode == 'open_settings':
        xbmcaddon.Addon().openSettings()
        xbmcplugin.endOfDirectory(addon_handle)
    if mode == 'showNBA':
        transType = params.get('trType')
        nba_channels = json.loads(params.get('nba_channels'))
        ShowChannels(transType, nba_channels)
    if mode == 'country':
        country = params.get('country')
        show_country_channels(country)
