from __future__ import absolute_import
from __future__ import unicode_literals

from subprocess import PIPE
from subprocess import Popen
from time import sleep

import pytest
from testing import norm
from testing.subprocess import assert_command
from testing.subprocess import show_both


@pytest.mark.parametrize('service_name', ['slow-shutdown'])
@pytest.mark.usefixtures('in_example_dir')
def it_is_disallowed():
    assert_command(
        ('pgctl-2015', 'start'),
        '',
        '''\
[pgctl] Starting: sweet
[pgctl] Started: sweet
''',
        0,
    )

    first = Popen(('pgctl-2015', 'restart'), stdout=PIPE, stderr=PIPE)

    # slow-shutdown takes two seconds to shut down; aim for the middle:
    sleep(1)

    second = Popen(('pgctl-2015', 'restart'), stdout=PIPE, stderr=PIPE)

    first_stdout, first_stderr = first.communicate()
    show_both(first_stdout, first_stderr)
    assert norm.pgctl(first_stderr) == '''\
[pgctl] Stopping: sweet
[pgctl] ERROR: service 'sweet' failed to stop after {TIME} seconds, its status is ready (pid {PID}) {TIME} seconds
==> playground/sweet/log <==
{TIMESTAMP} sweet
{TIMESTAMP} sweet_error
[pgctl] ERROR: Some services failed to stop: sweet
'''
    assert first_stdout == ''
    assert first.returncode == 1

    second_stdout, second_stderr = second.communicate()
    show_both(second_stdout, second_stderr)
    assert second_stderr == '[pgctl] ERROR: another pgctl instance is already managing this playground.\n'
    assert second_stdout == ''
    assert second.returncode == 1
