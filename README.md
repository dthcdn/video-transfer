## Requirements
- Python 3
- Python package: pycrypto, requests, boto3
- ffpmeg & ffprobe

## Config

Config files, aka preset, are placed in `presets` folder. Basically, a preset contains following settings:

- `transcode.resolutions`: (Array) Resolutions needed. Support `144, 240, 360, 480, 720, 1080`
- `transcode.upscale`: (Boolean) Upscale video. For example, origin video is 360p and the `transcode.resolutions` contains 1080, then the video will be upscale to 1080p. Default 'false'.
- `output`: temp output transcoded folder
- `api.host`, `api.key`, `api.domain`: api server provided by DTH

## Example

```
from dth_submit import exec
if __name__ == '__main__':
  exec("./sample-video.mp4", "my-preset")

```
