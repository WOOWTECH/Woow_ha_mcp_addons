"""Owned in-memory fake of the Nextcloud endpoints the pinned child uses (OCS cloud/user, WebDAV files, CalDAV).

Only dummy credentials; never a real backend. Shapes follow Nextcloud 35 as the vendored child parses them
(nextcloud_mcp_server/client.py, webdav.py, caldav.py): a 207 multistatus with DAV: props, ETag headers on GET and
PUT, If-None-Match / If-Match preconditions answered with 412.
"""
import base64
from urllib.parse import quote, unquote, urlsplit
from xml.sax.saxutils import escape

USER = 'tester'
PASSWORD = 'DUMMY'
OCS_PATH = '/ocs/v2.php/cloud/user?format=json'
FILES = f'/remote.php/dav/files/{USER}/'
CALENDARS = f'/remote.php/dav/calendars/{USER}/'
TODO = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//owned//test//EN\r\nBEGIN:VTODO\r\nUID:owned-task\r\n'
        'SUMMARY:Owned task\r\nSTATUS:NEEDS-ACTION\r\nDUE:20261010T090000Z\r\nEND:VTODO\r\nEND:VCALENDAR\r\n')


def basic(user=USER, password=PASSWORD):
    return 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()


def initial_files():
    """path -> (bytes or None for a folder, etag)."""
    return {'': (None, 'home'), 'Documents': (None, 'docs'), 'Owned': (None, 'owned'),
            'Documents/notes.md': (b'# Notes\nhello\n', 'one'), 'Documents/old.txt': (b'old\n', 'old')}


def multistatus(responses):
    body = ''.join(f'<d:response><d:href>{escape(href)}</d:href><d:propstat><d:prop>{props}</d:prop>'
                   f'<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>' for href, props in responses)
    return ('<?xml version="1.0" encoding="utf-8"?><d:multistatus xmlns:d="DAV:" '
            'xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:a="http://apple.com/ns/ical/">' + body
            + '</d:multistatus>').encode()


