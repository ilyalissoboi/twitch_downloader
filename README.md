# twitch_downloader
A universal [twitch.tv](http://www.twitch.tv) VOD download script. Compatible with both old- and new-style VODs. Uses some code from [Livestreamer](https://github.com/chrippa/livestreamer) as well as [this script](https://gist.github.com/EhsanKia/0330132521ee3c6caf7e). 

All VODs will be concatenated into a single file, however old-style VODs may have problems with sound synchronization due to Twitch blocking copyrighted music.

Requires:
- [cement](https://pypi.python.org/pypi/cement/2.4.0)
- [m3u8](https://github.com/ilyalissoboi/m3u8)
- [requests](https://pypi.python.org/pypi/requests)
- [wget](https://www.gnu.org/software/wget/)
- [FFmpeg](https://www.ffmpeg.org/)

#Usage
`python downloader.py -u <VOD URL>`
