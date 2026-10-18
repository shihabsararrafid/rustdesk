import argparse
import getpass
from pathlib import Path

from .database import connect_database, migrate
from .security import create_user
from .settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['create-admin', 'process-recordings', 'cleanup-recordings'])
    parser.add_argument('--username')
    parser.add_argument('--password-file')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    settings = Settings.from_env()
    migrate(settings.database_path)
    if args.command == 'process-recordings':
        from .media_processing import process_once
        import time
        while True:
            process_once(settings)
            if args.once:
                return
            time.sleep(5)
    if args.command == 'cleanup-recordings':
        from .media_retention import cleanup
        import json
        if args.apply and args.dry_run:
            parser.error('Choose --apply or --dry-run')
        print(json.dumps(cleanup(settings, apply=args.apply)))
        return
    import re
    if not args.username or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', args.username):
        parser.error('Invalid username')
    password = (Path(args.password_file).read_text().rstrip('\r\n')
                if args.password_file else getpass.getpass('Administrator password: '))
    with connect_database(settings.database_path) as db:
        create_user(db, args.username, password, 'admin')
    print('Administrator created')


if __name__ == '__main__':
    main()
