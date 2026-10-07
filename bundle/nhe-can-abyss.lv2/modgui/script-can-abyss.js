function (event, funcs) {
    // Moves the Disc Size and Mix caps and scales the can. Kept tiny on purpose:
    // if a face script throws, mod-ui silently disables it.
    // Caps: top at y 44 (value max) down to y 248 (value 0, just above the labels).
    // Can: 140 px tall at Disc Size 0, 280 px at 10, scaling from its centre (y 196).
    function cap(sel, x) {
        event.icon.find(sel).css('top', (248 - 204 * Math.max(0, Math.min(1, x))) + 'px');
    }
    function disc(v) {
        var h = 140 + 14 * Math.max(0, Math.min(10, v));
        event.icon.find('.ca-can').css({ top: (196 - h / 2) + 'px', height: h + 'px' });
        cap('.ca-cap-disc', v / 10);
    }
    function mix(v) {
        cap('.ca-cap-mix', v / 100);
    }
    if (event.type == 'start') {
        var ports = event.ports || [];
        for (var i = 0; i < ports.length; i++) {
            if (ports[i].symbol == 'disc_size') disc(ports[i].value);
            if (ports[i].symbol == 'mix') mix(ports[i].value);
        }
    } else if (event.type == 'change') {
        if (event.symbol == 'disc_size') disc(event.value);
        if (event.symbol == 'mix') mix(event.value);
    }
}
