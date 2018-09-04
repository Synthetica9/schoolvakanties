#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p "with python3Packages; [GitPython flask beautifulsoup4 requests dateparser icalendar urllib3 chardet python]"

__author__ = 'Synthetica9'
__package__ = 'schoolvakanties'

from bs4 import BeautifulSoup
import requests
import dateparser
from urllib.parse import urljoin
import re
from icalendar import Event, Calendar
import git
import json
import os
from flask import Flask, Response

from uuid import uuid4

ENTRY_URL = 'https://www.rijksoverheid.nl/onderwerpen/schoolvakanties/overzicht-schoolvakanties-per-schooljaar'
PARSER = 'html.parser'
CONTENT_ID = 'content'
ICAL_VERSION = '2.0'
DATE_FORMAT = 'DATE:%Y%m%d'
TIMEZONE = 'Europe/Amsterdam'

def get_prodid():
    try:
        repo = git.Repo()
        version = repo.git.describe(always=True)
    except:
        with open('.source_version', 'r') as f:
            version = f.read().strip()

    author = __author__
    package = __package__
    return f'-//{author}//{package}-{version}//NL'


PRODID = get_prodid()
# get_data_urls parses https://www.rijksoverheid.nl/onderwerpen/schoolvakanties/overzicht-schoolvakanties-per-schooljaar

def soupify_url(url, parser=PARSER):
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
    year = end[-4:]
    if not ends_in_year(begin):
        begin += " " + year
    for timestring in begin, end:
        date = dateparser.parse(timestring, languages=['nl'])
        yield date.strftime(DATE_FORMAT)

def ends_in_year(datestring):
    return re.fullmatch(r'^.*\d{4}$', datestring)

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
            event['summary'] = name
            event['location'] = region
            event['dtstart;value'] = begin
            event['dtend;value'] = end
            event['uid'] = uuid4()
            event['description'] = description

            calendars.setdefault(region, []).append(event)

    return calendars

def generate_calendars(entry_url=ENTRY_URL):
    calendars = dict()
    urls = data_urls(entry_url)
    for url in urls:
        for region, events in parse_data(url).items():
            calendar = calendars.setdefault(region.replace(' ', ''), Calendar())
            calendar['prodid'] = PRODID
            calendar['version'] = ICAL_VERSION
            calendar['summary'] = f'Schoolvakanties {region}'
            calendar['x-wr-timezone'] = TIMEZONE
            for event in events:
                calendar.add_component(event)
    return calendars


app = Flask(__name__)
calendars = generate_calendars()

@app.route('/<region>.ical')
def region_ical(region):
    try:
        content = calendars[region].to_ical()
    except KeyError:
        return "Region not found", 404

    resp = Response(content)
    resp.headers['Content-type'] = 'text/calendar; charset=utf-8'
    return resp

port = int(os.environ.get('PORT', 33507))
if __name__ == "__main__":
    app.run(port=port)
