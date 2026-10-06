"""Recipient preferences for AdGuard alerts; never changes DNS restrictions."""
import copy, json, time
import auth

PROTECTIONS = ('@filtering', '@parental', '@safebrowsing', '@safesearch')
MODES = ('all', 'selected', 'none')



def defaults():
    return {'mode': 'all', 'services': [], 'protections': [], 'cooldown_minutes': 5, 'clients': {}}


def preferences(user, allowed=None):
    with auth.LOCK:
        row = auth.DB.execute('SELECT config,updated FROM notification_preferences WHERE user_id=?', (user['id'],)).fetchone()
    config = json.loads(row['config']) if row else defaults()
    if allowed is not None:
        config['clients'] = {name: value for name, value in config['clients'].items() if name in allowed}
    return {'preferences': config, 'updated': row['updated'] if row else 0}


def selection(value, catalog):
    if not isinstance(value, dict) or set(value) != {'mode', 'services', 'protections'}:
        raise ValueError('Selección de avisos inválida')
    if value['mode'] not in MODES:
        raise ValueError('Selecciona todos, algunos o ningún servicio')
    for key, allowed in (('services', catalog), ('protections', set(PROTECTIONS))):
        items = value[key]
        if not isinstance(items, list) or len(items) > len(allowed) or any(not isinstance(item, str) or item not in allowed for item in items):
            raise ValueError('Servicio o protección de avisos desconocidos')
    return {'mode': value['mode'], 'services': sorted(set(value['services'])), 'protections': sorted(set(value['protections']))}


def save(user, body, catalog, allowed):
    auth.require(user, 'admin', 'responsable')
    if not isinstance(body, dict) or set(body) != {'mode', 'services', 'protections', 'cooldown_minutes', 'clients'}:
        raise ValueError('Preferencias de avisos inválidas')
    cooldown = body['cooldown_minutes']
    if type(cooldown) is not int or not 5 <= cooldown <= 1440:
        raise ValueError('El intervalo entre avisos debe estar entre 5 y 1440 minutos')
    overrides = body['clients']
    if not isinstance(overrides, dict) or len(overrides) > len(allowed):
        raise ValueError('Clientes de avisos inválidos')
    normalized = selection({key: body[key] for key in ('mode', 'services', 'protections')}, catalog)
    normalized.update(cooldown_minutes=cooldown, clients={})
    for name, value in overrides.items():
        if not isinstance(name, str) or name not in allowed:
            raise auth.Forbidden('No puedes configurar avisos de ese cliente')
        normalized['clients'][name] = selection(value, catalog)
    with auth.LOCK:
        # Keep inaccessible overrides privately, so changing assignments does not expose/delete them.
        old = preferences(user)['preferences']
        preserved = {name: value for name, value in old['clients'].items() if name not in allowed}
        stored = copy.deepcopy(normalized)
        stored['clients'].update(preserved)
        auth.DB.execute('INSERT OR REPLACE INTO notification_preferences VALUES(?,?,?)', (user['id'], json.dumps(stored), time.time()))
        auth.DB.commit()
        auth.audit(user, 'notification_preferences', {'mode': normalized['mode'], 'clients': sorted(normalized['clients'])})
    return preferences(user, allowed)


def eligible(user, events, config, now=None):
    return evaluate(user,events,config,now)[0]


def evaluate(user, events, config, now=None):
    """Pure feed suitable for web and future external channels. No delivery claims."""
    if user['role'] not in ('admin', 'responsable'):
        return [], {'role':len(events)}
    now = time.time() if now is None else now
    preference = config['preferences']
    last = {}
    result = []
    reasons={}
    def excluded(reason): reasons[reason]=reasons.get(reason,0)+1
    for event in sorted(events, key=lambda item: (item['time'], item['id'])):
        if event['kind'] != 'blocked' or (user['role'] != 'admin' and event['client'] not in user['clients']):
            excluded('not_blocked_or_outside_scope')
            continue
        chosen = preference['clients'].get(event['client'], preference)
        service = event['service']
        selected = service in chosen['protections'] if service.startswith('@') else chosen['mode'] == 'all' or (chosen['mode'] == 'selected' and service in chosen['services'])
        if not selected or event['time'] <= config['updated']:
            excluded('service_not_selected' if not selected else 'before_preferences_changed')
            continue
        key = (event['client'], service)
        if event['time'] - last.get(key, float('-inf')) < preference['cooldown_minutes'] * 60:
            excluded('cooldown')
            continue
        last[key] = event['time']
        # Backfilled/history queries are activity, never new notifications.
        if now - 120 <= event['time'] <= now + 30:
            result.append(event)
        else: excluded('older_than_120_seconds' if event['time']<now-120 else 'future_timestamp')
    return result,reasons
