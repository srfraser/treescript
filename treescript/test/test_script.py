import json
import mock
import os
import pytest

import scriptworker.client
from scriptworker.context import Context
from scriptworker.exceptions import ScriptWorkerTaskException, ScriptWorkerException
from unittest.mock import MagicMock

from treescript.test import noop_async, noop_sync, read_file, tmpdir, BASE_DIR
import treescript.script as script

assert tmpdir  # silence flake8

# helper constants, fixtures, functions {{{1
EXAMPLE_CONFIG = os.path.join(BASE_DIR, 'config_example.json')


@pytest.fixture(scope='function')
def context():
    return Context()


def get_conf_file(tmpdir, **kwargs):
    conf = json.loads(read_file(EXAMPLE_CONFIG))
    conf.update(kwargs)
    conf['work_dir'] = os.path.join(tmpdir, 'work')
    conf['artifact_dir'] = os.path.join(tmpdir, 'artifact')
    path = os.path.join(tmpdir, "new_config.json")
    with open(path, "w") as fh:
        json.dump(conf, fh)
    return path


async def die_async(*args, **kwargs):
    raise ScriptWorkerTaskException("Expected exception.")


# async_main {{{1
@pytest.mark.asyncio
@pytest.mark.parametrize(
    'robustcheckout_works,raises,actions',
    ((
        False, ScriptWorkerException, ["foo:bar:some_action"]
    ), (
        True, None, ["foo:bar:some_action"]
    ), (
        True, None, None
    ))
)
async def test_async_main(tmpdir, mocker, robustcheckout_works, raises, actions):

    async def fake_validate_robustcheckout(_):
        return robustcheckout_works

    def action_fun(*args, **kwargs):
        return actions

    mocker.patch.object(scriptworker.client, 'get_task', new=noop_sync)
    mocker.patch.object(script, 'task_action_types', new=action_fun)
    mocker.patch.object(script, 'validate_robustcheckout_works', new=fake_validate_robustcheckout)
    mocker.patch.object(script, 'log_mercurial_version', new=noop_async)
    mocker.patch.object(script, 'checkout_repo', new=noop_async)
    mocker.patch.object(script, 'do_actions', new=noop_async)
    context = mock.MagicMock()
    if raises:
        with pytest.raises(raises):
            await script.async_main(context)
    else:
        await script.async_main(context)


# get_default_config {{{1
def test_get_default_config():
    parent_dir = os.path.dirname(os.getcwd())
    c = script.get_default_config()
    assert c['work_dir'] == os.path.join(parent_dir, 'work_dir')


# do_actions {{{1
@pytest.mark.asyncio
@pytest.mark.parametrize(
    'push_scope,dry_run,push_expect_called,verify_expect_called',
    (
        (['push'], True, False, False),
        (['push'], False, True, False),
        (['push', 'verify_bump'], True, False, False),
        (['push', 'verify_bump'], False, True, True),
        ([], False, False, False),
        ([], True, False, False),
    )
)
async def test_do_actions(mocker, context, push_scope, dry_run, push_expect_called, verify_expect_called):
    actions = ["tagging", "version_bump"]
    actions += push_scope
    called_tag = [False]
    called_bump = [False]
    called_push = [False]
    called_checkout = [False]
    called_verify = [False]

    async def mocked_tag(*args, **kwargs):
        called_tag[0] = True

    async def mocked_bump(*args, **kwargs):
        called_bump[0] = True

    async def mocked_push(*args, **kwargs):
        called_push[0] = True

    async def mocked_checkout_repo(context, directory):
        called_checkout[0] = True

    async def mocked_verify(*args, **kwargs):
        called_verify[0] = True

    mocker.patch.object(script, 'do_tagging', new=mocked_tag)
    mocker.patch.object(script, 'bump_version', new=mocked_bump)
    mocker.patch.object(script, 'push', new=mocked_push)
    mocker.patch.object(script, 'checkout_repo', new=mocked_checkout_repo)
    mocker.patch.object(script, 'verify_bump', new=mocked_verify)
    mocker.patch.object(script, 'log_outgoing', new=noop_async)
    mocker.patch.object(script, 'is_dry_run').return_value = dry_run
    await script.do_actions(context, actions, directory='/some/folder/here')
    assert called_tag[0]
    assert called_bump[0]
    assert called_push[0] is push_expect_called
    assert called_verify[0] is verify_expect_called


@pytest.mark.asyncio
async def test_do_actions_unknown(mocker, context):
    actions = ["foo:bar:unknown"]
    called_tag = [False]
    called_bump = [False]

    async def mocked_tag(*args, **kwargs):
        called_tag[0] = True

    async def mocked_bump(*args, **kwargs):
        called_bump[0] = True

    mocker.patch.object(script, 'do_tagging', new=mocked_tag)
    mocker.patch.object(script, 'bump_version', new=mocked_bump)
    mocker.patch.object(script, 'log_outgoing', new=noop_async)
    with pytest.raises(NotImplementedError):
        await script.do_actions(context, actions, directory='/some/folder/here')
    assert called_tag[0] is False
    assert called_bump[0] is False


def test_main(monkeypatch):
    sync_main_mock = MagicMock()
    monkeypatch.setattr(scriptworker.client, 'sync_main', sync_main_mock)
    script.main()
    sync_main_mock.asset_called_once_with(script.async_main, default_config=script.get_default_config())
