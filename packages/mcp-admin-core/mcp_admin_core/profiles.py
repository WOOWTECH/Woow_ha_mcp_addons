"""Additional connection profiles: the index, the directory layout, consistency, capacity and naming rules.

Multi-profile plan §4 (data), §5.2 (quotas), §5.4 (ports); docs/multi-profile/contract.md §3.6, §5 and §8 (HM-00).
HM-07 made it a library; HM-08 wires it: the gateway takes PROFILE_ID from here, and a switched-on product's
ProfileManager (profile_runtime) reads the index, opens the profiles it lists and routes MCP requests with them
(profile_router); a switched-off product reads none of it (tests/test_router_passthrough.py). HM-09 starts the
children: the spawn check's test bind (port_occupied), allocation around what is held (allocate_port occupied=) and
the memory readings (memory_limit_mib, available_memory_mib). HM-10 (profile_admin) lists, creates, renames and
deletes profiles and quarantines an unusable index with these rules and the file helpers below
(free_index_quarantine_name, move_index_aside, index_bytes, remove_profile_directory); HM-13b's boot guard checks
whether profile data exists. restore_detect (HM-13a, not wired yet) takes its file names from here. It never
writes the default profile's files (invariant I6).

Layout (plan §4.1)::

    /data/mcp/                         the default profile: today's state.json, .writer.lock, journal, child/
    ├── profiles.json                  the index; written when the first profile is created, kept when empty
    ├── .profiles.json.operations.json the receipts of profile creation, deletion and index quarantine (HM-10)
    └── profiles/                      0700
        ├── <24 lowercase hex>/        one additional profile: state.json, .writer.lock, journal, child/
        └── .quarantine-<id>-<UTC>/    a profile the boot guard could not prove revoked (HM-13b): delete only

The index is a file of its own because a ProductState has an exact key set (a key the running image does not know
stops it, products.ProductStore), and it holds no credential: profile ids, labels and loopback child ports only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
from typing import Callable, Iterable, Mapping, Sequence
import unicodedata

from .config import strict_json

logger = logging.getLogger(__name__)
DEFAULT_PROFILE = 'default'
DEFAULT_LABEL = 'Default'  # the default profile's row in the profile list (the panel shows 預設帳號)
INDEX_VERSION = 1
MAX_INDEX_BYTES = 65536
MAX_EXTRA_PROFILES = 5

# Ports (plan §5.4; contract §7, §8). The default profile's child keeps 3000 (lifecycle.CHILD_PORT); additional
# children get the first free port of 18000-18099 (more than enough for five; tests/owned_network.py keeps the tests
# off the same range), never 3000, 8081 or 8099. The index rules are the PaaS ones, word for word (HM-07 review MF-1,
# decided 2026-11-15): any port of 1024-65535 is no structural error (_index_entries); a duplicate or the default
# child's port stops only the profiles holding it (port_conflicts, PaaS _port_collisions); a port of the add-on's own
# listeners is not checked here either: the spawn check refuses it (HM-09: blocked, child_port_conflict; PaaS
# _port_refusal).
DEFAULT_CHILD_PORT = 3000
LISTENER_PORTS = frozenset({8081, 8099})
RESERVED_PORTS = frozenset({DEFAULT_CHILD_PORT, *LISTENER_PORTS})
MIN_PORT, MAX_PORT = 1024, 65535
FIRST_PROFILE_PORT, LAST_PROFILE_PORT = 18000, 18099

# Labels (contract §3.6; §8.8 #35, DQ-40 ④): stricter than the PaaS 1-80 characters and case-insensitive uniqueness.
LABEL_MAX = 80
RESERVED_LABELS = ('default', '預設帳號')
REFUSED_LABEL_CATEGORIES = frozenset({'Cc', 'Cf', 'Zl', 'Zp', 'Cs', 'Co', 'Cn'})

# Capacity (contract §5, DQ-07 + DQ-29 (a)): provisional values, as the PaaS launch policies have them; HM-19c measures
# on the target hardware before the first release and a change goes through a feature PR. OpenDesign and Odoo Manage
# get none (DQ-28: creating one answers 409 profile_product_unsupported).
EXTRA_PROFILE_LIMITS = {'odoo': 5, 'n8n': 2, 'hermes': 3, 'emqx': 3, 'litellm': 3, 'nextcloud': 3, 'headscale': 3,
                        'opendesign': 0, 'odoo-manage': 0}
CHILD_MEMORY_MIB = {'odoo': 100, 'n8n': 300, 'hermes': 160, 'emqx': 160, 'litellm': 160, 'nextcloud': 160,
                    'headscale': 160, 'opendesign': None, 'odoo-manage': None}
PROFILE_MEMORY_RESERVE_MIB = 256
MiB = 1024 * 1024


@dataclass(frozen=True)
class ProfileQuota:
    """One profile's request limits once its product is switched on (contract §5; §8.8 #15). No pool is shared: a
    profile never uses another profile's slots or bytes."""
    admission: int                # requests admitted before their body is read
    body_bytes: int               # request bytes read into memory and not forwarded yet
    forward_slots: int            # requests forwarded to the child at once
    forward_wait_seconds: float   # how long a request waits for a forward slot
    get_streams: int              # GET (SSE) streams at once
    queue: int                    # waiting requests per queue
    reserved_notifications: int   # slots kept for POSTs that carry no request
    pending_reply_bytes: int      # processed reply bytes not sent to the client yet
    child_connections: int        # the profile's own httpx client to its child


