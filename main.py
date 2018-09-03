#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p "with python3Packages; [GitPython beautifulsoup4 requests dateparser icalendar urllib3 chardet python]"

from bs4 import BeautifulSoup
import requests
import dateparser
from urllib.parse import urljoin
import re
from icalendar import Event, Calendar
import git

ENTRY_URL = 'https://www.rijksoverheid.nl/onderwerpen/schoolvakanties/overzicht-schoolvakanties-per-schooljaar'
PARSER = 'html.parser'
CONTENT_ID = 'content'

def get_prodid():
    repo = git.Repo()
    return repo.git.describe()

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
    for time in begin, end:
        yield dateparser.parse(time, languages=['nl'])

def ends_in_year(datestring):
    return re.fullmatch(r'^.*\d{4}$', datestring)

def parse_data(url):
    calendars = dict()
    print(url)
    soup = soupify_url(url)
    table_headers = soup.find_all('th', scope='col')
    regions = [header.string for header in table_headers]
    print(regions)
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

            print(region, name, begin, end, sep=" - ")
            calendars.setdefault(region, []).append(event)

    return calendars

def generate_calendar(entry_url=ENTRY_URL):
    calendars = dict()
    urls = data_urls(entry_url)
    for url in urls:
        for region, events in parse_data(url).items():
            for event in events:
                calendar = calendars.setdefault(region, Calendar())
                calendar['prodid'] = 'Synthetica9'
    return calendars

if __name__ == '__main__':
    generate_calendar()
