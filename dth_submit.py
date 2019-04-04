import os, re, json, uuid, time, requests, hashlib, shutil, boto3
from subprocess import Popen, PIPE, STDOUT
from urllib.request import urlopen, HTTPError, URLError
from contextlib import closing
from Crypto.Cipher import AES
from base64 import b64encode, b64decode

RENDITIONS = {
  "144p": {"width": 256, "height": 144, "bitrate": 300, "audiorate": 32},
  "240p": {"width": 426, "height": 240, "bitrate": 400, "audiorate": 64},
  "360p": {"width": 640, "height": 360, "bitrate": 800, "audiorate": 96},
  "480p": {"width": 842, "height": 480, "bitrate": 1400, "audiorate": 128},
  "720p": {"width": 1280, "height": 720, "bitrate": 2800, "audiorate": 128},
  "1080p": {"width": 1920, "height": 1080, "bitrate": 5000, "audiorate": 192}
}

DEFAULT_INGEST_RESOLUTION = [144, 240, 360, 480, 720, 1080]

PWD = os.path.dirname(os.path.realpath(__file__))

def decrypt(cipher, key, salt):
  aesObj = AES.new(key, AES.MODE_CFB, salt)
  strTmp = b64decode(cipher.encode('utf-8'))
  strDec = aesObj.decrypt(strTmp)
  mret = strDec.decode('utf-8')
  return mret
          
def hash(txt):
  return hashlib.sha256(txt.encode()).hexdigest()

def epoch():
  return int(round(time.time() * 1000))

def inputFactoryDriver__local(config):
  if not "path" in config:
    raise ValueError(2002, "Input path does not exist")
  file = config["path"]
  if not os.path.isfile(file):
    raise ValueError(2003, "File not exists %s"%(file))
  return file

def inputFactoryDriver__remote(config):
  if not "url" in config:
    raise ValueError(2010, "url not exist")
  tmpDir = './tmp/remote-download'
  print("[Download] %s"%(config["url"]))
  try:
    if not os.path.exists(tmpDir):
      os.makedirs(tmpDir)
  except OSError:  
    raise ValueError(2011, "can not create download temp dir")
  filedata = None
  try:
    filedata = urlopen(config["url"])
  except HTTPError as e:
    raise ValueError(2012, e.code)
  except URLError as e2:
    raise ValueError(2013, e2)
  datatowrite = filedata.read()
  file = "%s/%s"%(tmpDir, str(uuid.uuid4()))
  try:
    with open(file, 'wb') as f:
      f.write(datatowrite)
  except:
    raise ValueError(2013, 'Fail to save downloaded file')
  print("[Downloaded] %s"%(file))
  return file

def inputFactoryDriver__ftp(config):
  if not "url" in config:
    raise ValueError(2010, "url not exist")
  tmpDir = './tmp/remote-download'
  print("[Download] %s"%(config["url"]))
  try:
    if not os.path.exists(tmpDir):
      os.makedirs(tmpDir)
  except OSError:  
    raise ValueError(2011, "can not create download temp dir")
  file = "%s/%s"%(tmpDir, str(uuid.uuid4()))
  with closing(urlopen(config["url"])) as r:
    with open(file, 'wb') as f:
      shutil.copyfileobj(r, f)
  print("[Downloaded] %s"%(file))
  return file

def inputFactory(inputCnf):
  inputDriver = None
  if "driver" in inputCnf:
    inputDriver = inputCnf["driver"]
  else:
    if "path" in inputCnf:
      inputDriver = "local"
    elif "url" in inputCnf:
      inputDriver = "remote"

  if inputDriver == "local":
    return inputFactoryDriver__local(inputCnf)
  elif inputDriver == "remote":
    return inputFactoryDriver__remote(inputCnf)
  elif inputDriver == "ftp":
    return inputFactoryDriver__ftp(inputCnf)
  else:
    raise ValueError(2001, 'input driver is not supported')

