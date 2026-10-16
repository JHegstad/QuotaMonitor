import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Pango from 'gi://Pango';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {lastUpdatedDescription, limitingLabel, resetDescription, status} from './display.js';

const REFRESH_SECONDS = 120;
const SCHEMA = 'org.gnome.shell.extensions.quotamonitor';

function label(text, styleClass = '') {
    const actor = new St.Label({text, style_class: styleClass, x_expand: true});
    actor.clutter_text.set_line_wrap(true);
    actor.clutter_text.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);
    actor.clutter_text.set_ellipsize(Pango.EllipsizeMode.NONE);
    return actor;
}

class QuotaRow {
    constructor(title) {
        this.actor = new St.BoxLayout({vertical: true, style_class: 'qm-row'});
        const heading = new St.BoxLayout();
        heading.add_child(label(title, 'qm-row-title'));
        this.percent = label('--', 'qm-percent');
        this.percent.x_expand = false;
        heading.add_child(this.percent);
        this.actor.add_child(heading);

        // A horizontal box packs the fill from the leading edge. BinLayout
        // centers non-expanding children despite their actor x_align setting.
        this.track = new St.BoxLayout({style_class: 'qm-track', x_expand: true});
        this.fill = new St.Widget({style_class: 'qm-fill qm-unknown',
            x_align: Clutter.ActorAlign.START, y_expand: true});
        this.track.add_child(this.fill);
        this.track.connect('notify::width', () => this._resize());
        this.actor.add_child(this.track);
        this.reset = label('Reset: Ikke registrert', 'qm-detail');
        this.actor.add_child(this.reset);
        this._fraction = 0;
    }

    _resize() {
        this.fill.width = Math.max(0, this.track.width * this._fraction);
    }

    update(remaining, reset, now) {
        const state = status(remaining);
        this.percent.text = state === 'unknown' ? '--' : `${remaining} %`;
        this._fraction = state === 'unknown' ? 0 : Math.max(0, Math.min(100, remaining)) / 100;
        this.fill.set_style_class_name(`qm-fill qm-${state}`);
        this._resize();
        this.reset.text = resetDescription(reset, now);
    }
}

class QuotaCard {
    constructor(refresh) {
        this.actor = new St.BoxLayout({vertical: true, style_class: 'qm-card', reactive: !!refresh});
        this.actor.add_child(label('WORK + CODEX', 'qm-title'));
        this.five = new QuotaRow('5 timer');
        this.week = new QuotaRow('Uke');
        this.actor.add_child(this.five.actor);
        this.actor.add_child(this.week.actor);
        this.updated = label('Sist oppdatert: aldri', 'qm-detail');
        this.actor.add_child(this.updated);
        this.message = label('', 'qm-detail qm-message');
        this.actor.add_child(this.message);
        if (refresh) {
            this.button = new St.Button({label: 'Oppdater fra Codex nå',
                style_class: 'qm-refresh', can_focus: true});
            this.button.connect('clicked', refresh);
            this.actor.add_child(this.button);
        }
    }

    update(quota, busy) {
        const now = new Date();
        this.five.update(quota.fiveHourRemaining, quota.fiveHourReset, now);
        this.week.update(quota.weeklyRemaining, quota.weeklyReset, now);
        this.updated.text = lastUpdatedDescription(quota.lastUpdated, now);
        this.message.text = quota.lastRefreshFailed ? 'Kunne ikke oppdatere – viser siste data' : '';
        this.message.visible = !!quota.lastRefreshFailed;
        if (this.button) {
            this.button.label = busy ? 'Oppdaterer …' : 'Oppdater fra Codex nå';
            this.button.reactive = !busy;
        }
    }
}

