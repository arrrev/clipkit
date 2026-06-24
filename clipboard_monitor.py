import time
import objc
from Foundation import NSObject, NSTimer, NSRunLoop
from AppKit import NSPasteboard, NSStringPboardType, NSTIFFPboardType, NSImage
import settings as S


class ClipboardItem:
    def __init__(self, kind, data, preview):
        self.kind = kind      # 'text' or 'image'
        self.data = data      # str or NSImage
        self.preview = preview
        self.timestamp = time.time()
        self.size_bytes = len(data.encode('utf-8')) if kind == 'text' else 0

    def copy_to_clipboard(self):
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        if self.kind == 'text':
            pb.setString_forType_(self.data, NSStringPboardType)
        elif self.kind == 'image':
            pb.writeObjects_([self.data])


class ClipboardMonitor(NSObject):

    def init(self):
        self = objc.super(ClipboardMonitor, self).init()
        self._on_change = None
        self._history = []       # list of ClipboardItem, newest first
        self._last_change_count = -1
        self._timer = None
        return self

    def setCallback_(self, callback):
        self._on_change = callback

    @property
    def history(self):
        return list(self._history)

    def start(self):
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, 'checkClipboard:', None, True)
        NSRunLoop.mainRunLoop().addTimer_forMode_(self._timer, 'kCFRunLoopCommonModes')

    def stop(self):
        if self._timer:
            self._timer.invalidate()
            self._timer = None

    @objc.typedSelector(b'v@:@')
    def checkClipboard_(self, timer):
        pb = NSPasteboard.generalPasteboard()
        count = pb.changeCount()
        if count == self._last_change_count:
            return
        self._last_change_count = count
        item = self._readPasteboard_(pb)
        if item:
            self._storeItem_(item)

    def _readPasteboard_(self, pb):
        types = pb.types()
        if not types:
            return None

        if (NSTIFFPboardType in types or 'public.png' in types or 'public.tiff' in types):
            img = NSImage.alloc().initWithPasteboard_(pb)
            if img:
                size = img.size()
                preview = f"Image ({int(size.width)}×{int(size.height)})"
                item = ClipboardItem('image', img, preview)
                item.size_bytes = int(size.width * size.height * 4)
                return item

        text = pb.stringForType_(NSStringPboardType)
        if text is None:
            text = pb.stringForType_('public.utf8-plain-text')
        if text:
            text = str(text)
            if not text.strip():
                return None
            preview = text[:120].replace('\n', ' ↵ ')
            return ClipboardItem('text', text, preview)

        return None

    def _storeItem_(self, item):
        # Skip duplicate of most recent
        if self._history:
            last = self._history[0]
            if last.kind == item.kind == 'text' and last.data == item.data:
                return

        self._history.insert(0, item)
        self._enforce_limits()

        if self._on_change:
            self._on_change()

    def _enforce_limits(self):
        cfg = S.get()
        max_items = cfg.max_items
        max_bytes = cfg.buffer_size_mb * 1024 * 1024

        # Trim by count
        while len(self._history) > max_items:
            self._history.pop()

        # Trim by total size
        total = sum(it.size_bytes for it in self._history)
        while total > max_bytes and self._history:
            removed = self._history.pop()
            total -= removed.size_bytes

    def clearHistory(self):
        self._history.clear()
