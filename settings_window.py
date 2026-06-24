import objc
import settings as S
import startup
from Foundation import NSObject, NSIndexSet, NSMutableArray
from AppKit import (
    NSPanel, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSMakeRect, NSMakeSize, NSScreen,
    NSTextField, NSFont, NSColor, NSButton, NSSlider,
    NSScrollView, NSTableView, NSTableColumn,
    NSApplication, NSFloatingWindowLevel,
    NSBezelStyleRounded, NSBezelStyleInline, NSOnState, NSOffState,
    NSSwitchButton, NSViewWidthSizable, NSViewHeightSizable,
    NSViewMinYMargin, NSViewMinXMargin,
    NSPasteboard, NSStringPboardType,
    NSTableViewDropAbove,
    NSButtonCell, NSView,
    NSWindowStyleMaskBorderless,
    NSEventModifierFlagCommand, NSEventModifierFlagOption,
    NSEventModifierFlagControl, NSEventModifierFlagShift,
    NSTextAlignmentRight, NSTextAlignmentLeft, NSTextAlignmentCenter,
    NSBox,
)
from transform import TRANSFORMS


# ── Hotkey recorder ───────────────────────────────────────────────────────────

def _flags_to_symbols(flags):
    s = ''
    if flags & NSEventModifierFlagControl:  s += '⌃'
    if flags & NSEventModifierFlagOption:   s += '⌥'
    if flags & NSEventModifierFlagShift:    s += '⇧'
    if flags & NSEventModifierFlagCommand:  s += '⌘'
    return s

def _flags_to_names(flags):
    parts = []
    if flags & NSEventModifierFlagControl: parts.append('ctrl')
    if flags & NSEventModifierFlagOption:  parts.append('alt')
    if flags & NSEventModifierFlagShift:   parts.append('shift')
    if flags & NSEventModifierFlagCommand: parts.append('cmd')
    return parts

_KEYCODE_DISPLAY = {
    36: '↩', 48: '⇥', 49: '␣', 51: '⌫', 53: '⎋',
    122: 'F1', 120: 'F2', 99: 'F3', 118: 'F4', 96: 'F5',
    97: 'F6', 98: 'F7', 100: 'F8', 101: 'F9', 109: 'F10',
    103: 'F11', 111: 'F12',
}
_KEYCODE_NAMES = {
    36: 'return', 48: 'tab', 49: 'space', 51: 'delete', 53: 'escape',
    122: 'f1', 120: 'f2', 99: 'f3', 118: 'f4', 96: 'f5',
    97: 'f6', 98: 'f7', 100: 'f8', 101: 'f9', 109: 'f10',
    103: 'f11', 111: 'f12',
}


class _RecorderView(NSView):
    def initWithCallback_(self, callback):
        self = objc.super(_RecorderView, self).init()
        self._callback = callback
        self._label = None
        return self

    def setLabel_(self, lbl):
        self._label = lbl

    def acceptsFirstResponder(self):
        return True

    def keyDown_(self, event):
        flags = int(event.modifierFlags()) & (
            NSEventModifierFlagCommand | NSEventModifierFlagOption |
            NSEventModifierFlagControl | NSEventModifierFlagShift)
        keycode = event.keyCode()

        if keycode == 53:  # Escape — cancel
            self._callback(None, None)
            return

        chars = str(event.charactersIgnoringModifiers() or '').lower()
        if chars and chars.isprintable() and chars not in ('\x1b', '\r', '\t', '\x7f'):
            key_display = chars.upper()
            key_name = chars
        elif keycode in _KEYCODE_DISPLAY:
            key_display = _KEYCODE_DISPLAY[keycode]
            key_name = _KEYCODE_NAMES.get(keycode, chars)
        else:
            return

        if not flags:
            if self._label:
                self._label.setStringValue_('Need a modifier key (⌘ ⌥ ⌃ ⇧)')
            return

        symbol = _flags_to_symbols(flags) + key_display
        parts  = _flags_to_names(flags) + [key_name]
        hotkey_str = '+'.join(parts)
        self._callback(symbol, hotkey_str)


