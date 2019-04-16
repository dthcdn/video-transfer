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

## Running with docker
```
docker run -v $(pwd):/project/video/ --env VIDEO=big_buck_bunny.mp4 -v $(pwd)/presets/default.json:/project/presets/default.json rickyngk/dth-video-transfer:v0.2
```

Replace 
- `-v $(pwd):/project/video/`: replace $(pwd) by your video path
- `--env VIDEO=big_buck_bunny.mp4`: replace `big_buck_bunny.mp4` by your video name
- `-v $(pwd)/presets/default.json`: replace by your actual preset file


## Get video id

The video id is placed in the output:
```
[Transcoding]
[Upload] 144p
[Upload] 240p
[Upload] 360p
[Upload] smil
[Done]j2--big_buck_bunny--1554404047711--1554404064855
```
You can grep the id after `[Done]`. In this example, the video id is `j2--big_buck_bunny--1554404047711--1554404064855`

## API Callback

You can also get the video id result via api callback using preset:
`api.callback`: `https://path/to/your/server/{id}`, for `{id}` is pattern that replaced by actual video id by this script.



