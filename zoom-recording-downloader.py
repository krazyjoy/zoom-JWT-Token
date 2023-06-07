
from tqdm import tqdm

from appenv import JWT_TOKEN # HERE SETUP VARIABLE
from sys import exit
from signal import signal, SIGINT
from dateutil.parser import parse
import datetime
from datetime import date
from dateutil import relativedelta
from datetime import date, timedelta
import itertools
import requests
import time
import sys
import os
import json




requests.adapters.DEFAULT_RETRIES = 5

class color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def API_ENDPOINT_RECORDING_LIST(email):
    API_ENDPOINT = 'https://api.zoom.us/v2/users/' + email + '/recordings'
    return API_ENDPOINT


def get_credentials(host_id, page_number, rec_start_date):
    return {
        'host_id': host_id,
        'page_number': page_number,
        'from': rec_start_date,
    }


def get_user_ids():
    # get total page count, convert to integer, increment by 1
    response = requests.get(url=API_ENDPOINT_USER_LIST,
                            headers=AUTHORIZATION_HEADER)
    if not response.ok:
        print(response)
        print('Is your JWT still valid?')
        exit(1)
    page_data = response.json()
    total_pages = int(page_data['page_count']) + 1

    # results will be appended to this list
    all_entries = []

    # loop through all pages and return user data
    for page in range(1, total_pages):
        url = API_ENDPOINT_USER_LIST + "?page_number=" + str(page)
        user_data = requests.get(url=url, headers=AUTHORIZATION_HEADER).json()
        time.sleep(6)
        user_ids = [(user['email'], user['id'], user['first_name'],
                     user['last_name']) for user in user_data['users']]
        all_entries.extend(user_ids)
        data = all_entries
        page += 1
    return data


def format_filename(recording, file_type, file_extension, recording_type, recording_id):
    uuid = recording['uuid']
    topic = recording['topic'].replace('/', '&')
    topic  = topic.split(":")[0]
    rec_type = recording_type.replace("_", " ").title()
    meeting_time = parse(recording['start_time']).strftime('%Y.%m.%d')
    return '{} - {} - {}.{}'.format(
        meeting_time, topic+" - "+rec_type, recording_id, file_extension.lower()),'{} - {}'.format(meeting_time, topic)


def get_downloads(recording):
    try:
        downloads = []

        for download in recording['recording_files']:
            file_type = download['file_type']
            file_extension = download['file_extension']
            recording_id = download['id']
            if file_type == "":
                recording_type = 'incomplete'
            elif file_type != "TIMELINE":
                recording_type = download['recording_type']
            else:
                recording_type = download['file_type']

            download_url = download['download_url'] + "?access_token=" + JWT_TOKEN
            downloads.append((file_type, file_extension, download_url, recording_type, recording_id))
        print("downloads: \n", downloads)
        return downloads
    except requests.exceptions.ConnectionError:
        print('refused connection')


def get_recordings(email, page_size, rec_start_date, rec_end_date):
    return {
        'userId':       email,
        'page_size':    page_size,
        'from':         rec_start_date,
        'to':           rec_end_date
    }


# Generator used to create deltas for recording start and end dates
def perdelta(start, end, delta):
    curr = start
    while curr < end:
        yield curr, min(curr + delta, end)
        curr += delta


def list_recordings(email):
    recordings = []

    for start, end in perdelta(date(RECORDING_START_YEAR, RECORDING_START_MONTH, RECORDING_START_DAY), 
                               RECORDING_END_DATE, timedelta(days=30)):
        print('start: ', start)
        print('end: ', end)
        post_data = get_recordings(email, 300, start, end)
        time.sleep(10)
        response = requests.get(url=API_ENDPOINT_RECORDING_LIST(
            email), headers=AUTHORIZATION_HEADER, params=post_data)
        recordings_data = response.json()
        print('type',type(recordings_data))
        time.sleep(5)

        with open('list_of_recordings.json', 'r') as jf:
            if os.path.getsize('list_of_recordings.json') == 0:
                json_data = []
            else:
                json_data = json.load(jf)
            json_data.append(recordings_data)
            jf.close()
        with open('list_of_recordings.json', 'w') as jf:
            jf.seek(0)
            json.dump(json_data, jf, indent=4)
            jf.close()
        recordings.extend(recordings_data['meetings'])

    return recordings


