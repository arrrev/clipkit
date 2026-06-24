import time
import objc
from Foundation import NSObject, NSIndexSet, NSMutableArray
from transform import TRANSFORMS, applicable_transforms, detect_input_type
from AppKit import (
    NSPanel, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSMakeRect, NSMakeSize, NSScreen,
    NSScrollView, NSTableView, NSTableColumn,
    NSTextField, NSFont, NSColor, NSButton,
    NSBezelStyleRounded, NSBezelStyleInline, NSView, NSMenu, NSMenuItem,
    NSViewWidthSizable, NSViewHeightSizable, NSViewMinYMargin, NSViewMinXMargin,
    NSApplication, NSFloatingWindowLevel,
    NSPasteboard, NSStringPboardType,
    NSLineBreakByTruncatingTail,
    NSTextAlignmentCenter,
    NSTextAlignmentLeft,
)

ROW_H = 52
SIDEBAR_W = 0  # no sidebar, full-width list

# Type → (label, bg hex, fg hex)
_TYPE_BADGE = {
    'json':        ('JSON',  '#EEEDFE', '#3C3489'),
    'json_string': ('JSON',  '#EEEDFE', '#3C3489'),
    'sql':         ('SQL',   '#E1F5EE', '#085041'),
    'csv':         ('CSV',   '#FFF3CD', '#7B5900'),
    'url':         ('URL',   '#E3F0FF', '#0A3D82'),
    'code':        ('Code',  '#F0F0F0', '#444444'),
}


def _nscolor_hex(hex_str):
    hex_str = hex_str.lstrip('#')
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)


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
        return None  # view-based cells


