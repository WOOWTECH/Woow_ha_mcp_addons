"""Build-context closure: every Dockerfile COPY source must reach the builder.

Mirrors moby/patternmatcher MatchesOrParentMatches (last match wins, and a
pattern matching a PARENT directory decides for everything below it), which is
what Docker/BuildKit apply to .dockerignore. A tracked file that a production
Dockerfile COPYs but the context drops fails only on a real builder; this
catches it offline. Read-only: no Docker, no network.
"""
import os
from pathlib import Path
import re
import subprocess
import sys

from validate import PRODUCTS


def compile_pattern(pattern):
    out, i = '^', 0
    while i < len(pattern):
        c = pattern[i]
        if c == '*':
            if pattern[i + 1:i + 2] == '*':
                i += 1
                if pattern[i + 1:i + 2] == '/':
                    i += 1
                    out += '(.*/)?'
                else:
                    out += '.*'
            else:
                out += '[^/]*'
        elif c == '?':
            out += '[^/]'
        elif c == '\\' and i + 1 < len(pattern):
            i += 1
            out += re.escape(pattern[i])
        else:
            out += re.escape(c)
        i += 1
    return re.compile(out + '$')


def load_ignore(text):
    patterns = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        exclusion = line.startswith('!')
        line = line[1:].strip() if exclusion else line
        patterns.append((exclusion, compile_pattern(os.path.normpath(line.lstrip('/')))))
    return patterns


def excluded(patterns, path):
    matched = False
    parents = path.split('/')[:-1]
    for exclusion, regex in patterns:
        if exclusion != matched:
            continue
        hit = bool(regex.match(path)) or any(regex.match('/'.join(parents[:i + 1])) for i in range(len(parents)))
        if hit:
            matched = not exclusion
    return matched


def copy_sources(dockerfile):
    sources = []
    for line in dockerfile.splitlines():
        words = line.split()
        if words[:1] == ['COPY'] and not any(w.startswith('--from') for w in words):
            sources += [w for w in words[1:-1] if not w.startswith('--')]
    return sources


def problems(files, ignore_text, dockerfile):
    patterns = load_ignore(ignore_text)
    found = []
    for source in copy_sources(dockerfile):
        selected = [f for f in files if f == source or f.startswith(source.rstrip('/') + '/')]
        if not selected:
            found.append('COPY source not tracked: ' + source)
        found += ['COPY source excluded from context: ' + f for f in selected if excluded(patterns, f)]
    return found


def main(root='.'):
    root = Path(root)
    files = subprocess.run(['git', 'ls-files', '-z'], cwd=root, check=True, capture_output=True,
                           text=True, timeout=60).stdout.split('\0')
    files = [f for f in files if f]
    ignore = (root / '.dockerignore').read_text()
    failures = {app: problems(files, ignore, (root / 'apps' / app / 'Dockerfile').read_text()) for app in PRODUCTS}
    failures = {app: p for app, p in failures.items() if p}
    if failures:
        raise SystemExit('FAIL: ' + repr(failures))
    print('PASS: every COPY source of seven Dockerfiles is tracked and inside the build context')


if __name__ == '__main__':
    main(*sys.argv[1:])
