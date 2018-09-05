#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p "with python3Packages; [GitPython flask beautifulsoup4 requests dateparser icalendar urllib3 chardet python]"

__author__ = 'Synthetica9'
__package__ = 'schoolvakanties'

from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

from flask import Flask, Response

import dateparser
from datetime import *
from time import time

from icalendar import Event, Calendar

import re
import git
import os
from functools import wraps
from uuid import uuid4
from io import StringIO

ENTRY_URL = 'https://www.rijksoverheid.nl/onderwerpen/schoolvakanties/overzicht-schoolvakanties-per-schooljaar'
PARSER = 'html.parser'
CONTENT_ID = 'content'
ICAL_VERSION = '2.0'
DATE_FORMAT = '%Y%m%d'
DATETIME_UTC_FORMAT = '%Y%m%dT%H%SZ'
TIMEZONE = 'Europe/Amsterdam'
UID_POSTFIX = "@schoolvakanties.herokuapp"

try:
    repo = git.Repo()
    SOURCE_VERSION = repo.git.describe(always=True)
except:
    with open('.source_version', 'r') as f:
        SOURCE_VERSION = f.read().strip()

def get_prodid():
    author = __author__
    package = __package__
    return f'-//{author}//{package}-{SOURCE_VERSION}//NL'


PRODID = get_prodid()
# get_data_urls parses https://www.rijksoverheid.nl/onderwerpen/schoolvakanties/overzicht-schoolvakanties-per-schooljaar

# http://book.pythontips.com/en/latest/function_caching.html


def cache(duration=None, **kwargs):
    if duration is not None:
        assert not kwargs

    else:
        duration = timedelta(**kwargs)

    if isinstance(duration, timedelta):
        duration = duration.total_seconds()

    def wrapper(function):
        memo = {}

        @wraps(function)
        def wrapped(*args):
            try:
                memo_time, memo_rv = memo[args]
            except KeyError:
                pass
            else:
                if memo_time + duration > time():
                    print('Using cached value')
                    return memo_rv

            rv = function(*args)
            memo[args] = (time(), rv)
            return rv
        return wrapped
    return wrapper


def soupify_url(url, parser=PARSER):
    print('Grabbing url:', url)
    r = requests.get(url)
    return BeautifulSoup(r.text, parser)


def data_urls(entry_url=ENTRY_URL):
    soup = soupify_url(entry_url)
    for a in soup.find('div', id=CONTENT_ID).find_all('a'):
        relative_url = a.get('href')
        absolute_url = urljoin(entry_url, relative_url)
        yield absolute_url


def parse_daterange(to_parse):
    begin, end = to_parse.split(' t/m ')
    assert(ends_in_year(end))
    year = end[-4:]
    if not ends_in_year(begin):
        begin += ' ' + year
    for timestring in begin, end:
        date = dateparser.parse(timestring, languages=['nl'])
        if timestring == end:
            # Ends are exclusive in ical
            date += timedelta(days=1)
        yield date.strftime(DATE_FORMAT)


def ends_in_year(datestring):
    return re.fullmatch(r'^.*\d{4}$', datestring)


def gen_UID(name, region, begin, end):
    return "-".join((name, region.replace(' ', ''), begin, end)) + UID_POSTFIX


def utc_now():
    return datetime.utcnow().strftime(DATETIME_UTC_FORMAT)


def parse_data(url):
    calendars = dict()
    description = f'Source: {url}'
    soup = soupify_url(url)
    table_headers = soup.find_all('th', scope='col')
    regions = [header.string for header in table_headers]
    rows = soup.tbody.find_all('tr')
    for row in rows:
        name = row.th.p.string
        for region, date in zip(regions, row.find_all('td')):
            begin, end = parse_daterange(date.string)

            event = Event()
            d = {
                'summary': name,
                'location': region,
                'dtstart;value=date': begin,
                'dtend;value=date': end,
                'uid': gen_UID(name, region, begin, end),
                'description': description,
                'last-modified': utc_now(),
            }
            for k, v in d.items():
                event[k] = v

            calendars.setdefault(region, []).append(event)

    return calendars


@cache(days=7)
def generate_calendars(entry_url=ENTRY_URL):
    calendars = dict()
    urls = data_urls(entry_url)
    for url in urls:
        for region, events in parse_data(url).items():
            calendar = calendars.setdefault(
                region.replace(' ', ''), Calendar())
            name = f'Schoolvakanties {region}'
            calendar['prodid'] = PRODID
            calendar['version'] = ICAL_VERSION
            calendar['name'] = name
            calendar['x-wr-calname'] = name
            calendar['x-wr-timezone'] = TIMEZONE
            for event in events:
                calendar.add_component(event)
    return calendars


app = Flask(__name__)


@app.route('/<region>.ical')
def region_ical(region):
    calendars = generate_calendars()
    try:
        content = calendars[region].to_ical()
    except KeyError:
        return 'Region not found', 404

    resp = Response(content)
    resp.headers['Content-type'] = 'text/calendar; charset=utf-8'
    return resp


@app.route('/')
def index():
    sb = StringIO()
    calendars = generate_calendars()

    sb.write('<h1>Available Calendars</h1>')
    for calendar in calendars:
        sb.write(f'<li><a href="/{calendar}.ical">{calendar}</a></li>')
    sb.write('''
        <br />
        <a href="https://github.com/Synthetica9/schoolvakanties">
            Source code
        </a>''')
    return sb.getvalue()

generate_calendars()  # Warm up the cache.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 33507))
    app.run(port=port)
