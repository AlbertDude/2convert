# 2convert
Batch conversion of audio files
  - put files in the folders: [2wav, 2mp3, 2flac] and run this script
  - contents of those folders will be converted to their respective formats
  - sets tags in target mp3 files using 2 mechanisms
     - embedded in the source file (takes precedence)
     - from the filepath folder heirarchy and filename:
        genre/artist/year-album/track_title
  - place jpeg image file in folder to embed (for mp3 only)

Usage:
    ./2convert.py preview
    ./2convert.py go

Requirements:
- system installation of:
  - flac (wav->flac, flac->wav)
  - lame (->mp3)
  - sox (mp3->wav) (probably requires sox mp3 module)
  - ffmpeg (mp3->wav) (alternative)

TODO: 
- print n/M progress
