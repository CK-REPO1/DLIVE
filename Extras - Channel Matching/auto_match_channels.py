import gzip
import io
import requests
import xml.etree.ElementTree as ET

# Your DaddyLive extracted channels list
CHANNELS_FILE = "daddylive_channels.txt"

# Your EPG feed URL
EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"

def load_daddylive_channels(filename):
    """Load DaddyLive channels from text file."""
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def download_and_parse_epg(url):
    """Download and parse the EPG XML feed."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        compressed = io.BytesIO(response.content)
        decompressed = gzip.GzipFile(fileobj=compressed)
        
        tree = ET.parse(decompressed)
        root = tree.getroot()
        
        epg_channels = {}

        for channel in root.findall('channel'):
            epg_id = channel.attrib.get('id')
            display_name = None
            for name in channel.findall('display-name'):
                if name.text:
                    display_name = name.text.strip()
                    break
            if epg_id and display_name:
                epg_channels[display_name.lower()] = epg_id  # Lowercase for easier matching
        
        return epg_channels
    
    except Exception as e:
        print(f"Failed to download or parse EPG: {e}")
        return {}

def auto_match(daddylive_channels, epg_channels):
    """Attempt to match DaddyLive channels to EPG IDs."""
    matches = {}
    unmatched = []

    for live_name in daddylive_channels:
        key = live_name.lower().strip()
        if key in epg_channels:
            matches[live_name] = epg_channels[key]
        else:
            unmatched.append(live_name)
    
    return matches, unmatched

def save_matches(matches, filename="channel_matches_output.txt"):
    """Save the matches into a Python dictionary format."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("CHANNEL_MATCHES = {\n")
        for k, v in matches.items():
            f.write(f'    "{k}": "{v}",\n')
        f.write("}\n")
    print(f"✅ Matches saved to {filename}!")

def save_unmatched(unmatched, filename="unmatched_channels.txt"):
    """Save unmatched channels for manual review."""
    if unmatched:
        with open(filename, "w", encoding="utf-8") as f:
            for name in unmatched:
                f.write(name + "\n")
        print(f"⚠️ Unmatched channels saved to {filename}.")

if __name__ == "__main__":
    print("🔎 Loading DaddyLive channels...")
    live_channels = load_daddylive_channels(CHANNELS_FILE)

    print("🔎 Downloading and parsing EPG feed...")
    epg_channels = download_and_parse_epg(EPG_URL)

    print("🔎 Auto-matching channels...")
    matches, unmatched = auto_match(live_channels, epg_channels)

    save_matches(matches)
    save_unmatched(unmatched)

    print(f"\n✅ Auto-matching complete!")
    print(f"Matched {len(matches)} channels ✅")
    print(f"Unmatched {len(unmatched)} channels ⚠️ (check manually)")