def download_recording(download_url, uploader, filename, foldername):
    
    upload_dir = os.sep.join([DOWNLOAD_DIRECTORY, uploader])
    dl_dir = os.sep.join([upload_dir, foldername])
    full_filename = os.sep.join([dl_dir, filename])
    print("fullname", full_filename)
    if os.path.exists(upload_dir) == False:
        os.makedirs(upload_dir, exist_ok=True)
    if os.path.exists(dl_dir) == False:
        os.makedirs(dl_dir, exist_ok=True)

    time.sleep(20)
    response = requests.get(download_url, stream=True)

    # total size in bytes.
    total_size = int(response.headers.get('content-length', 0))
    block_size = 32 * 1024  # 32 Kibibytes

    # create TQDM progress bar
    t = tqdm(total=total_size, unit='iB', unit_scale=True)
    try:
        with open(full_filename, 'wb') as fd:
            for chunk in response.iter_content(block_size):
                t.update(len(chunk))
                fd.write(chunk)  # write video chunk to disk
        t.close()
        return True
    except Exception as e:
        print("\nwriting files error...")
        print(e)
        time.sleep(6)
        return False

def load_completed_meeting_ids():
    try:
        with open(COMPLETED_MEETING_IDS_LOG, 'r') as fd:
            for line in fd:
                COMPLETED_MEETING_IDS.add(line.strip())
    except FileNotFoundError:
        print("Log file not found. Creating new log file: ",
              COMPLETED_MEETING_IDS_LOG)
        print()


def handler(signal_received, frame):
    # handle cleanup here
    print(color.RED + "\nSIGINT or CTRL-C detected. Exiting gracefully." + color.END)
    exit(0)


def main(users: list):

    # clear the screen buffer
    os.system('cls' if os.name == 'nt' else 'clear')

    
    uploader = users[0][2] + "-" + users[0][3]

    for email, user_id, first_name, last_name in users:
        print(color.BOLD + "\nGetting recording list for {} {} ({})".format(first_name,
                                                                            last_name, email) + color.END)
        # wait for seconds so we don't breach the API rate limit
        time.sleep(5)
        recordings = list_recordings(user_id)
        
        total_count = len(recordings)
        print("==> Found {} recordings".format(total_count))

        for index, recording in enumerate(recordings):

            success = False # reset success flag to false

            meeting_id = recording['uuid']

            # check duration 
            if recording['duration'] < 5:
                print("skipped", index)
                continue

            # check if downloaded before
            if meeting_id in COMPLETED_MEETING_IDS:
                print("==> Skipping already downloaded meeting: {}".format(meeting_id))
                continue


            ##---------------------------get downloads---------------------------##
            downloads = get_downloads(recording)

            if downloads is not None:
                print("downloads\n", len(downloads))
                for file_type, file_extension, download_url, recording_type, recording_id in downloads:
                    print('recording_type', recording_type)
                    if recording_type != 'incomplete':
                        filename, foldername = format_filename(
                            recording, file_type, file_extension, recording_type, recording_id)
                      
                        print("filename", filename)
                        print("foldername", foldername)
                        truncated_url = download_url[0:64] + "..."
                        print("==> Downloading ({} of {}) as {}: {}: {}".format(
                            index+1, total_count, recording_type, recording_id, truncated_url))
                        success |= download_recording(download_url, uploader, filename, foldername)

                        time.sleep(20)
                        #success = True
                    else:
                        print("### Incomplete Recording ({} of {}) for {}".format(index+1, total_count, recording_id))
                        success = False

                if success:
                    # if successful, write the ID of this recording to the completed file
                    with open(COMPLETED_MEETING_IDS_LOG, 'a') as log:
                        COMPLETED_MEETING_IDS.add(meeting_id)
                        log.write(meeting_id)
                        log.write('\n')
                        log.flush()

        print(color.BOLD + color.GREEN + "\n*** All done! ***" + color.END)
        save_location = os.path.abspath(DOWNLOAD_DIRECTORY)
        print(color.BLUE + "\nRecordings have been saved to: " +
              color.UNDERLINE + "{}".format(save_location) + color.END + "\n")

if __name__ == "__main__":
    # tell Python to run the handler() function when SIGINT is recieved
    signal(SIGINT, handler)


    # JWT_TOKEN ---->  appenv.py
    ACCESS_TOKEN = 'Bearer ' + JWT_TOKEN
    AUTHORIZATION_HEADER = {'Authorization': ACCESS_TOKEN}
    API_ENDPOINT_USER_LIST = 'https://api.zoom.us/v2/users'


    RECORDING_START_YEAR = 2021
    RECORDING_START_MONTH = 12
    RECORDING_START_DAY = 1
    RECORDING_END_DATE = date(2022, 6, 30)
    DOWNLOAD_DIRECTORY = 'downloads'
    COMPLETED_MEETING_IDS_LOG = 'completed-downloads.log' 
    COMPLETED_MEETING_IDS = set()

    users = [('rooms_Gm-YB4KkSgmQlewn45SHGA@tomofun.com', 'Gm-YB4KkSgmQlewn45SHGA', 'Open','Minded')]
    main(users)
