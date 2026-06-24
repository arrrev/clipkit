import time
import objc
from Foundation import NSObject, NSIndexSet, NSMutableArray
from transform import TRANSFORMS, applicable_transforms
from AppKit import (
    NSPanel, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSMakeRect, NSMakeSize, NSScreen,
    NSScrollView, NSTableView, NSTableColumn, NSTableCellView,
    NSTextField, NSFont, NSColor, NSImage, NSButton, NSImageView,
    NSBezelStyleRounded, NSView, NSMenu, NSMenuItem,
    NSViewWidthSizable, NSViewHeightSizable, NSViewMinYMargin,
    NSApplication, NSFloatingWindowLevel,
    NSPasteboard, NSStringPboardType,
    NSImageScaleProportionallyUpOrDown,
    NSImageScaleProportionallyDown,
    NSLineBreakByTruncatingTail,
    NSCellImagePosition,
)

ROW_H = 56
THUMB_W = 60


class HistoryDataSource(NSObject):
    def init(self):
        self = objc.super(HistoryDataSource, self).init()
        self._items = []
        return self

    def setItems_(self, items):
        self._items = items

    def numberOfRowsInTableView_(self, tv):
        return len(self._items)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        return None  # we use view-based cells


class HistoryWindowController(NSObject):

    def init(self):
        self = objc.super(HistoryWindowController, self).init()
        self._monitor = None
        self._transform_ctrl = None
        self._all_items = []   # all (item, pinned) pairs
        self._shown = []       # currently filtered/sorted list of items
        self._window = None
        self._table = None
        self._data_source = None
        self._search = None
        self._build()
        return self

    def setMonitor_onPaste_(self, monitor, on_paste):
        self._monitor = monitor

    def setTransformCtrl_(self, ctrl):
        self._transform_ctrl = ctrl

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        screen = NSScreen.mainScreen().frame()
        w, h = 560, 520
        x = (screen.size.width - w) / 2
        y = (screen.size.height - h) / 2

        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskResizable)
        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h), style, NSBackingStoreBuffered, False)
        self._window.setTitle_('ClipKit — History')
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setReleasedWhenClosed_(False)
        self._window.setDelegate_(self)

        cv = self._window.contentView()

        # Search bar
        self._search = NSTextField.alloc().initWithFrame_(NSMakeRect(12, h - 44, w - 24, 28))
        self._search.setPlaceholderString_('🔍  Search history…')
        self._search.setTarget_(self)
        self._search.setAction_('filterItems:')
        self._search.setAutoresizingMask_(NSViewWidthSizable)
        cv.addSubview_(self._search)

        # Table
        sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 44, w, h - 92))
        sv.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        sv.setHasVerticalScroller_(True)

        tv = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h - 92))
        tv.setRowHeight_(ROW_H)
        tv.setUsesAlternatingRowBackgroundColors_(True)
        tv.setHeaderView_(None)
        tv.setAllowsEmptySelection_(True)
        tv.setDelegate_(self)

        col = NSTableColumn.alloc().initWithIdentifier_('main')
        col.setWidth_(w)
        tv.addTableColumn_(col)

        self._data_source = HistoryDataSource.alloc().init()
        tv.setDataSource_(self._data_source)
        tv.setDoubleAction_('copySelected:')
        tv.setTarget_(self)

        # Right-click context menu
        ctx = NSMenu.alloc().init()
        ctx.setDelegate_(self)   # menuWillOpen_ will show/hide items per item type

        for title, sel in [
            ('Copy',         'copySelected:'),
            ('Pin / Unpin',  'togglePin:'),
        ]:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, '')
            it.setTarget_(self)
            ctx.addItem_(it)

        ctx.addItem_(NSMenuItem.separatorItem())

        # "Transform…" — opens Transform window with selected text pre-filled
        transform_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            'Transform…', 'openInTransform:', '')
        transform_item.setTarget_(self)
        transform_item.setTag_(900)  # used to hide for image items
        ctx.addItem_(transform_item)

        # Quick Transform submenu
        qt_parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            'Quick Transform', None, '')
        qt_parent.setTag_(901)
        submenu = NSMenu.alloc().initWithTitle_('Quick Transform')
        for idx, (name, _, _req) in enumerate(TRANSFORMS):
            sub_it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name, 'applyTransformTag:', '')
            sub_it.setTag_(idx)
            sub_it.setTarget_(self)
            submenu.addItem_(sub_it)
        qt_parent.setSubmenu_(submenu)
        ctx.addItem_(qt_parent)

        ctx.addItem_(NSMenuItem.separatorItem())

        del_it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Delete', 'deleteSelected:', '')
        del_it.setTarget_(self)
        ctx.addItem_(del_it)

        tv.setMenu_(ctx)

        sv.setDocumentView_(tv)
        cv.addSubview_(sv)
        self._table = tv

        # Bottom bar
        hint = NSTextField.labelWithString_('↩ / double-click → Copy   📌 → Pin   ⌫ → Delete')
        hint.setFont_(NSFont.systemFontOfSize_(11))
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setFrame_(NSMakeRect(12, 10, w - 170, 20))
        hint.setAutoresizingMask_(NSViewWidthSizable)
        cv.addSubview_(hint)

        # "Open in Transform" button — always visible, acts on selected row
        self._transform_btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 155, 6, 143, 28))
        self._transform_btn.setTitle_('Open in Transform →')
        self._transform_btn.setBezelStyle_(NSBezelStyleRounded)
        self._transform_btn.setTarget_(self)
        self._transform_btn.setAction_('openInTransform:')
        self._transform_btn.setAutoresizingMask_(0x02)  # NSViewMinXMargin
        cv.addSubview_(self._transform_btn)

    # ── Cell view ─────────────────────────────────────────────────────────────

    def tableView_viewForTableColumn_row_(self, tv, col, row):
        if row >= len(self._shown):
            return None

        item, pinned = self._shown[row]
        cell_id = 'ClipCell'
        cell = tv.makeViewWithIdentifier_owner_(cell_id, self)

        if cell is None:
            cell = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 560, ROW_H))
            cell.setIdentifier_(cell_id)

            # Thumbnail / icon area
            thumb = NSImageView.alloc().initWithFrame_(NSMakeRect(8, 4, THUMB_W - 4, ROW_H - 8))
            thumb.setImageScaling_(NSImageScaleProportionallyDown)
            thumb.setIdentifier_('thumb')
            cell.addSubview_(thumb)

            # Preview text (main line)
            preview = NSTextField.labelWithString_('')
            preview.setFont_(NSFont.systemFontOfSize_(13))
            preview.setLineBreakMode_(NSLineBreakByTruncatingTail)
            preview.setFrame_(NSMakeRect(THUMB_W + 4, ROW_H // 2 - 2, 460, 18))
            preview.setAutoresizingMask_(NSViewWidthSizable)
            preview.setIdentifier_('preview')
            cell.addSubview_(preview)

            # Sub-line: timestamp + size
            sub = NSTextField.labelWithString_('')
            sub.setFont_(NSFont.systemFontOfSize_(11))
            sub.setTextColor_(NSColor.secondaryLabelColor())
            sub.setFrame_(NSMakeRect(THUMB_W + 4, ROW_H // 2 - 20, 460, 16))
            sub.setAutoresizingMask_(NSViewWidthSizable)
            sub.setIdentifier_('sub')
            cell.addSubview_(sub)

            # Pin indicator
            pin_lbl = NSTextField.labelWithString_('')
            pin_lbl.setFont_(NSFont.systemFontOfSize_(14))
            pin_lbl.setFrame_(NSMakeRect(2, ROW_H // 2 - 8, 12, 16))
            pin_lbl.setIdentifier_('pin')
            cell.addSubview_(pin_lbl)

        # Populate fields
        thumb_v = cell.viewWithTag_(0) or _find(cell, 'thumb')
        prev_v  = _find(cell, 'preview')
        sub_v   = _find(cell, 'sub')
        pin_v   = _find(cell, 'pin')

        if pin_v:
            pin_v.setStringValue_('📌' if pinned else '')

        if item.kind == 'image':
            if thumb_v:
                thumb_v.setImage_(item.data)
            if prev_v:
                prev_v.setStringValue_(item.preview)
        else:
            if thumb_v:
                thumb_v.setImage_(None)
            if prev_v:
                first_line = item.data.split('\n')[0][:140]
                prev_v.setStringValue_(first_line)

        if sub_v:
            age = _age(item.timestamp)
            if item.kind == 'text':
                lines = item.data.count('\n') + 1
                chars = len(item.data)
                sub_v.setStringValue_(f'{age}  ·  {lines} line{"s" if lines>1 else ""}  ·  {chars} chars')
            else:
                sub_v.setStringValue_(f'{age}  ·  {item.preview}')

        return cell

    def menuWillOpen_(self, menu):
        row = self._table.clickedRow()
        is_text = (0 <= row < len(self._shown)) and self._shown[row][0].kind == 'text'
        for tag in (900, 901):
            item = menu.itemWithTag_(tag)
            if item:
                item.setHidden_(not is_text)

        # Rebuild Quick Transform submenu filtered to matching transforms
        qt_parent = menu.itemWithTag_(901)
        if qt_parent and is_text:
            text = self._shown[row][0].data
            matches = applicable_transforms(text)  # list of (orig_idx, name, fn)
            submenu = NSMenu.alloc().initWithTitle_('Quick Transform')
            for orig_idx, name, fn in matches:
                sub_it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    name, 'applyTransformTag:', '')
                sub_it.setTag_(orig_idx)
                sub_it.setTarget_(self)
                submenu.addItem_(sub_it)
            qt_parent.setSubmenu_(submenu)

    def tableView_shouldSelectRow_(self, tv, row):
        return True

    # ── Actions ───────────────────────────────────────────────────────────────

    def filterItems_(self, sender):
        q = str(sender.stringValue()).lower().strip()
        self._refresh(query=q)

    def copySelected_(self, sender):
        row = self._table.selectedRow()
        if 0 <= row < len(self._shown):
            item, _ = self._shown[row]
            item.copy_to_clipboard()
            self.hide()

    def togglePin_(self, sender):
        row = self._table.clickedRow()
        if row < 0:
            row = self._table.selectedRow()
        if 0 <= row < len(self._shown):
            item, pinned = self._shown[row]
            # Update in _all_items
            for i, (it, p) in enumerate(self._all_items):
                if it is item:
                    self._all_items[i] = (it, not p)
                    break
            self._refresh()

    def openInTransform_(self, sender):
        # Prefer clicked row (right-click), fall back to selected row (button click)
        row = self._table.clickedRow()
        if row < 0:
            row = self._table.selectedRow()
        if 0 <= row < len(self._shown):
            item, _ = self._shown[row]
            if self._transform_ctrl:
                text = item.data if item.kind == 'text' else None
                if text:
                    self._transform_ctrl.showWithText_(text)
        elif self._transform_ctrl:
            # No item selected — open transform empty
            self._transform_ctrl.show()

    def applyTransformTag_(self, sender):
        row = self._table.clickedRow()
        if row < 0:
            row = self._table.selectedRow()
        if 0 <= row < len(self._shown):
            item, _ = self._shown[row]
            if item.kind != 'text':
                return
            idx = sender.tag()
            if 0 <= idx < len(TRANSFORMS):
                _, fn, _req = TRANSFORMS[idx]
                try:
                    result = fn(item.data)
                except Exception as e:
                    result = f'Error: {e}'
                pb = NSPasteboard.generalPasteboard()
                pb.clearContents()
                pb.setString_forType_(result, NSStringPboardType)

    def deleteSelected_(self, sender):
        row = self._table.clickedRow()
        if row < 0:
            row = self._table.selectedRow()
        if 0 <= row < len(self._shown):
            item, _ = self._shown[row]
            self._all_items = [(it, p) for it, p in self._all_items if it is not item]
            if self._monitor:
                try:
                    self._monitor._history.remove(item)
                except ValueError:
                    pass
            self._refresh()

    # ── Show / hide ───────────────────────────────────────────────────────────

    def show(self):
        self._sync_from_monitor()
        self._refresh()
        self._search.setStringValue_('')
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def hide(self):
        self._window.orderOut_(None)

    def toggle(self):
        if self._window.isVisible():
            self.hide()
        else:
            self.show()

    def windowShouldClose_(self, sender):
        self.hide()
        return False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sync_from_monitor(self):
        if not self._monitor:
            return
        known = {id(it) for it, _ in self._all_items}
        # prepend new items from monitor
        new_pairs = []
        for item in self._monitor.history:
            if id(item) not in known:
                new_pairs.append((item, False))
        self._all_items = new_pairs + self._all_items

    def _refresh(self, query=''):
        self._sync_from_monitor()
        items = self._all_items
        if query:
            items = [(it, p) for it, p in items
                     if query in it.preview.lower() or
                        (it.kind == 'text' and query in it.data.lower())]
        # Pinned first, then rest
        pinned = [(it, True)  for it, p in items if p]
        rest   = [(it, False) for it, p in items if not p]
        self._shown = pinned + rest
        self._data_source.setItems_(self._shown)
        self._table.reloadData()

    def clearUnpinned(self):
        self._all_items = [(it, p) for it, p in self._all_items if p]
        self._refresh()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find(view, ident):
    for sub in view.subviews():
        if sub.identifier() == ident:
            return sub
    return None


def _age(ts):
    delta = time.time() - ts
    if delta < 60:
        return 'just now'
    if delta < 3600:
        return f'{int(delta/60)}m ago'
    if delta < 86400:
        return f'{int(delta/3600)}h ago'
    return f'{int(delta/86400)}d ago'
