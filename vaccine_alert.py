# This script checks https://www.mtreadyclinic.org/ every N minutes and
# emails a notification if new appointments are avaliable.
import time
from datetime import datetime
import pathlib
import json
import collections
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

Site = collections.namedtuple('Site', ['found', 'site', 'site_info'])

def get_html(url, search_params):
    """
    Get the html text.
    """
    params = '&'.join([f'{k}={v}' for k,v in search_params.items()])
    r = requests.get(url, params=params)
    return r

def parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Get the list of avaliable vaccine sites
    vaccine_site_list = soup.find_all('div', class_='md:flex-shrink text-gray-800')

    sites = {}

    for vaccine_site in vaccine_site_list:
        # Get the site name, date, and address.
        site_name_date_soup = vaccine_site.find('p', class_='text-xl font-black')
        site_name_date_str = site_name_date_soup.text.strip()
        site_name = site_name_date_str.split(' on ')[0]
        sites[site_name] = {}
        sites[site_name]['date'] = site_name_date_str.split(' on ')[1]
        sites[site_name]['address'] = site_name_date_soup.find_next_sibling().text.strip()

        sites[site_name]['vaccinations offered'] = vaccine_site.find('strong', 
            text='Vaccinations offered:').find_next_sibling().text.strip()

        # Get the number of avalible appointments
        sites[site_name]['appointments'] = int(
                vaccine_site.find('strong', text='Available Appointments:').next.next.strip()
                )
    return sites

def detect_change(current_sites, 
                json_file_name='vaccination_sites.json', 
                search_address='Bozeman'):
    """
    This function detects when the address appears on the vaccination site list and
    sends an email.

    Truth table (True/False refers to if search_address is found in the site list)
    1. current_sites = True  and past_sites = True, DON'T SEND
    2. current_sites = True  and past_sites = False, SEND
    3. current_sites = False and past_sites = True, DON'T SEND
    4. current_sites = False and past_sites = False, DON'T SEND
    """

    # If json_file_name exists, look for search_address in the current_sites 
    # and past_sites and send an email if the search_address was added between
    # the current and past site lists.
    if pathlib.Path(json_file_name).exists():
        # Load the most recent JSON site file and check what changed.
        with open(json_file_name, 'r') as f:
            past_sites = json.load(f)

        # Save the updated list
        with open(json_file_name, 'w') as f:
            json.dump(current_sites, f)

        # Look for matched site in the past list of sites.
        past_matched_site = _find_matching_site(past_sites, search_address)
        print('past_matched_site', past_matched_site)
        # Look for matched site in the current list of sites.
        current_matched_site = _find_matching_site(current_sites, search_address)
        print('current_matched_site', current_matched_site)
        if current_matched_site.found and (not past_matched_site.found):
            return current_matched_site
        else:
            return Site(False, None, None)

    else:
        # If this program is run for the first time and json_file_name does not
        # exist, look for search_address in current_sites and email the address matches.
        matched_site = _find_matching_site(current_sites, search_address)

        # Save the file
        with open(json_file_name, 'w') as f:
            json.dump(current_sites, f)

        return matched_site
    return

def send_email(matched_site, recipients, vaccine_url):
    """
    Sends an email if a vaccination site opens up.
    """
    port = 465  # For SSL
    with open('password.txt') as f:
        password = f.read()

    text = (
        f'Hello!\n\nI found a recently-avaliable vaccination site that may interest you!\n\n'
        f'site: {matched_site.site}\n'
    )

    for key, val in matched_site.site_info.items():
        text += f'{key}: {val}\n'

    text += f'\nSearch results are at: {vaccine_url}\n'
    text += f'This is an automated message. Blame Mike if you are getting spammed!'

    # Create a secure SSL context
    context = ssl.create_default_context()

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Vaccine Site Avaliability Alert"
    message["From"] = 'shumko.ghost+vaccine_alert@gmail.com'
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(text, 'plain'))

    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login("shumko.ghost@gmail.com", password)
        server.sendmail("shumko.ghost+vaccine_alert@gmail.com", recipients, 
                        message.as_string())

    return

def _find_matching_site(sites, search_address):
    """
    Searches the sites dictionary and looks for search_address in the 'address'
    key:value pair. This is case insensitive.
    """
    for site, site_info in sites.items():
        if search_address.lower() in site_info['address'].lower():
            return Site(True, site, site_info)
    return Site(False, None, None)

if __name__ == '__main__':
    sleep_time_min = 10

    search_params = {
        'location':59715,
        'search_radius':'50+miles'
    } 

    recipients = ['shumko.ghost@gmail.com', 'msshumko@gmail.com', 'zethstone@gmail.com']

    search_address = 'Bozeman'

    url = 'https://www.mtreadyclinic.org/clinic/search/'

    while True:
        # Don't check in the middle of the night.
        if (datetime.now().hour >= 6) and (datetime.now().hour <= 22):
            request = get_html(url, search_params)
            print(request.url)
            current_sites = parse_html(request.text)
            matched_site = detect_change(current_sites, search_address=search_address)
            
            if matched_site.found:
                # Send out the email.
                send_email(matched_site, recipients, request.url)

            print('Last ran at:', datetime.now().isoformat())

        time.sleep(60*sleep_time_min)