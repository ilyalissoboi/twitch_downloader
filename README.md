# twitch_downloader
A universal [twitch.tv](http://www.twitch.tv) VOD download script. Compatible with both old- and new-style VODs. Uses some code from [Livestreamer](https://github.com/chrippa/livestreamer) as well as [this script](https://gist.github.com/EhsanKia/0330132521ee3c6caf7e). 

Old-style VODs will be downloaded as 30-minute chunks, new-style VODs will be concatenated into a single file.

Requires:
-[cement](https://pypi.python.org/pypi/cement/2.4.0)
-[m3u8](https://pypi.python.org/pypi/m3u8/0.2.2)
-[requests](https://pypi.python.org/pypi/requests)
-[aria2](http://aria2.sourceforge.net/)
-[FFmpeg](https://www.ffmpeg.org/)

#Usage
`python downloader.py -u <VOD URL>`