def getVideoMeta(input):
  rc = 0
  output = ""
  try:
    p = Popen(['ffprobe', '-v', 'error', '-show_entries', 'stream=r_frame_rate,width,height', '-of', 'json', input], stderr=STDOUT, stdout=PIPE)
    output = p.communicate()[0]
    rc = p.returncode
  except OSError:
    raise ValueError(3001, "ffprobe is not installed.")
  except:
    raise ValueError(3002, "Something went wrong while executing ffprobe %s"%(input))
  if (not rc == 0):
    raise ValueError(3003, "Invalid video format")
  tmp = json.loads(output)
  videoStreams = list(filter(lambda s: ("width" in s) and (s["width"] > 0), tmp["streams"]))
  if (len(videoStreams) > 0):
    stream0 = videoStreams[0]
    meta = {
      "fps": eval(stream0["r_frame_rate"]),
      "width": stream0["width"],
      "height": stream0["height"]
    }
  else:
    raise ValueError(3004, "no video stream found")
  return meta

def transcodeParams(inputVideoMeta, resolutions, outputPath):
  resolutions.sort()
  keyFramesInterval = inputVideoMeta["fps"] * 2
  maxBitrateRatio = 1.07
  rateMonitorBufferRatio = 1.5
  static = "-c:a aac -ar 48000 -c:v h264 -profile:v main -crf 20 -sc_threshold 0"
  static += " -g %d -keyint_min %d"%(keyFramesInterval, keyFramesInterval)
  cmd = ""
  for i in range(len(resolutions)):
    rH = "%dp"%(resolutions[i])
    if rH in RENDITIONS:
      rendition = RENDITIONS[rH]
      maxrate = rendition["bitrate"] * maxBitrateRatio
      bufsize = rendition["bitrate"] * rateMonitorBufferRatio
      cmd += " %s -vf scale=w=%d:h=%d:force_original_aspect_ratio=decrease"%(static, rendition["width"], rendition["height"])
      cmd += " -b:v %d -maxrate %dk -bufsize %dk -b:a %d"%(rendition["bitrate"], maxrate, bufsize, rendition["audiorate"])
      cmd += " %s/%d.mp4"%(outputPath, rendition["height"])
  return cmd

def requestApiId(host, domain, apiKey, name):
  t=epoch()
  sign = hash("{}-{}-{}-{}".format(domain, apiKey, name, t))
  r = requests.post("%s/newVideo?domain=%s&name=%s&t=%ld&sig=%s"%(host, domain, name, t, sign))
  r.raise_for_status()

  jsonObj = json.loads(r.text)
  pStorage = jsonObj["storage"]
  if (pStorage["type"] == "s3"):
    for key in pStorage:
      if (key != "type"):
        pStorage[key] = decrypt(pStorage[key], apiKey, jsonObj["sessionId"])
  return jsonObj

def uploadS3(inputFile, key, cfn):
  regionName = cfn["region_name"]
  bucketName = cfn["bucket"]
  remotePath = cfn["prefix"]
  accessKey = cfn["aws_access_key_id"]
  secretKey = cfn["aws_secret_access_key"]
  endpoint = cfn["endpoint_url"]
  session = boto3.session.Session(
    region_name=regionName,
    aws_access_key_id=accessKey,
    aws_secret_access_key=secretKey
  )
  client = session.client('s3', endpoint_url=endpoint, use_ssl=True)
  key = "{}/{}".format(remotePath, key)
  if (key[0] == "/"): key = key[1:]
  key = re.sub('/+', '/', key)
  client.upload_file(Filename = inputFile, Bucket = bucketName, Key=key)

def upload(cfn, originalName, path, resolutions):
  host = cfn["api"]["host"]
  domain = cfn["api"]["domain"]
  key = cfn["api"]["key"]

  session = requestApiId(host, domain, key, originalName)
  smil = '<?xml version="1.0" encoding="UTF-8"?><smil title=""><body><switch>'
  pStorage = session["storage"]
  if (pStorage["type"] == "s3"):
    for v in resolutions:
      rf = RENDITIONS["{}p".format(v)]
      smil += '<video src="{}.mp4" system-bitrate="{}" width="{}" height="{}" systemLanguage="en"></video>'.format(v, rf['bitrate'] * 1000, rf['width'], rf['height'])
      print("[Upload] {}p".format(v))
      filePath = "%s/%s.mp4"%(path, v)
      key = "%s/%s.mp4"%(session["id"], v)
      uploadS3(filePath, key, pStorage)
  else:
    raise ValueError(5001, "Storage type not support")
  smil += '</switch></body></smil>'
  smilFile = "%s/index.smil"%(path)
  with open(smilFile, "w") as file: 
    file.write(smil) 
  print("[Upload] smil")
  uploadS3(smilFile, "%s/index.smil"%(session["id"]), pStorage)
  return session["id"]

