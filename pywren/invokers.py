#
# Copyright 2018 PyWren Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import absolute_import

import json
import os
import shutil
import threading
import tempfile
import atexit
import sys
import glob2
import botocore
import botocore.session
from six.moves import queue
from pywren import local

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))


class LambdaInvoker(object):
    def __init__(self, region_name, lambda_function_name):

        self.session = botocore.session.get_session()

        self.region_name = region_name
        self.lambda_function_name = lambda_function_name
        self.lambclient = self.session.create_client('lambda',
                                                     region_name=region_name)
        self.TIME_LIMIT = True

    def invoke(self, payload):
        """
        Invoke -- return information about this invocation
        """
        self.lambclient.invoke(FunctionName=self.lambda_function_name,
                               Payload=json.dumps(payload),
                               InvocationType='Event')
        # FIXME check response
        return {}

    def config(self):
        """
        Return config dict
        """
        return {'lambda_function_name' : self.lambda_function_name,
                'region_name' : self.region_name}

TEMP_DIR = tempfile.gettempdir()
LOCAL_RUN_DIR = os.path.join(TEMP_DIR, "task")
def local_clean():
    dirs = glob2.glob(os.path.join(TEMP_DIR, 'pymodules*'))
    dirs.append(LOCAL_RUN_DIR)
    dirs.append(os.path.join(TEMP_DIR, 'runtimes'))
    files = [os.path.join(TEMP_DIR, 'runtime_download_lock')]
    files += glob2.glob(os.path.join(TEMP_DIR, 'jobrunner*'))
    files += glob2.glob(os.path.join(TEMP_DIR, 'condaruntime_*'))
    for d in dirs:
        shutil.rmtree(d, True)
    for f in files:
        if os.path.exists(f):
            os.remove(f)


class DummyInvoker(object):
    """
    A mock invoker that simply appends payloads to a list. You must then
    call run()
    """

    def __init__(self):
        self.payloads = []
        self.TIME_LIMIT = False
        atexit.register(local_clean)

    def invoke(self, payload):
        self.payloads.append(payload)

    def config(self): # pylint: disable=no-self-use
        return {}


    def run_jobs(self, MAXJOBS=-1, run_dir=LOCAL_RUN_DIR):
        """
        run MAXJOBS in the queue
        MAXJOBS = -1  to run all

        # FIXME not multithreaded safe
        """

        jobn = len(self.payloads)
        if MAXJOBS != -1:
            jobn = MAXJOBS
        jobs = self.payloads[:jobn]

        local.local_handler(jobs, run_dir,
                            {'invoker' : 'DummyInvoker'})

        self.payloads = self.payloads[jobn:]


class LocalInvoker(object):
    """
    An invoker which spawns a thread that then waits
    for jobs on a queue. This is a more self-contained invoker in that
    it doesn't require the run_jobs() of the dummy invoker.
    """

    # When Windows runtimes are made available, local invoker should be ready
    # to run on Windows as well
    if not sys.platform.startswith('linux'):
        raise RuntimeError("LocalInvoker can only be run under linux")

    def __init__(self, run_dir=LOCAL_RUN_DIR):

        self.running = True

        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._thread_runner)
        self.thread.daemon = True
        self.run_dir = run_dir
        self.thread.start()
        atexit.register(local_clean)


    def _thread_runner(self):
        while True:
            res = self.queue.get(True)
            jobs = [res]

            local.local_handler(jobs, self.run_dir,
                                {'invoker' : 'LocalInvoker'})
            self.queue.task_done()

    def invoke(self, payload):
        self.queue.put(payload)

    def config(self): # pylint: disable=no-self-use
        return {}
