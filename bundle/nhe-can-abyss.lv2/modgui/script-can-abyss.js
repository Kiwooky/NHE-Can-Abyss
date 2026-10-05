function (event, funcs) {
    // dim the noise trims while Noise Mods is locked (the DSP ignores them)
    function locked(value) {
        var el = event.icon.find('.ca-trim, .ca-hum_hz');
        if (value > 0.5) {
            el.removeClass('ca-dim');
        } else {
            el.addClass('ca-dim');
        }
    }
    if (event.type == 'start') {
        var ports = event.ports || [];
        var found = false;
        for (var i = 0; i < ports.length; i++) {
            if (ports[i].symbol == 'noise_mods') {
                locked(ports[i].value);
                found = true;
            }
        }
        if (!found) {
            locked(0);
        }
    } else if (event.type == 'change' && event.symbol == 'noise_mods') {
        locked(event.value);
    }
}
