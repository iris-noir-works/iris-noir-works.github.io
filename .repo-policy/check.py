#!/usr/bin/env python3
"""Shared, offline Git object scanner. Reports paths/rules, never secret values."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import PurePosixPath

DENIED_DIRS = {'evidence', 'Evidence', 'DerivedData', 'build', '.build', '.cache', '__pycache__'}
SECRET_SUFFIXES = {'.p12', '.pfx', '.mobileprovision', '.p8', '.pem', '.key', '.cer', '.crt'}
PLACEHOLDER_SUFFIXES = ('.example', '.template', '.sample')
CONTENT_RULES = {
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b'),
    'aws-access-key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'service-token': re.compile(rb'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,255}|xox[baprs]-[A-Za-z0-9-]{20,255})\b'),
}
ASSIGNMENT = re.compile(rb'''(?im)\b(?:api[_-]?key|token|password|passwd|secret|client[_-]?secret|access[_-]?key)\s*["']?\s*[:=]\s*["']([^\r\n"']{8,256})["']''')


def path_rules(path):
    parts = PurePosixPath(path).parts
    base = parts[-1] if parts else ''
    rules = []
    if any(p in DENIED_DIRS or p.endswith('.xcresult') for p in parts):
        rules.append('local-only-directory')
    if any(parts[i:i + 2] == ('docs', 'verification') for i in range(len(parts) - 1)):
        rules.append('verification-evidence')
    if PurePosixPath(base).suffix.lower() in SECRET_SUFFIXES:
        rules.append('credential-file')
    if (base == '.env' or base.startswith('.env.') or base.endswith('.env')) and not base.endswith(PLACEHOLDER_SUFFIXES):
        rules.append('env-values-file')
    if base.endswith('.log'):
        rules.append('diagnostic-log')
    return rules


def content_rules(data):
    found = {name for name, pattern in CONTENT_RULES.items() if pattern.search(data)}
    # Binary assets are allowed; private-key / recognizable tokens still scanned.
    if b'\0' not in data:
        for match in ASSIGNMENT.finditer(data):
            value = match.group(1).strip()
            lower = value.lower()
            if (lower in {b'example', b'placeholder', b'changeme', b'your-token', b'your-api-key', b'password'}
                    or lower.startswith((b'${', b'$(', b'<', b'your_', b'example_', b'dummy_', b'test_', b'replace_'))):
                continue
            if re.fullmatch(rb'[A-Za-z0-9_./+!=:@-]{8,256}', value):
                found.add('literal-secret-assignment')
    return sorted(found)


def git(*args, input=None):
    return subprocess.check_output(['git', *args], input=input, stderr=subprocess.PIPE)


def records(raw):
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        yield meta.split(), path.decode('utf-8', 'surrogateescape')


def scan_blob(oid):
    # Streaming prevents build artifacts from exhausting memory. Preserve overlap
    # so tokens crossing a chunk boundary are also detected.
    proc = subprocess.Popen(['git', 'cat-file', 'blob', oid], stdout=subprocess.PIPE)
    found, tail = set(), b''
    while True:
        chunk = proc.stdout.read(1024 * 1024)
        if not chunk:
            break
        data = tail + chunk
        found.update(content_rules(data))
        tail = data[-1024:]
    proc.stdout.close()
    if proc.wait() != 0:
        raise RuntimeError('Cannot read Git blob')
    return sorted(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--index', action='store_true')
    group.add_argument('--tree', metavar='REF')
    group.add_argument('--history', metavar='REF')
    group.add_argument('--push', action='store_true')
    ap.add_argument('--json', action='store_true', help='Complete path/rule findings as JSON')
    args = ap.parse_args()
    git('rev-parse', '--show-toplevel')
    findings, seen_pairs, blobs = [], set(), {}

    def inspect(meta, path, tree=False):
        if tree:
            mode, kind, oid = (x.decode() for x in meta)
            if kind != 'blob' and kind != 'commit':
                return
        else:
            mode, oid, stage = (x.decode() for x in meta)
            if stage != '0':
                raise RuntimeError('Unmerged index')
        pair = (path, oid)
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        rules = path_rules(path)
        # Path violations already fail; do not read forbidden large Evidence.
        # A dedicated audit can scan those blobs separately for secrets.
        if not rules and mode != '160000':
            if oid not in blobs:
                blobs[oid] = scan_blob(oid)
            rules += blobs[oid]
        for rule in rules:
            findings.append({'path': path, 'rule': rule, 'blob': oid})

    if args.index:
        for meta, path in records(git('ls-files', '--stage', '-z')):
            inspect(meta, path)
    else:
        refs = []
        if args.push:
            for line in sys.stdin:
                fields = line.split()
                if len(fields) != 4:
                    raise RuntimeError('Invalid pre-push input')
                if fields[1] != '0' * 40:  # deletion carries no new data
                    refs.append(fields[1])
        else:
            refs = [args.tree or args.history]
        trees = set()
        for ref in refs:
            commit = git('rev-parse', '--verify', ref + '^{commit}').decode().strip()
            commits = [commit] if args.tree else git('rev-list', commit).decode().splitlines()
            for c in commits:
                tree = git('rev-parse', c + '^{tree}').decode().strip()
                if tree in trees:
                    continue
                trees.add(tree)
                for meta, path in records(git('ls-tree', '-rz', tree)):
                    inspect(meta, path, tree=True)
    findings.sort(key=lambda x: (x['path'], x['rule'], x['blob']))
    if args.json:
        print(json.dumps({'findings': findings, 'checked_path_blobs': len(seen_pairs)}, indent=2, ensure_ascii=True))
    elif findings:
        for item in findings[:30]:
            print('DENY ' + item['rule'] + ': ' + repr(item['path']), file=sys.stderr)
        print(f'FAIL: {len(findings)} violations; --json lists all path/rule findings.', file=sys.stderr)
    else:
        print(f'PASS app-git-ssot: {len(seen_pairs)} Git path/blob pairs checked')
    return 1 if findings else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (subprocess.CalledProcessError, RuntimeError, OSError, ValueError) as exc:
        # Do not print Git stderr, object content, or exception data containing secrets.
        print('FAIL app-git-ssot: Git/input error (' + type(exc).__name__ + ')', file=sys.stderr)
        sys.exit(2)
