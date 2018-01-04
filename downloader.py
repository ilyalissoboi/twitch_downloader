import math
import m3u8
import os
import re
import requests
import subprocess
import sys
import webbrowser

from cement.core import foundation, hook
from cement.utils.misc import init_defaults
from pprint import pprint
from random import random

CLIENT_ID = 'qlj10cyuk2moe38hzmvsbd4zzvooe1o'
REDIRECT_URL = 'https://ilyalissoboi.github.io/twitch_downloader/landing.html'

defaults = init_defaults('twitch_downloader')
defaults['twitch_downloader']['debug'] = False
defaults['twitch_downloader']['url'] = None

def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i+n]

def authenticate_twitch_oauth():
    """Opens a web browser to allow the user to grant the script access to their Twitch account."""

    url = ("https://api.twitch.tv/kraken/oauth2/authorize/"
           "?response_type=token&client_id={0}&redirect_uri="
           "{1}&scope=user_read+user_subscriptions").format(CLIENT_ID, REDIRECT_URL)

    print "Attempting to open a browser to let you authenticate with Twitch"

    try:
        if not webbrowser.open_new_tab(url):
            raise webbrowser.Error
    except webbrowser.Error:
        print "Unable to open a web browser, try accessing this URL manually instead:\n{0}".format(url)
        sys.exit(1)

app = foundation.CementApp('twitch_downloader')
try:
    app.setup()

    app.args.add_argument('-u', '--url', action='store', help='broadcast or highlight url')
    app.args.add_argument('-o', '--output', action='store', help='output folder for downloaded files', default='.')
    app.args.add_argument('-q', '--quality', action='store', help='desired stream quality', default='live')
    app.args.add_argument('-n', '--name', action='store', help='name for the complete stream file', default='')
    app.args.add_argument('-s', '--start', action='store', help='start time (in seconds) for new-type VODs', default=0)
    app.args.add_argument('-e', '--end', action='store', help='end time (in seconds) for new-type VODs', default=sys.maxint)
    app.args.add_argument('-a', '--authenticate', action='store_true', help='authenticate with your twitch account')

    app.run()

    if app.pargs.authenticate:
        authenticate_twitch_oauth()
        sys.exit(0)

    try:
        common_headers = {
            'Authorization': 'OAuth %s' % open(os.path.expanduser('~/.twitch_token')).readline().rstrip('\n'),
            'Client-ID': CLIENT_ID
            }
    except Exception as e:
        common_headers = {'Client-ID': CLIENT_ID}

    if app.pargs.url:
        _url_re = re.compile(r"""
            http(s)?://
            (?:
                (?P<subdomain>\w+)
                \.
            )?
            twitch.tv
            /videos/
                (?P<video_id>\d+)?
        """, re.VERBOSE)

        #new API specific variables
        _chunk_re = "(.+\.ts)\?start_offset=(\d+)&end_offset=(\d+)"
        _simple_chunk_re = "(.+\.ts)"
        _vod_api_url = "https://api.twitch.tv/api/vods/{}/access_token"
        _index_api_url = "http://usher.ttvnw.net/vod/{}"

        match = _url_re.match(app.pargs.url).groupdict()

        channel = match.get("channel", "twitch").lower()
        subdomain = match.get("subdomain")
        video_type = match.get("video_type", "v")
        video_id = match.get("video_id")

        output_file_name = ''

        if not app.pargs.name:
            if app.pargs.end:
                output_file_name = '%s_%s_%s.mp4' % (channel, video_id, app.pargs.end)
            if app.pargs.start and app.pargs.end:
                output_file_name = '%s_%s_%s_%s.mp4' % (channel, video_id, app.pargs.start, app.pargs.end)
            else:
                output_file_name = '%s_%s.mp4' % (channel, video_id)
        else:
            if app.pargs.end:
                output_file_name = '%s_%s_%s.mp4' % (app.pargs.name, video_id, app.pargs.end)
            if app.pargs.start and app.pargs.end:
                output_file_name = '%s_%s_%s_%s.mp4' % (app.pargs.name, video_id, app.pargs.start, app.pargs.end)
            else:
                output_file_name = '%s_%s.mp4' % (app.pargs.name, video_id)

        app.pargs.name = output_file_name

        assert video_type == 'v'

        # Get access code
        url = _vod_api_url.format(video_id)
        r = requests.get(url, headers=common_headers)
        data = r.json()

        # Fetch vod index
        url = _index_api_url.format(video_id)
        payload = {'nauth': data['token'], 'nauthsig': data['sig'], 'allow_source': True, 'allow_spectre': False, "player": "twitchweb", "p": int(random() * 999999), "allow_audio_only": True, "type": "any"}
        r = requests.get(url, params=payload, headers=common_headers)
        m = m3u8.loads(r.content)
        index_url = m.playlists[0].uri
        index = m3u8.load(index_url)

        # Get the piece we need
        position = 0
        chunks = []

        for seg in index.segments:
            # Add duration of current segment
            position += seg.duration

            # Check if we have gotten to the start of the clip
            if position < int(app.pargs.start):
                continue

            # Extract clip name and byte range
            p = re.match(_chunk_re, seg.absolute_uri)
            # match for playlists without byte offsets
            if not p:
                p = re.match(_simple_chunk_re, seg.absolute_uri)
                filename = p.groups()[0]
                start_byte = 0
                end_byte = 0
            else:
                filename, start_byte, end_byte = p.groups()

            chunks.append([filename, start_byte, end_byte])

            # Check if we have reached the end of clip
            if position > int(app.pargs.end):
                break

        if channel == 'twitch':
            channel = chunks[0][0].split('chunked')[0].strip('/').split('/')[-1].split('_')[1]
            app.pargs.name = app.pargs.name.replace('twitch', channel)

        #download clip chunks and merge into single file
        with open(os.path.join(app.pargs.output, 'chunks.txt'), 'w+') as cf:
            for c in chunks:
                video_url = "{}?start_offset={}&end_offset={}".format(*c)
                cf.write('%s\n' % video_url)

        transport_stream_file_name = app.pargs.name.replace('.mp4', '.ts')
        subprocess.call('wget -i %s -nv -O %s' % (os.path.join(app.pargs.output, 'chunks.txt'), transport_stream_file_name), cwd=app.pargs.output, shell=True)
        subprocess.call('ffmpeg -i %s -bsf:a aac_adtstoasc -c copy %s' % (transport_stream_file_name, app.pargs.name), cwd=app.pargs.output, shell=True)
        os.remove(os.path.join(app.pargs.output, 'chunks.txt'))
        os.remove(os.path.join(app.pargs.output, transport_stream_file_name))
    else:
        app.log.error("Did not receive a value for 'url' option.")
        app.close(1)
except Exception, e:
    import traceback
    traceback.print_exc(file=sys.stdout)
    raise e
finally:
    app.close()
