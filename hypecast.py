#!/usr/bin/env python

import xml.etree.ElementTree as ET
import sys
import random
from urllib.error import URLError, HTTPError
import random
import time
import feedgen
from feedgen.feed import FeedGenerator
import tempfile
import string
import time
import logging
import json
import urllib.request, urllib.error, urllib.parse
import os.path
import urllib.request, urllib.parse, urllib.error, urllib.request, urllib.error, urllib.parse
from os import path
import argparse
import random
import pydub
import subprocess
import shutil
import datetime
from pydub import AudioSegment
import optparse
from pydub.utils import db_to_float
from dotenv import load_dotenv, find_dotenv
from bs4 import BeautifulSoup

from pathlib import Path  # python3 only
env_path = Path('~') / '.env'
load_dotenv(dotenv_path=env_path)

# TODO:
# muck with the crossfades, still probably wrong
# make sure the IDs are all right
# pull in random soundbeds at boot
# put api keys into ignored file
# allow it to work with different API parts
# paginate
# find a linux compatble tts->file
# output a podcast rss thing
# make it scripted weekly
# make this a class

ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n/10%10!=1)*(n%10<4)*n%10::4])

def getMacVoices():
  return [l.split(" ")[0] for l in str(subprocess.check_output(["say", "-v", "?"])).split('\n')]

def hasOsXVoice(v):
  voices = getMacVoices()
  for avail in voices:
    if avail == v:
      return True
  print("\n\n\n=============\nMust download OS X Voice: %s\n============\n\n\n" % v)
  return False

def hasHighQualityOsXVoices():
  high_quality_voices = ["Ava", "Allison", "Tom"]
  for v in high_quality_voices:
    if hasOsXVoice(v):
      return v
  print("\n\n\n=============\nYou should really download the high quality os x voices\n============\n\n\n")
  return None

def listify(v):
  if not isinstance(v, list):
    return [v,]
  return v

def unicodeify(v):
  if not isinstance(v, str):
    return v
  return v.decode('u')

def fetchPage(url, params):
  print(url)
  print(params)
  data = urllib.parse.urlencode(dict([k, v.encode('utf-8')] for k, v in list(params.items())))
  print(data)
  method = "GET"
  request  = urllib.request.Request(url, data)
  request.get_method = lambda: method
  request.add_header("User-Agent", "Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11" )
  return urllib.request.urlopen(request).read()

