function (event, funcs) {
    // Can-Abyss face script. Kept small and old-style (ES5) on purpose:
    // if a face script throws, mod-ui silently disables it.
    //  - Disc Size / Mix: move the caps (y 248 at zero, just above the labels, to y 44)
    //    and scale the can from its centre (140 px tall at 0, 280 px at 10).
    //  - Time / Ceiling readouts: drawn here; click one to type a value (Enter = set,
    //    Esc = cancel). mod-ui does not echo values set from a script back to it,
    //    so the readout is updated here after setting.
    //  - Time also takes tempo: "120bpm" (or "120b") sets a quarter note at 120 BPM;
    //    add a division for other notes: "120b 1/8", "120b 1/8." (dotted), "120b 1/8t"
    //    (triplet). "1.2s" works too. The readout always shows ms.
    var icon = event.icon;
    var RANGE = { time: [40, 2000], ceiling: [-24, 0] };
    var UNIT = { time: 'ms', ceiling: 'dB' };

    // "500", "500ms", "1.2s", "120bpm", "120b 1/8", "120b 1/8.", "120b 1/8t" -> ms (NaN if unreadable)
    function parseTime(txt) {
        var t = String(txt).toLowerCase().replace(/,/g, '.').replace(/\s+/g, '');
        var m = /^(\d*\.?\d+)b(?:pm)?(?:(\d+)\/(\d+)([.t])?)?$/.exec(t);
        if (m) {
            var bpm = parseFloat(m[1]);
            if (!(bpm > 0)) return NaN;
            var notes = m[2] ? (4 * parseFloat(m[2]) / parseFloat(m[3])) : 1;   // in quarter notes
            if (m[4] == '.') notes *= 1.5;
            if (m[4] == 't') notes *= 2 / 3;
            return 60000 / bpm * notes;
        }
        m = /^(\d*\.?\d+)(ms|s)?$/.exec(t);
        if (!m) return NaN;
        return parseFloat(m[1]) * (m[2] == 's' ? 1000 : 1);
    }
    function cap(sel, x) {
        icon.find(sel).css('top', (248 - 204 * Math.max(0, Math.min(1, x))) + 'px');
    }
    function disc(v) {
        var h = 140 + 14 * Math.max(0, Math.min(10, v));
        icon.find('.ca-can').css({ top: (196 - h / 2) + 'px', height: h + 'px' });
        cap('.ca-cap-disc', v / 10);
    }
    function mix(v) {
        cap('.ca-cap-mix', v / 100);
    }
    function show(sym, v) {
        var box = icon.find('.ca-' + sym + '-value');
        var abort = box.data('abort');
        if (abort) abort();               // a change from elsewhere closes an open edit
        box.data('v', v);
        box.text(Math.round(v) + UNIT[sym]);
    }
    function edit(sym) {
        var box = icon.find('.ca-' + sym + '-value');
        if (box.find('input').length) return;
        var cur = box.data('v');
        var done = false;
        // Time takes letters (bpm, s), so it gets the full keyboard
        var input = $('<input type="text" autocomplete="off" autocapitalize="off" spellcheck="false">')
            .attr('inputmode', sym == 'time' ? 'text' : 'decimal').val(Math.round(cur));
        function outside(e) {
            if (e.target !== input[0]) finish(true);
        }
        function finish(commit) {
            if (done) return;
            done = true;
            box.removeData('abort');
            document.removeEventListener('mousedown', outside, true);
            document.removeEventListener('touchstart', outside, true);
            document.removeEventListener('pointerdown', outside, true);
            var v = sym == 'time' ? parseTime(input.val()) : parseFloat(input.val());
            input.remove();
            if (commit && !isNaN(v)) {
                v = Math.max(RANGE[sym][0], Math.min(RANGE[sym][1], v));
                funcs.set_port_value(sym, v);
                show(sym, v);
            } else {
                show(sym, cur);
            }
        }
        input.on('keydown', function (e) {
            e.stopPropagation();
            if (e.keyCode == 13) { finish(true); return false; }
            if (e.keyCode == 27) { finish(false); return false; }
        });
        input.on('blur', function () { finish(true); });
        input.on('mousedown click', function (e) { e.stopPropagation(); });
        box.data('abort', function () {
            done = true;
            box.removeData('abort');
            document.removeEventListener('mousedown', outside, true);
            document.removeEventListener('touchstart', outside, true);
            document.removeEventListener('pointerdown', outside, true);
            input.remove();
        });
        // a press anywhere else applies the typed value (capture phase, because
        // knobs and other widgets swallow the event before it reaches us)
        document.addEventListener('mousedown', outside, true);
        document.addEventListener('touchstart', outside, true);
        document.addEventListener('pointerdown', outside, true);
        box.empty().append(input);
        input.focus().select();
    }

    if (event.type == 'start') {
        var ports = event.ports || [];
        for (var i = 0; i < ports.length; i++) {
            var p = ports[i];
            if (p.symbol == 'disc_size') disc(p.value);
            if (p.symbol == 'mix') mix(p.value);
            if (RANGE[p.symbol]) show(p.symbol, p.value);
        }
        icon.find('.ca-time-value').on('click', function (e) { e.stopPropagation(); edit('time'); });
        icon.find('.ca-ceiling-value').on('click', function (e) { e.stopPropagation(); edit('ceiling'); });
        icon.find('.ca-readout').on('mousedown', function (e) { e.stopPropagation(); });
    } else if (event.type == 'change') {
        if (event.symbol == 'disc_size') disc(event.value);
        if (event.symbol == 'mix') mix(event.value);
        if (RANGE[event.symbol]) show(event.symbol, event.value);
    }
}