class NextcloudFake:
    """handle() answers one request: (status, headers, body). Each successful PUT/DELETE appends a mutation."""

    def __init__(self, files=None):
        self.files = initial_files() if files is None else files
        self.mutations = []
        self.counter = 0

    def file_props(self, path):
        data, etag = self.files[path]
        if data is None:
            return f'<d:resourcetype><d:collection/></d:resourcetype><d:getetag>"{etag}"</d:getetag>'
        return (f'<d:resourcetype/><d:getcontentlength>{len(data)}</d:getcontentlength>'
                f'<d:getlastmodified>Wed, 07 Oct 2026 12:00:00 GMT</d:getlastmodified>'
                f'<d:getetag>"{etag}"</d:getetag><d:getcontenttype>text/plain</d:getcontenttype>')

    @staticmethod
    def href(path):
        return FILES + '/'.join(quote(part) for part in path.split('/')) if path else FILES

    def handle(self, command, target, headers, body):
        if headers.get('Authorization') != basic():
            return 401, {}, b''
        if target == OCS_PATH and command == 'GET':
            assert headers.get('OCS-APIRequest') == 'true'
            return 200, {'Content-Type': 'application/json'}, (
                b'{"ocs": {"meta": {"status": "ok", "statuscode": 200}, "data": {"id": "%s"}}}' % USER.encode())
        path = unquote(urlsplit(target).path)
        if path.startswith(CALENDARS):
            return self.calendar(command, path[len(CALENDARS):].strip('/'))
        if not path.startswith(FILES):
            return 404, {}, b''
        name = path[len(FILES):].strip('/')
        if command == 'PROPFIND':
            if name not in self.files:
                return 404, {}, b''
            entries = [name]
            if headers.get('Depth') == '1' and self.files[name][0] is None:
                prefix = name + '/' if name else ''
                entries += sorted(p for p in self.files if p and p.startswith(prefix) and '/' not in p[len(prefix):])
            return 207, {'Content-Type': 'application/xml; charset=utf-8'}, multistatus(
                [(self.href(p), self.file_props(p)) for p in entries])
        if command == 'GET':
            if name not in self.files or self.files[name][0] is None:
                return 404, {}, b''
            data, etag = self.files[name]
            return 200, {'Content-Type': 'text/plain', 'ETag': f'"{etag}"'}, data
        if command == 'PUT':
            parent = name.rsplit('/', 1)[0] if '/' in name else ''
            if parent not in self.files or self.files[parent][0] is not None:
                return 404, {}, b''
            if headers.get('If-None-Match') == '*' and name in self.files:
                return 412, {}, b''
            match = headers.get('If-Match')
            if match is not None and (name not in self.files or match != f'"{self.files[name][1]}"'):
                return 412, {}, b''
            created = name not in self.files
            self.counter += 1
            self.files[name] = (body, f'v{self.counter}')
            self.mutations.append(('PUT', name))
            return (201 if created else 204), {'ETag': f'"v{self.counter}"'}, b''
        if command == 'DELETE':
            if name not in self.files:
                return 404, {}, b''
            if headers.get('If-Match') != f'"{self.files[name][1]}"':
                return 412, {}, b''
            del self.files[name]
            self.mutations.append(('DELETE', name))
            return 204, {}, b''
        return 405, {}, b''

    @staticmethod
    def calendar(command, name):
        if command == 'PROPFIND' and name == '':
            home = '<d:resourcetype><d:collection/></d:resourcetype>'
            personal = ('<d:displayname>Personal</d:displayname><d:resourcetype><d:collection/><c:calendar/>'
                        '</d:resourcetype><c:supported-calendar-component-set><c:comp name="VEVENT"/>'
                        '<c:comp name="VTODO"/></c:supported-calendar-component-set>'
                        '<a:calendar-color>#0082c9</a:calendar-color>'
                        '<d:current-user-privilege-set><d:privilege><d:read/></d:privilege>'
                        '<d:privilege><d:write/></d:privilege></d:current-user-privilege-set>')
            return 207, {'Content-Type': 'application/xml; charset=utf-8'}, multistatus(
                [(CALENDARS, home), (CALENDARS + 'personal/', personal)])
        if command == 'REPORT' and name == 'personal':
            props = f'<d:getetag>"task"</d:getetag><c:calendar-data>{escape(TODO)}</c:calendar-data>'
            return 207, {'Content-Type': 'application/xml; charset=utf-8'}, multistatus(
                [(CALENDARS + 'personal/owned-task.ics', props)])
        return 404, {}, b''


def respond(handler, status, headers, body):
    """Write a NextcloudFake answer through a BaseHTTPRequestHandler."""
    handler.send_response(status)
    for key, value in headers.items():
        handler.send_header(key, value)
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    if body:
        handler.wfile.write(body)


def is_nextcloud(path):
    return path.startswith(('/ocs/', '/remote.php/'))


READS = [('get_file_tree', {}), ('get_file_tree', {'path': 'Documents', 'depth': 2}),
         ('get_file_content', {'path': 'Documents/notes.md'}), ('read_text_file', {'path': '/Documents/notes.md'}),
         ('list_calendars', {}), ('list_tasks', {}), ('list_tasks', {'calendar': 'personal', 'include_completed': True})]
WRITES = [('create_text_file', {'path': 'Owned/new.md', 'content': '# New\n'}),
          ('update_text_file', {'path': 'Documents/notes.md', 'content': '# Notes\nchanged\n', 'expected_etag': 'one'}),
          ('upload_file', {'path': 'Owned/upload.bin', 'content_base64': base64.b64encode(b'\x00\x01owned').decode()}),
          ('delete_file_checked', {'path': 'Documents/old.txt', 'expected_etag': 'old'})]