DEFAULT_PROFILE_QUOTA = ProfileQuota(64, 64 * MiB, 32, 1.0, 24, 32, 4, 32 * MiB, 40)
EXTRA_PROFILE_QUOTA = ProfileQuota(32, 64 * MiB, 16, 1.0, 8, 16, 4, 32 * MiB, 24)

# Index verdicts (DQ-12, 2026-11-14): CORRUPT and MODIFIED make 8081 answer 503 for every token, the default
# profile's included (a duplicate token cannot be ruled out); the panel still opens and offers "quarantine the profile
# index"; there is no manual repair on HA.
INDEX_ABSENT, INDEX_OK, INDEX_CORRUPT, INDEX_MODIFIED = 'absent', 'ok', 'corrupt', 'modified'
_STATES = (INDEX_ABSENT, INDEX_OK, INDEX_CORRUPT, INDEX_MODIFIED)

_PROFILE_ID = re.compile(r'[0-9a-f]{24}')
# Any profile's id (contract 1.1): the default profile's or an additional one's. HM-08: the one source of the grammar;
# gateway (the profile echo) and profile_runtime take it from here (HM-05 review, other observations 4).
PROFILE_ID = re.compile(DEFAULT_PROFILE + '|' + _PROFILE_ID.pattern)
_UTC = '%Y%m%dT%H%M%SZ'
QUARANTINE_PREFIX = '.quarantine-'
_QUARANTINE = re.compile(re.escape(QUARANTINE_PREFIX) + r'([0-9a-f]{24})-([0-9]{8}T[0-9]{6}Z)')


class ProfileDataError(RuntimeError):
    """Profile data on disk cannot be used or written (fails closed; never names a token or a label)."""


class IndexCorrupt(ValueError):
    """The profile index is unusable as a whole (plan §4.2: "整份壞")."""


class LabelError(ValueError):
    code = 'profile_label_invalid'


# ---------------------------------------------------------------------------------------------------------------
# Ids and labels
# ---------------------------------------------------------------------------------------------------------------

def is_profile_id(value) -> bool:
    """An additional profile's id: 24 lowercase hex characters (secrets.token_hex(12)), safe as a directory name."""
    return isinstance(value, str) and _PROFILE_ID.fullmatch(value) is not None


def new_profile_id(taken: Iterable[str] = ()) -> str:
    taken = set(taken)
    while (value := secrets.token_hex(12)) in taken:
        pass
    return value


def log_id(profile_id: str) -> str:
    """How log lines name a profile: 'default' or the first 8 characters of its id; never its label (I7)."""
    if profile_id == DEFAULT_PROFILE:
        return DEFAULT_PROFILE
    if not is_profile_id(profile_id):
        raise ValueError('not a profile id')
    return profile_id[:8]


def normalize_label(value) -> str:
    """The label as it is stored: the text without outer whitespace, 1-80 code points, and no control, format (bidi,
    zero-width), line or paragraph separator, surrogate, private-use or unassigned character."""
    if not isinstance(value, str):
        raise LabelError('invalid profile label')
    label = value.strip()
    if not 1 <= len(label) <= LABEL_MAX or any(unicodedata.category(c) in REFUSED_LABEL_CATEGORIES for c in label):
        raise LabelError('invalid profile label')
    return label


def label_key(label: str) -> str:
    """What two labels are compared by: NFKC, casefold, NFKC again (the second NFKC makes the key of a key the same
    key, e.g. after casefold expands a character)."""
    return unicodedata.normalize('NFKC', unicodedata.normalize('NFKC', label).casefold())


def label_taken(label: str, labels: Iterable[str]) -> bool:
    """Whether *label* equals a reserved name or one of *labels* after label_key (409 profile_label_conflict)."""
    key = label_key(label)
    return key in {label_key(value) for value in (*RESERVED_LABELS, *labels)}


# ---------------------------------------------------------------------------------------------------------------
# The index: profiles.json = {"version": 1, "profile_index": {id: {"label": ..., "port": ...}}}, in creation order
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexEntry:
    id: str
    label: str
    port: int


def _stored_label(value) -> bool:
    try:
        return normalize_label(value) == value
    except LabelError:
        return False


