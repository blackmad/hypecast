#!/usr/bin/env python

import sys
import tempfile
import string
import time
import logging
import json
import urllib2
import os.path
import urllib, urllib2
from os import path
import pydub
import shutil
from pydub import AudioSegment
from pydub.utils import db_to_float
from api_keys import *

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

def getMoreSongs( page = 1):
  print 'fetching again, page %d' % page
  url = 'http://api.hypem.com/playlist/popular/lastweek/json/%s/data.json?key=%s' % (page, HYPE_KEY)
  print 'fetching %s' % url
  response = urllib2.urlopen(url)
  response = json.loads(response.read())
  return [response[key] for key in sorted(response.keys()) if key.isdigit()]
 
def get_tts_mp3(sent, fname=None ):
    lang = 'en'
    print "Retrieving .mp3 for sentence: %s" % sent
    baseurl  = "http://translate.google.com/translate_tts"
    values   = { 'q': sent, 'tl': lang }
    data     = urllib.urlencode(values)
    request  = urllib2.Request(baseurl, data)
    request.add_header("User-Agent", "Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11" )
    response = urllib2.urlopen(request)
    if( fname==None ):
        fname = "_".join(sent.split())
    ofp = open(fname,"wb")
    ofp.write(response.read())
    print "Saved to file: %s" % fname
    return

def downloadSongs(songs, path):
  for index, s in enumerate(songs):
    print 'Downloading %s of %s songs' % (index + 1, len(songs))
    filename = '%s - %s.mp3' % (s['artist'], s['title'])
    filepath = os.path.join(path, filename)
    if not os.path.exists(filepath):
      req = urllib2.urlopen(s['stream_url_raw'])
      with open(filepath, 'wb') as fp:
        shutil.copyfileobj(req, fp)
    s['local_file'] = filepath

def mk_tts_tmp(texts, intro_time = 2, outro_time = 4):
  texts = listify(texts)

  segment = None
  if os.path.exists('/usr/bin/say'):
    # print 'Using OS X Say'
    text = ' '.join(texts)
    print ' ---> %s ' % text
    tf = tempfile.mkstemp(suffix = '.aiff')
    cmd = 'say  -o %s "%s"' % (tf[1], text)
    # print cmd
    os.system(cmd)
    # print tf[1]
    segment = AudioSegment.from_file(tf[1])
  else:
    for text in texts:
      print text
      tf = tempfile.mkstemp(suffix = '.mp3')
      if len(text) > 99:
        print 'text too longfor google tts ' + text
      get_tts_mp3(text, tf[1])
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

  intro = soundbed[0:intro_time]
  talking = segment * soundbed[intro_time:intro_time + len(segment)]
  outro = soundbed[intro_time + len(segment):intro_time + len(segment) + outro_time]
  talking_segment = intro + talking + outro
  talking_segment.fade_out(int(outro_time * 0.8))
  return talking_segment

def listify(v):
  if not isinstance(v, list):
    return [v,]
  return v

def mk_song_id(song):
  return '%s by %s' % (song['title'], song['artist'])

def mk_song_ids_string(songs):
  songs = listify(songs)
  if len(songs) == 1:
    return listify(mk_song_id(songs[0]))
  else:
    return [mk_song_id(s) + ', ' for s in songs[0:-1]] + listify(' and ' + mk_song_id(songs[-1]) + '.')

import datetime
ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n/10%10!=1)*(n%10<4)*n%10::4])
def buildPodcast(songs):
  mydate = datetime.datetime.now()
  
  intro = mk_tts_tmp('Welcome to hype machine robot radio for %s %s %s' % (
    mydate.strftime("%B"), 
    ordinal(int(mydate.strftime("%d"))),
    mydate.strftime("%Y")), outro_time = 10)

  playlist = intro
  last_id_index = 0

  def print_counter(s):
    playlist_secs = len(playlist) / 1000
    print '%s at %s:%s' % (s, playlist_secs / 60, playlist_secs % 60)

  id_positions = [2, 5, 8, 10, 13, 17, 19, 21]

  for index, s in enumerate(songs):
    segment = AudioSegment.from_mp3(s['local_file'])
    print_counter('switch to %s' % mk_song_ids_string(s))
    playlist = playlist.append(segment, crossfade=(10 * 1000))
    
    last_song_block = songs[last_id_index:index + 1]
    if index in id_positions or index == len(songs):
      ids = mk_song_ids_string(last_song_block)
      id_tts_string = listify('You just heard ') + ids 
      last_id_index = index + 1
      if index < len(songs) - 1:
        id_tts_string += listify('Up next ') + mk_song_ids_string(songs[index + 1:index + 2])
        last_id_index = index + 2
      outro_time = 10
      if index == len(songs):
        id_tts_string += listify('Thanks for listening.')
        outro_time = 30
      id_file = mk_tts_tmp(id_tts_string, intro_time = 10, outro_time = outro_time)
      print_counter('talking')
      playlist = playlist.append(id_file)

  playlist = playlist.fade_out(30)
  
  out_filename = "hypepod-%s.mp3" % mydate.strftime("%m-%d-%Y")
  out_f = open(out_filename, 'wb')
  playlist.export(out_f, format='mp3')
  print 'Done, written to %s' % out_filename

def main():
  workdir = '/tmp/hypem'
  if not os.path.exists(workdir):
    os.mkdir(workdir)
  songs = getMoreSongs()
  downloadSongs(songs, workdir)
  buildPodcast(songs)

main()
