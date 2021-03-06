import pytest

from cloudatcost_ansible_module.cac_server import CACTemplate, get_server, CACServer, CacApiError
from cloudatcost_ansible_module import cac_server as cac_server
import json
from ansible.module_utils import basic
from ansible.module_utils._text import to_bytes
from mock import call

from tests.conftest import simulated_build


def set_module_args(args):
    args = json.dumps({'ANSIBLE_MODULE_ARGS': args})
    basic._ANSIBLE_ARGS = to_bytes(args)


class TestServerClass(object):
    def test_template_lookup(self, mock_cac_api):
        template = CACTemplate.get_template(mock_cac_api, '27')
        assert template.desc == "Ubuntu-14.04.1-LTS-64bit"

        template = CACTemplate.get_template(mock_cac_api, "Ubuntu-14.04.1-LTS-64bit")
        assert template.template_id == "27"

    def test_teamplate_lookup_accepts_instance_as_parameter(self, mock_cac_api):
        template = CACTemplate.get_template(mock_cac_api, '27')
        template2 = CACTemplate.get_template(mock_cac_api, template)
        assert template2 == template

    def test_get_nonexistent_server_returns_none(self, mock_cac_api):
        server = get_server(mock_cac_api, 000000000)
        assert server is None

    def test_server_repr_valid(self, mock_cac_api):
        server = get_server(mock_cac_api, server_id='123456789')
        assert (server.__repr__() == 'CACServer(api_account=test@user.com, sid=123456789, label=serverlabel)')

    def test_get_server_by_sid(self, mock_cac_api):
        server = get_server(mock_cac_api, server_id='123456789')
        assert (server['sid'] == '123456789')

    def test_get_server_by_label(self, mock_cac_api):
        server = get_server(mock_cac_api, label='serverlabel')
        assert (server['sid'] == '123456789')

    def test_get_server_by_servername(self, mock_cac_api):
        server = get_server(mock_cac_api, server_name='c123456789-cloudpro-123456789')
        assert (server['sid'] == '123456789')

    def test_edit_existing_server_label(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['label'] = 'test'
        assert server['label'] == 'test'

    def test_update_uneditable_raises_error(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        pytest.raises(KeyError, server.__setitem__, 'cpu', '16')

    def test_update_edit_calls_api(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['label'] = "testing"
        server.commit()
        assert call.rename_server(new_name='testing', server_id='123456789') in mock_cac_api.method_calls

    def test_update_rdns(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['rdns'] = "server.test.com"
        server.commit()
        assert call.change_hostname(new_hostname='server.test.com', server_id='123456789') in mock_cac_api.method_calls

    def test_update_mode(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['mode'] = "safe"
        server.commit()
        assert call.set_run_mode(run_mode='safe', server_id='123456789') in mock_cac_api.method_calls

    def test_power_off_state(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['status'] = "Powered Off"
        server.commit()
        assert call.power_off_server(server_id='123456789') in mock_cac_api.method_calls

    def test_power_on_state(self, mock_cac_api):
        server = get_server(mock_cac_api, label="poweredoff")
        server['status'] = "Powered On"
        server.commit()
        assert call.power_on_server(server_id='000000001') in mock_cac_api.method_calls

    def test_restarted_state(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['status'] = "Restarted"
        server.commit()
        assert call.reset_server(server_id='123456789') in mock_cac_api.method_calls

    def test_delete(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['status'] = "Deleted"
        server.commit()
        assert call.server_delete(server_id='123456789') in mock_cac_api.method_calls

    def test_change_everything(self, mock_cac_api):
        server = get_server(mock_cac_api, 123456789)
        server['label'] = "testing"
        server['rdns'] = "server.test.com"
        server['mode'] = "normal"
        server['status'] = "Restarted"
        server.commit()
        assert call.rename_server(new_name='testing', server_id='123456789') in mock_cac_api.method_calls
        assert call.change_hostname(new_hostname='server.test.com', server_id='123456789') in mock_cac_api.method_calls
        assert call.set_run_mode(run_mode='normal', server_id='123456789') in mock_cac_api.method_calls
        assert call.reset_server(server_id='123456789') in mock_cac_api.method_calls

    def test_server_build_failure(self, cac_api_fail_build):
        pytest.raises(CacApiError, CACServer.build_server, api=cac_api_fail_build, cpu=1, ram=1024, disk=10,
                      template=27, label='test')

    @pytest.mark.usefixtures('patch_sleep')
    def test_server_build_success(self, mock_cac_api):
        mock_cac_api.get_server_info.side_effect = simulated_build()
        server = CACServer.build_server(mock_cac_api, cpu=1, ram=1024, disk=10, template=27, label="buildtest")
        assert server
        assert call.server_build(1, 1024, 10, '27') in mock_cac_api.method_calls

    @pytest.mark.usefixtures('patch_sleep')
    def test_server_build_with_wait(self, mock_cac_api):
        mock_cac_api.get_server_info.side_effect = simulated_build()

        server = CACServer.build_server(mock_cac_api, cpu=1, ram=1024, disk=10, template=27, label='test', wait=True,
                                        wait_timeout=30)
        assert server
        assert call.server_build(1, 1024, 10, '27') in mock_cac_api.method_calls


class TestAnsibleModule(object):
    # This is a bit of a mess.  A lot of work required to mock objects to test building a server, since there are
    # state change dependencies.  Maybe refactor code, to make it easier to simulate?

    def test_module_deletes_server(self, capsys):
        set_module_args(dict(api_user="test@guy.com", api_key="secret", server_id=123456789, state='absent'))
        pytest.raises(SystemExit, cac_server.main)
        out, err = capsys.readouterr()
        output = json.loads(out)
        assert output['changed'] is True
        api = cac_server.get_api('', '')
        api.server_delete.assert_has_calls(
            [call.server_delete(server_id='123456789'), ],
            any_order=True)

    def test_module_updates_server_rdns(self, capsys, ):
        set_module_args(dict(api_user="test@guy.com", api_key="secret", server_id=123456789, fqdn="test.server.com",
                             state='present'))
        pytest.raises(SystemExit, cac_server.main)
        out, err = capsys.readouterr()
        output = json.loads(out)
        assert output['changed'] is True
        api = cac_server.get_api('', '')
        api.change_hostname.assert_has_calls(
            [call.change_hostname(new_hostname='test.server.com', server_id='123456789'), ],
            any_order=True)

    def test_module_updates_runmode(self, capsys):
        set_module_args(dict(api_user="test@guy.com", api_key="secret", server_id=123456789,
                             runmode="safe", state='present'))
        pytest.raises(SystemExit, cac_server.main)
        out, err = capsys.readouterr()
        output = json.loads(out)
        assert output['changed'] is True
        api = cac_server.get_api('', '')
        api.set_run_mode.assert_has_calls(
            [call.set_run_mode(run_mode='safe', server_id='123456789'), ], any_order=True)

    def test_module_updates_status(self, capsys):
        set_module_args(dict(api_user="test@guy.com", api_key="secret", server_id=123456789,
                             state='stopped'))
        pytest.raises(SystemExit, cac_server.main)
        out, err = capsys.readouterr()
        output = json.loads(out)
        assert output['changed'] is True
        api = cac_server.get_api('', '')
        api.power_off_server.assert_has_calls(
            [call.power_off_server(server_id='123456789'), ], any_order=True)

    def test_check_mode(self, capsys):
        set_module_args(dict(api_user="test@guy.com", api_key="secret", server_id=123456789,
                             state='stopped', _ansible_check_mode=True))
        pytest.raises(SystemExit, cac_server.main)
        out, err = capsys.readouterr()
        output = json.loads(out)
        assert output['changed'] is True
        api = cac_server.get_api('', '')
        assert call.power_off_server(server_id='123456789') not in api.mock_calls

