#!/usr/bin/env python3
"""ClipKit — macOS clipboard manager."""

import os
import sys

# Single-instance guard via lock file
_LOCK = os.path.expanduser('~/.clipkit/clipkit.lock')
os.makedirs(os.path.dirname(_LOCK), exist_ok=True)
import fcntl
_lock_fh = open(_LOCK, 'w')
try:
    fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    # Check if the PID in the lock file is actually alive
    try:
        with open(_LOCK) as _lf:
            pid = int(_lf.read().strip() or '0')
    except Exception:
        pid = 0
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except (ProcessLookupError, PermissionError):
            alive = False
    if alive:
        print('ClipKit is already running.', file=sys.stderr)
        sys.exit(0)
    # Stale lock — reopen and acquire
    _lock_fh.close()
    _lock_fh = open(_LOCK, 'w')
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('ClipKit is already running.', file=sys.stderr)
        sys.exit(0)
_lock_fh.write(str(os.getpid()))
_lock_fh.flush()

import rumps
from clipboard_monitor import ClipboardMonitor
from history_window import HistoryWindowController
from transform_window import TransformWindowController
from settings_window import SettingsWindowController
import settings as S


class ClipKitApp(rumps.App):

    def __init__(self):
        super().__init__('✂', quit_button=None)
        cfg = S.get()
        self._menu_history   = rumps.MenuItem('', callback=self.show_history)
        self._menu_transform = rumps.MenuItem('', callback=self.show_transform)
        self.menu = [
            self._menu_history,
            self._menu_transform,
            None,
            rumps.MenuItem('Settings…', callback=self.show_settings),
            None,
            rumps.MenuItem('Clear History', callback=self.clear_history),
            None,
            rumps.MenuItem('Quit ClipKit', callback=self.quit_app),
        ]
        self._update_menu_titles(cfg)

        self._history_ctrl   = HistoryWindowController.alloc().init()
        self._transform_ctrl = TransformWindowController.alloc().init()
        self._settings_ctrl  = SettingsWindowController.alloc().init()

        self._history_ctrl.setTransformCtrl_(self._transform_ctrl)

        self._monitor = ClipboardMonitor.alloc().init()
        self._monitor.setCallback_(self._on_change)
        self._history_ctrl.setMonitor_onPaste_(self._monitor, None)

        # Standard Edit menu so Cmd+A/C/V/Z work in text views
        self._setup_edit_menu()

        # Keyboard shortcuts via NSEvent global monitor
        self._setup_hotkeys()

        # Delay monitor start until the run loop is ready
        rumps.Timer(self._start_monitor, 0.2).start()

        # Pin the status item so macOS remembers its position
        rumps.Timer(self._pin_status_item, 0.5).start()

    def _update_menu_titles(self, cfg=None):
        if cfg is None:
            cfg = S.get()
        from settings_window import _hotkey_str_to_display
        hk_h = _hotkey_str_to_display(cfg.hotkey_open or 'cmd+alt+v') or '⌘⌥V'
        hk_t = _hotkey_str_to_display(cfg.hotkey_transform or 'cmd+alt+t') or '⌘⌥T'
        self._menu_history.title   = f'Show History   {hk_h}'
        self._menu_transform.title = f'Transform Text   {hk_t}'

    def _start_monitor(self, timer):
        timer.stop()
        self._monitor.start()

    def _pin_status_item(self, timer):
        timer.stop()
        try:
            # Set autosaveName so macOS remembers the item's menu bar position
            # and set behavior so the user cannot accidentally CMD-drag it away
            from AppKit import NSStatusBar
            bar = NSStatusBar.systemStatusBar()
            # Access rumps' underlying status item
            item = self._status_item  # rumps stores it here
            item.setAutosaveName_('com.clipkit.statusitem')
            from AppKit import NSStatusItemBehaviorRemovalAllowed
            item.setBehavior_(0)  # 0 = no removal allowed
        except Exception:
            pass

    def _setup_edit_menu(self):
        from AppKit import NSApp, NSMenu, NSMenuItem
        main_menu = NSApp.mainMenu()
        if main_menu is None:
            main_menu = NSMenu.alloc().init()
            NSApp.setMainMenu_(main_menu)

        edit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Edit', None, '')
        edit_menu = NSMenu.alloc().initWithTitle_('Edit')

        from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagShift

        for title, action, key, shift in [
            ('Undo',       'undo:',      'z', False),
            ('Redo',       'redo:',      'z', True),
            (None, None, None, False),
            ('Cut',        'cut:',       'x', False),
            ('Copy',       'copy:',      'c', False),
            ('Paste',      'paste:',     'v', False),
            ('Delete',     'delete:',    '',  False),
            ('Select All', 'selectAll:', 'a', False),
        ]:
            if title is None:
                edit_menu.addItem_(NSMenuItem.separatorItem())
            else:
                it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
                if shift:
                    it.setKeyEquivalentModifierMask_(
                        NSEventModifierFlagCommand | NSEventModifierFlagShift)
                edit_menu.addItem_(it)

        edit_item.setSubmenu_(edit_menu)
        main_menu.addItem_(edit_item)

    def _setup_hotkeys(self):
        import ctypes
        import ctypes.util

        cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')

        # --- types ---
        CGEventTapProxy = ctypes.c_void_p
        CGEventRef      = ctypes.c_void_p
        CGEventType     = ctypes.c_uint32
        CGEventMask     = ctypes.c_uint64

        CALLBACK_TYPE = ctypes.CFUNCTYPE(
            CGEventRef, CGEventTapProxy, CGEventType, CGEventRef, ctypes.c_void_p)

        # --- constants ---
        kCGSessionEventTap    = 1
        kCGHeadInsertEventTap = 0
        kCGEventKeyDown       = 10
        kCGKeyboardEventKeycode = 9  # field selector

        # --- CoreGraphics functions ---
        cg.CGEventTapCreate.restype  = ctypes.c_void_p
        cg.CGEventTapCreate.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
            CGEventMask, CALLBACK_TYPE, ctypes.c_void_p]

        cg.CGEventGetFlags.restype  = ctypes.c_uint64
        cg.CGEventGetFlags.argtypes = [CGEventRef]

        cg.CGEventGetIntegerValueField.restype  = ctypes.c_int64
        cg.CGEventGetIntegerValueField.argtypes = [CGEventRef, ctypes.c_int32]

        cg.CGEventTapEnable.restype  = None
        cg.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]

        # --- CoreFoundation run loop ---
        cf.CFMachPortCreateRunLoopSource.restype  = ctypes.c_void_p
        cf.CFMachPortCreateRunLoopSource.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]

        cf.CFRunLoopGetMain.restype  = ctypes.c_void_p
        cf.CFRunLoopGetMain.argtypes = []

        cf.CFRunLoopAddSource.restype  = None
        cf.CFRunLoopAddSource.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

        # kCFRunLoopCommonModes as CFStringRef
        kCFRunLoopCommonModes = ctypes.c_void_p.in_dll(cf, 'kCFRunLoopCommonModes')

        app_ref = self

        # Key name → macOS keycode
        _KEY_CODES = {
            'a':0,'s':1,'d':2,'f':3,'h':4,'g':5,'z':6,'x':7,'c':8,'v':9,
            'b':11,'q':12,'w':13,'e':14,'r':15,'y':16,'t':17,'1':18,'2':19,
            '3':20,'4':21,'6':22,'5':23,'=':24,'9':25,'7':26,'-':27,'8':28,
            '0':29,']':30,'o':31,'u':32,'[':33,'i':34,'p':35,'return':36,
            'l':37,'j':38,"'":39,'k':40,';':41,'\\':42,',':43,'/':44,'n':45,
            'm':46,'.':47,'tab':48,'space':49,'`':50,'delete':51,'escape':53,
            'f1':122,'f2':120,'f3':99,'f4':118,'f5':96,'f6':97,'f7':98,
            'f8':100,'f9':101,'f10':109,'f11':103,'f12':111,
        }
        _MOD_FLAGS = {
            'cmd': 1 << 20, 'command': 1 << 20,
            'alt': 1 << 19, 'option': 1 << 19, 'opt': 1 << 19,
            'ctrl': 1 << 18, 'control': 1 << 18,
            'shift': 1 << 17,
        }

        def _parse_hotkey(hk_str):
            """Parse 'cmd+alt+1' → (flag_mask, keycode) or None."""
            parts = [p.strip().lower() for p in hk_str.strip().split('+')]
            mask_val = 0
            key = None
            for p in parts:
                if p in _MOD_FLAGS:
                    mask_val |= _MOD_FLAGS[p]
                elif p in _KEY_CODES:
                    key = _KEY_CODES[p]
            if key is None or mask_val == 0:
                return None
            return (mask_val, key)

        def _get_transform_hotkeys():
            import settings as S
            S._instance = None  # reload fresh
            return S.get().transform_hotkeys

        def _apply_transform_hotkey(transform_name):
            """Get latest clipboard text, apply transform, push result back."""
            from AppKit import NSPasteboard, NSStringPboardType
            from transform import TRANSFORMS, applicable_transforms
            pb = NSPasteboard.generalPasteboard()
            text = (pb.stringForType_(NSStringPboardType) or
                    pb.stringForType_('public.utf8-plain-text') or '')
            if not text.strip():
                return
            # Find the transform by name
            fn = None
            for name, f, _req in TRANSFORMS:
                if name == transform_name:
                    fn = f
                    break
            if fn is None:
                return
            try:
                result = fn(text)
            except Exception:
                return
            pb.clearContents()
            pb.setString_forType_(result, NSStringPboardType)

        # Pre-compute built-in hotkeys from settings (updated on save via this ref)
        import settings as S
        _cfg = S.get()
        _builtin = [
            _parse_hotkey(_cfg.hotkey_open or 'cmd+alt+v'),
            _parse_hotkey(_cfg.hotkey_transform or 'cmd+alt+t'),
        ]

        def _reload_builtin_hotkeys():
            S._instance = None
            cfg = S.get()
            _builtin[0] = _parse_hotkey(cfg.hotkey_open or 'cmd+alt+v')
            _builtin[1] = _parse_hotkey(cfg.hotkey_transform or 'cmd+alt+t')
            app_ref._update_menu_titles(cfg)

        app_ref._reload_builtin_hotkeys = _reload_builtin_hotkeys

        def tap_callback(proxy, event_type, event, refcon):
            try:
                flags = cg.CGEventGetFlags(event)
                keycode = cg.CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

                # Built-in hotkeys (configurable in Settings → Hotkeys)
                hk_open, hk_transform = _builtin[0], _builtin[1]
                if hk_open and keycode == hk_open[1] and (flags & hk_open[0]) == hk_open[0]:
                    app_ref._history_ctrl.performSelectorOnMainThread_withObject_waitUntilDone_(
                        'show', None, False)
                    return None
                if hk_transform and keycode == hk_transform[1] and (flags & hk_transform[0]) == hk_transform[0]:
                    app_ref._transform_ctrl.performSelectorOnMainThread_withObject_waitUntilDone_(
                        'show', None, False)
                    return None

                # Custom per-transform hotkeys from settings
                import settings as S
                hotkeys = S.get().transform_hotkeys
                for transform_name, hk_str in hotkeys.items():
                    parsed = _parse_hotkey(hk_str)
                    if parsed is None:
                        continue
                    hk_mask, hk_key = parsed
                    if keycode == hk_key and (flags & hk_mask) == hk_mask:
                        import threading
                        threading.Thread(
                            target=_apply_transform_hotkey,
                            args=(transform_name,),
                            daemon=True
                        ).start()
                        return None

            except Exception as e:
                print(f'tap_callback error: {e}', flush=True)
            return event

        self._tap_cb_c = CALLBACK_TYPE(tap_callback)  # must keep reference

        mask = CGEventMask(1 << kCGEventKeyDown)
        tap = cg.CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            0,
            mask,
            self._tap_cb_c,
            None,
        )

        if not tap:
            print('WARNING: CGEventTap failed — Accessibility permission needed.', flush=True)
            import subprocess
            subprocess.Popen([
                'open',
                'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
            ])
            return

        cg.CGEventTapEnable(tap, True)

        src = cf.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = cf.CFRunLoopGetMain()
        cf.CFRunLoopAddSource(loop, src, kCFRunLoopCommonModes)

        self._tap_port = tap
        self._tap_src  = src
        print('Hotkeys registered via CGEventTap (ctypes): ⌘⌥V  ⌘⌥T', flush=True)

    def _show_accessibility_alert(self):
        import threading
        def show():
            from AppKit import NSAlert, NSApp
            import time
            time.sleep(1)  # wait for app to be ready
            alert = NSAlert.alloc().init()
            alert.setMessageText_('ClipKit needs Accessibility permission')
            alert.setInformativeText_(
                'To enable global hotkeys (⌘⇧V / ⌘⇧T), open:\n\n'
                'System Settings → Privacy & Security → Accessibility\n\n'
                'Click the + button, add ClipKit (or Python), enable it, '
                'then restart ClipKit.')
            alert.addButtonWithTitle_('OK')
            NSApp.activateIgnoringOtherApps_(True)
            alert.runModal()
        t = threading.Thread(target=show, daemon=True)
        t.start()

    def showHistoryFromHotkey_(self, _):
        self._history_ctrl.show()

    def showTransformFromHotkey_(self, _):
        self._transform_ctrl.show()

    def _on_change(self):
        pass

    def show_history(self, _):
        self._history_ctrl.show()

    def show_transform(self, _):
        self._transform_ctrl.show()

    def show_settings(self, _):
        self._settings_ctrl.show()

    def clear_history(self, _):
        self._history_ctrl.clearUnpinned()
        self._monitor.clearHistory()

    def quit_app(self, _):
        rumps.quit_application()


if __name__ == '__main__':
    ClipKitApp().run()
