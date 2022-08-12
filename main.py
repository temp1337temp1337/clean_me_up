import sys
import shutil
import uuid
import json
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
    parser.add_argument('--remove', help='', type=bool, required=False)
    parser.add_argument('--create_db', help='', type=bool, required=False)
    parser.add_argument('--update_db', help='', type=bool, required=False)
    parser.add_argument('--show_counts', help='', type=bool, required=False)
    parser.add_argument('--show_empty', help='', type=bool, required=False)
    parser.add_argument('--show_duplicates', help='', type=bool, required=False)
    parser.add_argument('--skip_dir_file', help='', type=str, required=False)
    parser.add_argument('--cat_to_move_file', help='', type=str, required=False)
    parser.add_argument('--cat_to_remove_file', help='', type=str, required=False)
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


def recategorize(path, category_list_filename):
    with open(category_list_filename) as file:
        category_list = json.load(file)

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


def remove_category(path, category_list_filename):
    with open(category_list_filename) as file:
        category_list = json.load(file)

    for word, folder_name in category_list.items():
        files = execute_fetch_sql(word)
        target_path = f"{path}{folder_name}"

        remove = CONSOLE.input(f"{PROMPT} Do you want to delete the retrieved files? ")
        if any(remove.lower() == f for f in ["yes", 'y']):
            os.makedirs(target_path, exist_ok=False)

            for filename in files:
                os.remove(filename)
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
        if len(os.listdir(directory)) == 0:
            empty.append(directory)
            continue

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


def empty_database():
    SQL_CURSOR.execute('SELECT name FROM sqlite_master WHERE type="table"')  # retrieve tables
    tables_list = SQL_CURSOR.fetchall()  # retrieve results
    tables = list(sum(tables_list, ()))  # flatten the list

    if 'file_hashes' not in tables:
        return True

    SQL_CURSOR.execute('SELECT COUNT(*) FROM file_hashes')  # retrieve tables
    table_count = SQL_CURSOR.fetchall()[0][0]  # retrieve results
    return table_count == 0


def init_database():
    SQL_CURSOR.execute('CREATE TABLE file_hashes '
                       '(filehash TEXT PRIMARY KEY NOT NULL, '
                       'filename TEXT NOT NULL, '
                       'filetype TEXT NOT NULL, '
                       'filesize TEXT NOT NULL);')
    SQL_CONN.commit()
    return


def create_db(object_list):
    for file in object_list:
        SQL_CURSOR.execute('INSERT INTO file_hashes VALUES (?, ?, ?)', (file.hash, file.name, file.type))
        if SQL_CURSOR.rowcount != 1:  # an issue with the DB was encountered
            CONSOLE.print(f"{ERROR} Error while updating the database")
            CONSOLE.print(f"{ERROR} Raised while inserting: {file.name} - {file.hash} - {file.type}")

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
    SQL_CONN.close()   # close the database


def main(path, skip_dir_file):
    args = parse_args()
    skip_dir = read_skip_dir_file(skip_dir_file) if args.skip_dir_file else None

    if args.fdupes and args.show_duplicates:
        CONSOLE.print(f"{ERROR} Cannot run fdupes and show the duplicates.")
        CONSOLE.print(f"{ERROR} Duplicates would be removed afted fdupes.")

    if args.create_db and args.update_db:
        CONSOLE.print(f"{ERROR} Cannot run create and update the database.")
        CONSOLE.print(f"{ERROR} Only one of the two switches can be provided.")

    if args.recat and not args.cat_to_move_file:
        CONSOLE.print(f"{ERROR} Please provide the recat option and the filename")

    if args.remove and args.cat_to_remove_file:
        CONSOLE.print(f"{ERROR} Please provide the remove option and the filename")

    if args.fdupes:
        run_fdupes(root_dir=path)

    # TODO: any args that need the below, otherwise do not execute it
    with CONSOLE.status("[bold green]Walking the directory ...") as _:
        types, object_list, duplicates, empty = traverse(path, skip_dir)

    if args.create_db:
        if not empty_database():
            CONSOLE.print(f"{ERROR} Database not empty!")
            create = CONSOLE.input(f"{PROMPT} Do you want to create the database from scratch?")

            if any(create.lower() == f for f in ["yes", 'y']):
                os.remove("database.db")

                init_database()
                create_db(object_list=object_list)
                close_database()

    elif args.update_db:
        update_db(object_list)

    if args.show_counts:
        for filetype, count in sorted(types.items(), key=lambda x: -x[1]):
            CONSOLE.print(f"{ADDITION} Found {count:<5} files of {filetype = } ")

    if not args.fdupes and args.show_duplicates:
        export_duplicates(duplicates=duplicates)

    if args.show_empty:
        process_empty(empty_files=empty)

    if args.recat:
        recategorize(path, category_list_filename=args.cat_to_move_file)

    if args.remove:
        remove_category(path, category_list_filename=args.cat_to_remove_file)


if __name__ == '__main__':
    main(path=sys.argv[1], skip_dir_file=sys.argv[2])
