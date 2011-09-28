import csv
import time
import socket
import urllib2
import httplib
import collections
import email.parser

from idiokit import threado, util
from abusehelper.core import events
from cStringIO import StringIO

class FetchUrlFailed(Exception):
    pass

class HTTPError(FetchUrlFailed):
    def __init__(self, code, msg, headers, fileobj):
        FetchUrlFailed.__init__(self, code, msg)

        self.code = code
        self.msg = msg
        self.headers = headers
        self.fileobj = fileobj

    def __str__(self):
        return "HTTP Error %d: %s" % (self.code, self.msg)

@threado.stream
def fetch_url(inner, url, opener=None):
    if opener is None:
        opener = urllib2.build_opener()

    try:
        reader = inner.thread(opener.open, url)
        while not reader.has_result():
            yield inner, reader

        fileobj = reader.result()
        reader = inner.thread(fileobj.read)
        try:
            while not reader.has_result():
                yield inner, reader
        finally:
            fileobj.close()
            
        info = fileobj.info()
        info = email.parser.Parser().parsestr(str(info), headersonly=True)

        inner.finish(info, StringIO(reader.result()))
    except urllib2.HTTPError, he:
        raise HTTPError(he.code, he.msg, he.headers, he.fp)
    except (urllib2.URLError, httplib.HTTPException, socket.error), error:
        raise FetchUrlFailed(str(error))

@threado.stream
def csv_to_events(inner, fileobj, delimiter=",", columns=None, charset=None):
    if columns is None:
        reader = csv.DictReader(fileobj, delimiter=delimiter)
    else:
        reader = csv.reader(fileobj, delimiter=delimiter)

    if charset is None:
        decode = util.guess_encoding
    else:
        decode = lambda x: x.decode(charset)

    for row in reader:
        yield
        list(inner)

        if columns is not None:
            row = dict(zip(columns, row))
            
        event = events.Event()
        for key, value in row.items():
            if None in (key, value):
                continue
            if not value:
                continue
            key = decode(key.lower().strip())
            value = decode(value.strip())
            event.add(key, value)
                
        inner.send(event)

class TimedCache(object):
    def __init__(self, cache_time):
        self.cache = dict()
        self.queue = collections.deque()
        self.cache_time = cache_time

    def _expire(self):
        current_time = time.time()

        while self.queue:
            expire_time, key = self.queue[0]
            if expire_time > current_time:
                break
            self.queue.popleft()

            other_time, _ = self.cache[key]
            if other_time == expire_time:
                del self.cache[key]

    def get(self, key, default):
        self._expire()
        if key not in self.cache:
            return default
        _, value = self.cache[key]
        return value

    def set(self, key, value):
        self._expire()
        expire_time = time.time() + self.cache_time
        self.queue.append((expire_time, key))
        self.cache[key] = expire_time, value
