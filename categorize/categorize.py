import time
import requests
import urllib
import os
import mysql.connector
from mysql.connector import errorcode
from bs4 import BeautifulSoup
from bs4 import element
from threading import Thread

# --- CONSTANTS ---

SQL_CONFIG = {
    'user': 'root',
    'password': 'pass.word'
}

SQL_DB = 'satellites'

TABLE = (
    "CREATE TABLE IF NOT EXISTS `categorized` ("
    " `obj_no` varchar(9) NOT NULL,"
    " `name` varchar(32) NOT NULL,"
    " `description` varchar(120) NOT NULL)"
    " ENGINE=InnoDB")

# --- VARIABLES ---

buffer = []
tot_proc = 0

# --- UTILITY FUNCTIONS ---

def create_database(cursor):
    try:
        cursor.execute(
            f"CREATE DATABASE {SQL_DB} DEFAULT CHARACTER SET 'utf8'")
    except mysql.connector.Error as err:
        print(f'Failed creating database: {err}')
        os._exit(1)

def process_file(url, name, description):
    global buffer, tot_proc
    # load txt file
    _file = urllib.request.urlopen(url)
    i = 0
    for _line in _file.readlines():
        # read every 3rd line
        i += 1
        line = str(_line)[2:-3]
        if i == 3:
            entry = line.split(' ')
            obj_id = entry[1]
            # populate data in memory first and batch process after
            data = (obj_id, name[:-4], description.strip())
            buffer.append(data)
            i = 0
    tot_proc += 1


# --- INIT ---

if __name__ == '__main__':

    # connect to server
    try:
        cnx = mysql.connector.connect(**SQL_CONFIG)
        cursor = cnx.cursor()
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print('Something is wrong with your user name or password')
        else:
            print(err)
        print('Script is shutting down.')
        os._exit(1)

    # load DB and initialize table
    try:
        cursor.execute(f'USE {SQL_DB}')
    except mysql.connector.Error as err:
        print(f'Database {SQL_DB} does not exists.')
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            create_database(cursor)
            print(f'Database {SQL_DB} created successfully.')
            cnx.database = SQL_DB
        else:
            print(err)
            os._exit(1)
    cursor.execute(TABLE)

    # scrape main page
    URL = 'https://celestrak.com/NORAD/elements/'
    page = requests.get(URL)
    soup = BeautifulSoup(page.content, 'html.parser')
    tables = soup.find_all('table', class_='striped-odd')

    tot_files = 0

    for table in tables:
        # get main category
        header = table.find('tr', class_='header')
        main_cat = header.next.next
        # find all links within main category
        links = header.find_next_siblings()
        for link in links:
            _tmp_link = link.next.next
            if type(_tmp_link) != element.Tag:
                continue
            if 'href' in _tmp_link.attrs:
                name = _tmp_link['href']
                if name[-4:] == '.txt':
                    # start processing file in new thread
                    _url = URL + name
                    Thread(target=process_file, args=(_url, name, main_cat)).start()
                    tot_files += 1

    # scrape supplemental page
    URL_SUP = 'https://celestrak.com/NORAD/elements/supplemental/'
    page = requests.get(URL_SUP)
    soup = BeautifulSoup(page.content, 'html.parser')
    table = soup.find('table', class_='center outline')

    # get main category
    header = table.find('tr', class_='header')
    main_cat = header.next.next.next
    # find all links within main category
    links = header.find_next_siblings()
    for link in links:
        _tmp_link = link.next.next.next
        name = _tmp_link['href']
        if name[-4:] == '.txt':
            # start processing file in new thread
            _url = URL_SUP + name
            Thread(target=process_file, args=(_url, name, main_cat)).start()
            tot_files += 1

    # wait for all threads to finish while displaying progress
    while True:
        if tot_proc == tot_files: break
        print(f'Processed {tot_proc}/{tot_files} files', end='\r')
        time.sleep(0.25)

    print(f'{tot_proc} categories loaded successfully, with {len(buffer)} '
            'entries in total.\nSaving to database...', end='')
    
    # clear current records
    clear_table = ("TRUNCATE TABLE categorized")
    cursor.execute(clear_table)

    # save to DB
    add_entry = ("INSERT INTO categorized "
                "(obj_no, name, description) "
                "VALUES (%s, %s, %s)")
    for _x in buffer:
        cursor.execute(add_entry, _x)

    cnx.commit()
    print('done')

    cursor.close()
    cnx.close()
    print('All satellites successfully saved to database!')