class HypePodGenerator():
  def getSongs(self):
    if 'week:' in self.mode:
      return self.getSongsFromScraping()
    else:
      return self.getSongsFromApi()

  def getSongsFromScraping(self):
    ret_songs = []
    parts = self.mode.split(':')
    if not parts[0].endswith('week'):
      print('bad mode for scraping: ' + self.mode)
      sys.exit(1)
    week = parts[1]
    for page in range(1, self.max_pages+ 1):
      print('fetching again, page %d' % page)
      html = fetchPage('http://hypem.com/popular/week:%s/%s' % (week, page), {})
      soup = BeautifulSoup(html)
      # tracks = soup.find_all(attrs = {'class': 'section-track'})
      jsonStr = soup.find(id = 'displayList-data').text.replace('<script>', '').replace('</script>', '').strip()
      tracks = json.loads(jsonStr)['tracks']
      for track in tracks:
        track['title'] = track['song']
        track['stream_pub'] =  'http://hypem.com/serve/public/%s' % track['id']
        ret_songs.append(track)
    return ret_songs

  def getSongsFromApi(self):
    ret_songs = []
    for page in range(1, self.max_pages+ 1):
      print('fetching again, page %d' % page)

      params = {
        'page': str(page),
        'key': HYPE_API_KEY
      }
      mode = self.mode
      base_url = 'https://api.hypem.com/v2/'
      url = base_url + mode

      if mode.startswith('popular/'):
        parts = mode.split('/')
        url = base_url + 'popular'
        params['mode'] = parts[1]

      try:
        response = fetchPage(url, params)
        print(response)
        tracks = json.loads(response)
        for t in tracks:
          t['stream_pub'] =  'http://hypem.com/serve/public/%s' % t['itemid']
          print(t['stream_pub'])
          ret_songs.append(t)
      except URLError as e:
        print(e.reason)
        sys.exit(1)
      except:
        print(sys.exc_info()[0])
        print('No more songs on page %s' % page)
        sys.exit(1)
        return []
    return ret_songs

  def get_tts_mp3(self, sent, fname=None):
      lang = 'en'
      print("Retrieving .mp3 for sentence: %s" % sent)
      baseurl  = "http://translate.google.com/translate_tts"
      params   = { 'q': sent, 'tl': lang }
      response = fetchPage(baseurl, params)
      if( fname==None ):
          fname = "_".join(sent.split())
      ofp = open(fname,"wb")
      ofp.write(response.read())
      print("Saved to file: %s" % fname)
      return

  def downloadSongs(self):
    for index, s in enumerate(self.songs):
      print('Downloading %s of %s songs' % (index + 1, len(self.songs)))
      filename = ('%s - %s.mp3' % (s['artist'], s['title'])).replace('/', '_')
      filepath = os.path.join(self.workdir, filename)
      if not os.path.exists(filepath):
        try:
          headers = { 'User-Agent' : 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11' }
          url = s['stream_pub']
          request = urllib.request.Request(url, None, headers)
          req = urllib.request.urlopen(request)
          with open(filepath, 'wb') as fp:
            shutil.copyfileobj(req, fp)
        except URLError as e:
          print(e.code)
          print(e.fp.read())
          print('Failed to download %s' % filename)
          print(s)
          self.songs.remove(s)
        except:
          print('Failed to download %s' % filename)
          print(sys.exc_info()[0])
          print(s['stream_pub'])
          self.songs.remove(s)
      s['local_file'] = filepath
      s['filename'] = filename
    return self.songs

  def mk_tts_tmp(self, texts, intro_time = 2, outro_time = 4):
    texts = listify(texts)

    segment = None
    if os.path.exists('/usr/bin/say') and self.voice in getMacVoices():
      # print 'Using OS X Say'
      text = ' '.join(texts)
      print(' ---> %s ' % text)
      tf = tempfile.mkstemp(suffix = '.aiff', dir = self.tts_workdir)
      voice_opt = ''
      voice_opt = unicodeify('-v %s' % self.voice)
      cmd = 'say %s -o %s "%s"' % (voice_opt, unicodeify(tf[1]), text)
      print(cmd)
      subprocess.check_output(['say', '-v', self.voice, '-o', unicodeify(tf[1]), text])
      tempwav = tempfile.mktemp(suffix = '.wav', dir = self.tts_workdir)
      subprocess.check_output(['ffmpeg', '-i', tf[1], '-f', 'wav', tempwav])
      # print tf[1]
      segment = AudioSegment.from_file(tempwav)
    else:
      print(texts)
      for text in texts:
        print(text)
        tf = tempfile.mkstemp(suffix = '.mp3', dir = self.tts_workdir)
        if len(text) > 99:
          print('text too longfor google tts %s' % text)
        self.get_tts_mp3(text, tf[1])
        if segment is None:
          segment = AudioSegment.from_mp3(tf[1])
        else:
          segment.append(AudioSegment.from_mp3(tf[1]))

    soundbed = AudioSegment.from_mp3('soundbed1.mp3')

    intro_time = intro_time * 1000
    outro_time = outro_time * 1000
    #print 'talking len: %s' % len(segment)
    #print 'soundbed len: %s' % len(soundbed)
    #print 'intro from 0 to %s' % soundboard_padding
    #print 'talking from %s to %s' % (intro_time, intro_time + len(segment))
    #print 'outro from %s to %s' % (
    #  intro_time + len(segment), intro_time + len(segment) + intro_time + outro_time)
    print('soundbed rms %s' % soundbed.rms)
    print('soundbed rms %s' % soundbed.sample_width)
    print('voice rms %s' % segment.rms)

    total_time_needed = intro_time + outro_time + len(segment)
    start_offset = random.randint(0, len(soundbed) - total_time_needed - 50)
    intro = soundbed[start_offset:start_offset + intro_time]
    talking = (segment + 3) * (soundbed[start_offset + intro_time:start_offset + intro_time + len(segment)]  - 4)
    outro = soundbed[start_offset + intro_time + len(segment):start_offset + intro_time + len(segment) + outro_time]
    talking_segment = intro + talking + outro
    talking_segment.fade_out(int(outro_time * 0.8))
    tf = tempfile.mkstemp(suffix = '.mp3', dir = self.tts_workdir)
    talking_segment.export(tf[1], format='mp3')
    return talking_segment

  def mk_song_id(self, song):
    return '%s by %s' % (song['title'], song['artist'])

  def mk_song_ids_string(self, songs):
    songs = listify(songs)
    if len(songs) == 1:
      return listify(self.mk_song_id(songs[0]))
    else:
      return [self.mk_song_id(s) + ', ' for s in songs[0:-1]] + listify(' and ' + self.mk_song_id(songs[-1]) + '.')

  def mk_backwards_song_id(self, song):
    return '%s with %s' % (song['artist'], song['title'])

  def mk_backwards_song_ids_string(self, songs):
    songs = listify(songs)
    if len(songs) == 1:
      return listify(self.mk_backwards_song_id(songs[0]))
    else:
      return [self.mk_backwards_song_id(s) + ', ' for s in songs[0:-1]] + listify(' and ' + self.mk_song_id(songs[-1]) + '.')


  def buildPodcast(self):
    if self.voice in getMacVoices():
      self.intro_text += '. I\'m your host, ' + self.voice + ', we\'ve got a great show coming up.'
    intro = self.mk_tts_tmp(self.intro_text, outro_time = 10)

    playlist = intro
    last_id_index = 0

    def getNextIntroText():
      options = [
        'Up next',
        'Next up',
        'Coming up',
        'We\'ve got',
        'Stay tuned for'
      ]
      return random.choice(options)

    def getPreviousIdentText():
      options = [
        'That was',
        'You just heard',
        'Coming off of that set, we had'
      ]
      return random.choice(options)

    def print_counter(s):
      playlist_secs = len(playlist) / 1000
      print('%s at %s:%02d' % (unicodeify(s), playlist_secs / 60, playlist_secs % 60))

    # this is stupid
    id_positions = [2, 5, 8, 10, 13, 17, 19, 21, 25, 28, 31, 34, 37, 40, 42, 45, 47]

    print(len(self.songs))
    for index, s in enumerate(self.songs):
      segment = AudioSegment.from_mp3(s['local_file'])
      print_counter('switch to %s' % self.mk_song_ids_string(s))
      playlist = playlist.append(segment, crossfade=(10 * 1000))

      print('LAST ID INDEX: %s' % last_id_index)
      print('INDEX: %s' % index)
      print(len(self.songs))
      last_song_block = self.songs[last_id_index:index + 1]
      print(last_song_block)
      if index in id_positions or index == len(self.songs) - 1:
        id_tts_string = []
        if last_song_block:
          if random.random() < 0.7:
            ids = self.mk_song_ids_string(last_song_block)
          else:
            ids = self.mk_backwards_song_ids_string(last_song_block)
          id_tts_string = listify(getPreviousIdentText()) + ids + listify('.')

        last_id_index = index + 1
        if index < len(self.songs) - 1:
          id_tts_string += listify(str(getNextIntroText())) + self.mk_song_ids_string(self.songs[index + 1:index + 2])
          last_id_index = index + 2

        outro_time = 10
        if index == len(self.songs) - 1:
          id_tts_string += listify('Thanks for listening.')
          outro_time = 30
        id_file = self.mk_tts_tmp(id_tts_string, intro_time = 10, outro_time = outro_time)
        print_counter('talking')
        playlist = playlist.append(id_file)

    playlist = playlist.fade_out(30)

    print('Writing out, this will take a bit')
    out_filename = self.get_filename('mp3')
    out_f = open(out_filename, 'wb')

    playlist.export(out_f, format='mp3', tags={'artist': 'Hype Machine Robot Radio', 'track': self.track_name})
    print('Done, written to %s' % out_filename)
    return out_filename

  def get_filename(self, ext):
    return os.path.join(self.output_dir, "hypepod-%s-%s-%s.%s" % (self.mode.replace('/', '_'), self.voice, datetime.datetime.now().strftime("%Y-%m-%d"), ext))

  def makeRss(self):
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.id('http://hypecast.blackmad.com/' + self.mode)
    fg.title('Hype Machine Robot Radio: ' + self.mode)
    fg.author( {'name':'David Blackmad','email':'hypepod@davidblackman.com'} )
    fg.logo('http://dump.blackmad.com/the-hype-machine.jpg')
    fg.language('en')
    fg.link(href='http://hypecast.blackmad.com/' + self.mode)
    fg.description('Hype Machine Robot Radio: ' + self.mode)

    description = ' <br/>'.join(['%s. %s' % (index + 1, self.mk_song_id(s)) for index, s in enumerate(self.songs)])

    fe = fg.add_entry()
    fe.title(self.track_name)
    fe.description(description)
    fe.id(self.filename)
    # add length
    print(self.relative_dir)
    print(self.filename)
    fe.enclosure(url = 'http://hypecast.blackmad.com/%s' % (self.filename), type="audio/mpeg")

    rss_str = fg.rss_str()
    newItem = ET.fromstring(rss_str)[0].find('item')
    out = open(self.get_filename('xml'), 'w')
    out.write(ET.tostring(newItem))
    out.close()
    self.updateRss()

  def updateRss(self):
    opening_xml = """<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"><channel><title>Hype Machine Robot Radio: %(mode)s</title><link>http://hypecast.blackmad.com/%(mode)s</link><description>Hype Machine Robot Radio: %(mode)s</description><docs>http://www.rssboard.org/rss-specification</docs><generator>python-feedgen</generator><image><url>http://dump.blackmad.com/the-hype-machine.jpg</url><title>Hype Machine Robot Radio: %(mode)s</title><link>http://hypecast.blackmad.com/%(mode)s</link></image><language>en</language><lastBuildDate>%(date)s</lastBuildDate>""" % {
      'mode': self.mode,
      'date': datetime.datetime.now()
    }
    closing_xml =  """</channel></rss>"""

    xml = opening_xml
    xmlfiles = sorted([ os.path.join(self.output_dir,f) for f in os.listdir(self.output_dir) if f != 'podcast.xml' and f.endswith('.xml') ])
    xmlfiles.reverse()
    for x in xmlfiles:
      print('processing xml: ' + x)
      xml += open(x).read()
    xml += closing_xml

    podcast_xml_filename = os.path.join(self.output_dir, 'podcast.xml')
    podcast_xml_file = open(podcast_xml_filename, 'w')
    podcast_xml_file.write(xml)
    podcast_xml_file.close()

  def makePassThroughRss(self):
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.id('http://hypecast.blackmad.com/' + self.mode)
    fg.title('Hype Machine PassThru Radio: ' + self.mode)
    fg.author( {'name':'David Blackmad','email':'hypepod@davidblackman.com'} )
    fg.logo('http://themelkerproject.com/wp-content/uploads/2013/10/the-hype-machine.jpg')
    fg.language('en')
    fg.link(href='http://hypecast.blackmad.com/' + self.mode)
    fg.description('Hype Machine PassThru: ' + self.mode)

    # description = '<br/>'.join(['%s. %s' % (index + 1, self.mk_song_id(s)) for index, s in enumerate(self.songs)])

    for s in self.songs:
      fe = fg.add_entry()
      fe.title(self.mk_song_id(s))
      fe.id(s['mediaid'])
      fe.description(s['description'])
      fe.podcast.itunes_image(s['thumb_url'])
      # add length
      fe.enclosure(url = 'http://hypecast.blackmad.com/%s/%s' % ('hypecasts', s['filename']), type="audio/mpeg")

    podcast_xml_file = os.path.join(self.output_dir, 'podcast.xml')
    fg.rss_file(podcast_xml_file)

  def __init__(self, args):
    pass

  def make(self, args):
    self.voice = args.voice

    self.workdir = '/tmp/hypem'
    self.tts_workdir = os.path.join(self.workdir, 'tts')
    if not os.path.exists(self.workdir):
      os.mkdir(self.workdir)
    if not os.path.exists(self.tts_workdir):
      os.mkdir(self.tts_workdir)

    self.intro_text = ''
    self.track_name = ''

    def makeDate(mydate):
      return '%s %s %s' % (mydate.strftime("%B"),
        ordinal(int(mydate.strftime("%d"))),
        mydate.strftime("%Y"))


    if args.mode == 'popular':
      self.mode = 'popular/%s' % (args.when)

      mydate = datetime.datetime.now()
      date_text = makeDate(mydate)
      if args.when == 'lastweek':
        for_text = ' for the week of %s' % date_text
      elif args.when == 'now':
        for_text = ' for ' + date_text
      elif args.when == '3day':
        for_text = ' for the three days leading up to %s' % date_text
      elif args.when == 'noremix':
        for_text = ' without remixes for the week %s' % date_text
      elif 'week:' in args.when:
        week = args.when.split(':')[1]
        weektime = datetime.datetime.strptime(week, '%b-%d-%Y')
        for_text = ' from back in the week of %s' % makeDate(weektime)

      self.track_name = for_text.replace(' for ', '').capitalize()
      if 'week:' in args.when:
        self.intro_text = 'Welcome to hype machine robot radio ... time machine ... %s' % (for_text)
      else:
        self.intro_text = 'Welcome to hype machine robot radio %s' % (for_text)

    elif args.mode == 'favorites':
      self.mode = 'users/%s/favorites' % (args.user)
      url = 'https://api.hypem.com/api/get_profile?username=%s&key=%s' % (args.user, HYPE_API_KEY)
      print(url)
      response = urllib.request.urlopen(url)
      response = json.loads(response.read())
      print(response)
      name = response['username']
      if 'fullname' in response:
        name = response['fullname']
      self.intro_text = 'You are listening to %s\'s loved tracks on hype machine, robot radio' % (args.user)
      self.track_name = '%s\'s loved tracks' % name

    if args.feedonly:
      self.voice = 'feedonly'
    if 'week:' in self.mode:
      self.relative_dir = os.path.join('timemachine', self.voice)
    else:
      self.relative_dir = os.path.join(self.mode, self.voice)
    if not os.path.exists(args.basedir):
      print('basedir %s doesn\'t exist' % args.basedir)
      sys.exit(1)
    self.output_dir = os.path.join(args.basedir, self.relative_dir)
    if not os.path.exists(self.output_dir):
      os.makedirs(self.output_dir)

    if args.update:
      self.updateRss()
      return

    self.max_pages = 1
    if args.max_pages == 0:
      if args.mode == 'favorites' and args.feedonly:
        self.max_pages = 1000000
    else:
      self.max_pages = args.max_pages

    if args.feedonly:
      self.workdir = self.output_dir

    self.songs = self.getSongs()
    self.songs = self.downloadSongs()
    self.songs = [s for s in self.songs if 'local_file' in s]
    if not args.feedonly:
      self.filename = self.buildPodcast()
      self.makeRss()
    else:
      self.makePassThroughRss()

def main():
  def onMac():
    return os.path.exists('/usr/bin/say')

  voices = ['Google']
  if onMac():
    hasHighQualityOsXVoices()
    voices += getMacVoices()

  parser = argparse.ArgumentParser(description='Make a hypecast.')
  parser.add_argument('--mode', '-m', nargs='?', help='mode: popular, favorites', default='popular', choices= ['popular', 'favorites'])
  parser.add_argument('--when', '-w', nargs='?', help='when to fetch popular -- choices are lastweek, now, 3day, noremix, or week:MMM-DD-YYYY', default='lastweek')
  parser.add_argument('--voice', '-v', help='what voice to use', default='Ava', choices=voices + ['Ava',])
  parser.add_argument('--user', '-u', nargs='?', help='user for favorites mode')
  parser.add_argument('--basedir', '-d', nargs='?', default = './hypecasts', help='where to output finished data to')
  parser.add_argument('--max_pages', '-p', default=0, type=int, help='max pages to download, defaults to 1 for popular, -1 for favorites ')
  parser.add_argument("-f", "--feedonly", action="store_true", dest="feedonly", help='if set, don\'t chunk into robot podcasts')
  parser.add_argument("--update", action="store_true", dest="update", help='update rss, no mp3 building')
  args = parser.parse_args()

  generator = HypePodGenerator(args)
  generator.make(args)

main()