class HistoryWindowController(NSObject):

    def init(self):
        self = objc.super(HistoryWindowController, self).init()
        self._monitor = None
        self._transform_ctrl = None
        self._all_items = []
        self._shown = []
        self._window = None
        self._table = None
        self._data_source = None
        self._search = None
        self._active_filter = 'all'   # 'all' | 'text' | 'json' | 'sql' | 'csv'
        self._filter_btns = {}
        self._build()
        return self

    def setMonitor_onPaste_(self, monitor, on_paste):
        self._monitor = monitor

    def setTransformCtrl_(self, ctrl):
        self._transform_ctrl = ctrl

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        screen = NSScreen.mainScreen().frame()
        w, h = 560, 540
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

        # ── Bottom action bar (built first so table can leave room) ───────────
        BAR_H = 44
        bar = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, BAR_H))
        bar.setAutoresizingMask_(NSViewWidthSizable)

        # Separator line above bar
        sep = NSView.alloc().initWithFrame_(NSMakeRect(0, BAR_H - 1, w, 1))
        sep.setAutoresizingMask_(NSViewWidthSizable)
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(
            NSColor.separatorColor().CGColor())
        bar.addSubview_(sep)

        def _action_btn(title, x, w_btn, action, primary=False):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(x, 7, w_btn, 30))
            b.setTitle_(title)
            b.setBezelStyle_(NSBezelStyleRounded)
            b.setTarget_(self)
            b.setAction_(action)
            if primary:
                b.setKeyEquivalent_('\r')
            return b

        self._copy_btn    = _action_btn('Copy',      10,  70, 'copySelected:', primary=True)
        self._tfm_btn     = _action_btn('Transform', 86,  86, 'openInTransform:')
        self._pin_btn     = _action_btn('📌',         178, 34, 'togglePin:')
        self._del_btn     = _action_btn('⌫',          218, 34, 'deleteSelected:')
        for b in (self._copy_btn, self._tfm_btn, self._pin_btn, self._del_btn):
            bar.addSubview_(b)

        hint = NSTextField.labelWithString_('↩ copy · Space pin · ⌫ delete')
        hint.setFont_(NSFont.systemFontOfSize_(10))
        hint.setTextColor_(NSColor.tertiaryLabelColor())
        hint.setFrame_(NSMakeRect(260, 14, w - 270, 16))
        hint.setAutoresizingMask_(NSViewWidthSizable)
        bar.addSubview_(hint)

        cv.addSubview_(bar)

        # ── Filter tab bar ────────────────────────────────────────────────────
        FILTER_H = 36
        filter_bar = NSView.alloc().initWithFrame_(
            NSMakeRect(0, BAR_H, w, FILTER_H))
        filter_bar.setAutoresizingMask_(NSViewWidthSizable)

        sep2 = NSView.alloc().initWithFrame_(NSMakeRect(0, FILTER_H - 1, w, 1))
        sep2.setAutoresizingMask_(NSViewWidthSizable)
        sep2.setWantsLayer_(True)
        sep2.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        filter_bar.addSubview_(sep2)

        tabs = [('all', 'All'), ('text', 'Text'), ('json', 'JSON'),
                ('sql', 'SQL'), ('csv', 'CSV')]
        fx = 10
        for key, label in tabs:
            bw = len(label) * 8 + 22
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(fx, 6, bw, 24))
            btn.setTitle_(label)
            btn.setBezelStyle_(NSBezelStyleInline)
            btn.setTarget_(self)
            btn.setAction_('filterTab:')
            btn.setIdentifier_(key)
            filter_bar.addSubview_(btn)
            self._filter_btns[key] = btn
            fx += bw + 6

        cv.addSubview_(filter_bar)

        # ── Search bar ────────────────────────────────────────────────────────
        SEARCH_H = 40
        search_y = BAR_H + FILTER_H
        self._search = NSTextField.alloc().initWithFrame_(
            NSMakeRect(10, h - SEARCH_H, w - 20, 28))
        self._search.setPlaceholderString_('🔍  Search history…')
        self._search.setTarget_(self)
        self._search.setAction_('filterItems:')
        self._search.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        cv.addSubview_(self._search)

        # ── Table ─────────────────────────────────────────────────────────────
        table_y = BAR_H + FILTER_H
        table_h = h - SEARCH_H - 4 - table_y

        sv = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, table_y, w, table_h))
        sv.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        sv.setHasVerticalScroller_(True)
        sv.setBorderType_(0)

        tv = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, w, table_h))
        tv.setRowHeight_(ROW_H)
        tv.setUsesAlternatingRowBackgroundColors_(False)
        tv.setHeaderView_(None)
        tv.setAllowsEmptySelection_(True)
        tv.setDelegate_(self)
        tv.setIntercellSpacing_(NSMakeSize(0, 1))

        col = NSTableColumn.alloc().initWithIdentifier_('main')
        col.setWidth_(w)
        tv.addTableColumn_(col)

        self._data_source = HistoryDataSource.alloc().init()
        tv.setDataSource_(self._data_source)
        tv.setDoubleAction_('copySelected:')
        tv.setTarget_(self)

        # Context menu
        ctx = NSMenu.alloc().init()
        ctx.setDelegate_(self)
        for title, sel in [('Copy', 'copySelected:'), ('Pin / Unpin', 'togglePin:')]:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, '')
            it.setTarget_(self)
            ctx.addItem_(it)
        ctx.addItem_(NSMenuItem.separatorItem())

        transform_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            'Transform…', 'openInTransform:', '')
        transform_item.setTarget_(self)
        transform_item.setTag_(900)
        ctx.addItem_(transform_item)

        qt_parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            'Quick Transform', None, '')
        qt_parent.setTag_(901)
        qt_parent.setSubmenu_(NSMenu.alloc().initWithTitle_('Quick Transform'))
        ctx.addItem_(qt_parent)

        ctx.addItem_(NSMenuItem.separatorItem())
        del_it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            'Delete', 'deleteSelected:', '')
        del_it.setTarget_(self)
        ctx.addItem_(del_it)
        tv.setMenu_(ctx)

        sv.setDocumentView_(tv)
        cv.addSubview_(sv)
        self._table = tv

        self._update_filter_tabs()

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

            # Main preview text
            preview = NSTextField.labelWithString_('')
            preview.setFont_(NSFont.systemFontOfSize_(13))
            preview.setLineBreakMode_(NSLineBreakByTruncatingTail)
            preview.setFrame_(NSMakeRect(12, ROW_H - 22, 460, 18))
            preview.setAutoresizingMask_(NSViewWidthSizable)
            preview.setIdentifier_('preview')
            cell.addSubview_(preview)

            # Meta line
            sub = NSTextField.labelWithString_('')
            sub.setFont_(NSFont.systemFontOfSize_(10))
            sub.setTextColor_(NSColor.tertiaryLabelColor())
            sub.setFrame_(NSMakeRect(12, 7, 300, 14))
            sub.setAutoresizingMask_(NSViewWidthSizable)
            sub.setIdentifier_('sub')
            cell.addSubview_(sub)

            # Type badge
            badge = NSTextField.labelWithString_('')
            badge.setFont_(NSFont.boldSystemFontOfSize_(10))
            badge.setFrame_(NSMakeRect(0, 16, 52, 16))
            badge.setAlignment_(NSTextAlignmentCenter)
            badge.setWantsLayer_(True)
            badge.layer().setCornerRadius_(4)
            badge.setIdentifier_('badge')
            cell.addSubview_(badge)

            # Pin indicator
            pin_lbl = NSTextField.labelWithString_('')
            pin_lbl.setFont_(NSFont.systemFontOfSize_(14))
            pin_lbl.setFrame_(NSMakeRect(0, ROW_H - 20, 18, 18))
            pin_lbl.setAlignment_(NSTextAlignmentCenter)
            pin_lbl.setIdentifier_('pin')
            cell.addSubview_(pin_lbl)

        prev_v  = _find(cell, 'preview')
        sub_v   = _find(cell, 'sub')
        badge_v = _find(cell, 'badge')
        pin_v   = _find(cell, 'pin')

        if pin_v:
            pin_v.setStringValue_('📌' if pinned else '')

        if item.kind == 'image':
            if prev_v:
                prev_v.setStringValue_(item.preview)
            if badge_v:
                badge_v.setStringValue_('')
        else:
            if prev_v:
                first_line = item.data.split('\n')[0][:160]
                prev_v.setStringValue_(first_line)

            # Detect type for badge
            itype = detect_input_type(item.data) if item.kind == 'text' else set()
            badge_info = None
            for t in ('json', 'json_string', 'sql', 'csv', 'url', 'code'):
                if t in itype:
                    badge_info = _TYPE_BADGE.get(t)
                    break

            if badge_v:
                if badge_info:
                    label, bg, fg = badge_info
                    badge_v.setStringValue_(label)
                    badge_v.setTextColor_(_nscolor_hex(fg))
                    badge_v.layer().setBackgroundColor_(_nscolor_hex(bg).CGColor())
                    bw = len(label) * 7 + 12
                    fr = badge_v.frame()
                    badge_v.setFrame_(NSMakeRect(fr.origin.x, fr.origin.y, bw, fr.size.height))
                    # Position badge to the right
                    w_cv = cell.frame().size.width or 540
                    badge_v.setFrame_(NSMakeRect(w_cv - bw - 10, 16, bw, 16))
                else:
                    badge_v.setStringValue_('')

        if sub_v:
            age = _age(item.timestamp)
            if item.kind == 'text':
                chars = len(item.data)
                lines = item.data.count('\n') + 1
                if lines > 1:
                    sub_v.setStringValue_(f'{age}  ·  {lines} lines  ·  {chars} chars')
                else:
                    sub_v.setStringValue_(f'{age}  ·  {chars} chars')
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
        qt_parent = menu.itemWithTag_(901)
        if qt_parent and is_text:
            text = self._shown[row][0].data
            matches = applicable_transforms(text)
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

    def filterTab_(self, sender):
        key = str(sender.identifier())
        self._active_filter = key
        self._update_filter_tabs()
        self._refresh()

    def _update_filter_tabs(self):
        active_bg = NSColor.controlAccentColor()
        inactive_bg = NSColor.controlColor()
        for key, btn in self._filter_btns.items():
            if key == self._active_filter:
                btn.setContentTintColor_(NSColor.whiteColor())
            else:
                btn.setContentTintColor_(NSColor.labelColor())

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
            for i, (it, p) in enumerate(self._all_items):
                if it is item:
                    self._all_items[i] = (it, not p)
                    break
            self._refresh()

    def openInTransform_(self, sender):
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
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()

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
        new_pairs = []
        for item in self._monitor.history:
            if id(item) not in known:
                new_pairs.append((item, False))
        self._all_items = new_pairs + self._all_items

    def _refresh(self, query=''):
        self._sync_from_monitor()
        items = self._all_items

        # Apply type filter
        if self._active_filter != 'all':
            f = self._active_filter
            def _matches_filter(item):
                if item.kind != 'text':
                    return f == 'text'
                itype = detect_input_type(item.data)
                if f == 'text':
                    return not (itype & {'json', 'json_string', 'sql', 'csv', 'url', 'code'})
                return f in itype or f + '_string' in itype
            items = [(it, p) for it, p in items if _matches_filter(it)]

        if query:
            items = [(it, p) for it, p in items
                     if query in it.preview.lower() or
                        (it.kind == 'text' and query in it.data.lower())]

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
