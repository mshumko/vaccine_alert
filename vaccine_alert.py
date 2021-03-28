# This script checks https://www.mtreadyclinic.org/ every N minutes and
# emails a notification if new appointments are avaliable.
import time
from datetime import datetime
import pathlib
import json
import collections
import smtplib
import csv
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

Site = collections.namedtuple('Site', ['site', 'site_info'])

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
        past_matched_sites = _find_site_in_html(past_sites, search_address)
        print('past_matched_site', past_matched_sites)
        # Look for matched site in the current list of sites.
        current_matched_sites = _find_site_in_html(current_sites, search_address)
        print('current_matched_sites', current_matched_sites)

        if len(current_matched_sites):
            # Find what matched sites are new and updated.
            old_sites = []
            new_sites = []

            past_site_names = [past_matched_site.site for past_matched_site in past_matched_sites]
            past_site_dates = [past_matched_site.site_info['date'] for past_matched_site in past_matched_sites]
            past_site_tuple = [(name, date) for name, date in zip(past_site_names, past_site_dates)]

            for current_matched_site in current_matched_sites:
                current_site_tuple = (current_matched_site.site, current_matched_site.site_info['date'])
                if current_site_tuple in past_site_tuple:
                    old_sites.append(current_matched_site)
                else:
                    new_sites.append(current_matched_site)
            return {'new_sites':new_sites, 'old_sites':old_sites}
        else:
            return None

    else:
        # If this program is run for the first time and json_file_name does not
        # exist, look for search_address in current_sites and email the address matches.
        new_sites = _find_site_in_html(current_sites, search_address)

        # Save the file
        with open(json_file_name, 'w') as f:
            json.dump(current_sites, f)

        return {'new_sites':new_sites, 'old_sites':[]}
    return

def send_email(matched_sites_dict, recipients, vaccine_url):
    """
    Sends an email if a vaccination site opens up.
    """
    port = 465  # For SSL
    with open('password.txt') as f:
        password = f.read()

    if matched_sites_dict is None:
        return

    new_sites = matched_sites_dict['new_sites']
    old_sites = matched_sites_dict['old_sites']

    if len(new_sites) == 0:
        return

    # Write the text body
    text = (
        f'Hello!\n\nI found a recently-avaliable vaccination site that may interest you!\n\n'
        f'NEW vaccination sites:\n\n'
    )
    for new_site in new_sites:
        text += f'site: {new_site.site}\n'
        for key, val in new_site.site_info.items():
            text += f'{key}: {val}\n'
    
    if len(old_sites):
        text += '\n\nOLD Vaccination sites:\n\n'
    
        for old_site in old_sites:
            text += f'site: {old_site.site}\n'
            for key, val in old_site.site_info.items():
                text += f'{key}: {val}\n'
            text += '\n\n'

    text += f'Search results are at: {vaccine_url}\n\n'
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

def _find_site_in_html(sites, search_address):
    """
    Searches the sites dictionary and looks for search_address in the 'address'
    key:value pair. This is case insensitive.
    """
    matched_sites = []
    for site, site_info in sites.items():
        if search_address.lower() in site_info['address'].lower():
            matched_sites.append(Site(site, site_info))
    return matched_sites

if __name__ == '__main__':
    # Program parameters
    sleep_time_min = 10
    debug = False
    search_address = 'Bozeman'
    url = 'https://www.mtreadyclinic.org/clinic/search/'
    search_params = {
        'location':59715,
        'search_radius':'50+miles'
    } 

    if debug:
        recipients = ['shumko.ghost@gmail.com']
    else:
        # Load email list
        with open('email_list.csv') as f:
            reader = csv.reader(f)
            recipients = [row[0] for row in list(reader)]

    while True:
        # Don't check in the middle of the night.
        if ((datetime.now().hour >= 6) and (datetime.now().hour <= 22)) or debug:
            if debug:
                with open('old_listing.html') as f:
                    current_sites = parse_html(f.read())
            else:
                request = get_html(url, search_params)
                current_sites = parse_html(request.text)
            matched_sites_dict = detect_change(current_sites, search_address=search_address)
            
            
            # Send out the email. (This function will only send it out if a new site is added.)
            if debug:
                send_email(matched_sites_dict, recipients, 'Debug')
            else:
                send_email(matched_sites_dict, recipients, request.url)

            print('Last ran at:', datetime.now().isoformat())

        time.sleep(60*sleep_time_min)