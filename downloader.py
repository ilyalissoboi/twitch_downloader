import m3u8
import os
import re
import requests
import subprocess
import sys

from cement.core import foundation, hook
from cement.utils.misc import init_defaults
from pprint import pprint

defaults = init_defaults('twitch_downloader')
defaults['twitch_downloader']['debug'] = False
defaults['twitch_downloader']['url'] = None

app = foundation.CementApp('twitch_downloader')
try:
    app.setup()

    app.args.add_argument('-u', '--url', action='store', help='broadcast or highlight url')
    app.args.add_argument('-o', '--output', action='store', help='output folder for downloaded files', default='.')
    app.args.add_argument('-q', '--quality', action='store', help='desired stream quality', default='live')
    app.args.add_argument('-n', '--name', action='store', help='name for the complete stream file', default='stream')
    app.args.add_argument('-s', '--start', action='store', help='start time (in seconds) for new-type VODs', default=0)
    app.args.add_argument('-e', '--end', action='store', help='end time (in seconds) for new-type VODs', default=sys.maxint)

    app.run()

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

        #new API support
        _chunk_re = "(.+\.ts)\?start_offset=(\d+)&end_offset=(\d+)"
        _vod_api_url = "https://api.twitch.tv/api/vods/{}/access_token"
        _index_api_url = "http://usher.twitch.tv/vod/{}"

        match = _url_re.match(app.pargs.url).groupdict()
        channel = match.get("channel").lower()
        subdomain = match.get("subdomain")
        video_type = match.get("video_type")
        video_id = match.get("video_id")

        if video_type == 'b':
            video_type = 'a'

            api_url = 'https://api.twitch.tv/api/videos/%s%s/' %(video_type, video_id)
            api_headers = {'Accept': 'application/vnd.twitchtv.v2+json'}

            api_response = requests.get(api_url, headers=api_headers).json()
            video_qualities = [q for q in api_response['chunks']]

            if app.pargs.quality not in video_qualities:
                app.log.error('Quality "%s" not available!' % app.pargs.quality)
                app.close(1)

            chunks = [c['url'] for c in api_response['chunks'][app.pargs.quality]]

            with open(os.path.join(app.pargs.output, 'chunks.txt'), 'w+') as cf:
                first = True
                for c in chunks:
                    cf.write('%s\n' % c)

            subprocess.check_call(['aria2c', '-x 10', '--file-allocation=none', '-i %s' % os.path.join(app.pargs.output, 'chunks.txt')], cwd=app.pargs.output)
            os.remove(os.path.join(app.pargs.output, 'chunks.txt'))

        elif video_type == 'v':
            # Get access code
            url = _vod_api_url.format(video_id)
            r = requests.get(url)
            data = r.json()
         
            # Fetch vod index
            url = _index_api_url.format(video_id)
            payload = {'nauth': data['token'], 'nauthsig': data['sig']}
            r = requests.get(url, params=payload)
         
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
                if position < app.pargs.start:
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
                if position > app.pargs.end:
                    break
         
            with open(os.path.join(app.pargs.output, 'chunks.txt'), 'w+') as cf:
                file_names = []
                first = True
                for c in chunks:
                    video_url = "{}?start_offset={}&end_offset={}".format(*c)
                    file_names.append(c[0].split('/')[-1])
                    cf.write('%s\n' % video_url)

            subprocess.check_call(['aria2c', '-x 10', '--file-allocation=none', '-i %s' % os.path.join(app.pargs.output, 'chunks.txt')], cwd=app.pargs.output)   
            subprocess.check_call('ffmpeg -i "concat:%s" -bsf:a aac_adtstoasc -c copy %s' % ('|'.join(file_names), app.pargs.name), cwd=app.pargs.output, shell=True)

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