def _index_port(value) -> bool:
    return type(value) is int and MIN_PORT <= value <= MAX_PORT


def _entries(value) -> tuple[IndexEntry, ...]:
    if (not isinstance(value, dict) or set(value) != {'version', 'profile_index'}
            or type(value['version']) is not int or value['version'] != INDEX_VERSION
            or not isinstance(value['profile_index'], dict) or len(value['profile_index']) > MAX_EXTRA_PROFILES):
        raise IndexCorrupt('profile index unavailable')
    entries, keys = [], {label_key(name) for name in RESERVED_LABELS}
    for profile_id, item in value['profile_index'].items():
        if (not is_profile_id(profile_id) or not isinstance(item, dict) or set(item) != {'label', 'port'}
                or not _stored_label(item['label']) or not _index_port(item['port'])
                or label_key(item['label']) in keys):
            raise IndexCorrupt('profile index unavailable')
        keys.add(label_key(item['label']))
        entries.append(IndexEntry(profile_id, item['label'], item['port']))
    return tuple(entries)


def parse_index(raw: bytes) -> tuple[IndexEntry, ...]:
    """The entries of an index file's bytes, in creation order. Raises IndexCorrupt for anything else: not UTF-8
    JSON (strict: no duplicate key, no NaN), other top-level keys or version, more than five entries, an id, label or
    port the rules refuse, two labels with the same label_key or a reserved one."""
    if len(raw) > MAX_INDEX_BYTES:
        raise IndexCorrupt('profile index unavailable')
    try:
        value = strict_json(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise IndexCorrupt('profile index unavailable') from None
    return _entries(value)


def encode_index(entries: Sequence[IndexEntry]) -> bytes:
    """The file bytes of *entries*; IndexCorrupt for entries parse_index would refuse."""
    entries = tuple(entries)
    try:
        if len({entry.id for entry in entries}) != len(entries):
            raise ValueError
        raw = json.dumps({'version': INDEX_VERSION,
                          'profile_index': {e.id: {'label': e.label, 'port': e.port} for e in entries}},
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, AttributeError):
        raise IndexCorrupt('profile index unavailable') from None
    if parse_index(raw) != entries:
        raise IndexCorrupt('profile index unavailable')
    return raw


def port_conflicts(entries: Sequence[IndexEntry]) -> dict[int, tuple[str, ...]]:
    """Ports the index gives to more than one additional profile, or that are the default child's 3000, mapped to the
    profiles holding them in index order (PaaS _port_collisions): those are not started (disabled_reason
    port_conflict); every other profile, and the default profile with its port, keeps running. A listener port (8081,
    8099) that one profile holds is not listed, as in PaaS: the spawn check refuses it (HM-09, blocked_reason
    child_port_conflict)."""
    holders: dict[int, list[str]] = {}
    for entry in entries:
        holders.setdefault(entry.port, []).append(entry.id)
    return {port: tuple(ids) for port, ids in holders.items() if len(ids) > 1 or port == DEFAULT_CHILD_PORT}


def allocate_port(taken: Iterable[int] = (), *, occupied: Callable[[int], str | None] | None = None) -> int | None:
    """The first port of 18000-18099 that is not reserved or in *taken* (the index's ports and those of running
    children), or None (409 profile_port_unavailable). occupied (HM-09: port_occupied, the test bind of plan 5.4):
    a port it names a reason for is skipped too; left out, nothing is bound (the pure rule of HM-07)."""
    used = set(taken) | RESERVED_PORTS
    for port in range(FIRST_PROFILE_PORT, LAST_PROFILE_PORT + 1):
        if port in used or (occupied is not None and occupied(port) is not None):
            continue
        return port
    return None


# HM-09: the spawn check's test bind (plan 5.4; PaaS child_identity.port_occupied @69ac425, unchanged at cf3d0d5).
TEST_BIND_ADDRESSES = ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::1'),
                       (socket.AF_INET6, '::'))
# HM-09 review S-6: an IPv6 test bind the platform refuses (AppArmor, seccomp: EACCES, EPERM) is skipped, not taken for
# an occupied port (PaaS takes it so, and a switched-on product's default child would then never start); each
# (address, errno) is reported once a process.
REFUSED_IPV6_BINDS = (errno.EACCES, errno.EPERM)
_reported_binds: set = set()