class HotkeyRecorderPanel(NSObject):
    def initWithParent_(self, parent_window):
        self = objc.super(HotkeyRecorderPanel, self).init()
        self._panel = None
        self._status_label = None
        self._view = None
        self._active_callback = [None]
        self.__setup(parent_window)
        return self

    def __setup(self, parent):
        W, H = 320, 110
        pr = parent.frame()
        x = pr.origin.x + (pr.size.width  - W) / 2
        y = pr.origin.y + (pr.size.height - H) / 2

        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        self._panel.setTitle_('Record Hotkey')
        self._panel.setLevel_(NSFloatingWindowLevel + 1)
        self._panel.setReleasedWhenClosed_(False)

        cv = self._panel.contentView()

        title = NSTextField.labelWithString_('Press your hotkey combination')
        title.setFont_(NSFont.systemFontOfSize_(13))
        title.setFrame_(NSMakeRect(10, H - 36, W - 20, 20))
        title.setAlignment_(NSTextAlignmentCenter)
        cv.addSubview_(title)

        self._status_label = NSTextField.labelWithString_('— waiting —')
        self._status_label.setFont_(NSFont.boldSystemFontOfSize_(20))
        self._status_label.setTextColor_(NSColor.systemBlueColor())
        self._status_label.setFrame_(NSMakeRect(10, H - 72, W - 20, 30))
        self._status_label.setAlignment_(NSTextAlignmentCenter)
        cv.addSubview_(self._status_label)

        hint = NSTextField.labelWithString_('Escape = cancel / clear existing')
        hint.setFont_(NSFont.systemFontOfSize_(10))
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setFrame_(NSMakeRect(10, 8, W - 20, 16))
        hint.setAlignment_(NSTextAlignmentCenter)
        cv.addSubview_(hint)

        cb_cell = self._active_callback
        panel   = self._panel

        def on_key(symbol, hotkey_str):
            panel.orderOut_(None)
            fn = cb_cell[0]
            if fn:
                fn(symbol, hotkey_str)

        self._view = _RecorderView.alloc().initWithCallback_(on_key)
        self._view.setFrame_(NSMakeRect(0, 0, W, H))
        self._view.setLabel_(self._status_label)
        cv.addSubview_(self._view)

    def recordForRow_callback_(self, row, callback):
        self._active_callback[0] = callback
        self._status_label.setStringValue_('— waiting —')
        self._panel.makeKeyAndOrderFront_(None)
        self._panel.makeFirstResponder_(self._view)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


_DRAG_TYPE = 'com.clipkit.transformrow'


class TransformTableDataSource(NSObject):
    def initWithRows_(self, rows):
        self = objc.super(TransformTableDataSource, self).init()
        self._rows = list(rows)
        self._table = None
        return self

    def setTable_(self, table):
        self._table = table
        table.registerForDraggedTypes_([_DRAG_TYPE])

    @property
    def rows(self):
        return self._rows

    def numberOfRowsInTableView_(self, tv):
        return len(self._rows)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        name, enabled, hotkey = self._rows[row]
        ident = str(col.identifier())
        if ident == 'enabled':
            return NSOnState if enabled else NSOffState
        if ident == 'hotkey':
            return hotkey or '+ set'
        return name

    def tableView_setObjectValue_forTableColumn_row_(self, tv, value, col, row):
        ident = str(col.identifier())
        name, enabled, hotkey = self._rows[row]
        if ident == 'enabled':
            self._rows[row] = [name, bool(value), hotkey]
        elif ident == 'hotkey':
            self._rows[row] = [name, enabled, str(value or '').strip()]

    def tableView_writeRowsWithIndexes_toPasteboard_(self, tv, rowIndexes, pb):
        row = rowIndexes.firstIndex()
        pb.declareTypes_owner_([_DRAG_TYPE], None)
        pb.setString_forType_(str(row), _DRAG_TYPE)
        return True

    def tableView_validateDrop_proposedRow_proposedDropOperation_(
            self, tv, info, row, op):
        if op != NSTableViewDropAbove:
            tv.setDropRow_dropOperation_(row, NSTableViewDropAbove)
        return 2  # NSDragOperationMove

    def tableView_acceptDrop_row_dropOperation_(self, tv, info, dest_row, op):
        pb = info.draggingPasteboard()
        src_row = int(pb.stringForType_(_DRAG_TYPE))
        if src_row == dest_row or src_row == dest_row - 1:
            return False
        item = self._rows.pop(src_row)
        if dest_row > src_row:
            dest_row -= 1
        self._rows.insert(dest_row, item)
        tv.reloadData()
        return True

    def tableView_shouldEditTableColumn_row_(self, tv, col, row):
        return False


