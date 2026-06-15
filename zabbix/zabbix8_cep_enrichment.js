// zabbix8_cep_enrichment.js
//
// Example custom-logic snippet for a Zabbix 8.0 native CEP rule
// (Data collection > Event processing). It calls the sidecar /classify endpoint
// to add topology-derived root-cause tags to an event, then a *native* Zabbix
// CEP rule does the actual symptom suppression based on those tags.
//
// Division of labour in the post-8.0 architecture:
//   Zabbix 8.0 CEP : windows, dedup, cause/symptom suppression, severity, lifecycle
//   sidecar        : the one thing Zabbix can't derive itself — WHO is a symptom
//                    of WHOM, computed from the Nautobot topology graph
//
// NOTE: Zabbix 8.0 is in alpha at time of writing; the exact CEP rule JS API and
// how the active-problem set is exposed to a rule may change before GA. Treat the
// `value`/context handling below as illustrative and adapt to the shipped API.

var SIDECAR = 'http://cep-sidecar:8080/classify';

try {
    // `value` is the rule context Zabbix passes in; we only need the host.
    // The sidecar already knows what's currently down (fed by the webhook media
    // type on every problem), so we don't assemble the down-set here.
    var ctx = JSON.parse(value);
    var device = ctx.host;                 // {HOST.HOST}

    var req = new HttpRequest();
    req.addHeader('Content-Type: application/json');
    var resp = req.post(SIDECAR, JSON.stringify({ device: device }));

    if (req.getStatus() !== 200) {
        Zabbix.log(3, '[cep] classify HTTP ' + req.getStatus());
        return JSON.stringify({ tags: [] });   // fail open: change nothing
    }

    var r = JSON.parse(resp);
    // Return the tags for Zabbix to attach. A separate native CEP rule then says:
    //   IF event has tag cep_role=symptom  ->  mark as symptom / suppress
    //   (Zabbix links it to the cause event carrying cep_role=cause)
    return JSON.stringify({ tags: r.tags });

} catch (e) {
    Zabbix.log(3, '[cep] enrichment error: ' + e);
    return JSON.stringify({ tags: [] });       // never block event processing
}