def port_occupied(port: int) -> str | None:
    """Whether a child binding 127.0.0.1:port would run into a socket already there: the reason for the log (the
    address family and errno name only), or None. Test binds with SO_REUSEADDR on 127.0.0.1, 0.0.0.0, ::1 and :: (v6
    only): any listening socket, or a bound one without SO_REUSEADDR, on any of them (a wildcard included) makes one
    fail; a reusable one (TIME_WAIT) does not, as for uvicorn, Node and Go listeners. On Linux the wildcard test covers
    the specific addresses; BSD and macOS let SO_REUSEADDR stack a wildcard on a specific address, hence all four. No
    socket is kept, listened on or connected. A missing IPv6 is skipped, and so is an IPv6 bind the platform refuses
    (EACCES, EPERM: no program of the add-on binds IPv6 then, the child binds 127.0.0.1, and a dual-stack socket of
    another program still fails the IPv4 wildcard test), with one WARNING per address and errno; any IPv4 failure is
    an occupied port."""
    for family, address in TEST_BIND_ADDRESSES:
        try:
            probe = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue  # no such address family (IPv6 switched off)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            probe.bind((address, port))
        except OSError as exc:
            if family == socket.AF_INET6 and exc.errno in (errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT):
                continue
            name = errno.errorcode.get(exc.errno or 0, str(exc.errno))
            if family == socket.AF_INET6 and exc.errno in REFUSED_IPV6_BINDS:
                if (address, name) not in _reported_binds:
                    _reported_binds.add((address, name))
                    logger.warning('multi-profile: the IPv6 test bind on %s is refused (%s); the spawn check skips '
                                   'that address', address, name)
                continue
            return f"{'IPv6' if family == socket.AF_INET6 else 'IPv4'} test bind failed ({name})"
        finally:
            probe.close()
    return None


# ---------------------------------------------------------------------------------------------------------------
# Capacity (PaaS ProfileCapacity: the product's limit, and the cgroup memory formula when a limit is readable)
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ProfileCapacity:
    policy_limit: int
    memory_limit_mib: int | None = None
    child_memory_mib: int | None = None
    memory_extra_limit: int | None = None

    @property
    def limit(self) -> int:
        if self.memory_extra_limit is None:
            return self.policy_limit
        return min(self.policy_limit, self.memory_extra_limit)

    def required_memory_mib(self, extras: int) -> int | None:
        """The smallest memory limit that runs the default profile and *extras* additional ones."""
        if self.child_memory_mib is None:
            return None
        return PROFILE_MEMORY_RESERVE_MIB + (extras + 1) * self.child_memory_mib

    def disabled_reason(self, position: int) -> str | None:
        """Why the additional profile at 0-based index *position* is not started, or None (index order decides)."""
        if position >= self.policy_limit:
            return 'profile_limit'
        if self.memory_extra_limit is not None and position >= self.memory_extra_limit:
            return 'memory_capacity'
        return None


# HM-09: what the memory checks read (contract 5; PaaS profiles._memory_limit_mib @69ac425). Read when called.
CGROUP_MEMORY_LIMITS = (Path('/sys/fs/cgroup/memory.max'), Path('/sys/fs/cgroup/memory/memory.limit_in_bytes'))
MEMINFO = Path('/proc/meminfo')


def memory_limit_mib() -> int | None:
    """The container's memory ceiling in MiB (cgroup v2 memory.max, else v1 memory.limit_in_bytes), as PaaS reads it;
    None for no usable limit: "max", a v1 "no limit" (more than 1 TiB), nothing readable. An HA add-on normally has
    none (Supervisor sets no memory limit; HM-03a confirms on HAOS)."""
    for path in CGROUP_MEMORY_LIMITS:
        try:
            raw = path.read_text().strip()
        except OSError:
            continue
        if raw == 'max':
            return None
        try:
            mib = int(raw) // MiB
        except ValueError:
            continue
        return None if mib > 1024 * 1024 else mib
    return None


def available_memory_mib() -> int | None:
    """MemAvailable of /proc/meminfo in MiB (the host's, without lxcfs); None when it cannot be read (the caller then
    starts the child without the check and says so: never assumed)."""
    try:
        with open(MEMINFO, 'rb') as handle:
            text = handle.read(65536).decode('ascii', 'replace')
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith('MemAvailable:'):
            parts = line.split()
            if len(parts) == 3 and parts[2] == 'kB' and parts[1].isdigit():
                return int(parts[1]) // 1024
            return None
    return None


def supports_profiles(product: str) -> bool:
    return capacity(product).policy_limit > 0


