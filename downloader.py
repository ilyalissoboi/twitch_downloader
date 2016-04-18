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

CLIENT_ID = 'qlj10cyuk2moe38hzmvsbd4zzvooe1o'
REDIRECT_URL = 'https://ilyalissoboi.github.io/twitch_downloader/landing.html'

defaults = init_defaults('twitch_downloader')
defaults['twitch_downloader']['debug'] = False
defaults['twitch_downloader']['url'] = None

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
        common_headers = {'Authorization': 'OAuth %s' % open(os.path.expanduser('~/.twitch_token')).readline()}
    except Exception, e:
        common_headers = {}

    if app.pargs.url:
        _url_re = re.compile(r"""
            http(s)?://
            (?:
                (?P<subdomain>\w+)
                \.
            )?
            twitch.tv
            /
            (?P<channel>[^/]+)
            (?:
                /
                (?P<video_type>[bcv])
                /
                (?P<video_id>\d+)
            )?
        """, re.VERBOSE)

        #new API specific variables
        _chunk_re = "(.+\.ts)\?start_offset=(\d+)&end_offset=(\d+)"
        _vod_api_url = "https://api.twitch.tv/api/vods/{}/access_token"
        _index_api_url = "http://usher.ttvnw.net/vod/{}"

        match = _url_re.match(app.pargs.url).groupdict()
        channel = match.get("channel").lower()
        subdomain = match.get("subdomain")
        video_type = match.get("video_type")
        video_id = match.get("video_id")

        if not app.pargs.name:
            if app.pargs.end:
                app.pargs.name = '%s_%s_%s.mp4' % (channel, video_id, app.pargs.end)
            if app.pargs.start and app.pargs.end:
                app.pargs.name = '%s_%s_%s_%s.mp4' % (channel, video_id, app.pargs.start, app.pargs.end)
            else:
                app.pargs.name = '%s_%s.mp4' % (channel, video_id)

        #old-style video
        if video_type == 'b':
            video_type = 'a'

            api_url = 'https://api.twitch.tv/api/videos/%s%s/' %(video_type, video_id)
            api_headers = {'Accept': 'application/vnd.twitchtv.v2+json'}
            api_headers.update(common_headers)

            api_response = requests.get(api_url, headers=api_headers).json()
            video_qualities = [q for q in api_response['chunks']]

            #get chunks for selected quality
            if app.pargs.quality not in video_qualities:
                app.log.error('Quality "%s" not available!' % app.pargs.quality)
                app.close(1)

            chunks = [c['url'] for c in api_response['chunks'][app.pargs.quality]]
            chunk_names = []

            #approximate video chunks for selected clip duration
            first_chunk = int(int(app.pargs.start) / 1800)
            last_chunk = min(int(math.ceil(int(app.pargs.end) / 1800)), len(chunks))

            chunks = chunks[first_chunk:last_chunk]

            #list files for download and merge
            with open(os.path.join(app.pargs.output, 'chunks.txt'), 'w+') as cf:
                with open(os.path.join(app.pargs.output, 'demux.txt'), 'w+') as df:
                    for c in chunks:
                        cf.write('%s\n' % c)
                        df.write('file %s.%s\n' % (c.split('/')[-1].split('.')[0], 'mp4'))
                        chunk_names.append(c.split('/')[-1].split('.')[0])

            #download chunks, convert to mp4 and merge into single file
            subprocess.check_call(['aria2c', '-x 10', '--file-allocation=none', '-i %s' % os.path.join(app.pargs.output, 'chunks.txt')], cwd=app.pargs.output)
            for c in chunk_names:
                subprocess.check_call('ffmpeg -i %s.flv -vcodec copy -acodec copy %s.mp4' % (c, c), cwd=app.pargs.output, shell=True)
            subprocess.check_call('ffmpeg -f concat -i demux.txt -c copy %s' % app.pargs.name, cwd=app.pargs.output, shell=True)

            for c in chunk_names:
                os.remove(os.path.join(app.pargs.output, '%s.flv' % c))
                os.remove(os.path.join(app.pargs.output, '%s.mp4' % c))
            os.remove(os.path.join(app.pargs.output, 'demux.txt'))
            os.remove(os.path.join(app.pargs.output, 'chunks.txt'))

        #new-style video
        elif video_type == 'v':
            # Get access code
            url = _vod_api_url.format(video_id)
            r = requests.get(url, headers=common_headers)
            data = r.json()
         
            # Fetch vod index
            url = _index_api_url.format(video_id)
            payload = {'nauth': data['token'], 'nauthsig': data['sig'], 'allow_source': True, 'allow_spectre': True}
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
                filename, start_byte, end_byte = p.groups()
         
                # If we have a new file, add it tot he list
                if not chunks or chunks[-1][0] != filename:
                    chunks.append([filename, start_byte, end_byte])
                else: # Else, update the end byte
                    chunks[-1][2] = end_byte
         
                # Check if we have reached the end of clip
                if position > int(app.pargs.end):
                    break
         
            #download clip chunks and merge into single file
            with open(os.path.join(app.pargs.output, 'chunks.txt'), 'w+') as cf:
                file_names = []
                for c in chunks:
                    video_url = "{}?start_offset={}&end_offset={}".format(*c)
                    file_names.append(c[0].split('/')[-1])
                    cf.write('%s\n' % video_url)

            subprocess.check_call(['aria2c', '-x 10', '--file-allocation=none', '-i %s' % os.path.join(app.pargs.output, 'chunks.txt')], cwd=app.pargs.output)   
            subprocess.check_call('ffmpeg -i "concat:%s" -bsf:a aac_adtstoasc -c copy %s' % ('|'.join(file_names), app.pargs.name), cwd=app.pargs.output, shell=True)

            #clean up leftover files
            for c in chunks:
                os.remove(os.path.join(app.pargs.output, c[0].split('/')[-1]))
            os.remove(os.path.join(app.pargs.output, 'chunks.txt'))

    else:
        app.log.error("Did not receive a value for 'url' option.")
        app.close(1)
except Exception, e:
    raise e
finally:
    app.close()