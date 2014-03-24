#!/bin/sh

rsync -avz -e ssh hypepod.blackmad.com:~/sites/hypecasts/hypecasts .
./hypecast.py -v Ava -w noremix
./hypecast.py -v Ava -w 3day
./hypecast.py -v Ava -w lastweek
./hypecast.py -v Ava -w week:$(python -c 'import datetime; import dateutil.relativedelta; print (datetime.datetime.now() + dateutil.relativedelta.relativedelta(years=-1)).strftime("%b-%d-%Y")')
rsync -avz -e ssh hypecasts hypepod.blackmad.com:~/sites/hypecasts/

