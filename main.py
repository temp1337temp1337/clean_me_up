import sys
import shutil
import uuid
import magic
import os
import hashlib
import mmap
import sqlite3
from rich.console import Console

# SQL initializer
SQL_CONN = sqlite3.connect('database.db', check_same_thread=False)
SQL_CURSOR = SQL_CONN.cursor()
CONSOLE = Console()
HASH_FUNC = hashlib.sha512()

CATEGORIES = {
    # "ppt": "powerpoint,presentation",
    # "latex": "latex",
    # "pdf": "pdf",
    # "word": "word",
    "iso": "rom",
}


class FileEntry:
    def __init__(self, filename, filehash=None, filetype=None):
        self.name = filename
        self.hash = filehash
        self.type = filetype


def get_file_type(filename):
    return magic.from_file(filename).split(",")[0]


def sha512sum(filename):
    if os.lstat(filename).st_size <= 0:
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


def process_empty(empty_files):
    for filename in empty_files:
        CONSOLE.clear_live()
        CONSOLE.print(f"\n[bold yellow][-][/bold yellow] Zero sized file found: {filename}")
        delete = CONSOLE.input("[bold yellow][!][/bold yellow] Do you want to delete it? ")
        if any(delete.lower() == f for f in ["yes", 'y']):
            os.remove(filename)
            CONSOLE.print(f"[bold yellow][!][/bold yellow] Deleted: {filename}")


def recategorize(path, category_list):
    sql_base = "SELECT filename FROM file_hashes WHERE "
    for folder_name, match_words in category_list.items():
        target_path = path + folder_name
        like_words = match_words.split(',')
        # SQL Injection below! First!
        sql_statement = sql_base + " OR ".join(f"filetype LIKE '%{word}%'" for word in like_words if word.isalnum())
        CONSOLE.print(f"[bold red][+][/bold red] Executing: {sql_statement}")
        SQL_CURSOR.execute(sql_statement)
        files_found = SQL_CURSOR.fetchall()
        CONSOLE.print(f"[bold red][!][/bold red] Retrieved: {len(files_found)}")

        move = CONSOLE.input(f"[bold red][!][/bold red] Do you want to move those to {target_path}? ")
        if any(move.lower() == f for f in ["yes", 'y']):
            os.makedirs(target_path, exist_ok=False)
            for file_entry in files_found:
                filename = file_entry[0]
                target_filename = target_path + "/" + filename.split("/")[-1]

                # do not overwrite it
                if os.path.exists(target_filename):
                    target_filename = f"{target_filename}-{uuid.uuid4()}"
                shutil.move(filename, target_filename)
            CONSOLE.print(f"[bold red][!][/bold red] Moved {len(files_found)} files under {target_path}")
    return


def traverse(root_dir):
    object_list = []
    hashes = {}
    duplicates = {}
    types = {}
    empty = []

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

            if filehash == 0:
                empty.append(filename)

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

    return types, object_list, duplicates, empty


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


def close_database():
    """
    :return:
    """
    SQL_CONN.commit()                               # commit any non-committed changes
    SQL_CONN.close()                                # close the database


def main(path):
    init_database()
    '''
    with CONSOLE.status("[bold green]Walking the directory ...") as _:
        types, object_list, duplicates, empty = traverse(path)

    for filetype, count in sorted(types.items(), key=lambda x: -x[1]):
        CONSOLE.print(f"[bold red][+][/bold red] Found {count:<5} files of {filetype = } ")

    export_duplicates(duplicates=duplicates)
    process_empty(empty_files=empty)
    '''
    # create_db(object_list)
    # update_db(object_list)
    recategorize(path, category_list=CATEGORIES)
    # remove_category(path, category_list=["iso"])
    close_database()


if __name__ == '__main__':
    main(path=sys.argv[1])


