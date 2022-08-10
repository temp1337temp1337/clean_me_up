import sys
import shutil
import uuid
import magic
import os
import hashlib
import mmap
import sqlite3
import argparse
import subprocess
from rich.console import Console

# SQL initializer
SQL_CONN = sqlite3.connect('database.db', check_same_thread=False)
SQL_CURSOR = SQL_CONN.cursor()
CONSOLE = Console()
HASH_FUNC = hashlib.sha512()

ADDITION = "[bold yellow][+][/bold yellow]"
DELETION = "[bold cyan][-][/bold cyan]"
OPERATION = "[bold white][!][/bold white]"
ERROR = "[bold red][!][/bold red]"
INFO = "[bold cyan][!][/bold cyan]"
PROMPT = "[bold orange][!][/bold orange]"

CATEGORIES_TO_MOVE = {
    "powerpoint": "ppt",
    "presentation": "ppt",
    "tex": "latex",
    "pdf": "pdf",
    "word": "word",
}

CATEGORIES_TO_DEL = {
    "rom": "iso",
}

SKIP_DIRS = {
    "",
}


class FileEntry:
    def __init__(self, filename, filehash=None, filetype=None, filesize=None):
        self.name = filename
        self.hash = filehash
        self.type = filetype
        self.size = filesize


def get_file_type(filename):
    return magic.from_file(filename).split(",")[0]


def rename(filename):
    return f"{filename.split('.')[:-1]}{uuid.uuid4()}.{filename.split('.')[-1]}"


def calc_size(filename):
    return os.stat(filename).st_size


def wrap_word_output(word):
    return f"[bold blue]{word}[/bold blue]"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fdupes', help='', type=bool, required=False)
    parser.add_argument('--recat', help='', type=bool, required=False)
    parser.add_argument('--delete', help='', type=bool, required=False)
    parser.add_argument('--create_db', help='', type=bool, required=False)
    args = parser.parse_args()
    return args


def read_skip_dir_file(skip_dir_file):
    with open(skip_dir_file, "r") as file:
        lines = file.readlines()
    return [line.rstrip() for line in lines]


def run_fdupes(root_dir, log_file="fdupe_output.log"):
    if sys.platform in ["linux", "linux2"]:
        CONSOLE.print(f"{INFO} Checking if {wrap_word_output('fdupes')} is installed")

        rn = subprocess.check_call("which fdupes", shell=True)
        if rn != 0:
            CONSOLE.print(f"{ERROR} {wrap_word_output('fdupes')} not installed!")
            CONSOLE.print(f"{ERROR} Run {wrap_word_output('apt install fdupes')} to install it")

    elif sys.platform == "darwin":
        CONSOLE.print(f"{INFO} Checking if {wrap_word_output('fdupes')} is installed")

        rn = subprocess.check_call("which fdupes", shell=True)
        if rn != 0:
            CONSOLE.print(f"{ERROR} {wrap_word_output('fdupes')} not installed!")
            CONSOLE.print(f"{ERROR} Run {wrap_word_output('brew install fdupes')} to install it")

    elif sys.platform == "win32":
        CONSOLE.print(f"{ERROR} Sorry, cannot do windows ¯\_(ツ)_/¯")

    with open(log_file, "w") as log:
        return subprocess.check_call(f"fdupes -rdN {root_dir} -o 'time'", shell=True, stderr=log, stdout=log)


def sha512sum(filename):
    if os.lstat(filename).st_size <= 0:
        return 0

    with open(filename, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, prot=mmap.ACCESS_READ) as mem_map:
            HASH_FUNC.update(mem_map)
    return HASH_FUNC.hexdigest()


def export_duplicates(duplicates):
    for filehash, filename_list in duplicates.items():
        CONSOLE.print(f"{INFO} Hash: {filehash} is shared with:")
        for filename in filename_list:
            CONSOLE.print(f"{INFO} {filename}")


def process_empty(empty_files):
    for filename in empty_files:
        CONSOLE.clear_live()
        CONSOLE.print(f"\n{INFO} Zero sized file found: {filename}")
        delete = CONSOLE.input(f"{PROMPT} Do you want to delete it? ")
        if any(delete.lower() == f for f in ["yes", 'y']):
            os.remove(filename)
            CONSOLE.print(f"{DELETION} Deleted: {filename}")


