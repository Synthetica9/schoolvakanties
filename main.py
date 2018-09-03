#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p "with python3Packages; [GitPython beautifulsoup4 requests dateparser icalendar urllib3 chardet python]"

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

ENTRY_URL = 'https://www.rijksoverheid.nl/onderwerpen/schoolvakanties/overzicht-schoolvakanties-per-schooljaar'
PARSER = 'html.parser'
CONTENT_ID = 'content'
ICAL_VERSION = '2.0'

def get_prodid():
    try:
        repo = git.Repo()
        version = repo.git.describe(always=True)
    except git.exc.InvalidGitRepositoryError:
        version = os.environ['SOURCE_VERSION']

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
        yield date.isoformat()

def ends_in_year(datestring):
    return re.fullmatch(r'^.*\d{4}$', datestring)

def parse_data(url):
    calendars = dict()
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
            event['dtstart'] = begin
            event['dtend'] = end

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
            for event in events:
                calendar.add_component(event)
    return calendars

def static_root():
    with open("static.json") as f:
        j = json.load(f)
        return j['root']

def main():
    root = static_root()
    os.makedirs(root, exist_ok=True)
    for region, calendar in generate_calendars().items():
        path = os.path.join(root, region + '.ical')
        with open(path, 'wb') as f:
            f.write(calendar.to_ical())

if __name__ == '__main__':
    print(static_root())
    main()