def capacity(product: str, memory_limit_mib: int | None = None) -> ProfileCapacity:
    """The product's capacity; with a readable memory limit (cgroup memory.max, MiB) the PaaS formula: additional
    profiles = min(limit, max(1, (memory - 256) // child MiB) - 1). HM-09 reads the limit (memory_limit_mib) when the
    ProfileManager opens, and MemAvailable when the panel starts an additional child (profile_runtime)."""
    if product not in EXTRA_PROFILE_LIMITS:
        raise ValueError('unknown product')
    limit = min(MAX_EXTRA_PROFILES, EXTRA_PROFILE_LIMITS[product])
    child = CHILD_MEMORY_MIB[product]
    if child is None:
        return ProfileCapacity(limit)
    if memory_limit_mib is None:
        return ProfileCapacity(limit, child_memory_mib=child)
    children = max(1, (memory_limit_mib - PROFILE_MEMORY_RESERVE_MIB) // child)
    return ProfileCapacity(limit, memory_limit_mib, child, max(0, children - 1))


def mcp_listener_limit(product: str) -> int:
    """The 8081 listener's outer bound once switched on: the default profile's admission plus every additional
    profile's (64 + 32 x the product's limit; contract §5)."""
    return DEFAULT_PROFILE_QUOTA.admission + EXTRA_PROFILE_QUOTA.admission * capacity(product).policy_limit


def disabled_reasons(entries: Sequence[IndexEntry], limits: ProfileCapacity) -> dict[str, dict]:
    """Additional profiles whose child is not started, by id: the PaaS order (product limit, then memory, then a
    port conflict); HM-10 adds HA's own reasons (profile_unavailable, quarantined, dormant)."""
    blocks: dict[str, dict] = {}
    for position, entry in enumerate(entries):
        reason = limits.disabled_reason(position)
        if reason == 'memory_capacity':
            blocks[entry.id] = {'disabled_reason': reason, 'required_memory_mib': limits.required_memory_mib(position + 1)}
        elif reason is not None:
            blocks[entry.id] = {'disabled_reason': reason}
    for ids in port_conflicts(entries).values():
        for profile_id in ids:
            blocks.setdefault(profile_id, {'disabled_reason': 'port_conflict'})
    return blocks


# ---------------------------------------------------------------------------------------------------------------
# The index file: signature, read, recheck, write
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexSignature:
    """What the management process remembers of the index it last read or wrote (plan §4.2, C1-S8). The ctime and the
    link count catch what the same uid can put back (the bytes, the size, the mtime through os.utime). Same uid is no
    security boundary (DQ-37): this catches mistakes and stray edits, not an attacker."""
    st_dev: int
    st_ino: int
    st_mtime_ns: int
    st_ctime_ns: int
    st_size: int
    st_nlink: int

    @classmethod
    def of(cls, info: os.stat_result) -> 'IndexSignature':
        return cls(info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size, info.st_nlink)


def signature_of(path: Path) -> IndexSignature | None:
    """The signature of the entry at *path* (not following a link); None when there is none."""
    try:
        return IndexSignature.of(os.lstat(path))
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class IndexView:
    """The index as read or written last: its state, its entries (only when usable) and its signature."""
    state: str
    entries: tuple[IndexEntry, ...]
    signature: IndexSignature | None

    def __post_init__(self):
        if self.state not in _STATES or (self.entries and self.state != INDEX_OK):
            raise ValueError('invalid index view')

    @property
    def serves_mcp(self) -> bool:
        """False: 8081 answers 503 for every token, the default profile's included (DQ-12; HM-08)."""
        return self.state in (INDEX_ABSENT, INDEX_OK)

    @property
    def offers_quarantine(self) -> bool:
        """True: the panel opens as usual and offers "quarantine the profile index" (DQ-12; HM-10)."""
        return self.state in (INDEX_CORRUPT, INDEX_MODIFIED)


def read_index(path: Path) -> IndexView:
    """Read the index at startup (or after the index quarantine). ABSENT: no file (no additional profile was ever
    made). CORRUPT: not a single-link regular 0600 file of this uid within 64 KiB, or parse_index refuses it. Reading
    never creates, writes or chmods anything: a chmod would change the very ctime the signature compares."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (FileNotFoundError, NotADirectoryError):
        return IndexView(INDEX_ABSENT, (), None)
    except OSError:
        return IndexView(INDEX_CORRUPT, (), signature_of_or_none(path))
    try:
        info = os.fstat(fd)
        signature = IndexSignature.of(info)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_INDEX_BYTES):
            return IndexView(INDEX_CORRUPT, (), signature)
        chunks, size = [], 0
        while chunk := os.read(fd, MAX_INDEX_BYTES + 1 - size):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_INDEX_BYTES:
                return IndexView(INDEX_CORRUPT, (), signature)
        try:
            return IndexView(INDEX_OK, parse_index(b''.join(chunks)), signature)
        except IndexCorrupt:
            return IndexView(INDEX_CORRUPT, (), signature)
    except OSError:
        return IndexView(INDEX_CORRUPT, (), signature_of_or_none(path))
    finally:
        os.close(fd)


def signature_of_or_none(path: Path) -> IndexSignature | None:
    try:
        return signature_of(path)
    except OSError:
        return None


def recheck_index(path: Path, view: IndexView) -> IndexView:
    """The per-request check (one lstat): *view* itself while the index is the one this process last read or wrote,
    otherwise MODIFIED (changed, replaced, appeared or disappeared behind the add-on's back). The caller keeps the view
    this returns: a MODIFIED view stays MODIFIED whatever the file does next (put back, removed again), until a
    restart reads the index again (plan §4.2; contract §2.3 "直到重啟")."""
    if view.state == INDEX_MODIFIED:
        return view
    try:
        current = signature_of(path)
    except OSError:
        return IndexView(INDEX_MODIFIED, (), None)
    if current == view.signature:
        return view
    return IndexView(INDEX_MODIFIED, (), current)


def write_index(path: Path, entries: Sequence[IndexEntry], *, expected: IndexView) -> IndexView:
    """Replace the index with *entries* while it is still the one *expected* describes: the view this process read at
    startup or wrote last, ABSENT or OK. A CORRUPT or MODIFIED index, or one that changed behind the add-on's back since
    *expected*, is never written over (ProfileDataError): that would wash away DQ-12's "503 until a restart", which
    only the index quarantine (HM-10) ends. The write: a new 0600 file in the same directory, fsync, rename over the
    index, fsync the directory. Returns the view of what was written; its signature is the new baseline (the rename
    changes the ctime, so it is taken from the written file afterwards). On failure the previous index stays unless the
    rename already happened (then a recheck against the old baseline answers MODIFIED: fail closed)."""
    if expected.state not in (INDEX_ABSENT, INDEX_OK) or recheck_index(path, expected) is not expected:
        raise ProfileDataError('profile index changed')
    raw = encode_index(entries)
    path = Path(path)
    temporary = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)  # exactly 0600 whatever the umask: read_index refuses any other mode
        view = memoryview(raw)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        signature = IndexSignature.of(os.fstat(fd))
    except OSError:
        raise ProfileDataError('profile index write failed') from None
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temporary)  # gone after the rename; left only by a failure
        except OSError:
            pass
    return IndexView(INDEX_OK, tuple(entries), signature)


# ---------------------------------------------------------------------------------------------------------------
# Layout, the profiles directory and what it holds
# ---------------------------------------------------------------------------------------------------------------

# The names in the default profile's store directory (plan §4.1), written here and nowhere else in the package: Layout
# builds its paths from them and restore_detect (HM-13a) looks them up through its directory descriptor.
# packaging/entrypoint.py runs as root with the standard library only, before this package and its venv are on the
# path, so it keeps a copy of RESTORE_MARKER_NAME and PROFILE_DATA_NAMES; tests/test_restore_detection.py pins that
# copy to these. None of these files holds a secret.
INDEX_NAME = 'profiles.json'
INDEX_OPERATIONS_NAME = '.profiles.json.operations.json'
PROFILES_NAME = 'profiles'
PROFILE_DATA_NAMES = (INDEX_NAME, PROFILES_NAME)  # "profile data on disk" (plan §3.3): either name, any kind of entry
SENTINEL_NAME = '.instance-sentinel'  # restore detection, signal 2 (HM-13a)
INSTANCE_RECORD_NAME = '.instance-record'  # the sentinel's (st_ino, st_ctime_ns)
INSTANCE_RECORD_TEMPORARY_NAME = '.instance-record.tmp'  # the next record, before it replaces the record
RESTORE_MARKER_NAME = '.restore-detected'  # restore detection, signal 1: saved by packaging/entrypoint.py
REVOKE_ALL_MARKER_NAME = '.revoke-all-pending'  # the boot guard (HM-13b)
RESTORE_RECORD_NAME = 'restore-record.json'  # the boot guard (HM-13b)


@dataclass(frozen=True)
class Layout:
    """The paths of the multi-profile data under the default profile's store directory (normally /data/mcp)."""
    root: Path

    @property
    def index(self) -> Path:
        return self.root / INDEX_NAME

    @property
    def index_operations(self) -> Path:
        return self.root / INDEX_OPERATIONS_NAME

    @property
    def profiles(self) -> Path:
        return self.root / PROFILES_NAME

    def profile(self, profile_id: str) -> Path:
        if not is_profile_id(profile_id):
            raise ValueError('not a profile id')
        return self.profiles / profile_id

    def child(self, profile_id: str) -> Path:
        """The additional profile's child working directory (also HOME of an n8n child, HM-25)."""
        return self.profile(profile_id) / 'child'

    # Restore detection and the boot guard (HM-13a, HM-13b); none of them holds a secret.
    @property
    def sentinel(self) -> Path:
        return self.root / SENTINEL_NAME

    @property
    def instance_record(self) -> Path:
        return self.root / INSTANCE_RECORD_NAME

    @property
    def restore_marker(self) -> Path:
        return self.root / RESTORE_MARKER_NAME

    @property
    def revoke_all_marker(self) -> Path:
        return self.root / REVOKE_ALL_MARKER_NAME

    @property
    def restore_record(self) -> Path:
        return self.root / RESTORE_RECORD_NAME


def _utc(when: datetime) -> str:
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError('a time zone is required')
    return when.astimezone(timezone.utc).strftime(_UTC)


def quarantine_name(profile_id: str, when: datetime) -> str:
    """'.quarantine-<id>-<UTC>': where the boot guard moves a profile it cannot prove revoked (HM-13b)."""
    if not is_profile_id(profile_id):
        raise ValueError('not a profile id')
    return QUARANTINE_PREFIX + profile_id + '-' + _utc(when)


def parse_quarantine_name(name: str) -> tuple[str, str] | None:
    match = _QUARANTINE.fullmatch(name) if isinstance(name, str) else None
    return (match.group(1), match.group(2)) if match else None


def index_quarantine_name(when: datetime) -> str:
    """What "quarantine the profile index" renames profiles.json to (contract §3.6; HM-10)."""
    return INDEX_NAME + '.quarantine-' + _utc(when)


# HM-10 (HM-07 review S-15): the second quarantine within one second gets a number, never the first one's name.
MAX_QUARANTINE_NUMBER = 999


def free_index_quarantine_name(layout: Layout, when: datetime) -> str:
    """index_quarantine_name(when), or with -2, -3 ... appended when that name is taken (anything at it, a link or a
    dangling one included). ProfileDataError when none is free. The caller holds the add-on's profile lock, so no
    other quarantine of this process picks the same name before it is used (same uid is no boundary, DQ-37)."""
    base = index_quarantine_name(when)
    for number in range(1, MAX_QUARANTINE_NUMBER + 1):
        name = base if number == 1 else f'{base}-{number}'
        try:
            os.lstat(layout.root / name)
        except FileNotFoundError:
            return name
        except OSError:
            break
    raise ProfileDataError('no quarantine name is free')


def move_index_aside(layout: Layout, name: str) -> None:
    """"Quarantine the profile index" (DQ-12; contract §3.6): rename profiles.json, whatever it is (a file, a link, a
    directory: the rename never follows a link), to *name* (free_index_quarantine_name) in the same directory, then
    fsync the directory so the new name is on disk. ProfileDataError when the rename fails (nothing moved)."""
    try:
        os.rename(layout.index, layout.root / name)
    except OSError:
        raise ProfileDataError('profile index not moved') from None
    try:
        root = os.open(layout.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(root)
        finally:
            os.close(root)
    except OSError:
        pass  # moved; only its durability across a power loss is in doubt (the next start reads what is there)


def index_bytes(path: Path) -> tuple[IndexSignature | None, bytes]:
    """The index entry's signature and up to MAX_INDEX_BYTES + 1 of its bytes, read without following a link (empty
    when it is not a readable regular file): what an unusable index is identified by (HM-10: the quarantine's If-Match,
    contract §3.5)."""
    signature = signature_of_or_none(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return signature, b''
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return signature, b''
        chunks, size = [], 0
        while size <= MAX_INDEX_BYTES and (chunk := os.read(fd, MAX_INDEX_BYTES + 1 - size)):
            chunks.append(chunk)
            size += len(chunk)
        return signature, b''.join(chunks)
    except OSError:
        return signature, b''
    finally:
        os.close(fd)


def remove_profile_directory(layout: Layout, profile_id: str) -> bool:
    """Delete an additional profile's directory and all it holds (plan §4.4, the last step of a deletion; DQ-14), never
    following a link: from /data/mcp/profiles opened without following a link and checked as this uid's directory
    (scan_profiles' rule), shutil.rmtree's descriptor-based walk below it (a link at the profile's own name, or a
    profiles entry that is a link, is refused). False when anything could not be removed: what is left is an orphan,
    listed and deletable, never opened or routed."""
    name = layout.profile(profile_id).name  # ValueError for anything but a profile id
    try:
        fd = os.open(layout.profiles, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return True  # no profiles directory: nothing of the profile is left
    except OSError:
        return False
    try:
        _owned_directory(fd, layout.profiles)
        try:
            info = os.lstat(name, dir_fd=fd)
        except FileNotFoundError:
            return True
        if not stat.S_ISDIR(info.st_mode) or not shutil.rmtree.avoids_symlink_attacks:
            return False
        shutil.rmtree(name, dir_fd=fd)
        return True
    except (OSError, ProfileDataError):
        return False
    finally:
        os.close(fd)


def has_profile_data(root: Path) -> bool:
    """Plan §3.3: whether profile data exists (profiles.json or profiles/, any kind of entry, a link included). When
    that cannot be told, the answer is yes: that direction only revokes more or refuses a start."""
    for name in PROFILE_DATA_NAMES:
        try:
            os.lstat(Path(root) / name)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return True
        return True
    return False


def _owned_directory(fd: int, path: Path) -> os.stat_result:
    info = os.fstat(fd)
    current = os.lstat(path)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)):
        raise ProfileDataError('profiles directory unavailable')
    return info


def ensure_profiles_directory(layout: Layout) -> None:
    """Make /data/mcp/profiles (0700) when missing; refuse one that is a link, not a directory or another uid's, and
    tighten a widened mode (PaaS ProfileRegistry._directory). Then fsync /data/mcp, so the name profiles is on disk
    before a profile in it can be listed by the index."""
    try:
        try:
            os.mkdir(layout.profiles, 0o700)
        except FileExistsError:
            pass
        fd = os.open(layout.profiles, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = _owned_directory(fd, layout.profiles)
            if stat.S_IMODE(info.st_mode) != 0o700:
                os.fchmod(fd, 0o700)
        finally:
            os.close(fd)
        root = os.open(layout.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(root)
        finally:
            os.close(root)
    except OSError:
        raise ProfileDataError('profiles directory unavailable') from None


@dataclass(frozen=True)
class ProfilesScan:
    """What /data/mcp/profiles holds: profile directories (24 hex names), quarantine directories, and how many other
    entries (files, links, other names), each list sorted."""
    profiles: tuple[str, ...]
    quarantined: tuple[str, ...]
    other: int


def scan_profiles(layout: Layout) -> ProfilesScan:
    """List /data/mcp/profiles without following links (an empty scan when it does not exist). Only looks: never
    creates, opens a profile or changes a mode. ProfileDataError for a profiles entry that is a link, not a directory
    or another uid's."""
    try:
        fd = os.open(layout.profiles, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (FileNotFoundError, NotADirectoryError) as exc:
        if isinstance(exc, NotADirectoryError) or os.path.lexists(layout.profiles):
            raise ProfileDataError('profiles directory unavailable') from None
        return ProfilesScan((), (), 0)
    except OSError:
        raise ProfileDataError('profiles directory unavailable') from None
    try:
        _owned_directory(fd, layout.profiles)
        found, quarantined, other = [], [], 0
        with os.scandir(fd) as entries:
            for entry in entries:
                directory = entry.is_dir(follow_symlinks=False)
                if directory and is_profile_id(entry.name):
                    found.append(entry.name)
                elif directory and parse_quarantine_name(entry.name):
                    quarantined.append(entry.name)
                else:
                    other += 1
        return ProfilesScan(tuple(sorted(found)), tuple(sorted(quarantined)), other)
    except OSError:
        raise ProfileDataError('profiles directory unavailable') from None
    finally:
        os.close(fd)


@dataclass(frozen=True)
class Consistency:
    """Plan §4.4, checked at startup and after every index change. HM-07 reports; later slices act on it.

    unavailable: indexed profiles without their directory or a readable state (never re-created; delete only).
    orphans: profile directories the index does not list (never opened or routed; nothing here deletes them:
    the deletion rules are HM-10's, DQ-14).
    quarantined, other_entries: the scan's quarantine directories and its count of anything else.
    port_conflicts: port_conflicts() of the index.
    shared_secrets: groups of profiles linked by a shared token or child token value, of either kind (I2: a copied
    directory; HM-08 answers 503 for such a token, DQ-09); in a group the default profile comes first, then index
    order, then any other id given (an orphan).
    """
    unavailable: tuple[str, ...]
    orphans: tuple[str, ...]
    quarantined: tuple[str, ...]
    other_entries: int
    port_conflicts: Mapping[int, tuple[str, ...]]
    shared_secrets: tuple[tuple[str, ...], ...]


def check_consistency(entries: Sequence[IndexEntry], scan: ProfilesScan,
                      credentials: Mapping[str, tuple[str | None, str] | None]) -> Consistency:
    """*credentials*: (token, child token) by profile id for every profile whose state could be read (the default
    profile's under 'default'), None for one that could not; a revoked token is None and shares nothing."""
    ids = [entry.id for entry in entries]
    present = set(scan.profiles)
    unavailable = tuple(i for i in ids if i not in present or credentials.get(i) is None)
    orphans = tuple(sorted(present - set(ids)))
    position = {profile_id: number for number, profile_id in enumerate(ids)}

    def order(profile_id):
        if profile_id == DEFAULT_PROFILE:
            return (0, 0, '')
        if profile_id in position:
            return (1, position[profile_id], '')
        return (2, 0, profile_id)

    holders: dict[str, set[str]] = {}
    for profile_id, pair in credentials.items():
        for value in pair or ():
            if value is not None:
                holders.setdefault(value, set()).add(profile_id)
    groups: list[set[str]] = []
    for holding in holders.values():
        if len(holding) < 2:
            continue
        joined = set(holding)
        for group in [g for g in groups if g & joined]:  # profiles linked through any shared value: one group
            joined |= group
            groups.remove(group)
        groups.append(joined)
    shared = tuple(sorted((tuple(sorted(group, key=order)) for group in groups),
                          key=lambda group: [order(member) for member in group]))
    return Consistency(unavailable, orphans, scan.quarantined, scan.other, port_conflicts(entries), shared)
