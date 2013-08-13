import idiokit
import xml.etree.cElementTree as etree
from abusehelper.core import bot, cymruwhois, events, utils


class RSSBot(bot.PollingBot):
    feeds = bot.ListParam("a list of RSS feed URLs")
    use_cymru_whois = bot.BoolParam()
    http_headers = bot.ListParam("a list of http header (k,v) tuples", default=[])

    def __init__(self, *args, **keys):
        bot.PollingBot.__init__(self, *args, **keys)
        self.past_events = set()

    def feed_keys(self, **_):
        for feed in self.feeds:
            yield (feed,)

    def poll(self, url):
        if self.use_cymru_whois:
            return self._poll(url) | cymruwhois.augment()
        return self._poll(url)

    @idiokit.stream
    def _poll(self, url):
        try:
            self.log.info('Downloading feed from: "%s"', url)
            _, fileobj = yield utils.fetch_url(url, headers=self.http_headers)
        except utils.FetchUrlFailed, e:
            self.log.error('Failed to download feed "%s": %r', url, e)
            idiokit.stop(False)

        self.log.info("Finished downloading the feed.")
        new_events = set()

        byte = fileobj.read(1)
        while byte and byte != "<":
            byte = fileobj.read(1)

        if byte == "<":
            fileobj.seek(-1, 1)
            try:
                for _, elem in etree.iterparse(fileobj):
                    for event in self._parse(elem, url):
                        if event:
                            id = event.value("id", None)
                            if id:
                                new_events.add(id)
                            yield idiokit.send(event)
            except SyntaxError, e:
                self.log.error('Invalid format on feed: "%s", "%r"', url, e)

        for id in self.past_events:
            if id not in new_events:
                event = events.Event()
                event.add("id", id)
                yield idiokit.send(event)
        self.past_events = new_events

    def _parse(self, elem, url):
        items = elem.findall("item")
        if not items:
            return

        for item in items:
            args = {"source": url}
            for element in list(item):
                if element.text and element.tag:
                    args[element.tag] = element.text

            event = self.create_event(**args)
            yield event

    def create_event(self, **keys):
        event = events.Event()
        for key, value in keys.iteritems():
            if value:
                event.add(key, value)
        return event

if __name__ == "__main__":
    RSSBot.from_command_line().execute()