# ── Settings window ───────────────────────────────────────────────────────────

SIDEBAR_W = 148
NAV_ITEMS = [
    ('general',    'General'),
    ('transforms', 'Transforms'),
    ('hotkeys',    'Hotkeys'),
]


def _hotkey_str_to_display(hk_str):
    """Convert 'cmd+alt+v' → '⌘⌥V'."""
    if not hk_str:
        return ''
    _MOD_DISPLAY = {
        'cmd': '⌘', 'command': '⌘',
        'alt': '⌥', 'option': '⌥', 'opt': '⌥',
        'ctrl': '⌃', 'control': '⌃',
        'shift': '⇧',
    }
    parts = [p.strip().lower() for p in hk_str.split('+')]
    result = ''
    key = ''
    for p in parts:
        if p in _MOD_DISPLAY:
            result += _MOD_DISPLAY[p]
        else:
            key = p.upper()
    return result + key


class SettingsWindowController(NSObject):

    def init(self):
        self = objc.super(SettingsWindowController, self).init()
        self._window = None
        self._startup_btn = None
        self._items_slider = None
        self._items_label = None
        self._mb_slider = None
        self._mb_label = None
        self._ds = None
        self._table = None
        self._recorder = None
        self._panels = {}       # section key → NSView panel
        self._nav_btns = {}     # section key → NSButton
        self._active_section = 'general'
        self._history_hk_btn = None
        self._transform_hk_btn = None
        self._history_hk_str = ''
        self._transform_hk_str = ''
        self._build()
        return self

    def _build(self):
        W, H = 620, 520
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - W) / 2
        y = (screen.size.height - H) / 2

        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered, False)
        self._window.setTitle_('ClipKit — Settings')
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setReleasedWhenClosed_(False)
        self._window.setDelegate_(self)

        cv = self._window.contentView()
        BOTTOM_BAR_H = 50

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W, BOTTOM_BAR_H))
        bottom.setAutoresizingMask_(NSViewWidthSizable)
        bottom.setWantsLayer_(True)
        bottom.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())

        sep_b = NSView.alloc().initWithFrame_(NSMakeRect(0, BOTTOM_BAR_H - 1, W, 1))
        sep_b.setAutoresizingMask_(NSViewWidthSizable)
        sep_b.setWantsLayer_(True)
        sep_b.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        bottom.addSubview_(sep_b)

        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(W - 110, 10, 96, 30))
        save_btn.setTitle_('Save')
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_('saveSettings:')
        save_btn.setKeyEquivalent_('\r')
        save_btn.setAutoresizingMask_(NSViewMinXMargin)
        bottom.addSubview_(save_btn)

        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(W - 214, 10, 96, 30))
        cancel_btn.setTitle_('Cancel')
        cancel_btn.setBezelStyle_(NSBezelStyleRounded)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_('cancelSettings:')
        cancel_btn.setKeyEquivalent_('\x1b')
        cancel_btn.setAutoresizingMask_(NSViewMinXMargin)
        bottom.addSubview_(cancel_btn)

        cv.addSubview_(bottom)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar_h = H - BOTTOM_BAR_H
        sidebar = NSView.alloc().initWithFrame_(
            NSMakeRect(0, BOTTOM_BAR_H, SIDEBAR_W, sidebar_h))
        sidebar.setAutoresizingMask_(NSViewHeightSizable)
        sidebar.setWantsLayer_(True)
        sidebar.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())

        sep_s = NSView.alloc().initWithFrame_(
            NSMakeRect(SIDEBAR_W - 1, 0, 1, sidebar_h))
        sep_s.setAutoresizingMask_(NSViewHeightSizable)
        sep_s.setWantsLayer_(True)
        sep_s.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sidebar.addSubview_(sep_s)

        ny = sidebar_h - 16
        for key, label in NAV_ITEMS:
            ny -= 34
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(8, ny, SIDEBAR_W - 16, 30))
            btn.setTitle_(label)
            btn.setBezelStyle_(NSBezelStyleInline)
            btn.setTarget_(self)
            btn.setAction_('navSelected:')
            btn.setIdentifier_(key)
            sidebar.addSubview_(btn)
            self._nav_btns[key] = btn

        cv.addSubview_(sidebar)

        # ── Content area ──────────────────────────────────────────────────────
        content_x = SIDEBAR_W
        content_w = W - SIDEBAR_W
        content_h = sidebar_h

        cfg = S.get()

        # -- General panel
        gen = self._make_panel(content_x, BOTTOM_BAR_H, content_w, content_h)
        self._build_general(gen, content_w, content_h, cfg)
        cv.addSubview_(gen)
        self._panels['general'] = gen

        # -- Transforms panel
        tfm = self._make_panel(content_x, BOTTOM_BAR_H, content_w, content_h)
        self._build_transforms(tfm, content_w, content_h, cfg)
        cv.addSubview_(tfm)
        self._panels['transforms'] = tfm

        # -- Hotkeys panel
        hk = self._make_panel(content_x, BOTTOM_BAR_H, content_w, content_h)
        self._build_hotkeys(hk, content_w, content_h)
        cv.addSubview_(hk)
        self._panels['hotkeys'] = hk

        self._recorder = HotkeyRecorderPanel.alloc().initWithParent_(self._window)
        self._select_section('general')

    # ── Panel factory ─────────────────────────────────────────────────────────

    def _make_panel(self, x, y, w, h):
        v = NSView.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        v.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        v.setHidden_(True)
        return v

    def _section_title(self, parent, text, y, w):
        lbl = NSTextField.labelWithString_(text.upper())
        lbl.setFont_(NSFont.boldSystemFontOfSize_(10))
        lbl.setTextColor_(NSColor.tertiaryLabelColor())
        lbl.setFrame_(NSMakeRect(20, y, w - 40, 14))
        parent.addSubview_(lbl)
        return lbl

    def _row_view(self, parent, y, w, h=44):
        """A rounded card-style row."""
        row = NSView.alloc().initWithFrame_(NSMakeRect(16, y, w - 32, h))
        row.setWantsLayer_(True)
        row.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
        row.layer().setCornerRadius_(8)
        row.layer().setBorderWidth_(0.5)
        row.layer().setBorderColor_(NSColor.separatorColor().CGColor())
        parent.addSubview_(row)
        return row

    # ── General panel ─────────────────────────────────────────────────────────

    def _build_general(self, parent, w, h, cfg):
        y = h - 20

        # ── Startup ───────────────────────────────────────────────────────────
        y -= 28
        self._section_title(parent, 'Startup', y, w)

        y -= 50
        row = self._row_view(parent, y, w)
        lbl = NSTextField.labelWithString_('Launch at login')
        lbl.setFont_(NSFont.systemFontOfSize_(13))
        lbl.setFrame_(NSMakeRect(14, 11, w - 80, 20))
        row.addSubview_(lbl)

        self._startup_btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 32 - 60, 11, 44, 22))
        self._startup_btn.setButtonType_(NSSwitchButton)
        self._startup_btn.setTitle_('')
        self._startup_btn.setState_(NSOnState if startup.is_enabled() else NSOffState)
        self._startup_btn.setTarget_(self)
        self._startup_btn.setAction_('toggleStartup:')
        row.addSubview_(self._startup_btn)

        # ── Storage ───────────────────────────────────────────────────────────
        # row width = w-32; keep 12px right padding inside row
        RW = w - 32
        VAL_W = 64
        VAL_X = RW - 12 - VAL_W          # right-aligned inside row
        SLD_W = VAL_X - 14 - 6           # slider fills remaining width

        y -= 36
        self._section_title(parent, 'Storage', y, w)

        y -= 64
        row2 = self._row_view(parent, y, w, h=56)
        lbl2 = NSTextField.labelWithString_('Max items to remember')
        lbl2.setFont_(NSFont.systemFontOfSize_(13))
        lbl2.setFrame_(NSMakeRect(14, 30, SLD_W, 18))
        row2.addSubview_(lbl2)

        self._items_slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(14, 8, SLD_W, 18))
        self._items_slider.setMinValue_(20)
        self._items_slider.setMaxValue_(500)
        self._items_slider.setIntValue_(cfg.max_items)
        self._items_slider.setTarget_(self)
        self._items_slider.setAction_('sliderChanged:')
        row2.addSubview_(self._items_slider)

        self._items_label = NSTextField.labelWithString_(str(cfg.max_items))
        self._items_label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0))
        self._items_label.setAlignment_(NSTextAlignmentRight)
        self._items_label.setFrame_(NSMakeRect(VAL_X, 30, VAL_W, 18))
        row2.addSubview_(self._items_label)

        y -= 68
        row3 = self._row_view(parent, y, w, h=56)
        lbl3 = NSTextField.labelWithString_('Max buffer size')
        lbl3.setFont_(NSFont.systemFontOfSize_(13))
        lbl3.setFrame_(NSMakeRect(14, 30, SLD_W, 18))
        row3.addSubview_(lbl3)

        self._mb_slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(14, 8, SLD_W, 18))
        self._mb_slider.setMinValue_(10)
        self._mb_slider.setMaxValue_(500)
        self._mb_slider.setIntValue_(cfg.buffer_size_mb)
        self._mb_slider.setTarget_(self)
        self._mb_slider.setAction_('mbSliderChanged:')
        row3.addSubview_(self._mb_slider)

        self._mb_label = NSTextField.labelWithString_(f'{cfg.buffer_size_mb} MB')
        self._mb_label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0))
        self._mb_label.setAlignment_(NSTextAlignmentRight)
        self._mb_label.setFrame_(NSMakeRect(VAL_X, 30, VAL_W, 18))
        row3.addSubview_(self._mb_label)

    # ── Transforms panel ─────────────────────────────────────────────────────

    def _build_transforms(self, parent, w, h, cfg):
        y = h - 20

        y -= 24
        self._section_title(parent, 'Transforms  ·  drag to reorder  ·  click hotkey to set', y, w)

        y -= 14
        scroll_h = y - 8
        sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(16, 8, w - 32, scroll_h))
        sv.setHasVerticalScroller_(True)
        sv.setBorderType_(2)
        sv.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)

        tv = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 32, scroll_h))
        tv.setUsesAlternatingRowBackgroundColors_(True)
        tv.setRowHeight_(26)
        tv.setAllowsMultipleSelection_(False)

        from AppKit import NSTableHeaderView
        tv.setHeaderView_(NSTableHeaderView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 32, 22)))

        chk_col = NSTableColumn.alloc().initWithIdentifier_('enabled')
        chk_col.setWidth_(28)
        chk_col.setMinWidth_(28)
        chk_col.setMaxWidth_(28)
        chk_col.headerCell().setStringValue_('')
        cell = NSButtonCell.alloc().init()
        cell.setButtonType_(NSSwitchButton)
        cell.setTitle_('')
        chk_col.setDataCell_(cell)
        tv.addTableColumn_(chk_col)

        name_col = NSTableColumn.alloc().initWithIdentifier_('name')
        name_col.setWidth_(w - 32 - 28 - 110 - 16)
        name_col.headerCell().setStringValue_('Transform')
        tv.addTableColumn_(name_col)

        hk_col = NSTableColumn.alloc().initWithIdentifier_('hotkey')
        hk_col.setWidth_(105)
        hk_col.setMinWidth_(80)
        hk_col.headerCell().setStringValue_('Hotkey')
        tv.addTableColumn_(hk_col)

        rows = self._build_rows(cfg)
        self._ds = TransformTableDataSource.alloc().initWithRows_(rows)
        self._ds.setTable_(tv)
        tv.setDataSource_(self._ds)
        tv.setDelegate_(self._ds)
        tv.setTarget_(self)
        tv.setAction_('tableClicked:')
        sv.setDocumentView_(tv)
        parent.addSubview_(sv)
        self._table = tv

    # ── Hotkeys panel ─────────────────────────────────────────────────────────

    def _build_hotkeys(self, parent, w, h):
        cfg = S.get()
        y = h - 20

        y -= 28
        self._section_title(parent, 'Global Hotkeys', y, w)

        for label, attr, default in [
            ('Open History',    'hotkey_open',      'cmd+alt+v'),
            ('Transform Text',  'hotkey_transform', 'cmd+alt+t'),
        ]:
            y -= 54
            row = self._row_view(parent, y, w)
            lbl = NSTextField.labelWithString_(label)
            lbl.setFont_(NSFont.systemFontOfSize_(13))
            lbl.setFrame_(NSMakeRect(14, 12, w - 160, 20))
            row.addSubview_(lbl)

            hk_str = getattr(cfg, attr, default) or default
            display = _hotkey_str_to_display(hk_str) or '+ set'

            btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 148, 8, 128, 28))
            btn.setTitle_(display)
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setFont_(NSFont.monospacedSystemFontOfSize_weight_(13, 0.3))
            btn.setTarget_(self)
            btn.setAction_('globalHotkeyClicked:')
            btn.setIdentifier_(attr)
            row.addSubview_(btn)

            if attr == 'hotkey_open':
                self._history_hk_btn = btn
                self._history_hk_str = hk_str
            else:
                self._transform_hk_btn = btn
                self._transform_hk_str = hk_str

        y -= 20
        note = NSTextField.labelWithString_(
            'Click a shortcut to change it. Requires Accessibility permission in System Settings → Privacy & Security.')
        note.setFont_(NSFont.systemFontOfSize_(11))
        note.setTextColor_(NSColor.tertiaryLabelColor())
        note.setFrame_(NSMakeRect(20, y - 36, w - 40, 36))
        note.setLineBreakMode_(3)
        note.cell().setWraps_(True)
        parent.addSubview_(note)

    # ── Nav ───────────────────────────────────────────────────────────────────

    def _select_section(self, key):
        self._active_section = key
        for k, panel in self._panels.items():
            panel.setHidden_(k != key)
        for k, btn in self._nav_btns.items():
            if k == key:
                btn.setContentTintColor_(NSColor.controlAccentColor())
            else:
                btn.setContentTintColor_(NSColor.secondaryLabelColor())

    def navSelected_(self, sender):
        self._select_section(str(sender.identifier()))

    # ── Actions ───────────────────────────────────────────────────────────────

    def tableClicked_(self, sender):
        row = self._table.clickedRow()
        col = self._table.clickedColumn()
        if row < 0 or col < 0:
            return
        col_id = str(self._table.tableColumns()[col].identifier())
        if col_id != 'hotkey':
            return
        def on_recorded(symbol, hotkey_str):
            name, enabled, _hk = self._ds._rows[row]
            self._ds._rows[row] = [name, enabled, hotkey_str or '']
            self._table.reloadData()
        self._recorder.recordForRow_callback_(row, on_recorded)

    def globalHotkeyClicked_(self, sender):
        attr = str(sender.identifier())
        btn = sender

        def on_recorded(symbol, hotkey_str):
            if hotkey_str is None:
                # Escape pressed — clear
                if attr == 'hotkey_open':
                    self._history_hk_str = ''
                    self._history_hk_btn.setTitle_('+ set')
                else:
                    self._transform_hk_str = ''
                    self._transform_hk_btn.setTitle_('+ set')
                return
            display = _hotkey_str_to_display(hotkey_str) or hotkey_str
            btn.setTitle_(display)
            if attr == 'hotkey_open':
                self._history_hk_str = hotkey_str
            else:
                self._transform_hk_str = hotkey_str

        self._recorder.recordForRow_callback_(0, on_recorded)

    def toggleStartup_(self, sender):
        enabled = startup.toggle()
        sender.setState_(NSOnState if enabled else NSOffState)
        S.get().start_at_login = enabled

    def sliderChanged_(self, sender):
        val = int(sender.intValue())
        self._items_label.setStringValue_(str(val))
        S.get().max_items = val

    def mbSliderChanged_(self, sender):
        val = int(sender.intValue())
        self._mb_label.setStringValue_(f'{val} MB')
        S.get().buffer_size_mb = val

    def saveSettings_(self, sender):
        rows = self._ds.rows
        cfg = S.get()
        cfg.transform_order = [name for name, _, _hk in rows]
        cfg.hidden_transforms = [name for name, enabled, _hk in rows if not enabled]
        cfg.transform_hotkeys = {name: hk for name, _, hk in rows if hk.strip()}
        cfg.hotkey_open = self._history_hk_str
        cfg.hotkey_transform = self._transform_hk_str
        S.save()
        self.hide()

    def cancelSettings_(self, sender):
        self.hide()

    def _build_rows(self, cfg):
        hidden = set(cfg.hidden_transforms)
        hotkeys = cfg.transform_hotkeys
        all_names = [name for name, _, _ in TRANSFORMS]
        order = cfg.transform_order or all_names
        seen = set()
        names = []
        for name in order:
            if name in set(all_names):
                names.append(name)
                seen.add(name)
        for name in all_names:
            if name not in seen:
                names.append(name)
        return [[name, name not in hidden, hotkeys.get(name, '')] for name in names]

    def show(self):
        # Force the app to be active first
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        app = NSRunningApplication.currentApplication()
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        self._startup_btn.setState_(NSOnState if startup.is_enabled() else NSOffState)
        cfg = S.get()
        self._items_slider.setIntValue_(cfg.max_items)
        self._items_label.setStringValue_(str(cfg.max_items))
        self._mb_slider.setIntValue_(cfg.buffer_size_mb)
        self._mb_label.setStringValue_(f'{cfg.buffer_size_mb} MB')
        # Refresh hotkey buttons
        self._history_hk_str = cfg.hotkey_open or 'cmd+alt+v'
        self._transform_hk_str = cfg.hotkey_transform or 'cmd+alt+t'
        self._history_hk_btn.setTitle_(_hotkey_str_to_display(self._history_hk_str) or '+ set')
        self._transform_hk_btn.setTitle_(_hotkey_str_to_display(self._transform_hk_str) or '+ set')
        rows = self._build_rows(cfg)
        self._ds._rows = rows
        self._table.reloadData()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()

    def hide(self):
        self._window.orderOut_(None)

    def windowShouldClose_(self, sender):
        self.hide()
        return False
