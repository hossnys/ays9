from js9 import j

from JumpScale9AYS.ays.lib.TemplateRepo import TemplateRepoCollection
from JumpScale9AYS.ays.lib import ActionsBase
from JumpScale9AYS.ays.lib.AtYourServiceRepo import AtYourServiceRepoCollection
from JumpScale9AYS.ays.lib.AtYourServiceTester import AtYourServiceTester

import colored_traceback
import os
import sys
from inotify.adapters import BaseTree, _DEFAULT_EPOLL_BLOCK_DURATION_S
from inotify.calls import InotifyError
import inotify.constants
import threading
if "." not in sys.path:
    sys.path.append(".")

import inspect
import asyncio

colored_traceback.add_hook(always=True)


class AtYourServiceFactory:

    def __init__(self):
        self.__jslocation__ = "j.atyourservice.server"
        self.__imports__ = "pycapnp"
        self.loop = None
        self._config = None
        self._domains = []
        self.debug = j.application.config['system']['debug']
        self.logger = j.logger.get('j.atyourservice.server')
        self.started = False

        self.baseActions = {}
        self.templateRepos = None
        self.aysRepos = None
        self._cleanupHandle = None

    def start(self, bind='127.0.0.1', port=5000, log='info'):
        """
        start an ays service on your local platform
        """
        try:
            sname = j.tools.prefab.local.tmux.getSessions()[0]
        except:
            sname = "main"
        cmd = "cd {codedir}/github/jumpscale/ays9; python3 main.py --host {host} --port {port} --log {log}".format(
            codedir=j.dirs.CODEDIR, host=bind, port=port, log=log)
        print("Starting AtYourService server in a tmux session")
        # execute ays in tmux with wait=0 because of the check ok output with ays will never be true
        rc, out = j.tools.prefab.local.tmux.executeInScreen(sname, "ays", cmd, reset=True, wait=0)
        if rc > 0:
            raise RuntimeError("Cannot start AYS service")

        if log == 'debug':
            print("debug logging enabled")
        print("AYS server running at http://{}:{}".format(bind, port))
        return rc, out

    def cleanup(self):
        sleep = 60
        runs = j.core.jobcontroller.db.runs.find()
        limit = int(j.data.time.getEpochAgo("-2h"))
        for run in runs:
            if run.dbobj.state in ['error', 'ok']:
                j.core.jobcontroller.db.runs.delete(state=run.dbobj.state, repo=run.dbobj.repo, toEpoch=limit)
        jobs = j.core.jobcontroller.db.jobs.find()
        for job in jobs:
            if job is None:
                continue

            elif job.state in ['error', 'ok']:
                j.core.jobcontroller.db.jobs.delete(actor=job.dbobj.actorName, service=job.dbobj.serviceName,
                                                    action=job.dbobj.actionName, state=job.state,
                                                    serviceKey=job.dbobj.serviceKey, toEpoch=limit)
                del job
        self._cleanupHandle = self.loop.call_later(sleep, self.cleanup)

    def _start(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.templateRepos = TemplateRepoCollection(loop=loop)  # actor templates repositories
        self.aysRepos = AtYourServiceRepoCollection(loop=loop)  # ays repositories
        self.started = True
        if not self._cleanupHandle:
            self._cleanupHandle = self.loop.call_soon(self.cleanup)

    async def _stop(self):
        self.logger.info("stopping AtYourService")
        self.started = False
        to_wait = [repo.stop() for repo in self.aysRepos.list()]
        await asyncio.wait(to_wait)

    @property
    def actorTemplates(self):
        templates = []
        for template_repo in self.templateRepos.list():
            if template_repo.is_global:
                templates.extend(template_repo.templates)
        return templates

    @property
    def config(self):
        if self._config is None:
            cfg = j.application.config.get('ays')
            if not cfg:
                cfg = {}
            if 'redis' not in cfg:
                rediskwargs = j.core.db.config_get('unixsocket')
                if not rediskwargs['unixsocket']:
                    dbkwargs = j.core.db.connection_pool.connection_kwargs
                    rediskwargs = {'host': dbkwargs['host'], 'port': dbkwargs['port']}
                cfg.update({'redis': rediskwargs})
            self._config = cfg
        return self._config

    def reset(self):
        self._domains = []
        self.baseActions = {}
        self.templateRepos = None
        self.aysRepos = None
        self._start(loop=self.loop)

    def getAYSTester(self, name="fake_IT_env"):
        self._init()
        return AtYourServiceTester(name)

    def _loadActionBase(self):
        """
        load all the basic actions for atyourservice
        """
        if self.baseActions == {}:
            for method in [item[1] for item in inspect.getmembers(ActionsBase) if item[0][0] != "_"]:
                action_code_model = j.core.jobcontroller.getActionObjFromMethod(method)
                if not j.core.jobcontroller.db.actions.exists(action_code_model.key):
                    # will save in DB
                    action_code_model.save()
                self.baseActions[action_code_model.dbobj.name] = action_code_model, method
