import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from datetime import datetime
from zoneinfo import ZoneInfo

import nintendo


class FakeBackend:
    def __init__(self):
        self.reads = self.grants = self.cancels = self.restores = self.closed = 0
        self.confirms = 0
        self.confirm_mode = 'success'
        self.confirm_to = '21:20'
        self.read_after_update = None
        self.extra = 0
        self.mode = 'success'
        self.read_error = None
        self.restore_error = None
        self.available = True
        self.complete_on = None
        self.device = {
            'id': 'ABC', 'key': 'nintendo:ABC', 'name': 'Switch de Martín', 'model': 'Switch',
            'used_minutes': 60, 'remaining_minutes': 0, 'limit_minutes': 60,
            'extra_minutes': 0, 'bedtime': '21:00', 'forced_termination': True,
            'last_sync': 1700000000, 'console_sync_pending': False,
            'available': True, 'can_grant': True,
            'base_bedtime': '21:00', 'effective_bedtime': '21:00',
            'daily_extra_minutes': 0, 'bedtime_extra_minutes': 0,
            'restrictions_suspended': False,
        }

    async def begin_login(self):
        self.begin_on = asyncio.get_running_loop()
        return 'https://accounts.nintendo.com/connect/1.0.0/authorize?' + urlencode({
            'state': 'oauth-state', 'redirect_uri': 'npf54789bef://auth',
            'session_token_code_challenge': 'verifier-challenge',
        })

    async def complete_login(self, response_url, timezone):
        self.complete_on = asyncio.get_running_loop()
        return {'session_token': 'secret-session-token', 'account_id': 'private-account', 'timezone': timezone}

    async def restore(self, credentials):
        self.restores += 1
        if self.restore_error:
            raise self.restore_error

    async def snapshot(self):
        self.reads += 1
        if self.read_error:
            raise self.read_error
        device = copy.deepcopy(self.device)
        device['extra_minutes'] = self.extra
        device['daily_extra_minutes'] = self.extra
        device['available'] = self.available
        return [device]

    async def grant(self, device_id, minutes):
        self.grants += 1
        if self.mode == 'next_step':
            if self.read_after_update:
                self.read_after_update()
            return {'json': {'status': 'TO_ADDED', 'nextStepDetail': {'estimatedBedtimeChanges': {
                'from': {'hour': 21, 'minute': 0},
                'to': {'hour': int(self.confirm_to[:2]), 'minute': int(self.confirm_to[3:])},
            }}}}
        if self.mode == 'rejected':
            return {'json': {'status': 'OVERTIME_ERROR'}}
        if self.mode == 'unknown':
            self.extra += minutes
            return {'json': {'status': 'UNKNOWN'}}
        if self.mode == 'delayed':
            return {'json': {'status': 'SUCCESS'}}
        self.extra += minutes
        if self.mode == 'timeout':
            raise TimeoutError('secret-token-in-unsafe-sdk-error')
        return {'json': {'status': 'TO_ADDED'}}

    async def confirm(self, device_id, minutes):
        self.confirms += 1
        if self.confirm_mode != 'delayed':
            self.extra += minutes
            self.device['bedtime'] = self.device['effective_bedtime'] = self.confirm_to
        if self.confirm_mode == 'timeout':
            raise TimeoutError('private-confirm-token')
        if self.confirm_mode == 'conflict':
            self.device['effective_bedtime'] = self.device['bedtime'] = '22:00'
        return {'json': {'status': 'SUCCESS'}}

    async def cancel(self, device_id):
        self.cancels += 1
        self.extra = 0
        self.device['bedtime'] = self.device['effective_bedtime'] = self.device['base_bedtime']
        return {'json': {'status': 'TO_CANCELED'}}

    async def close(self):
        self.closed += 1


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.backend = FakeBackend()
        self.now = 1788516000.0
        self.connector = self.make_connector()

    def make_connector(self):
        return nintendo.Connector(self.folder.name, backend_factory=lambda: self.backend, clock=lambda: self.now)

    def tearDown(self):
        self.connector.close()
        self.folder.cleanup()

    def connect(self):
        state = self.connector.begin_login()
        return self.connector.complete_login(state['state_id'], 'npf54789bef://auth#state=oauth-state&session_token_code=secret-code')

    def grant(self, operation_id='direct:1:example', minutes=20, extend_bedtime=False):
        return self.connector.grant('nintendo:ABC', minutes, operation_id, extend_bedtime=extend_bedtime)

    def test_not_configured_without_sdk(self):
        self.assertFalse(self.connector.public_config()['configured'])
        self.assertEqual(self.connector.devices()['devices'], [])
        with self.assertRaises(nintendo.NintendoError):
            self.grant()

    def test_interactive_verifier_keeps_same_backend_and_loop(self):
        data = self.connect()
        self.assertTrue(data['configured'])
        self.assertIs(self.backend.begin_on, self.backend.complete_on)
        self.assertEqual(self.backend.restores, 0)
        self.assertEqual(data['devices'][0]['name'], 'Switch de Martín')
        self.assertNotIn('secret', json.dumps(data))
        self.assertNotIn('private-account', json.dumps(self.connector.public_config()))

    def test_credentials_atomic_private_and_restored_after_restart(self):
        self.connect()
        path = Path(self.folder.name) / 'nintendo.json'
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text())['session_token'], 'secret-session-token')
        self.assertEqual(list(Path(self.folder.name).glob('.nintendo-*')), [])
        self.connector.close()
        self.connector = self.make_connector()
        self.assertTrue(self.connector.devices()['configured'])
        self.assertEqual(self.backend.restores, 1)

    def test_oauth_state_scheme_and_expiration_checked_before_auth(self):
        state = self.connector.begin_login()
        for response in ('npf54789bef://auth#state=wrong&session_token_code=a',
                         'https://attacker.test/#state=oauth-state&session_token_code=a',
                         'npf54789bef://auth#session_token_code=a'):
            with self.assertRaises(nintendo.NintendoError):
                self.connector.complete_login(state['state_id'], response)
        self.assertIsNone(self.backend.complete_on)
        self.now += 601
        with self.assertRaisesRegex(nintendo.NintendoError, 'caducado'):
            self.connector.complete_login(state['state_id'], 'npf54789bef://auth#state=oauth-state&session_token_code=a')
        self.assertGreater(self.backend.closed, 0)

    def test_timezone_checked_and_login_state_used_once(self):
        state = self.connector.begin_login()
        response = 'npf54789bef://auth#state=oauth-state&session_token_code=a'
        with self.assertRaises(nintendo.NintendoError):
            self.connector.complete_login(state['state_id'], response, 'invalid/timezone')
        self.connector.complete_login(state['state_id'], response)
        with self.assertRaises(nintendo.NintendoError):
            self.connector.complete_login(state['state_id'], response)

    def test_confirmed_grant_idempotent_and_persisted(self):
        self.connect()
        result = self.grant()
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(self.grant()['status'], 'confirmed')
        self.assertEqual(self.backend.grants, 1)
        self.assertEqual(self.backend.extra, 20)
        self.connector.close()
        self.connector = self.make_connector()
        self.assertEqual(self.grant()['status'], 'confirmed')
        self.assertEqual(self.backend.grants, 1)
        self.assertEqual(self.connector.devices()['devices'][0]['last_operation']['operation_id'], result['operation_id'])

    def test_duplicate_operation_cannot_change_target_or_duration(self):
        self.connect()
        self.grant()
        with self.assertRaises(ValueError):
            self.grant(minutes=10)
        with self.assertRaises(ValueError):
            self.connector.grant('nintendo:OTHER', 20, 'direct:1:example')
        self.assertEqual(self.backend.grants, 1)

    def test_next_step_refuses_bedtime_confirmation(self):
        self.connect()
        self.backend.mode = 'next_step'
        result = self.grant()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('descanso', result['message'])
        self.assertEqual(self.backend.extra, 0)
        self.assertEqual(self.grant()['status'], 'failed')
        self.assertEqual(self.backend.grants, 1)
        self.assertEqual(self.backend.confirms, 0)

    def test_explicit_extension_verified_in_both_dimensions_and_persisted(self):
        self.connect()
        self.backend.mode = 'next_step'
        result = self.grant(extend_bedtime=True)
        self.assertEqual(result['status'], 'confirmed')
        self.assertTrue(result['extend_bedtime'])
        self.assertEqual(result['stage'], 'confirm_sent')
        self.assertEqual(self.backend.confirms, 1)
        self.assertEqual(self.backend.extra, 20)
        self.assertEqual(self.backend.device['bedtime'], '21:20')
        self.connector.close()
        self.connector = self.make_connector()
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'confirmed')
        self.assertEqual(self.backend.confirms, 1)
        with self.assertRaises(ValueError):
            self.grant(extend_bedtime=False)

    def test_bedtime_only_extension_does_not_require_extra_daily_delta(self):
        self.connect()
        self.backend.extra = 40
        self.backend.device['used_minutes'] = 40
        self.backend.mode = 'next_step'
        async def bedtime_only(device_id, minutes):
            self.backend.confirms += 1
            self.backend.device['effective_bedtime'] = self.backend.device['bedtime'] = '21:20'
            return {'json': {'status': 'TO_ADDED'}}
        self.backend.confirm = bedtime_only
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'confirmed')
        self.assertEqual(self.backend.extra, 40)
        self.assertEqual(self.backend.device['effective_bedtime'], '21:20')

    def test_wrong_base_limit_readback_never_claims_confirmed(self):
        self.connect()
        original = self.backend.grant
        async def conflict(device_id, minutes):
            result = await original(device_id, minutes)
            self.backend.device['limit_minutes'] = 120
            return result
        self.backend.grant = conflict
        self.assertEqual(self.grant()['status'], 'failed')

    def test_ledger_survives_crash_before_remote_call_without_resending(self):
        self.connect()
        device = self.connector.validate('nintendo:ABC', 20)
        self.connector._insert('direct:1:example', device, 20, 'grant', extend_bedtime=True)
        self.connector.close()
        self.connector = self.make_connector()
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'pending')
        self.assertEqual(self.backend.grants, 0)

    def test_timestamp_units_normalized_without_exposing_invalid_dates(self):
        self.connect()
        self.backend.device['last_sync'] = 1700000000000
        self.assertEqual(self.connector.devices(force=True)['devices'][0]['last_sync'], 1700000000)
        self.backend.device['last_sync'] = float('nan')
        self.assertIsNone(self.connector.devices(force=True)['devices'][0]['last_sync'])

    def test_optional_extension_does_not_confirm_when_not_needed(self):
        self.connect()
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'confirmed')
        self.assertEqual(self.backend.confirms, 0)
        self.assertEqual(self.backend.device['bedtime'], '21:00')

    def test_small_overrun_does_not_prevent_a_new_daily_bonus(self):
        self.connect()
        self.backend.device['used_minutes'] = 61
        self.assertEqual(self.grant()['status'], 'confirmed')
        self.assertEqual(self.backend.extra, 20)

    def test_bonus_that_cannot_cover_overrun_is_rejected_before_write(self):
        self.connect()
        self.backend.device['used_minutes'] = 80
        with self.assertRaises(nintendo.NintendoError):
            self.grant()
        self.assertEqual(self.backend.grants, 0)

    def test_approved_bedtime_extension_after_curfew_is_limited_from_now(self):
        self.connect()
        self.now = datetime(2026, 9, 4, 21, 50, tzinfo=ZoneInfo('Europe/Madrid')).timestamp()
        self.backend.mode = 'next_step'
        self.backend.confirm_to = '22:10'
        async def confirm(device_id, minutes):
            self.backend.confirms += 1
            self.backend.extra = 70  # SDK exposes max(daily bonus, bedtime shift).
            self.backend.device['bedtime'] = self.backend.device['effective_bedtime'] = '22:10'
            return {'json': {'status': 'TO_ADDED'}}
        self.backend.confirm = confirm
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'confirmed')
        self.assertEqual(self.backend.confirms, 1)

    def test_late_proposal_exceeding_approved_play_window_is_not_confirmed(self):
        self.connect()
        self.now = datetime(2026, 9, 4, 21, 50, tzinfo=ZoneInfo('Europe/Madrid')).timestamp()
        self.backend.mode = 'next_step'
        self.backend.confirm_to = '22:20'
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'failed')
        self.assertEqual(self.backend.confirms, 0)

    def test_unknown_confirmation_outcome_never_retries(self):
        self.connect()
        self.backend.mode = 'next_step'
        self.backend.confirm_mode = 'timeout'
        result = self.grant(extend_bedtime=True)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['stage'], 'confirm_sent')
        self.assertNotIn('private-confirm', result['message'])
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'pending')
        self.connector.close()
        self.connector = self.make_connector()
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'pending')
        self.assertEqual(self.backend.grants, 1)
        self.assertEqual(self.backend.confirms, 1)

    def test_delayed_bedtime_confirmation_reads_only(self):
        self.connect()
        self.backend.mode = 'next_step'
        self.backend.confirm_mode = 'delayed'
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'pending')
        self.backend.extra = 20
        self.backend.device['effective_bedtime'] = self.backend.device['bedtime'] = '21:20'
        self.connector.refresh_pending()
        self.assertEqual(self.connector.operation_status('direct:1:example')['status'], 'confirmed')
        self.assertEqual(self.backend.confirms, 1)

    def test_changed_settings_between_update_and_confirm_are_not_confirmed(self):
        self.connect()
        self.backend.mode = 'next_step'
        self.backend.read_after_update = lambda: self.backend.device.update(limit_minutes=30)
        result = self.grant(extend_bedtime=True)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.backend.confirms, 0)

    def test_incomplete_or_excessive_bedtime_estimate_is_never_confirmed(self):
        self.connect()
        self.backend.mode = 'next_step'
        self.backend.confirm_to = '22:00'
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'failed')
        self.assertEqual(self.backend.confirms, 0)

    def test_wrong_readback_bedtime_does_not_claim_confirmed(self):
        self.connect()
        self.backend.mode = 'next_step'
        self.backend.confirm_mode = 'conflict'
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'pending')
        self.assertEqual(self.backend.confirms, 1)

    def test_suspended_or_alarm_only_console_never_receives_a_grant(self):
        self.connect()
        self.backend.device['restrictions_suspended'] = True
        with self.assertRaises(nintendo.NintendoError):
            self.grant(extend_bedtime=True)
        self.backend.device['restrictions_suspended'] = False
        self.backend.device['forced_termination'] = False
        with self.assertRaises(nintendo.NintendoError):
            self.grant()
        self.assertEqual(self.backend.grants, 0)

    def test_nighttime_request_validation_does_not_mutate_or_reject_just_time(self):
        self.connect()
        self.backend.device['bedtime_remaining_minutes'] = 0
        self.assertEqual(self.connector.validate('nintendo:ABC', 20)['key'], 'nintendo:ABC')
        with self.assertRaises(nintendo.NintendoError):
            self.grant()
        self.assertEqual(self.backend.grants, 0)

    def test_bedtime_flag_strict_boolean(self):
        self.connect()
        for value in (1, 0, None, 'true'):
            with self.assertRaises(ValueError):
                self.grant(extend_bedtime=value)
        self.assertEqual(self.backend.grants, 0)

    def test_login_completion_cannot_replace_account_with_new_pending_operation(self):
        self.connect()
        login = self.connector.begin_login()
        self.backend.mode = 'timeout'
        self.grant()
        with self.assertRaises(nintendo.NintendoError):
            self.connector.complete_login(login['state_id'], 'npf54789bef://auth#state=oauth-state&session_token_code=other')

    def test_known_rejection_is_failed(self):
        self.connect()
        self.backend.mode = 'rejected'
        self.assertEqual(self.grant()['status'], 'failed')
        self.assertEqual(self.backend.extra, 0)

    def test_delayed_readback_reconciles_without_resending(self):
        self.connect()
        self.backend.mode = 'delayed'
        self.assertEqual(self.grant()['status'], 'pending')
        with self.assertRaisesRegex(nintendo.NintendoError, 'pendiente'):
            self.grant('direct:1:other')
        self.backend.extra = 20
        self.connector.refresh_pending()
        self.assertEqual(self.connector.operation_status('direct:1:example')['status'], 'confirmed')
        self.assertEqual(self.backend.grants, 1)

    def test_timeout_never_retries_even_if_remote_write_was_applied(self):
        self.connect()
        self.backend.mode = 'timeout'
        result = self.grant()
        self.assertEqual(result['status'], 'pending')
        self.assertNotIn('secret-token', result['message'])
        self.assertEqual(self.backend.extra, 20)
        self.assertEqual(self.grant()['status'], 'pending')
        device = self.connector.devices(force=True)['devices'][0]
        self.assertFalse(device['can_grant'])
        self.assertFalse(device['can_cancel'])
        self.assertEqual(device['pending_operation']['operation_id'], result['operation_id'])
        self.connector.close()
        self.connector = self.make_connector()
        self.assertEqual(self.grant()['status'], 'pending')
        with self.assertRaises(nintendo.NintendoError):
            self.grant('direct:1:new')
        self.assertEqual(self.backend.grants, 1)

    def test_unknown_success_shape_not_trusted(self):
        self.connect()
        self.backend.mode = 'unknown'
        self.assertEqual(self.grant()['status'], 'pending')
        self.connector.devices(force=True)
        self.assertEqual(self.connector.operation_status('direct:1:example')['status'], 'pending')

    def test_invalid_scope_duration_and_unlimited_never_mutate(self):
        self.connect()
        for minutes in (0, -1, 4, 31, 60, 10.0, True, '20'):
            with self.assertRaises(ValueError):
                self.connector.validate('nintendo:ABC', minutes)
        with self.assertRaises(ValueError):
            self.connector.validate('nintendo:MISSING', 20)
        self.backend.extra = -1
        with self.assertRaises(nintendo.NintendoError):
            self.grant()
        self.assertEqual(self.backend.grants, 0)

    def test_failed_fresh_read_prevents_writes_and_disables_stale_cards(self):
        self.connect()
        self.backend.read_error = RuntimeError('sensitive-cookie-token')
        result = self.connector.devices(force=True)
        self.assertNotIn('sensitive', json.dumps(result))
        self.assertFalse(result['devices'][0]['available'])
        self.assertFalse(self.connector.devices()['devices'][0]['can_grant'])
        with self.assertRaises(nintendo.NintendoError):
            self.grant()
        self.assertEqual(self.backend.grants, 0)
        self.assertIsNone(self.connector.operation_status('direct:1:example'))

    def test_read_cache_20_seconds(self):
        self.connect()
        first = self.backend.reads
        self.connector.devices()
        self.connector.devices()
        self.assertEqual(self.backend.reads, first)
        self.now += 21
        self.connector.devices()
        self.assertEqual(self.backend.reads, first + 1)

    def test_safe_cancel_own_single_grant_is_durable(self):
        self.connect()
        self.grant()
        self.assertTrue(self.connector.devices()['devices'][0]['can_cancel'])
        result = self.connector.cancel('nintendo:ABC', 'cancel:1:example')
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(self.backend.extra, 0)
        self.assertTrue(self.connector.operation_status('direct:1:example')['cancelled'])
        self.assertEqual(self.connector.cancel('nintendo:ABC', 'cancel:1:example')['status'], 'confirmed')
        self.assertEqual(self.backend.cancels, 1)

    def test_cancel_never_removes_time_granted_outside_app(self):
        self.connect()
        self.backend.extra = 10
        self.grant()
        self.assertFalse(self.connector.devices()['devices'][0]['can_cancel'])
        with self.assertRaises(nintendo.NintendoError):
            self.connector.cancel('nintendo:ABC', 'cancel:1:example')
        self.assertEqual(self.backend.cancels, 0)

    def test_cancel_rechecks_remote_delta_even_if_button_was_visible(self):
        self.connect()
        self.grant()
        self.assertTrue(self.connector.devices()['devices'][0]['can_cancel'])
        self.backend.extra += 5
        with self.assertRaises(nintendo.NintendoError):
            self.connector.cancel('nintendo:ABC', 'cancel:1:example')
        self.assertEqual(self.backend.cancels, 0)

    def test_disconnect_blocks_pending_but_next_day_expires(self):
        self.connect()
        self.backend.mode = 'timeout'
        self.grant()
        with self.assertRaises(nintendo.NintendoError):
            self.connector.disconnect()
        with self.assertRaises(nintendo.NintendoError):
            self.connector.begin_login()
        self.now += 86400
        self.assertFalse(self.connector.disconnect()['configured'])
        self.assertFalse((Path(self.folder.name) / 'nintendo.json').exists())
        self.assertEqual(self.connector.operation_status('direct:1:example')['status'], 'failed')

    def test_parallel_duplicate_grants_send_once(self):
        self.connect()
        results, errors = [], []
        def run():
            try:
                results.append(self.grant())
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(result['status'] == 'confirmed' for result in results))
        self.assertEqual(self.backend.grants, 1)

    def test_ledger_committed_before_remote_write(self):
        self.connect()
        original = self.backend.grant
        async def inspect(device_id, minutes):
            self.assertEqual(self.connector._db.execute('SELECT status FROM operations').fetchone()[0], 'pending')
            return await original(device_id, minutes)
        self.backend.grant = inspect
        self.assertEqual(self.grant()['status'], 'confirmed')

    def test_bedtime_flag_and_stage_committed_before_confirm(self):
        self.connect()
        self.backend.mode = 'next_step'
        original = self.backend.confirm
        async def inspect(device_id, minutes):
            row = self.connector._db.execute('SELECT extend_bedtime,stage,ack FROM operations').fetchone()
            self.assertEqual(tuple(row), (1, 'confirm_sent', 0))
            return await original(device_id, minutes)
        self.backend.confirm = inspect
        self.assertEqual(self.grant(extend_bedtime=True)['status'], 'confirmed')


