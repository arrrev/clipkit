import objc
from Foundation import NSObject
from AppKit import (
    NSPanel, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSMakeRect, NSMakeSize, NSScreen,
    NSScrollView, NSTextView, NSView,
    NSTextField, NSFont, NSColor, NSButton, NSBezelStyleRounded, NSBezelStyleInline,
    NSApplication, NSFloatingWindowLevel,
    NSPasteboard, NSStringPboardType,
    NSPopUpButton, NSViewWidthSizable, NSViewHeightSizable,
    NSViewMinYMargin, NSViewMinXMargin,
    NSTextAlignmentCenter,
)
from transform import TRANSFORMS, applicable_transforms, output_extension, detect_input_type


def _nscolor_hex(hex_str):
    hex_str = hex_str.lstrip('#')
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)


_TYPE_BADGE = {
    'json':        ('JSON',  '#EEEDFE', '#3C3489'),
    'json_string': ('JSON',  '#EEEDFE', '#3C3489'),
    'sql':         ('SQL',   '#E1F5EE', '#085041'),
    'csv':         ('CSV',   '#FFF3CD', '#7B5900'),
    'url':         ('URL',   '#E3F0FF', '#0A3D82'),
    'code':        ('Code',  '#F0F0F0', '#444444'),
}


def _scroll_with_textview(x, y, w, h, editable=True):
    sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    sv.setHasVerticalScroller_(True)
    sv.setBorderType_(0)
    sv.setWantsLayer_(True)
    sv.layer().setCornerRadius_(6)
    sv.layer().setBorderWidth_(0.5)
    sv.layer().setBorderColor_(NSColor.separatorColor().CGColor())
    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 4, h))
    tv.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12, 0))
    tv.setEditable_(editable)
    tv.setRichText_(False)
    tv.setAutomaticQuoteSubstitutionEnabled_(False)
    tv.setAutomaticDashSubstitutionEnabled_(False)
    tv.setAutomaticTextReplacementEnabled_(False)
    tv.setAutomaticSpellingCorrectionEnabled_(False)
    tv.setContinuousSpellCheckingEnabled_(False)
    tv.textContainer().setLineFragmentPadding_(8)
    sv.setDocumentView_(tv)
    return sv, tv