def execute_fetch_sql(word):
    sql_statement = f"SELECT filename FROM file_hashes WHERE filetype LIKE %{word}%"
    CONSOLE.print(f"{INFO} Executing: {sql_statement}")

    SQL_CURSOR.execute('SELECT filename FROM file_hashes WHERE filetype LIKE ?', (f"%{word}%",))
    files_found = SQL_CURSOR.fetchall()

    CONSOLE.print(f"{ADDITION} Retrieved: {len(files_found)}")
    return [filename[0] for filename in files_found]


def recategorize(path, category_list):
    for word, folder_name in category_list.items():
        files = execute_fetch_sql(word)
        target_path = f"{path}{folder_name}"

        move = CONSOLE.input(f"{PROMPT} Do you want to move those to {target_path}? ")
        if any(move.lower() == f for f in ["yes", 'y']):
            os.makedirs(target_path, exist_ok=False)

            for filename in files:
                target_filename = f"{target_path}/{filename.split('/')[-1]}"

                if os.path.exists(target_filename):
                    target_filename = rename(target_filename)
                shutil.move(filename, target_filename)
            # TODO: update_db(files)
            CONSOLE.print(f"{OPERATION} Moved {len(files)} files under {target_path}")
    return


def traverse(root_dir, skip_dir):
    object_list = []
    hashes = {}
    duplicates = {}
    types = {}
    empty = []

    if not os.path.isdir(root_dir):
        CONSOLE.print(f"{ERROR} {root_dir} does not exists!")

    for subdir, dirs, files in os.walk(root_dir):

        directory = os.path.join(root_dir, subdir)
        if directory in skip_dir or subdir in skip_dir:
            continue

        for file in files:
            filename = os.path.join(directory, file)
            filesize = calc_size(filename)
            filehash = 0 if filesize <= 0 else sha512sum(filename)
            filetype = get_file_type(filename)
            file_obj = FileEntry(filename, filehash, filetype, filesize)
            object_list.append(file_obj)

            if filehash == 0:
                empty.append(filename)

            types[filetype] = 1 if filetype in types else types[filetype] + 1

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
    tables_list = SQL_CURSOR.fetchall()  # retrieve results
    tables = list(sum(tables_list, ()))  # flatten the list

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
            CONSOLE.print(f"{ERROR} Error while updating the database")
            CONSOLE.print(f"{ERROR} Raised while inserting: {file.name} - {file.hash} - {file.type}")
            # raise

    SQL_CONN.commit()


def update_db(object_list):
    for file in object_list:
        SQL_CURSOR.execute('SELECT filehash FROM file_hashes WHERE filehash=?', (file.name,))
        file_obj = SQL_CURSOR.fetchall()
        if len(file_obj) >= 1:  # the entry with this hash exists - duplicate found
            CONSOLE.print(f"{ERROR} Raised while inserting: {file.name} - {file.hash} - {file.type} to the database")

        SQL_CURSOR.execute('INSERT INTO file_hashes VALUES (?, ?, ?)', (file.hash, file.name, file.type))
        if SQL_CURSOR.rowcount != 1:  # an issue with the DB was encountered
            CONSOLE.print(f"{ERROR} Raised while inserting: {file.name} - {file.hash} - {file.type} to the database")
            # raise

    SQL_CONN.commit()


def close_database():
    SQL_CONN.commit()  # commit any non-committed changes
    SQL_CONN.close()  # close the database


def main(path, skip_dir_file):
    parse_args()
    skip_dir = read_skip_dir_file(skip_dir_file) if skip_dir_file else None

    init_database()
    with CONSOLE.status("[bold green]Walking the directory ...") as _:
        types, object_list, duplicates, empty = traverse(path, skip_dir)

    for filetype, count in sorted(types.items(), key=lambda x: -x[1]):
        CONSOLE.print(f"[bold red][+][/bold red] Found {count:<5} files of {filetype = } ")

    export_duplicates(duplicates=duplicates)
    process_empty(empty_files=empty)
    create_db(object_list)
    # update_db(object_list)
    recategorize(path, category_list=CATEGORIES_TO_MOVE)
    # remove_category(path, category_list=CATEGORIES_TO_DEL)
    close_database()


if __name__ == '__main__':
    main(path=sys.argv[1], skip_dir_file=sys.argv[2])
