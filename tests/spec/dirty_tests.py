# pylint:disable=no-self-use, unused-argument
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import os
from subprocess import CalledProcessError
from subprocess import check_call

import pytest
from testfixtures import StringComparison as S
from testing import assert_command
from testing.assertions import assert_svstat

from pgctl.daemontools import SvStat
from pgctl.errors import LockHeld
from pgctl.functions import check_lock
from pgctl.functions import lsof


def clean_service(service_path):
    # we use SIGTERM; SIGKILL is cheating.
    print('killing.')
    limit = 100
    while limit > 0:  # pragma: no cover: we don't expect to ever hit the limit
        try:
            check_lock(service_path)
            break
        except LockHeld:
            for pid in lsof(service_path):
                try:
                    os.kill(pid, 10)
                except OSError as error:
                    if error.errno == 3:  # no such process
                        pass
                    else:
                        raise
                #with ignored(OSErorr(3, 'No such process')):
                #    os.kill(pid, 10)
            limit -= 1


class DirtyTest(object):

    LOCKERROR = '''\
\\[pgctl\\] Stopping: {service}
\\[pgctl\\] ERROR: '{service}' timed out at {time} seconds: The supervisor has stopped, but these processes did not:
UID +PID +PPID +PGID +SID +C +STIME +TTY +STAT +TIME +CMD
\\S+ +\\d+ +\\d+ +\\d+ +\\d+ +\\d+ +\\S+ +\\S+ +\\S+ +\\S+ +{cmd}

There are two ways you can fix this:
  \\* temporarily: lsof -t playground/{service} | xargs kill -9
  \\* permanently: http://pgctl.readthedocs.org/en/latest/user/quickstart.html#writing-playground-services

\\[pgctl\\] ERROR: Some services failed to stop: {service}
$'''

    @pytest.yield_fixture(autouse=True)
    def cleanup(self, in_example_dir):
        try:
            yield in_example_dir
        finally:
            try:
                clean_service('playground/sweet')
                clean_service('playground/slow-startup')
            except CalledProcessError:
                pass


class DescribeOrphanSubprocess(DirtyTest):

    @pytest.yield_fixture(autouse=True)
    def environment(self):
        os.environ['PGCTL_TIMEOUT'] = '5'
        yield
        del os.environ['PGCTL_TIMEOUT']

    @pytest.yield_fixture
    def service_name(self):
        yield 'orphan-subprocess'

    def it_starts_up_fine(self):
        assert_command(
            ('pgctl-2015', 'start'),
            '',
            '''\
[pgctl] Starting: slow-startup, sweet
[pgctl] Started: sweet
[pgctl] Started: slow-startup
''',
            0,
        )
        assert_command(
            ('pgctl-2015', 'log'),
            '''\
==> playground/slow-startup/stdout.log <==

==> playground/slow-startup/stderr.log <==
pgctl-poll-ready: service's ready check succeeded

==> playground/sweet/stdout.log <==
sweet

==> playground/sweet/stderr.log <==
sweet_error
''',
            '',
            0,
        )

    def it_shows_error_on_stop_for_sweet(self):
        assert_command(
            ('pgctl-2015', 'start', 'sweet'),
            '',
            '''\
[pgctl] Starting: sweet
[pgctl] Started: sweet
''',
            0,
        )
        assert_command(
            ('pgctl-2015', 'restart', 'sweet'),
            '''\
==> playground/sweet/stdout.log <==
sweet

==> playground/sweet/stderr.log <==
sweet_error
''',
            S(self.LOCKERROR.format(service='sweet', time='5', cmd='sleep infinity')),
            1,
        )

    def it_shows_error_on_stop_for_slow_start(self):
        assert_command(
            ('pgctl-2015', 'start', 'slow-startup'),
            '',
            '''\
[pgctl] Starting: slow-startup
[pgctl] Started: slow-startup
''',
            0,
        )
        assert_command(
            ('pgctl-2015', 'restart', 'slow-startup'),
            '''\
==> playground/slow-startup/stdout.log <==

==> playground/slow-startup/stderr.log <==
pgctl-poll-ready: service's ready check succeeded
pgctl-poll-ready: service is stopping -- quitting the poll
''',
            S(self.LOCKERROR.format(service='slow-startup', time='5', cmd='sleep 987654')),
            1,
        )


class DescribeSlowShutdown(DirtyTest):
    """This test case takes three seconds to shut down"""

    @pytest.yield_fixture()
    def service_name(self):
        yield 'slow-shutdown'

    @pytest.yield_fixture(autouse=True)
    def environment(self):
        os.environ['PGCTL_TIMEOUT'] = '1.5'
        yield
        del os.environ['PGCTL_TIMEOUT']

    def it_fails_by_default(self):
        check_call(('pgctl-2015', 'start'))
        assert_svstat('playground/sweet', state='up')
        assert_command(
            ('pgctl-2015', 'stop'),
            '''\
==> playground/sweet/stdout.log <==
sweet

==> playground/sweet/stderr.log <==
sweet_error
''',
            S(self.LOCKERROR.format(service='sweet', time='1\\.5', cmd='sleep 2\\.25')),
            1,
        )

    def it_can_shut_down_successfully(self):
        # if we configure it to wait a bit longer, it works fine
        with open('playground/sweet/timeout-stop', 'w') as timeout:
            timeout.write('3')

        check_call(('pgctl-2015', 'start'))
        assert_svstat('playground/sweet', state='up')

        check_call(('pgctl-2015', 'restart'))
        assert_svstat('playground/sweet', state='up')

        check_call(('pgctl-2015', 'stop'))
        assert_svstat('playground/sweet', state=SvStat.UNSUPERVISED)
