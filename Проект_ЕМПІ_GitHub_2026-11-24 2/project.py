"""Configure, verify and maintain the compact GitHub distribution (Python 3.10+)."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    return json.loads((ROOT / 'release-manifest.json').read_text(encoding='utf-8'))


def verify():
    info = manifest()
    errors = []
    for name, checksum in info['files'].items():
        path = ROOT / name
        if not path.is_file() or digest(path.read_bytes()) != checksum:
            errors.append(name)
    with ZipFile(ROOT / 'development-extras.zip') as archive:
        if set(archive.namelist()) != set(info['extras']):
            errors.append('development-extras.zip: unexpected entries')
        else:
            errors.extend(name for name, checksum in info['extras'].items()
                          if digest(archive.read(name)) != checksum)
    if errors:
        raise SystemExit('Verification failed (missing or modified files):\n' + '\n'.join(errors))
    print(f"Verified {info['published_file_count']} publication files, including the manifest.")
    print(f"All {len(info['extras'])} archived development files are intact.")


def extras():
    info = manifest()
    if digest((ROOT / 'development-extras.zip').read_bytes()) != info['files']['development-extras.zip']:
        raise SystemExit('The development archive does not match release-manifest.json.')
    with ZipFile(ROOT / 'development-extras.zip') as archive:
        pending = []
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or '..' in relative.parts or '\\' in member.filename:
                raise SystemExit('Unsafe archive member: ' + member.filename)
            content = archive.read(member)
            if member.filename not in info['extras'] or digest(content) != info['extras'][member.filename]:
                raise SystemExit('Unexpected or corrupt archive member: ' + member.filename)
            target = ROOT.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(ROOT.resolve()):
                raise SystemExit('Archive member escapes the project: ' + member.filename)
            if target.exists() and target.read_bytes() != content:
                raise SystemExit(f'Existing changes preserved: {member.filename}. Move this file before restoring.')
            pending.append((target, content))
        for target, content in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print(f'Restored {len(pending)} test and documentation files. They are excluded from git by .gitignore.')


def configure(web_port, db_port):
    target = ROOT / '.env'
    if target.exists():
        raise SystemExit('.env already exists and has been preserved.')
    database_password = secrets.token_urlsafe(24)
    replacements = {
        'POSTGRES_PASSWORD': database_password,
        'DATABASE_URL': f'postgresql+psycopg://empi:{database_password}@127.0.0.1:{db_port}/empi',
        'JWT_SECRET': secrets.token_urlsafe(48),
        'DEMO_PASSWORD': secrets.token_urlsafe(24),
        'WEB_PORT': str(web_port),
        'DB_PORT': str(db_port),
    }
    lines = []
    for line in (ROOT / '.env.example').read_text(encoding='utf-8').splitlines():
        key = line.partition('=')[0]
        lines.append(f'{key}={replacements[key]}' if key in replacements else line)
    with target.open('x', encoding='utf-8', newline='\n') as output:
        os.chmod(target, 0o600)
        output.write('\n'.join(lines) + '\n')
    print('Created a private .env with independent database, JWT and demo credentials.')
    print('Read DEMO_PASSWORD in .env after creating the demo accounts. Do not publish .env.')
    print(f'Web address: http://127.0.0.1:{web_port}')
    print('Next: docker compose up -d --build')


def compose(*args, **kwargs):
    return subprocess.run(['docker', 'compose', *args], cwd=ROOT, check=True, **kwargs)


def backup(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open('xb') as output:
            created = True
            os.chmod(path, 0o600)
            compose('exec', '-T', 'db', 'sh', '-c',
                    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                    '--format=custom --no-owner --no-privileges', stdout=output)
        if not path.stat().st_size:
            raise RuntimeError('The database backup is empty.')
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    print(f'Private database backup saved: {path}')


def restore(path):
    with path.open('rb') as source:
        if source.read(5) != b'PGDMP':
            raise SystemExit('Expected a PostgreSQL custom-format .dump file.')
    running = compose('ps', '--status', 'running', '-q', 'api', 'worker', capture_output=True, text=True)
    if running.stdout.strip():
        raise SystemExit('Stop API and worker first: docker compose stop api worker')
    tables = compose('exec', '-T', 'db', 'sh', '-c',
                     'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 '
                     '-c "SELECT count(*) FROM pg_tables WHERE schemaname = \'public\';"',
                     capture_output=True, text=True)
    if tables.stdout.strip() != '0':
        raise SystemExit('Restore requires an empty database. Existing data has been preserved.')
    with path.open('rb') as source:
        compose('exec', '-T', 'db', 'sh', '-c',
                'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                '--no-owner --no-privileges --exit-on-error --single-transaction', stdin=source)
    print('Database restored. Existing account passwords are unchanged. Sign in again.')


def port(value):
    parsed = int(value)
    if not 1024 <= parsed <= 65535:
        raise argparse.ArgumentTypeError('Use a port from 1024 to 65535.')
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    config = actions.add_parser('configure', help='Create a private .env without overwriting existing settings')
    config.add_argument('--web-port', type=port, default=8080)
    config.add_argument('--db-port', type=port, default=55432)
    actions.add_parser('verify', help='Verify published file and archive checksums')
    actions.add_parser('extras', help='Restore all tests and additional documents')
    for name in ('backup', 'restore'):
        command = actions.add_parser(name, help=f'{name.title()} a private database dump')
        command.add_argument('path', type=Path)
    args = parser.parse_args()
    if args.action == 'configure':
        configure(args.web_port, args.db_port)
    elif args.action == 'verify':
        verify()
    elif args.action == 'extras':
        extras()
    else:
        if not (ROOT / '.env').is_file():
            raise SystemExit('Create .env first: python3 project.py configure')
        {'backup': backup, 'restore': restore}[args.action](args.path.resolve())


if __name__ == '__main__':
    main()
