#!/usr/bin/python3
# https://github.com/ras434/noisyPi

import os
import subprocess
import time
import datetime
import sys

# Paho MQTT - See https://pypi.org/project/paho-mqtt/
# Instalation:
# pip install paho-mqtt
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt

hostname = "ha"             # Add the DNS or IP address of your MQTT server/broker (i.e. Mosquitto)
username = "mqtt"           # Change to your desired MQTT username
password = "mqtt1234"       # Change to the password for your chosen MQTT username

_audioDevice = "Headphone"  # Audio device to use on Raspberry Pi - Default = "Headphone"
_colors = ["whitenoise", "pinknoise", "brownnoise"]   # color list must match input_list choices in Home Assistant
_currentColor = _colors[len(_colors)-1]               # Set default color to last entry in _colors
_publishInterval = 300                                # 300 seconds (5 minutes) publish state update interval


auth = {"username":username,"password":password}
command_topic = "cmnd/noisypi/NOISE"
state_topic = "stat/noisypi/NOISE"
availability_topic = "tele/noisypi/LWT"
volume_command_topic = "cmnd/noisypi/VOLUME"
volume_state_topic = "stat/noisypi/VOLUME"
_volumeMax = 95
_volumeMin = 50
color_command_topic = "cmnd/noisypi/COLOR"
color_state_topic = "stat/noisypi/COLOR"
qos = 1
client_name = "noisyPi"
_clean_session = True
subscribe_topics = [(command_topic,qos), (state_topic,qos), (availability_topic,qos),
                    (volume_command_topic,qos), (volume_state_topic,qos),
                    (color_command_topic,qos), (color_state_topic,qos)]
retain = True

def publishUpdate():
  _state = getState()
  _stateVolume = getVolume()
  _stateColor = getColor()
  pubList = [(state_topic, _state), (volume_state_topic, _stateVolume), (color_state_topic, _stateColor)]
  for _topic, _payload in pubList:
    pub(_topic, _payload)
    time.sleep(0.5)


def getState():
  if _playRunning():
    return "on"
  else:
    return "off"


def _playRunning():
  try:
    call = subprocess.check_output("pidof 'play'", shell=True)
    return True
  except subprocess.CalledProcessError:
    return False


def _dateTime():
  _date = datetime.datetime.now()
  _time = _date.strftime("%X")
  _date = _date.strftime("%x")
  return f"{_date} {_time} - "

def isNumber(number):
  return type(number) == int or type(number) == float

def inVolumeRange(number):  
  if not isNumber(number):  
    return False
  else:
    if int(number) >= _volumeMin and int(number) <= _volumeMax:
      return True
    else:      
      return False

def setNoise(state, color = _currentColor):    
  if state == "on":    
    ret = os.system(f"nohup play -n synth {color} >/dev/null 2>&1  &") # Plays in BG with no output    
    pub(state_topic, "on")
    print(f"{_dateTime()}setNoise({state})")
  else:
    ret = os.system("sudo kill $(ps -e | grep play | awk '{print $1}')") # Stop playing of noise
    pub(state_topic, "off")
    print(f"{_dateTime()}setNoise({state})")


def setColor(color):
  print(f"{_dateTime()}setColor({color})")
  global _currentColor  
  if _playRunning() and color != _currentColor:    
    setNoise("off")
    time.sleep(0.5)
    setNoise("on", color)    
    time.sleep(0.5)      
  _currentColor = color
  pub(color_state_topic, _currentColor)
    

def getColor():
  global _currentColor
  if _playRunning():
    return_color = os.popen("ps -e -f | grep -m1 synth | awk '{print $11}'").read()
    if return_color in _colors:
      _currentColor = return_color
  return _currentColor


def setVolume(volume):
  print(f"{_dateTime()}setVolume({volume})")
  if not getVolume() == volume:    
    ret = os.system(f"amixer sset '{_audioDevice}' {volume}% -q")
    pub(volume_state_topic, volume)

def getVolume():
  return int(os.popen("amixer | grep % | awk '{print $4}' | sed 's/\[//; s/\]//; s/\%//'").read())


