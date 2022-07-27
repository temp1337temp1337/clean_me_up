import magic
import os
import hashlib
import mmap
import sqlite3

'''
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

'''


# SQL initializer
conn = sqlite3.connect('server.db', check_same_thread=False)
cursor = conn.cursor()

HASH_FUNC = hashlib.sha512()


class FileEntry:
    def __init__(self, filename, filehash=None, filetype=None):
        self.filename = filename
        self.hash = filehash
        self.type = filetype


def get_file_type(filename):
    return magic.from_file(filename)


def sha512sum(filename):
    with open(filename, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, prot=mmap.PROT_READ) as mem_map:
            HASH_FUNC.update(mem_map)
    return HASH_FUNC.hexdigest()


def export_duplicates():
    return


def traverse(root_dir):
    object_list = []
    hashes = {}
    duplicates = {}

    for subdir, dirs, files in os.walk(root_dir):
        for file in files:
            filename = os.path.join(root_dir, subdir, file)
            filehash = sha512sum(filename)
            filetype = get_file_type(filename)
            file_obj = FileEntry(filename, filehash, filetype)

            object_list.append(file_obj)

            if filehash in hashes and filehash in duplicates:
                duplicates[filehash].append(filename)
                continue

            if filehash in hashes and filehash not in duplicates:
                duplicates[filehash] = [filename, hashes[filehash]]
                continue

            hashes[filehash] = filename

    export_duplicates()
    update_db(object_list)


def init_database():
    """
    :return:
    """
    cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')  # retrieve tables
    tables_list = cursor.fetchall()                                      # retrieve results
    tables = list(sum(tables_list, ()))                                  # flatten the list

    if 'file_hashes' not in tables:
        cursor.execute('CREATE TABLE file_hashes '
                       '(filename TEXT PRIMARY KEY NOT NULL, '
                       'filepath TEXT NOT NULL, '
                       'filehash TEXT NOT NULL);')
    conn.commit()
    return


def close_database():
    """
    :return:
    """
    conn.commit()                               # commit any non-committed changes
    conn.close()                                # close the database


def update_db(object_list):

    for file in object_list:
        cursor.execute('SELECT filename FROM file_hashes WHERE filename=?', (file.filename, ))
        filename = cursor.fetchall()  # check if user is already active
        if len(filename) >= 1:
            print(f"Entry {filename} already exists in the database, skipping it")
            print(f"Raised while inserting: {file.filename} - {file.hash} - {file.type}")

        cursor.execute('INSERT INTO file_hashes VALUES (?, ?, ?)', (file.filename, file.hash, file.type))
        if cursor.rowcount != 1:  # an issue with the DB was encountered
            print(f"Error while updating the database")
            print(f"Raised while inserting: {file.filename} - {file.hash} - {file.type}")
            # raise

    conn.commit()


def main():
    return


if __name__ == '__main__':
    main()

