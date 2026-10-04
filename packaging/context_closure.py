"""Build-context closure: every Dockerfile COPY source must reach the builder.

Mirrors moby/patternmatcher MatchesOrParentMatches (last match wins, and a
pattern matching a PARENT directory decides for everything below it), which is
what Docker/BuildKit apply to .dockerignore. A tracked file that a production
Dockerfile COPYs but the context drops fails only on a real builder; this
catches it offline. Read-only: no Docker, no network.

Supported subset only; anything else raises ValueError instead of being
silently under-counted. This is a model of the rules, not builder evidence.
- .dockerignore: comments, blank lines, `!` exceptions, `*`, `**`, `?`, `\\`
  escapes. Character classes `[...]` are rejected.
- Dockerfile: `\\` line continuations are joined into one instruction (comment
  lines inside are dropped, as Docker does); upper-case `COPY` in shell form with
  literal relative sources. `COPY --from=...` is skipped (stage copy). Other
  `--flag=value` options are ignored except `--parents`/`--exclude`, which change
  source selection and are rejected. Rejected: JSON-form COPY, heredocs (`<<`
  anywhere, since a body changes how later lines parse), a dangling continuation, `ADD`, parser directives, and `$`, `*`, `?`, `[` in sources.
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
        if '[' in line:
            raise ValueError('unsupported .dockerignore character class: ' + line)
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


def instructions(dockerfile):
    pending, start = [], 0
    for number, line in enumerate(dockerfile.splitlines(), 1):
        stripped = line.strip()
        if number == 1 and re.match(r'#\s*(syntax|escape|check)\s*=', stripped, re.I):
            raise ValueError('Dockerfile line 1: unsupported parser directive')
        if stripped.startswith('#') or (not stripped and not pending):
            continue
        if '<<' in stripped:
            raise ValueError('Dockerfile line %d: unsupported heredoc' % number)
        start = start if pending else number
        if stripped.endswith('\\'):
            pending.append(stripped[:-1])
            continue
        yield start, ' '.join(pending + [stripped])
        pending = []
    if pending:
        raise ValueError('Dockerfile line %d: dangling continuation' % start)


def copy_sources(dockerfile):
    sources = []
    for number, stripped in instructions(dockerfile):
        where = 'Dockerfile line %d: ' % number
        words = stripped.split()
        instruction = words[0].upper()
        if instruction == 'ADD':
            raise ValueError(where + 'unsupported ADD')
        if instruction != 'COPY':
            continue
        if words[0] != 'COPY' or (len(words) > 1 and words[1].startswith('[')):
            raise ValueError(where + 'unsupported COPY form')
        flags = [w for w in words[1:] if w.startswith('--')]
        if any(f.startswith(('--parents', '--exclude')) for f in flags):
            raise ValueError(where + 'unsupported COPY flag')
        if any(f.startswith('--from') for f in flags):
            continue
        args = [w for w in words[1:] if not w.startswith('--')]
        if len(args) < 2:
            raise ValueError(where + 'COPY needs source and destination')
        for source in args[:-1]:
            if any(c in source for c in '$*?[') or source.startswith(('/', '..')):
                raise ValueError(where + 'unsupported COPY source ' + source)
        sources += args[:-1]
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