class TransformWindowController(NSObject):

    def init(self):
        self = objc.super(TransformWindowController, self).init()
        self._window = None
        self._input_tv = None
        self._output_tv = None
        self._popup = None
        self._visible_transforms = []
        self._stats_label = None
        self._out_badge = None
        self._build()
        return self

    def _build(self):
        screen = NSScreen.mainScreen().frame()
        W, H = 700, 600
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

        # ── Bottom output actions bar ─────────────────────────────────────────
        OUT_BAR_H = 44
        out_bar = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W, OUT_BAR_H))
        out_bar.setAutoresizingMask_(NSViewWidthSizable)

        sep_out = NSView.alloc().initWithFrame_(NSMakeRect(0, OUT_BAR_H - 1, W, 1))
        sep_out.setAutoresizingMask_(NSViewWidthSizable)
        sep_out.setWantsLayer_(True)
        sep_out.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        out_bar.addSubview_(sep_out)

        copy_btn = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, 7, 140, 30))
        copy_btn.setTitle_('Copy to Clipboard')
        copy_btn.setBezelStyle_(NSBezelStyleRounded)
        copy_btn.setTarget_(self)
        copy_btn.setAction_('copyOutput:')
        copy_btn.setKeyEquivalent_('\r')
        out_bar.addSubview_(copy_btn)

        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(158, 7, 100, 30))
        save_btn.setTitle_('Save to File…')
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_('saveOutput:')
        out_bar.addSubview_(save_btn)

        self._stats_label = NSTextField.labelWithString_('')
        self._stats_label.setFont_(NSFont.systemFontOfSize_(10))
        self._stats_label.setTextColor_(NSColor.tertiaryLabelColor())
        self._stats_label.setFrame_(NSMakeRect(270, 14, W - 280, 16))
        self._stats_label.setAutoresizingMask_(NSViewWidthSizable)
        out_bar.addSubview_(self._stats_label)

        cv.addSubview_(out_bar)

        # ── Transform action bar ──────────────────────────────────────────────
        TFM_BAR_H = 46
        TFM_BAR_Y = OUT_BAR_H + (H - OUT_BAR_H) // 2 - TFM_BAR_H // 2

        tfm_bar = NSView.alloc().initWithFrame_(NSMakeRect(0, TFM_BAR_Y, W, TFM_BAR_H))
        tfm_bar.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        tfm_bar.setWantsLayer_(True)
        tfm_bar.layer().setBackgroundColor_(
            NSColor.controlBackgroundColor().CGColor())

        sep_t1 = NSView.alloc().initWithFrame_(NSMakeRect(0, TFM_BAR_H - 1, W, 1))
        sep_t1.setAutoresizingMask_(NSViewWidthSizable)
        sep_t1.setWantsLayer_(True)
        sep_t1.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        tfm_bar.addSubview_(sep_t1)

        sep_t2 = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W, 1))
        sep_t2.setAutoresizingMask_(NSViewWidthSizable)
        sep_t2.setWantsLayer_(True)
        sep_t2.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        tfm_bar.addSubview_(sep_t2)

        # Popup
        self._popup = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(PAD, 9, W - PAD * 2 - 180, 28))
        self._popup.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        tfm_bar.addSubview_(self._popup)

        # Apply button
        apply_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(W - PAD - 155, 10, 80, 26))
        apply_btn.setTitle_('Apply')
        apply_btn.setBezelStyle_(NSBezelStyleRounded)
        apply_btn.setTarget_(self)
        apply_btn.setAction_('applyTransform:')
        apply_btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        tfm_bar.addSubview_(apply_btn)

        # Swap button
        swap_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(W - PAD - 68, 10, 56, 26))
        swap_btn.setTitle_('⇅')
        swap_btn.setBezelStyle_(NSBezelStyleRounded)
        swap_btn.setTarget_(self)
        swap_btn.setAction_('swapInputOutput:')
        swap_btn.setToolTip_('Swap input ↔ output')
        swap_btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        tfm_bar.addSubview_(swap_btn)

        cv.addSubview_(tfm_bar)
        self._tfm_bar = tfm_bar
        self._tfm_bar_y = TFM_BAR_Y
        self._tfm_bar_h = TFM_BAR_H

        # ── Input section ─────────────────────────────────────────────────────
        in_top = H
        in_bot = TFM_BAR_Y + TFM_BAR_H
        in_h = in_top - in_bot

        # Input header
        in_header = NSView.alloc().initWithFrame_(
            NSMakeRect(0, in_bot + in_h - 34, W, 34))
        in_header.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)

        lbl_in = NSTextField.labelWithString_('INPUT')
        lbl_in.setFont_(NSFont.boldSystemFontOfSize_(10))
        lbl_in.setTextColor_(NSColor.tertiaryLabelColor())
        lbl_in.setFrame_(NSMakeRect(PAD, 10, 60, 14))
        in_header.addSubview_(lbl_in)

        paste_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(W - PAD - 140, 6, 140, 22))
        paste_btn.setTitle_('Paste from Clipboard')
        paste_btn.setBezelStyle_(NSBezelStyleInline)
        paste_btn.setTarget_(self)
        paste_btn.setAction_('pasteInput:')
        paste_btn.setAutoresizingMask_(NSViewMinXMargin)
        in_header.addSubview_(paste_btn)

        cv.addSubview_(in_header)

        # Input text area
        in_sv, self._input_tv = _scroll_with_textview(
            PAD, in_bot, W - PAD * 2, in_h - 34 - 4, editable=True)
        in_sv.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        self._input_tv.setDelegate_(self)
        cv.addSubview_(in_sv)

        # ── Output section ────────────────────────────────────────────────────
        out_top = TFM_BAR_Y
        out_h = out_top - OUT_BAR_H

        # Output header
        out_header = NSView.alloc().initWithFrame_(
            NSMakeRect(0, OUT_BAR_H + out_h - 34, W, 34))
        out_header.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)

        lbl_out = NSTextField.labelWithString_('OUTPUT')
        lbl_out.setFont_(NSFont.boldSystemFontOfSize_(10))
        lbl_out.setTextColor_(NSColor.tertiaryLabelColor())
        lbl_out.setFrame_(NSMakeRect(PAD, 10, 60, 14))
        out_header.addSubview_(lbl_out)

        self._out_badge = NSTextField.labelWithString_('')
        self._out_badge.setFont_(NSFont.boldSystemFontOfSize_(10))
        self._out_badge.setFrame_(NSMakeRect(PAD + 66, 10, 50, 14))
        self._out_badge.setWantsLayer_(True)
        self._out_badge.layer().setCornerRadius_(3)
        out_header.addSubview_(self._out_badge)

        cv.addSubview_(out_header)

        # Output text area
        out_sv, self._output_tv = _scroll_with_textview(
            PAD, OUT_BAR_H, W - PAD * 2, out_h - 34 - 4, editable=False)
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

        restored = False
        if selected_name:
            idx = self._popup.indexOfItemWithTitle_(selected_name)
            if idx >= 0:
                self._popup.selectItemAtIndex_(idx)
                restored = True
        if not restored:
            # Prefer the first transform with a specific (non-empty) required set
            # so 'any'-type transforms like JSON Stringify don't take priority
            from transform import TRANSFORMS as _ALL
            _req_map = {name: req for name, _, req in _ALL}
            best = 0
            for i, (_, name, _fn) in enumerate(self._visible_transforms):
                if _req_map.get(name):
                    best = i
                    break
            self._popup.selectItemAtIndex_(best)

    # ── Actions ─────────────────────────────────────────────────────────────

    def pasteInput_(self, sender):
        pb = NSPasteboard.generalPasteboard()
        text = (pb.stringForType_(NSStringPboardType) or
                pb.stringForType_('public.utf8-plain-text'))
        if text:
            self._input_tv.setString_(str(text))
            self._refreshPopup()

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
        self.__updateOutputMeta(text, result)
        # Auto-copy result to clipboard
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(result, NSStringPboardType)

    def __updateOutputMeta(self, input_text, output_text):
        # Stats label
        in_lines = input_text.count('\n') + 1 if input_text.strip() else 0
        out_lines = output_text.count('\n') + 1 if output_text.strip() else 0
        if in_lines and out_lines:
            self._stats_label.setStringValue_(
                f'{in_lines} line{"s" if in_lines!=1 else ""} → {out_lines} line{"s" if out_lines!=1 else ""}  ·  {len(output_text)} chars')
        else:
            self._stats_label.setStringValue_('')

        # Output type badge
        if output_text.strip():
            itype = detect_input_type(output_text)
            badge_info = None
            for t in ('json', 'json_string', 'sql', 'csv', 'url', 'code'):
                if t in itype:
                    badge_info = _TYPE_BADGE.get(t)
                    break
            if badge_info and self._out_badge:
                label, bg, fg = badge_info
                self._out_badge.setStringValue_(label)
                self._out_badge.setTextColor_(_nscolor_hex(fg))
                self._out_badge.layer().setBackgroundColor_(_nscolor_hex(bg).CGColor())
                bw = len(label) * 7 + 12
                fr = self._out_badge.frame()
                self._out_badge.setFrame_(NSMakeRect(fr.origin.x, fr.origin.y, bw, fr.size.height))
            elif self._out_badge:
                self._out_badge.setStringValue_('')
        elif self._out_badge:
            self._out_badge.setStringValue_('')

    def saveOutput_(self, sender):
        text = str(self._output_tv.string())
        if not text.strip():
            return
        from AppKit import NSSavePanel
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
        self._refreshPopup()

    # ── Public interface ────────────────────────────────────────────────────

    def _autoApply(self):
        if self._visible_transforms:
            self.applyTransform_(None)

    def showWithText_(self, text):
        self._input_tv.setString_(str(text))
        self._output_tv.setString_('')
        if self._stats_label:
            self._stats_label.setStringValue_('')
        if self._out_badge:
            self._out_badge.setStringValue_('')
        self._refreshPopup()
        self._autoApply()
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        self._window.makeKeyAndOrderFront_(None)

    def show(self):
        pb = NSPasteboard.generalPasteboard()
        text = (pb.stringForType_(NSStringPboardType) or
                pb.stringForType_('public.utf8-plain-text'))
        if text:
            self._input_tv.setString_(str(text))
        self._refreshPopup()
        self._autoApply()
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        self._window.makeKeyAndOrderFront_(None)

    def hide(self):
        self._window.orderOut_(None)

    def windowShouldClose_(self, sender):
        self.hide()
        return False