class SDKAdapterTests(unittest.TestCase):
    def test_additional_time_api_never_calls_automatic_bedtime_method(self):
        class Api:
            calls = []
            async def async_update_extra_playing_time(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return {'json': {'status': 'SUCCESS', 'nextStepDetail': {'bedtime': True}}}
            async def async_confirm_extra_playing_time(self, *args, **kwargs):
                raise AssertionError('Must never confirm bedtime expansion')
        backend = nintendo._NintendoBackend()
        backend.api = Api()
        asyncio.run(backend.grant('ABC', 20))
        asyncio.run(backend.cancel('ABC'))
        self.assertEqual(backend.api.calls, [(('ABC', 20), {}), (('ABC',), {'cancel': True})])

    def test_explicit_device_update_errors_are_not_swallowed(self):
        class Api:
            async def async_get_account_devices(self):
                return {'json': {'ownedDevices': [{'deviceId': 'ABC'}]}}
        class Device:
            @classmethod
            def from_device_response(cls, raw, api):
                return cls()
            async def update(self, now):
                raise TimeoutError('unsafe-HTTP-body')
        backend = nintendo._NintendoBackend()
        backend.api, backend._Device = Api(), Device
        with self.assertRaises(TimeoutError):
            asyncio.run(backend.snapshot())

    def test_real_sdk_bedtime_only_payload_and_suspended_restrictions(self):
        try:
            from pynintendoparental.device import Device
        except ImportError:
            self.skipTest('Pinned SDK is installed in Docker and CI')
        class Api:
            _tz = 'Europe/Madrid'
            visibility = 'VISIBLE'
            async def async_get_account_devices(self):
                return {'json': {'ownedDevices': [{'deviceId': 'ABC', 'label': 'Switch de Martín',
                    'parentalControlSettingState': {'updatedAt': 1700000000000}}]}}
            def owned(self):
                return {'deviceId': 'ABC', 'device': {'platformGeneration': 'P00',
                    'alarmSetting': {'visibility': self.visibility},
                    'synchronizedParentalControlSetting': {'synchronizedAt': 1700000000000},
                    'extraPlayingTime': {'bedtime': {'endTime': {'hour': 21, 'minute': 20}},
                        'inOneDay': None, 'expiresAt': 1900000000000}},
                    'parentalControlSettingState': {'synchronizationStatus': 'SYNCHRONIZED'}}
            async def async_get_account_device(self, device_id):
                return {'json': {'ownedDevice': self.owned()}}
            async def async_get_device_daily_summaries(self, device_id):
                return {'json': {'dailySummaries': [{'date': datetime.now(ZoneInfo(self._tz)).strftime('%Y-%m-%d'), 'playingTime': 60}]}}
            async def async_get_device_monthly_summaries(self, device_id):
                return {'json': {'available': []}}
            async def async_get_device_parental_control_setting(self, device_id):
                return {'json': {'parentalControlSetting': {
                    'playTimerRegulations': {'restrictionMode': 'FORCED_TERMINATION', 'timerMode': 'DAILY',
                        'dailyRegulations': {'timeToPlayInOneDay': {'enabled': True, 'limitTime': 60},
                            'bedtime': {'enabled': True, 'endingTime': {'hour': 21, 'minute': 0},
                                'startingTime': {'hour': 6, 'minute': 0}}}},
                    'whitelistedApplicationList': []}, 'ownedDevice': self.owned()}}
        backend = nintendo._NintendoBackend()
        backend.api, backend._Device = Api(), Device
        snapshot = asyncio.run(backend.snapshot())[0]
        self.assertEqual(snapshot['daily_extra_minutes'], 0)
        self.assertEqual(snapshot['bedtime_extra_minutes'], 20)
        self.assertEqual(snapshot['extra_minutes'], 20)
        self.assertEqual(snapshot['bedtime'], '21:20')
        self.assertEqual(snapshot['last_sync'], 1700000000)
        self.assertTrue(snapshot['can_grant'])
        backend.api.visibility = 'INVISIBLE'
        suspended = asyncio.run(backend.snapshot())[0]
        self.assertTrue(suspended['restrictions_suspended'])
        self.assertFalse(suspended['can_grant'])
        self.assertIsNone(suspended['remaining_minutes'])


if __name__ == '__main__':
    unittest.main()
