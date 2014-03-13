#!/bin/sh

rsync -avz -e ssh hypepod.blackmad.com:~/sites/hypecasts/hypecasts .
./hypecast.py -v Ava -w noremix
./hypecast.py -v Ava -w 3day
./hypecast.py -v Ava -w lastweek
rsync -avz -e ssh hypecasts hypepod.blackmad.com:~/sites/hypecasts/