export default class QuotaMonitorExtension extends Extension {
    enable() {
        this._active = true;
        this._generation = (this._generation ?? 0) + 1;
        this._signals = [];
        this._quota = {};
        this._busy = false;
        this._process = null;
        this._refreshTimer = 0;
        this._displayTimer = 0;
        this._watchdog = 0;
        try {
            this._settings = this.getSettings(SCHEMA);
            this._indicator = new PanelMenu.Button(0.0, 'QuotaMonitor');
            this._panelLabel = new St.Label({text: 'Work --', y_align: Clutter.ActorAlign.CENTER});
            this._indicator.add_child(this._panelLabel);
            Main.panel.addToStatusArea(this.uuid, this._indicator);

            this._menuCard = new QuotaCard(() => this._refresh(true));
            const section = new PopupMenu.PopupMenuSection();
            section.actor.add_child(this._menuCard.actor);
            this._indicator.menu.addMenuItem(section);
            this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            this._desktopToggle = new PopupMenu.PopupSwitchMenuItem('Vis skrivebordskort',
                this._settings.get_boolean('show-desktop'));
            this._desktopToggle.connect('toggled', (_item, value) => {
                this._settings.set_boolean('show-desktop', value);
            });
            this._indicator.menu.addMenuItem(this._desktopToggle);
            const positions = new PopupMenu.PopupSubMenuMenuItem('Plasser skrivebordskort');
            for (const [value, text] of [['top-right', 'Øverst til høyre'], ['top-left', 'Øverst til venstre'],
                ['bottom-right', 'Nederst til høyre'], ['bottom-left', 'Nederst til venstre']]) {
                positions.menu.addAction(text, () => this._settings.set_string('desktop-corner', value));
            }
            this._indicator.menu.addMenuItem(positions);
            this._errorItem = new PopupMenu.PopupMenuItem('', {reactive: false});
            this._errorItem.label.clutter_text.set_line_wrap(true);
            this._errorItem.label.clutter_text.set_ellipsize(Pango.EllipsizeMode.NONE);
            this._errorItem.label.set_style('max-width: 340px;');
            this._indicator.menu.addMenuItem(this._errorItem);

            // The desktop card is display-only. Actions live in the top-bar
            // menu so no Shell input region can intercept an overlapping X11 app.
            this._desktopCard = new QuotaCard(null);
            // Keep the card above desktop-icon windows but below application
            // windows, including Ubuntu's Desktop Icons NG (DING) surface.
            global.window_group.add_child(this._desktopCard.actor);
            this._connect(global.display, 'restacked', () => this._restack());
            this._connect(global.display, 'workareas-changed', () => this._position());
            this._connect(Main.layoutManager, 'monitors-changed', () => this._position());
            this._connect(this._settings, 'changed', () => this._position());
            this._connect(this._indicator.menu, 'open-state-changed', () => this._render());

            this._render();
            this._position();
            this._restack();
            this._refreshTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            });
            // This only redraws local countdowns; it never requests quota.
            this._displayTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 60, () => {
                this._render();
                return GLib.SOURCE_CONTINUE;
            });
            const generation = this._generation;
            this._runReader(['--cached-only']).finally(() => {
                if (this._active && this._generation === generation)
                    this._refresh();
            });
        } catch (error) {
            this.disable();
            throw error;
        }
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _position() {
        if (!this._active || !this._desktopCard || Main.layoutManager.primaryIndex < 0)
            return;
        const actor = this._desktopCard.actor;
        actor.visible = this._settings.get_boolean('show-desktop');
        const area = Main.layoutManager.getWorkAreaForMonitor(Main.layoutManager.primaryIndex);
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const margin = 20 * scale;
        actor.width = Math.max(1, Math.min(360 * scale, area.width - 2 * margin));
        const [, naturalHeight] = actor.get_preferred_height(actor.width);
        actor.height = naturalHeight;
        const corner = this._settings.get_string('desktop-corner');
        const x = corner.endsWith('right') ? area.x + area.width - actor.width - margin : area.x + margin;
        const y = corner.startsWith('bottom') ? area.y + area.height - actor.height - margin : area.y + margin;
        actor.set_position(Math.round(x), Math.round(Math.max(area.y + margin, y)));
    }

    _restack() {
        if (!this._active || !this._desktopCard)
            return;
        const card = this._desktopCard.actor;
        const firstApplication = global.window_group.get_children().find(actor => {
            if (typeof actor.get_meta_window !== 'function')
                return false;
            const window = actor.get_meta_window();
            if (!window)
                return false;
            const appId = window.get_gtk_application_id() ?? '';
            const wmClass = window.get_wm_class() ?? '';
            const desktop = window.get_window_type() === Meta.WindowType.DESKTOP ||
                /com\.rastersoft\.ding|desktop-icons/i.test(`${appId} ${wmClass}`);
            return !desktop;
        });
        if (firstApplication)
            global.window_group.set_child_below_sibling(card, firstApplication);
        else
            global.window_group.set_child_above_sibling(card, null);
    }

    _render() {
        if (!this._active)
            return;
        this._panelLabel.text = limitingLabel(this._quota);
        this._menuCard.update(this._quota, this._busy);
        this._desktopCard.update(this._quota, this._busy);
        this._errorItem.label.text = this._quota.error ?? this._quota.cacheWarning ?? '';
        this._errorItem.visible = !!this._errorItem.label.text;
        this._position();
    }

    _refresh(manual = false) {
        if (this._active && !this._busy)
            this._runReader(manual ? ['--force'] : []);
    }

    async _runReader(args) {
        if (!this._active || this._busy)
            return;
        const generation = this._generation;
        this._busy = true;
        this._render();
        let process = null;
        let watchdog = 0;
        let timedOut = false;
        try {
            process = Gio.Subprocess.new(['/usr/bin/python3', `${this.path}/quota_reader.py`, ...args],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            this._process = process;
            watchdog = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 20, () => {
                timedOut = true;
                process.send_signal(15);
                this._watchdog = 0;
                watchdog = 0;
                return GLib.SOURCE_REMOVE;
            });
            this._watchdog = watchdog;
            const [success, stdout] = await new Promise((resolve, reject) => {
                process.communicate_utf8_async(null, null, (source, result) => {
                    try {
                        resolve(source.communicate_utf8_finish(result));
                    } catch (error) {
                        reject(error);
                    }
                });
            });
            if (!this._active || this._generation !== generation)
                return;
            if (timedOut || !success || !process.get_successful())
                throw new Error('Kunne ikke lese Codex. Kontroller installasjonen og innloggingen.');
            const quota = JSON.parse(stdout);
            if (!quota || typeof quota !== 'object' || Array.isArray(quota))
                throw new Error('Ugyldig svar fra kvoteleseren.');
            this._quota = quota;
        } catch (error) {
            if (this._active && this._generation === generation) {
                this._quota = {...this._quota, lastRefreshFailed: true, error: error.message};
                console.error(`[QuotaMonitor] ${error.message}`);
            }
        } finally {
            if (this._active && this._generation === generation) {
                if (watchdog)
                    GLib.Source.remove(watchdog);
                this._watchdog = 0;
                this._process = null;
                this._busy = false;
                this._render();
            }
        }
    }

    disable() {
        this._active = false;
        this._generation = (this._generation ?? 0) + 1;
        for (const name of ['_refreshTimer', '_displayTimer', '_watchdog']) {
            if (this[name])
                GLib.Source.remove(this[name]);
            this[name] = 0;
        }
        // SIGTERM lets the Python worker reap its short-lived Codex child.
        this._process?.send_signal(15);
        this._process = null;
        for (const [object, id] of this._signals ?? [])
            object.disconnect(id);
        this._signals = [];
        if (this._desktopCard) {
            this._desktopCard.actor.destroy();
        }
        this._indicator?.destroy();
        this._settings = null;
        this._desktopCard = null;
        this._menuCard = null;
        this._indicator = null;
        this._panelLabel = null;
        this._desktopToggle = null;
        this._errorItem = null;
        this._quota = null;
    }
}
