"""OutlineEditor, part: popup menus (numbered 1-9, 0): the item menu, the add menu and the right-click menu."""
from __future__ import annotations

import time
import weakref

from gi.repository import Gdk, Gio, GLib, Graphene, Gtk

from ..model import enclosing_heading, heading_numbers, is_text
from .helpers import let_go_when_closed, run_once
from .rows import TextRow, _mods


def _mi(label, action=None, target=None, accel=None):
    item = Gio.MenuItem.new(label, None)
    if action:
        if target is None:
            item.set_action_and_target_value(action, None)
        else:
            item.set_action_and_target_value(action, GLib.Variant.new_string(target))
    if accel:
        item.set_attribute_value("accel", GLib.Variant.new_string(accel))
    return item


class MenuRow(Gtk.ListBoxRow):
    """A row of the editor's popup lists. A choice gets a number key (_number_rows); the row
    runs its action (act, with target) or its callback (cb)."""

    def __init__(self, choice=False, act=None, target=None, cb=None, **props):
        super().__init__(**props)
        self.choice, self.act, self.target, self.cb = choice, act, target, cb


def _digit(keyval):
    """Digit keys (top row or keypad) as menu numbers: 1–9 → 1–9, 0 → 10; else None."""
    name = Gdk.keyval_name(keyval) or ""
    if name.startswith("KP_"):
        name = name[3:]
    return (int(name) or 10) if len(name) == 1 and name.isdigit() else None


def _number_rows(lb):
    """Put 1–9, 0 in front of the first ten choices of a menu list; returns {number: row}.
    Greyed-out choices get a blank in the number column so the text stays aligned."""
    numbered = {}
    r = lb.get_first_child()
    while r is not None:
        if isinstance(r, MenuRow) and r.choice:
            n = len(numbered) + 1
            on = r.get_sensitive() and n <= 10
            num = Gtk.Label(label=str(n % 10) if on else "", width_chars=1, css_classes=["menu-num"])
            child = r.get_child()
            r.set_child(None)
            child.set_hexpand(True)
            box = Gtk.Box(spacing=10)
            box.append(num)
            box.append(child)
            r.set_child(box)
            if on:
                numbered[n] = r
        r = r.get_next_sibling()
    return numbered


class MenuList:
    """A Gio.Menu as the app's numbered popup list (CR49 in CODE_REVIEW.md): `list` is the
    ListBox, a MenuRow per item with its accelerator, and a check mark in front when the
    menu has an item of a stateful editor action ("ed." in `actions`); sections become a
    separator and their label a heading. `numbered` is {number key: row}, `first` the
    first row that can be chosen."""

    def __init__(self, model, actions):
        self.actions = actions
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, activate_on_single_click=True)
        self.first = None
        self.marks = self._stateful(model)
        self._add(model)
        self.numbered = _number_rows(self.list)

    def _action(self, name):
        """The editor's action for an "ed.…" name; None for other actions."""
        return self.actions.lookup_action(name[3:]) if name and name.startswith("ed.") else None

    def _stateful(self, menu):
        for i in range(menu.get_n_items()):
            sec = menu.get_item_link(i, "section")
            if sec is not None and self._stateful(sec):
                return True
            a = menu.get_item_attribute_value(i, "action", GLib.VariantType.new("s"))
            ga = self._action(a.unpack()) if a else None
            if ga is not None and ga.get_state() is not None:
                return True
        return False

    def _add(self, menu):
        for i in range(menu.get_n_items()):
            sec = menu.get_item_link(i, "section")
            if sec is None:
                self._add_item(menu, i)
                continue
            last = self.list.get_last_child()
            if last is not None and not (last.has_css_class("head") or last.has_css_class("sep")):
                sep = Gtk.ListBoxRow(activatable=False, selectable=False, can_focus=False, child=Gtk.Separator())
                sep.add_css_class("sep")
                self.list.append(sep)
            head = menu.get_item_attribute_value(i, "label", GLib.VariantType.new("s"))
            if head is not None:
                hl = Gtk.Label(label=head.unpack(), xalign=0, css_classes=["heading", "dim-label"])
                hr = Gtk.ListBoxRow(activatable=False, selectable=False, can_focus=False, child=hl)
                hr.add_css_class("head")
                self.list.append(hr)
            self._add(sec)

    def _add_item(self, menu, i):
        label = menu.get_item_attribute_value(i, "label", GLib.VariantType.new("s"))
        action = menu.get_item_attribute_value(i, "action", GLib.VariantType.new("s"))
        target = menu.get_item_attribute_value(i, "target", None)
        accel = menu.get_item_attribute_value(i, "accel", GLib.VariantType.new("s"))
        act = action.unpack() if action else None
        ga = self._action(act)
        checked = bool(ga and ga.get_state() is not None and target is not None and ga.get_state().equal(target))
        row = MenuRow(choice=True, act=act, target=target)
        box = Gtk.Box(spacing=10)
        if self.marks:
            mark = Gtk.Image.new_from_icon_name("object-select-symbolic")
            mark.set_opacity(1 if checked else 0)
            box.append(mark)
        box.append(Gtk.Label(label=label.unpack() if label else "", xalign=0, hexpand=True))
        if accel:
            ok, key, mods = Gtk.accelerator_parse(accel.unpack())
            al = Gtk.Label(label=Gtk.accelerator_get_label(key, mods) if ok else "", css_classes=["dim-label"])
            al.set_margin_start(24)
            box.append(al)
        row.set_child(box)
        row.set_sensitive(ga is None or ga.get_enabled())
        self.list.append(row)
        if self.first is None and row.get_sensitive():
            self.first = row


class MenusMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- menus -----------------------------------------------------------------------------

    def _kind_section(self, node):
        cur = "heading" if node.kind == "heading" else f"bullet:{node.marker}"
        self.actions.lookup_action("set-kind").set_state(GLib.Variant.new_string(cur))
        m = Gio.Menu()
        for kind, marker, label, trig in self.kind_options():
            m.append_item(_mi(f"{label}      {trig}␣" if trig else label, "ed.set-kind",
                              "heading" if kind == "heading" else f"bullet:{marker}"))
        return m

    def add_menu_model(self, node):
        h = enclosing_heading(node)
        label = self.rules.label
        m = Gio.Menu()
        s1 = Gio.Menu()
        if h is not None:
            nums = heading_numbers(h)
            s1.append_item(_mi(f"Next Item   {label(nums[:-1] + [nums[-1] + 1])}", "ed.add", "next",
                               "<Control>Return"))
            nchild = sum(1 for c in h.children if c.kind == "heading")
            s1.append_item(_mi(f"Sub-item   {label(nums + [nchild + 1])}", "ed.add", "child"))
            if h.parent.kind == "heading":
                pn = heading_numbers(h.parent)
                s1.append_item(_mi(f"Parent-level Item   {label(pn[:-1] + [pn[-1] + 1])}", "ed.add", "parent"))
        else:
            n = sum(1 for c in self.doc.root.children if c.kind == "heading")
            s1.append_item(_mi(f"Numbered Item   {label([n + 1])}", "ed.add", "next", "<Control>Return"))
        m.append_section(None, s1)
        s2 = Gio.Menu()
        for name, spec in self.rules["markers"].items():
            s2.append_item(_mi(f"{spec['symbol']}   {spec.get('label', name)}", "ed.add", f"bullet:{name}"))
        m.append_section(None, s2)
        s3 = Gio.Menu()
        s3.append_item(_mi("Table", "ed.add", "table", "<Control>t"))
        s3.append_item(_mi("Drawing", "ed.add", "drawing", "<Control>d"))
        m.append_section(None, s3)
        return m

    def popup_menu(self, model, parent, rect=None):
        """Show a Gio.Menu as the app's numbered popup list (also used by the sidebar)."""
        self._popup(model, parent, rect)

    def _popup(self, model, parent, rect=None, node=None):
        """Show a Gio.Menu as a plain list popover. (GtkPopoverMenu mis-measures its
        height here and adds a scrollbar; a ListBox never scrolls.)"""
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("menu")
        pop.add_css_class("ntz-menu")
        menu = MenuList(model, self.actions)
        lb, numbered = menu.list, menu.numbered

        def activated(_lb, row):
            pop.popdown()

            def run():
                self._menu_node = node
                if row.act:
                    parent.activate_action(row.act, row.target)
                self._menu_node = None
                return False
            GLib.idle_add(run)

        lb.connect("row-activated", activated)

        def on_key(_c, keyval, _kc, state):
            ctrl, _shift, alt = _mods(state)
            n = None if ctrl or alt else _digit(keyval)
            if n in numbered:
                activated(lb, numbered[n])
                return True
            return False

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", on_key)
        pop.add_controller(keys)
        pop.set_child(lb)
        pop.set_parent(parent)
        pos = Gtk.PositionType.BOTTOM
        if rect is not None:
            pop.set_pointing_to(rect)
            ok, pt = parent.compute_point(self, Graphene.Point().init(rect.x, rect.y))
            if ok and pt.y > self.get_height() * 0.5:
                pos = Gtk.PositionType.TOP
        pop.set_position(pos)
        let_go_when_closed(pop, keys)
        pop.popup()
        if menu.first is not None:
            GLib.idle_add(run_once, menu.first.grab_focus)
        return pop

    def show_add_menu(self, row, view):
        self._popup(self.add_menu_model(row.node), view, view.cursor_rect(), node=row.node)

    def show_item_menu(self, row):
        self.clear_carets()
        node = row.node
        m = Gio.Menu()
        if is_text(node):
            m.append_section("Item Type", self._kind_section(node))
            m.append_section("Add", self.add_menu_model(node))
            d = Gio.Menu()
            d.append_item(_mi("Delete Item", "ed.delete-item"))
            m.append_section(None, d)
        else:
            d = Gio.Menu()
            if node.kind == "drawing":
                d.append_item(_mi("Edit Drawing", "ed.edit-drawing"))
                d.append_item(_mi("Copy Drawing", "ed.copy-drawing"))
            d.append_item(_mi({"table": "Delete Table", "drawing": "Delete Drawing"}.get(node.kind, "Delete Block"),
                              "ed.delete-item"))
            m.append_section(None, d)
        self._popup(m, row.prefix, node=node)

    def on_click(self, row, view, gesture, x, y):
        self._click_time = time.monotonic()
        self.clear_carets()
        btn = gesture.get_current_button()
        if btn == 3:
            self.set_current(row.node, view)
            self._prepare_context(row, view, (x, y))
            return
        state = gesture.get_current_event_state()
        if btn == 1 and state & Gdk.ModifierType.SHIFT_MASK and self.current is not None \
                and self.current is not row.node:
            order = self._order()
            at = {id(n): i for i, n in enumerate(order)}
            anchor = self.sel_anchor if self.sel and id(self.sel_anchor) in at else self.current
            if id(anchor) not in at:  # (the item it began at is gone)
                anchor = row.node
            self.sel_anchor, self.sel_head = anchor, row.node
            a, b = sorted((at[id(anchor)], at[id(row.node)]))
            self.set_selection(order[a:b + 1])
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            return
        self.clear_selection()
        if btn == 1:
            self.start_drag_select(row, view, x, y)

    def _prepare_context(self, row, view, point):
        """Fill the text view's right-click menu (shown below GTK's cut/copy/paste)."""
        menu = Gio.Menu()
        it = view.iter_at_widget_point(*point) if point else view.cursor_iter()
        self._ctx = None
        sp = self.spelling.speller
        if self.spelling.enabled and sp is not None and it is not None:
            hit = view.misspelled_at(it)
            if hit:
                (s, e), word = hit
                self._ctx = (weakref.ref(view), s, e)
                sec = Gio.Menu()
                sugg = sp.suggest(word)
                for w in sugg:
                    sec.append_item(_mi(w, "ed.spell-replace", w))
                if not sugg:
                    sec.append_item(_mi("No Suggestions", "ed.noop"))
                sec.append_item(_mi(f"Add “{word}” to Dictionary", "ed.spell-add", word))
                sec.append_item(_mi("Ignore", "ed.spell-ignore", word))
                menu.append_section(None, sec)
        if self.sel:
            s = Gio.Menu()
            s.append_item(_mi("Copy Items", "ed.copy-items", accel="<Control>c"))
            s.append_item(_mi("Cut Items", "ed.cut-items", accel="<Control>x"))
            s.append_item(_mi("Delete Items", "ed.delete-items", accel="Delete"))
            menu.append_section(None, s)
        f = Gio.Menu()
        f.append_item(_mi("Bold", "ed.bold", accel="<Control>b"))
        f.append_item(_mi("Italic", "ed.italic", accel="<Control>i"))
        menu.append_section(None, f)
        if isinstance(row, TextRow):
            self._menu_node = None
            s = Gio.Menu()
            s.append_submenu("Item Type", self._kind_section(row.node))
            s.append_submenu("Add", self.add_menu_model(row.node))
            menu.append_section(None, s)
            s = Gio.Menu()
            s.append_item(_mi("Expand Selection", "ed.select-scope", accel="<Control>w"))
            s.append_item(_mi("Select All Items", "ed.select-all", accel="<Control>a"))
            s.append_item(_mi("Paste as Plain Text", "ed.paste-plain", accel="<Control><Shift>v"))
            s.append_item(_mi("Delete Item", "ed.delete-item"))
            menu.append_section(None, s)
        if self.spell_menu is not None:
            sm = Gio.Menu()
            sm.append_submenu("Spelling", self.spell_menu)
            menu.append_section(None, sm)
        u = Gio.Menu()
        u.append_item(_mi("Undo", "ed.undo", accel="<Control>z"))
        u.append_item(_mi("Redo", "ed.redo", accel="<Control><Shift>z"))
        menu.append_section(None, u)
        view.set_extra_menu(menu)

    def _format_cmd(self, attr):
        if self.sel:
            self.format_items(attr)
        elif self.cur_view is not None:
            self.cur_view.toggle(attr)
