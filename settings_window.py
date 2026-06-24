import objc
import settings as S
import startup
from Foundation import NSObject, NSIndexSet, NSMutableArray
from AppKit import (
    NSPanel, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSMakeRect, NSScreen,
    NSTextField, NSFont, NSColor, NSButton, NSSlider,
    NSScrollView, NSTableView, NSTableColumn,
    NSApplication, NSFloatingWindowLevel,
    NSBezelStyleRounded, NSOnState, NSOffState,
    NSSwitchButton, NSViewWidthSizable, NSViewHeightSizable,
    NSPasteboard, NSStringPboardType,
    NSTableViewDropAbove,
    NSButtonCell, NSView,
    NSWindowStyleMaskBorderless,
    NSEventModifierFlagCommand, NSEventModifierFlagOption,
    NSEventModifierFlagControl, NSEventModifierFlagShift,
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

# Special key names for display
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
    """Transparent overlay that becomes key and captures one key combo."""

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

        # Get printable character
        chars = str(event.charactersIgnoringModifiers() or '').lower()
        if chars and chars.isprintable() and chars not in ('\x1b', '\r', '\t', '\x7f'):
            key_display = chars.upper()
            key_name = chars
        elif keycode in _KEYCODE_DISPLAY:
            key_display = _KEYCODE_DISPLAY[keycode]
            key_name = _KEYCODE_NAMES.get(keycode, chars)
        else:
            return  # ignore modifier-only

        if not flags:  # require at least one modifier
            if self._label:
                self._label.setStringValue_('Need a modifier key (⌘ ⌥ ⌃ ⇧)')
            return

        symbol = _flags_to_symbols(flags) + key_display
        parts  = _flags_to_names(flags) + [key_name]
        hotkey_str = '+'.join(parts)
        self._callback(symbol, hotkey_str)


class HotkeyRecorderPanel(NSObject):
    """Small floating panel that records one key combination."""

    def initWithParent_(self, parent_window):
        self = objc.super(HotkeyRecorderPanel, self).init()
        self._panel = None
        self._status_label = None
        self._view = None
        self._active_callback = [None]  # mutable cell for closure
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
        title.setAlignment_(1)
        cv.addSubview_(title)

        self._status_label = NSTextField.labelWithString_('— waiting —')
        self._status_label.setFont_(NSFont.boldSystemFontOfSize_(20))
        self._status_label.setTextColor_(NSColor.systemBlueColor())
        self._status_label.setFrame_(NSMakeRect(10, H - 72, W - 20, 30))
        self._status_label.setAlignment_(1)
        cv.addSubview_(self._status_label)

        hint = NSTextField.labelWithString_('Escape = cancel / clear existing')
        hint.setFont_(NSFont.systemFontOfSize_(10))
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setFrame_(NSMakeRect(10, 8, W - 20, 16))
        hint.setAlignment_(1)
        cv.addSubview_(hint)

        cb_cell = self._active_callback
        lbl     = self._status_label
        panel   = self._panel

        def on_key(symbol, hotkey_str):
            panel.orderOut_(None)
            fn = cb_cell[0]
            if fn:
                fn(symbol, hotkey_str)

        self._view = _RecorderView.alloc().initWithCallback_(on_key)
        self._view.setFrame_(NSMakeRect(0, 0, W, H))
        self._view.setLabel_(lbl)
        cv.addSubview_(self._view)

    def recordForRow_callback_(self, row, callback):
        self._active_callback[0] = callback
        self._status_label.setStringValue_('— waiting —')
        self._panel.makeKeyAndOrderFront_(None)
        self._panel.makeFirstResponder_(self._view)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


_DRAG_TYPE = 'com.clipkit.transformrow'


class TransformTableDataSource(NSObject):
    """NSTableView data source + delegate for the transforms list."""

    def initWithRows_(self, rows):
        self = objc.super(TransformTableDataSource, self).init()
        # rows: list of [name, enabled, hotkey_str]
        self._rows = list(rows)
        self._table = None
        return self

    def setTable_(self, table):
        self._table = table
        table.registerForDraggedTypes_([_DRAG_TYPE])

    @property
    def rows(self):
        return self._rows

    # ── NSTableViewDataSource ────────────────────────────────────────────────

    def numberOfRowsInTableView_(self, tv):
        return len(self._rows)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        name, enabled, hotkey = self._rows[row]
        ident = str(col.identifier())
        if ident == 'enabled':
            return NSOnState if enabled else NSOffState
        if ident == 'hotkey':
            return hotkey or '+ set hotkey'
        return name

    def tableView_setObjectValue_forTableColumn_row_(self, tv, value, col, row):
        ident = str(col.identifier())
        name, enabled, hotkey = self._rows[row]
        if ident == 'enabled':
            self._rows[row] = [name, bool(value), hotkey]
        elif ident == 'hotkey':
            self._rows[row] = [name, enabled, str(value or '').strip()]

    # ── Drag source ──────────────────────────────────────────────────────────

    def tableView_writeRowsWithIndexes_toPasteboard_(self, tv, rowIndexes, pb):
        row = rowIndexes.firstIndex()
        pb.declareTypes_owner_([_DRAG_TYPE], None)
        pb.setString_forType_(str(row), _DRAG_TYPE)
        return True

    # ── Drag destination ─────────────────────────────────────────────────────

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
        # Never allow inline text editing for hotkey — recorder handles it
        return False


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
        self._build()
        return self

    def _build(self):
        w, h = 440, 620
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - w) / 2
        y = (screen.size.height - h) / 2

        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered, False)
        self._window.setTitle_('ClipKit — Settings')
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setReleasedWhenClosed_(False)
        self._window.setDelegate_(self)

        cv = self._window.contentView()
        cfg = S.get()
        y_cur = h - 20

        def section(title, y):
            lbl = NSTextField.labelWithString_(title)
            lbl.setFont_(NSFont.boldSystemFontOfSize_(13))
            lbl.setTextColor_(NSColor.secondaryLabelColor())
            lbl.setFrame_(NSMakeRect(20, y, w - 40, 20))
            cv.addSubview_(lbl)

        def label(text, y, size=13):
            lbl = NSTextField.labelWithString_(text)
            lbl.setFont_(NSFont.systemFontOfSize_(size))
            lbl.setFrame_(NSMakeRect(20, y, w - 40, 20))
            cv.addSubview_(lbl)
            return lbl

        # ── General ───────────────────────────────────────────────────────────
        y_cur -= 30
        section('General', y_cur)

        y_cur -= 34
        self._startup_btn = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_cur, w - 40, 24))
        self._startup_btn.setButtonType_(NSSwitchButton)
        self._startup_btn.setTitle_('Launch ClipKit at login')
        self._startup_btn.setState_(NSOnState if startup.is_enabled() else NSOffState)
        self._startup_btn.setTarget_(self)
        self._startup_btn.setAction_('toggleStartup:')
        cv.addSubview_(self._startup_btn)

        # ── Buffer ────────────────────────────────────────────────────────────
        y_cur -= 44
        section('Clipboard Buffer', y_cur)

        y_cur -= 30
        label('Max items to remember:', y_cur)

        y_cur -= 30
        self._items_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(20, y_cur, w - 120, 24))
        self._items_slider.setMinValue_(20)
        self._items_slider.setMaxValue_(500)
        self._items_slider.setIntValue_(cfg.max_items)
        self._items_slider.setTarget_(self)
        self._items_slider.setAction_('sliderChanged:')
        cv.addSubview_(self._items_slider)

        self._items_label = NSTextField.labelWithString_(str(cfg.max_items))
        self._items_label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0))
        self._items_label.setFrame_(NSMakeRect(w - 90, y_cur, 70, 24))
        cv.addSubview_(self._items_label)

        y_cur -= 30
        label('Max buffer size (MB):', y_cur)

        y_cur -= 30
        self._mb_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(20, y_cur, w - 120, 24))
        self._mb_slider.setMinValue_(10)
        self._mb_slider.setMaxValue_(500)
        self._mb_slider.setIntValue_(cfg.buffer_size_mb)
        self._mb_slider.setTarget_(self)
        self._mb_slider.setAction_('mbSliderChanged:')
        cv.addSubview_(self._mb_slider)

        self._mb_label = NSTextField.labelWithString_(f'{cfg.buffer_size_mb} MB')
        self._mb_label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0))
        self._mb_label.setFrame_(NSMakeRect(w - 90, y_cur, 70, 24))
        cv.addSubview_(self._mb_label)

        # ── Hotkeys ───────────────────────────────────────────────────────────
        y_cur -= 44
        section('Hotkeys', y_cur)

        y_cur -= 28
        label('Open History:      ⌘ ⌥ V', y_cur)
        y_cur -= 24
        label('Transform Text:   ⌘ ⌥ T', y_cur)

        # ── Transforms ────────────────────────────────────────────────────────
        y_cur -= 44
        section('Transforms  (drag to reorder · uncheck to hide · set hotkey)', y_cur)
        y_cur -= 16
        label('Hotkey format: cmd+alt+1  or  ctrl+shift+f1  (applied to latest clipboard)', y_cur, size=11)
        y_cur -= 8

        scroll_h = y_cur - 50
        sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(16, 50, w - 32, scroll_h))
        sv.setHasVerticalScroller_(True)
        sv.setBorderType_(2)
        sv.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)

        tv = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 32, scroll_h))
        tv.setUsesAlternatingRowBackgroundColors_(True)
        tv.setRowHeight_(22)
        tv.setAllowsMultipleSelection_(False)

        # Header
        from AppKit import NSTableHeaderView
        tv.setHeaderView_(NSTableHeaderView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 32, 18)))

        # Checkbox column
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

        # Name column
        name_col = NSTableColumn.alloc().initWithIdentifier_('name')
        name_col.setWidth_(w - 32 - 28 - 110 - 16)
        name_col.headerCell().setStringValue_('Transform')
        tv.addTableColumn_(name_col)

        # Hotkey column
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
        cv.addSubview_(sv)
        self._table = tv
        self._recorder = HotkeyRecorderPanel.alloc().initWithParent_(self._window)

        # ── Save button ───────────────────────────────────────────────────────
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 120, 14, 100, 30))
        save_btn.setTitle_('Save')
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_('saveSettings:')
        cv.addSubview_(save_btn)

    def _build_rows(self, cfg):
        """Build ordered [name, enabled, hotkey] rows respecting saved order."""
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

    # ── Actions ───────────────────────────────────────────────────────────────

    def tableClicked_(self, sender):
        row = self._table.clickedRow()
        col = self._table.clickedColumn()
        if row < 0 or col < 0:
            return
        col_id = str(self._table.tableColumns()[col].identifier())
        if col_id != 'hotkey':
            return
        # Open recorder for this row
        def on_recorded(symbol, hotkey_str):
            name, enabled, _hk = self._ds._rows[row]
            self._ds._rows[row] = [name, enabled, hotkey_str or '']
            self._table.reloadData()
        self._recorder.recordForRow_callback_(row, on_recorded)

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
        S.save()
        self.hide()

    def show(self):
        self._startup_btn.setState_(NSOnState if startup.is_enabled() else NSOffState)
        cfg = S.get()
        self._items_slider.setIntValue_(cfg.max_items)
        self._items_label.setStringValue_(str(cfg.max_items))
        self._mb_slider.setIntValue_(cfg.buffer_size_mb)
        self._mb_label.setStringValue_(f'{cfg.buffer_size_mb} MB')
        cfg = S.get()
        rows = self._build_rows(cfg)
        self._ds._rows = rows
        self._table.reloadData()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def hide(self):
        self._window.orderOut_(None)

    def windowShouldClose_(self, sender):
        self.hide()
        return False