def pub(topic, payload):
  if type(payload) == str:
    payload = payload.rstrip()  # remove CRLF, if exists
  print(f"{_dateTime()}Publishing to topic: [{topic}] payload: [{payload}]")
  time.sleep(1) 
  publish.single(topic=topic, payload=payload, qos=qos, retain=retain, hostname=hostname, auth=auth)


def do_disconnect():
  print(f"\n{_dateTime()}do_disconnect()")
  pub(availability_topic, "offline")
  _mqttc.loop_stop()
  _mqttc.disconnect()
  print(f"\n{_dateTime()}Disconnected from {hostname}.")


def _mqtt_on_connect(_mqttc, userdata, flags, rc):
  print(f"{_dateTime()}Connected to {hostname} with result code {rc}.")
  if rc==0:
    _mqttc.connected_flag=True
    print(f"{_dateTime()}Connected OK > Returned code={rc}")
    print(f"{_dateTime()}Subscribing to: \n{_dateTime()}{subscribe_topics}.")
    _mqttc.subscribe(subscribe_topics)
  else:
    print(f"{_dateTime()}Bad connection > Returned code={rc}")
    do_disconnect()
  
def _mqtt_on_disconnect(_mqttc, userdata, rc):
  print(f"{_dateTime()}on_disconnect(client: {client_name}, userdata: {userdata}, rc: {rc})")
  _mqttc.connected_flag=False

def _mqtt_on_message(_mqttc, userdata, msg):
  _payload = str(msg.payload.decode('utf-8')).rstrip()
  print(f"{_dateTime()}on_message({msg.topic} {_payload})")  
  if _payload in ('on', 'off') and msg.topic == command_topic:
    setNoise(_payload)
  if _payload in _colors and msg.topic == color_command_topic:
    setColor(_payload)    
  if msg.topic == volume_command_topic:
    try:
      number = int(_payload)
    except:
      pass
    if inVolumeRange(number):
        setVolume(number)
  

def _mqtt_on_publish(_mqttc, userdata, rc):
  print(f"{_dateTime()}on_publish(client: {client_name}, userdata: {userdata}, rc: {rc})")

def _mqtt_on_subscribe(_mqttc, userdata, mid, granted_qos):
  print(f"{_dateTime()}on_subscribe(client: {client_name}, userdata: {userdata}, rc: {mid}, granted_qos: {granted_qos})")

def _mqtt_on_unsubscribe(_mqttc, userdata, mid, granted_qos):
  print(f"{_dateTime()}on_unsubscribe(client: {client_name}, userdata: {userdata}, rc: {mid}, granted_qos: {granted_qos})")


_mqttc = mqtt.Client(client_name, clean_session=_clean_session)
_mqttc.enable_logger()
_mqttc.on_connect = _mqtt_on_connect
_mqttc.on_disconnect = _mqtt_on_disconnect
_mqttc.on_message = _mqtt_on_message
_mqttc.on_publish = _mqtt_on_publish
_mqttc.on_subscribe = _mqtt_on_subscribe
_mqttc.on_unsubscribe = _mqtt_on_unsubscribe

if username is not None:
    _mqttc.username_pw_set(username, password)

_mqttc.connect(hostname, port=1883, keepalive=60)
try:
  _mqttc.loop_start()
  time.sleep(1)
  while not _mqttc.connected_flag:
    time.sleep(0.1)
    sys.stdout.write(".")
  print()

except Exception as e:
  print(f"\n{_dateTime()}Error: {e}")
  do_disconnect()
  
time.sleep(3)
pub(availability_topic, "online")

try:
  while _mqttc.connected_flag:
    print(f"{_dateTime()}===========[ Interval Update ]======================")
    publishUpdate()
    print(f"{_dateTime()}===========[ Waiting for {_publishInterval} seconds... ]===========\n")
    time.sleep(_publishInterval)
    

except Exception as e:
  print(f"\n{_dateTime()}Exit from sleep loop.")
  print(f"\n{_dateTime()}_mqttc.connected_flag({_mqttc.connected_flag})")
  print(f"\n{_dateTime()}Error: {e}")
  do_disconnect()

except KeyboardInterrupt:
  print(f"\n{_dateTime()}Aborting. (KeyboardInterrupt)")
  do_disconnect()
  print("\n\nGood bye.\n")
  os._exit(0)