def transcode(inputFile, resolutions, outputPath, opts):
  opts = opts if opts else {}
  upscale = opts["upscale"] if "upscale" in opts else False
  videoMeta = getVideoMeta(inputFile)
  samples = resolutions
  if not upscale:
    samples = list(filter(lambda r: r <= videoMeta["height"], resolutions))
  baseInputName = os.path.splitext(os.path.basename(inputFile))[0]
  actualOutputPath = "%s/%s--%s"%(outputPath, baseInputName, epoch())
  try:
    if not os.path.exists(actualOutputPath):
      os.makedirs(actualOutputPath)
  except OSError:  
    raise ValueError(4001, "can not create output dir")
  
  if len(samples) == 0:
    raise ValueError(4002, "no matching sample")

  ffmpegParams = transcodeParams(videoMeta, samples, actualOutputPath)

  transcodeRc = -1
  transcodeOutput = ""
  try:
    tmp = list(filter(lambda v: v != '', map(lambda x: x.strip(), ffmpegParams.split(" "))))
    params = ['ffmpeg', '-hide_banner', '-y', '-i', inputFile] + tmp
    p = Popen(params, stderr=STDOUT, stdout=PIPE)
    transcodeOutput = p.communicate()[0]
    transcodeRc = p.returncode
  except:
    raise ValueError(4003, "Fail to transcode")
  if (transcodeRc != 0):
    print(transcodeOutput)
    raise ValueError(4004, "Fail to transcode")
  return actualOutputPath, samples

def exec(input, preset):
  conf = None
  presetFile = preset if preset else 'default'
  try:
    with open("%s/presets/%s.json"%(PWD, presetFile), 'r', encoding='utf-8') as file:
      data = file.read()
      conf = json.loads(data)
      if (input.find('http:') >= 0 or input.find('https:') >= 0):
        conf["input"] = {"url": input}
      elif input.find('ftp:') >= 0:
        conf["input"] = {"url": input, "driver": "ftp"}
      else:
        conf["input"] = {"path": input}
  except FileNotFoundError:
    raise ValueError(1000, 'preset not found')
  except:
    raise ValueError(1001, 'fail to load preset')

  if not "api" in conf:
    raise ValueError(1003, 'missing api config')
  else:
    apiCnf = conf["api"]
    if (not "host" in apiCnf) or (not "key" in apiCnf) or (not "domain" in apiCnf):
      raise ValueError(1003, 'missing api config param')

  resolutions = None
  transcodeConfig = conf["transcode"] if "transcode" in conf else {"resolutions": DEFAULT_INGEST_RESOLUTION, "upscale": False}
  if ((not "resolutions" in transcodeConfig) or (not transcodeConfig["resolutions"])):
    resolutions = DEFAULT_INGEST_RESOLUTION
  else:
    resolutions = transcodeConfig["resolutions"]
  if not isinstance(resolutions, list):
    raise ValueError(1002, 'Invalid input. Resolution must be an array')
    
  print("[Transcoding]")  
  inputFile = inputFactory(conf["input"])
  outputPath = conf["output"] if "output" in conf else "."
  transcodedOutput, transcodedResolutions = transcode(inputFile, resolutions, outputPath, {
    "upscale": transcodeConfig["upscale"] if "upscale" in transcodeConfig else False
  })

  id = upload(conf, os.path.splitext(os.path.basename(transcodedOutput))[0], transcodedOutput, transcodedResolutions)
  print("[Done]%s"%id)
