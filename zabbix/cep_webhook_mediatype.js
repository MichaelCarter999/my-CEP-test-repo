// Zabbix webhook media type script: forwards problems to the CEP sidecar.
// Configure in Zabbix: Alerts > Media types > Create > Webhook.
// Parameters to add:
//   sidecar_url = http://cep-sidecar:8080/events
//   device      = {HOST.HOST}
//   kind        = {EVENT.NAME}      (map your trigger names to NODE_DOWN/UNREACHABLE/IF_FLAP)
//   severity    = {EVENT.SEVERITY}
//   event_value = {EVENT.VALUE}     (1 = problem, 0 = recovery)
// Then attach this media to a user and an action so every problem is POSTed.
try {
    var p = JSON.parse(value);
    // Prefer an explicit cep_kind tag (set by the SNMP-trap triggers in
    // trapsim/zabbix-path, or by the Zabbix 8.0 enrichment rule). Fall back to
    // classifying the event name when no tag is present.
    var kind = null;
    if (p.cep_kind && p.cep_kind.indexOf('{') !== 0) {   // tag macro expanded
        kind = p.cep_kind;
    } else {
        var name = (p.kind || '').toLowerCase();
        kind = 'UNREACHABLE';
        if (name.indexOf('unavailable') >= 0 || name.indexOf('down') >= 0 ||
            name.indexOf('no snmp') >= 0 || name.indexOf('icmp') >= 0) kind = 'NODE_DOWN';
        if (name.indexOf('flap') >= 0 || name.indexOf('link') >= 0) kind = 'IF_FLAP';
    }

    var payload = JSON.stringify({
        device: p.device,
        kind: p.event_value === '0' ? 'CLEAR' : kind,
        severity: p.severity || 'high',
        source: 'zabbix',
        ts: Math.floor(Date.now() / 1000)
    });

    var req = new HttpRequest();
    req.addHeader('Content-Type: application/json');
    var resp = req.post(p.sidecar_url, payload);
    if (req.getStatus() < 200 || req.getStatus() >= 300) {
        throw 'sidecar returned ' + req.getStatus() + ': ' + resp;
    }
    return 'OK';
} catch (e) {
    Zabbix.log(3, '[cep webhook] ' + e);
    throw 'CEP webhook failed: ' + e;
}
