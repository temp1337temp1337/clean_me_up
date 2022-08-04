import sys

import magic
import os
import hashlib
import mmap
import sqlite3
from rich.console import Console

'''
TODO:
- Schedule
- pandas or dataframes?
- fdupes
- find /path/to -regex ".*\.\(jpg\|gif\|png\|jpeg\)" > log

Similar tools:
# - https://github.com/mruffalo/hash-db
# - https://github.com/trapexit/scorch
# - https://github.com/temp1337temp1337/awesome_career/blob/4d230d117a93834703ac2059f469b0903ec772a3/gatech/6238_secure_computer_systems/assignment%234/server.py

Requirements:
- create tool for cleaning up files
- database with hashes
- zipped, tar, gz files -> extract
- option to remove specific types of files (binary java files, vpn files etc.)
- categorize specific types of files (doc, ppt etc. or generally photos)
- skip folders/files
- get a list of files and check which already exist in the database
- get duplicates from the database
- classify similar files (hexdump/xxd + compare?/bitmasking? - error bound => similar files)
- get duplicates from the database
- binary instead of cpython

Links
- https://stackoverflow.com/questions/42630025/python-how-to-compare-two-binary-files
- https://codereview.stackexchange.com/questions/171003/python-code-that-compares-two-files-byte-by-byte
- https://superuser.com/questions/154699/is-there-any-way-to-find-similar-files-not-duplicates
- http://www.joerg-rosenthal.com/en/antitwin/
'''


# SQL initializer
SQL_CONN = sqlite3.connect('database.db', check_same_thread=False)
SQL_CURSOR = SQL_CONN.cursor()
CONSOLE = Console()
HASH_FUNC = hashlib.sha512()


class FileEntry:
    def __init__(self, filename, filehash=None, filetype=None):
        self.name = filename
        self.hash = filehash
        self.type = filetype


def get_file_type(filename):
    return magic.from_file(filename).split(",")[0]


def sha512sum(filename):
    if os.lstat(filename).st_size <= 0:
        CONSOLE.clear_live()
        CONSOLE.print(f"\n[bold yellow][-][/bold yellow] Zero sized file found: {filename}")
        return 0

    with open(filename, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, prot=mmap.ACCESS_READ) as mem_map:
            HASH_FUNC.update(mem_map)
    return HASH_FUNC.hexdigest()


def export_duplicates(duplicates):
    for filehash, filename_list in duplicates.items():
        CONSOLE.print(f"[bold cyan][!][/bold cyan] Hash: {filehash} is shared with:")
        for filename in filename_list:
            CONSOLE.print(f"[bold white][-][/bold white] {filename}")
    return


def traverse(root_dir):
    object_list = []
    hashes = {}
    duplicates = {}
    types = {}
    if not os.path.isdir(root_dir):
        CONSOLE.print(f"[bold white][-][/bold white] {root_dir} does not exists!")

    for subdir, dirs, files in os.walk(root_dir):
        for file in files:
            filename = os.path.join(root_dir, subdir, file)
            filehash = sha512sum(filename)
            filetype = get_file_type(filename)
            file_obj = FileEntry(filename, filehash, filetype)
            # print(f"Retrieved: {filename} - {filehash} - {filetype}")

            object_list.append(file_obj)

            if filetype in types:
                types[filetype] += 1
            else:
                types[filetype] = 1

            if filehash in hashes and filehash in duplicates:
                duplicates[filehash].append(filename)
                continue

            if filehash in hashes and filehash not in duplicates:
                duplicates[filehash] = [filename, hashes[filehash]]
                continue

            hashes[filehash] = filename  # stores the first entry with this hash

    return types, object_list, duplicates


def init_database():
    """
    :return:
    """
    SQL_CURSOR.execute('SELECT name FROM sqlite_master WHERE type="table"')  # retrieve tables
    tables_list = SQL_CURSOR.fetchall()                                      # retrieve results
    tables = list(sum(tables_list, ()))                                  # flatten the list

    if 'file_hashes' not in tables:
        SQL_CURSOR.execute('CREATE TABLE file_hashes '
                           '(filehash TEXT PRIMARY KEY NOT NULL, '
                           'filename TEXT NOT NULL, '
                           'filetype TEXT NOT NULL);')
    SQL_CONN.commit()
    return


def close_database():
    """
    :return:
    """
    SQL_CONN.commit()                               # commit any non-committed changes
    SQL_CONN.close()                                # close the database


def create_db(object_list):
    for file in object_list:
        SQL_CURSOR.execute('INSERT INTO file_hashes VALUES (?, ?, ?)', (file.hash, file.name, file.type))
        if SQL_CURSOR.rowcount != 1:  # an issue with the DB was encountered
            CONSOLE.print(f"[bold red][-][/bold red]Error while updating the database")
            CONSOLE.print(f"[bold red][-][/bold red]Raised while inserting: {file.name} - {file.hash} - {file.type}")
            # raise

    SQL_CONN.commit()


def update_db(object_list):

    for file in object_list:
        SQL_CURSOR.execute('SELECT filehash FROM file_hashes WHERE filehash=?', (file.name, ))
        file_obj = SQL_CURSOR.fetchall()
        if len(file_obj) >= 1:  # the entry with this hash exists - duplicate found
            print(f"Entry {file_obj} already exists in the database, skipping it")
            print(f"Raised while inserting: {file.name} - {file.hash} - {file.type}")

        SQL_CURSOR.execute('INSERT INTO file_hashes VALUES (?, ?, ?)', (file.hash, file.name, file.type))
        if SQL_CURSOR.rowcount != 1:  # an issue with the DB was encountered
            print(f"Error while updating the database")
            print(f"Raised while inserting: {file.name} - {file.hash} - {file.type}")
            # raise

    SQL_CONN.commit()


def main(path):
    init_database()

    with CONSOLE.status("[bold green]Walking the directory ...") as _:
        types, object_list, duplicates = traverse(path)

    for filetype, count in sorted(types.items(), key=lambda x: -x[1]):
        CONSOLE.print(f"[bold red][+][/bold red] Found {count:<5} files of {filetype = } ")

    export_duplicates(duplicates)
    create_db(object_list)
    # update_db(object_list)
    close_database()


if __name__ == '__main__':
    main(path=sys.argv[1])


