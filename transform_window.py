import objc
from Foundation import NSObject
from AppKit import (
    NSPanel, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSMakeRect, NSScreen,
    NSScrollView, NSTextView,
    NSTextField, NSFont, NSButton, NSBezelStyleRounded,
    NSApplication, NSFloatingWindowLevel,
    NSPasteboard, NSStringPboardType,
    NSPopUpButton, NSViewWidthSizable, NSViewHeightSizable,
    NSViewMinYMargin, NSViewMinXMargin,
)
from transform import TRANSFORMS, applicable_transforms, output_extension


def _btn(target, title, x, y, w, h, action):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setTitle_(title)
    b.setBezelStyle_(NSBezelStyleRounded)
    b.setTarget_(target)
    b.setAction_(action)
    return b


def _scroll_with_textview(x, y, w, h, editable=True):
    sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    sv.setHasVerticalScroller_(True)
    sv.setBorderType_(2)
    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 4, h))
    tv.setFont_(NSFont.monospacedSystemFontOfSize_weight_(13, 0))
    tv.setEditable_(editable)
    tv.setAutomaticQuoteSubstitutionEnabled_(False)
    tv.setAutomaticDashSubstitutionEnabled_(False)
    sv.setDocumentView_(tv)
    return sv, tv


class TransformWindowController(NSObject):

    def init(self):
        self = objc.super(TransformWindowController, self).init()
        self._window = None
        self._input_tv = None
        self._output_tv = None
        self._popup = None
        self._visible_transforms = []  # [(original_index, name, fn)]
        self._build()
        return self

    def _build(self):
        screen = NSScreen.mainScreen().frame()
        W, H = 700, 580
        x = (screen.size.width - W) / 2
        y = (screen.size.height - H) / 2

        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered, False)
        self._window.setTitle_('ClipKit — Transform')
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setReleasedWhenClosed_(False)
        self._window.setDelegate_(self)

        cv = self._window.contentView()
        PAD = 12
        half = (H - 116) // 2

        # ── Input ──────────────────────────────────────────────────────────
        lbl_in = NSTextField.labelWithString_('Input')
        lbl_in.setFrame_(NSMakeRect(PAD, H - 26, 50, 18))
        lbl_in.setAutoresizingMask_(NSViewMinYMargin)
        cv.addSubview_(lbl_in)

        cv.addSubview_(_btn(self, 'Paste from clipboard',
                            W - PAD - 160, H - 30, 160, 24, 'pasteInput:'))

        in_sv, self._input_tv = _scroll_with_textview(
            PAD, H - 28 - half, W - PAD * 2, half - 4, editable=True)
        in_sv.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        self._input_tv.setDelegate_(self)
        cv.addSubview_(in_sv)

        # ── Layout constants ─────────────────────────────────────────────────
        BTN_W   = 80   # Apply
        SWAP_W  = 76   # Swap
        COPY_W  = 150  # Copy to clipboard
        SAVE_W  = 110  # Save to file
        BTN_GAP = 8    # gap between buttons
        ROW_H   = 30   # height of each control row
        ROW_GAP = 10   # vertical gap between the two rows

        # Positions (from bottom of input scrollview downward)
        ctrl_y = H - 28 - half - PAD - ROW_H          # Transform row Y
        out_y  = ctrl_y - ROW_GAP - ROW_H             # Output row Y

        # ── Transform row ────────────────────────────────────────────────────
        RIGHT_FIXED = BTN_W + BTN_GAP + SWAP_W + PAD

        lbl_tr = NSTextField.labelWithString_('Transform:')
        lbl_tr.setFrame_(NSMakeRect(PAD, ctrl_y + 5, 82, 20))
        lbl_tr.setAutoresizingMask_(NSViewMinYMargin)
        cv.addSubview_(lbl_tr)

        popup_x = PAD + 86
        popup_w = W - popup_x - RIGHT_FIXED - BTN_GAP
        self._popup = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(popup_x, ctrl_y + 2, popup_w, 26))
        self._popup.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        cv.addSubview_(self._popup)

        apply_btn = _btn(self, 'Apply →',
                         W - PAD - SWAP_W - BTN_GAP - BTN_W, ctrl_y + 2, BTN_W, 26,
                         'applyTransform:')
        apply_btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        cv.addSubview_(apply_btn)

        swap_btn = _btn(self, '⇅ Swap',
                        W - PAD - SWAP_W, ctrl_y + 2, SWAP_W, 26,
                        'swapInputOutput:')
        swap_btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        cv.addSubview_(swap_btn)

        # ── Output row ───────────────────────────────────────────────────────
        lbl_out = NSTextField.labelWithString_('Output')
        lbl_out.setFrame_(NSMakeRect(PAD, out_y + 5, 50, 18))
        lbl_out.setAutoresizingMask_(NSViewMinYMargin)
        cv.addSubview_(lbl_out)

        copy_btn = _btn(self, 'Copy to clipboard',
                        W - PAD - COPY_W, out_y + 3, COPY_W, 24, 'copyOutput:')
        copy_btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        cv.addSubview_(copy_btn)

        save_btn = _btn(self, 'Save to file',
                        W - PAD - COPY_W - BTN_GAP - SAVE_W, out_y + 3, SAVE_W, 24, 'saveOutput:')
        save_btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        cv.addSubview_(save_btn)

        out_h = out_y - PAD
        out_sv, self._output_tv = _scroll_with_textview(
            PAD, PAD, W - PAD * 2, out_h, editable=False)
        out_sv.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        cv.addSubview_(out_sv)

    # ── Popup filtering ─────────────────────────────────────────────────────

    def textDidChange_(self, notification):
        self._refreshPopup()

    def _refreshPopup(self):
        text = str(self._input_tv.string())
        selected_name = None
        if self._popup.numberOfItems() > 0:
            selected_name = str(self._popup.titleOfSelectedItem())

        self._visible_transforms = applicable_transforms(text)
        self._popup.removeAllItems()

        if not self._visible_transforms:
            self._popup.addItemWithTitle_('— paste or type input first —')
            return

        for _, name, _ in self._visible_transforms:
            self._popup.addItemWithTitle_(name)

        # Restore previous selection if still available, else default to first
        restored = False
        if selected_name:
            idx = self._popup.indexOfItemWithTitle_(selected_name)
            if idx >= 0:
                self._popup.selectItemAtIndex_(idx)
                restored = True
        if not restored:
            self._popup.selectItemAtIndex_(0)

    # ── Button actions (plain string selectors — always work) ───────────────

    def pasteInput_(self, sender):
        pb = NSPasteboard.generalPasteboard()
        text = (pb.stringForType_(NSStringPboardType) or
                pb.stringForType_('public.utf8-plain-text'))
        if text:
            self._input_tv.setString_(str(text))

    def applyTransform_(self, sender):
        idx = self._popup.indexOfSelectedItem()
        if not (0 <= idx < len(self._visible_transforms)):
            return
        _, _, fn = self._visible_transforms[idx]
        text = str(self._input_tv.string())
        try:
            result = fn(text)
        except Exception as e:
            result = f'Error: {e}'
        self._output_tv.setString_(result)

    def saveOutput_(self, sender):
        text = str(self._output_tv.string())
        if not text.strip():
            return
        from AppKit import NSSavePanel, NSApp
        ext = output_extension(text)
        panel = NSSavePanel.savePanel()
        panel.setAllowedFileTypes_([ext])
        panel.setNameFieldStringValue_(f'output.{ext}')
        if panel.runModal() == 1:
            path = str(panel.URL().path())
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)

    def copyOutput_(self, sender):
        text = str(self._output_tv.string())
        if text:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(text, NSStringPboardType)

    def swapInputOutput_(self, sender):
        inp = str(self._input_tv.string())
        out = str(self._output_tv.string())
        self._input_tv.setString_(out)
        self._output_tv.setString_(inp)

    # ── Public interface ────────────────────────────────────────────────────

    def _autoApply(self):
        if self._visible_transforms:
            self.applyTransform_(None)

    def showWithText_(self, text):
        self._input_tv.setString_(str(text))
        self._output_tv.setString_('')
        self._refreshPopup()
        self._autoApply()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def show(self):
        pb = NSPasteboard.generalPasteboard()
        text = (pb.stringForType_(NSStringPboardType) or
                pb.stringForType_('public.utf8-plain-text'))
        if text:
            self._input_tv.setString_(str(text))
        self._refreshPopup()
        self._autoApply()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def hide(self):
        self._window.orderOut_(None)

    def windowShouldClose_(self, sender):
        self.hide()
        return False
