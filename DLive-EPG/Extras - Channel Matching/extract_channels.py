import re
import requests
import time

# Minimal dummy settings needed
baseurl = 'https://daddylivehd.sx'  # <- Change this if your DaddyLive URL is different
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
cache_duration = 600
livetv_cache = None
livetv_cache_timestamp = 0

def channels(fetch_live=False):
    global livetv_cache, livetv_cache_timestamp

    if not fetch_live:
        now = time.time()
        if livetv_cache and (now - livetv_cache_timestamp) < cache_duration:
            return livetv_cache
    
    url = baseurl + '/24-7-channels.php'
    hea = {
        'Referer': baseurl + '/',
        'user-agent': UA,
    }

    resp = requests.post(url, headers=hea).text
    ch_block = re.compile('<center><h1(.+?)tab-2', re.MULTILINE | re.DOTALL).findall(str(resp))
    chan_data = re.compile('href=\"(.*)\" target(.*)<strong>(.*)</strong>').findall(ch_block[0])

    channels = []
    for c in chan_data:
        if not "18+" in c[2]:
            channels.append([c[0], c[2]])
    return channels

if __name__ == "__main__":
    try:
        ch_list = channels()
        live_channel_names = [c[1] for c in ch_list]

        print("=== DaddyLive Channel Names ===")
        for name in live_channel_names:
            print(name)

        # Optionally save to a text file
        with open("daddylive_channels.txt", "w", encoding="utf-8") as f:
            for name in live_channel_names:
                f.write(name + "\n")

        print("\n✅ Channel names saved to 'daddylive_channels.txt'!")

    except Exception as e:
        print(f"Error fetching channel list: {e}")
