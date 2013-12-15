# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/19
# copy: (C) Copyright 2012-EOT metagriffin -- see LICENSE.txt
#------------------------------------------------------------------------------
# This software is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This software is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see http://www.gnu.org/licenses/.
#------------------------------------------------------------------------------

'''
The ``pysyncml.model.adapter`` package exposes the Adapter implementation of
the pysyncml package.
'''

import sys, os, time, logging
from sqlalchemy import orm
from sqlalchemy import Column, Integer, Boolean, String, Text, ForeignKey
from sqlalchemy.orm import relation, synonym, backref
import requests
from requests.structures import CaseInsensitiveDict as idict

from .. import common, constants, codec, state

log = logging.getLogger(__name__)

# TODO: the current algorithm for finding the "local" adapter is to search
#       for adapters where isLocal == False... i should move to one-to-many
#       parent-child relationships and search for adapters where parent
#       == None...

# TODO: move all the transmit/receive logic out of this class!...

#------------------------------------------------------------------------------
def decorateModel(model):

  #----------------------------------------------------------------------------
  class Adapter(model.DatabaseObject):
    devID             = Column(String(4095), nullable=False, index=True)
    name              = Column(String(4095), nullable=True)
    isLocal           = Column(Boolean, nullable=True)
    createdDate       = Column(Integer, default=common.ts)
    isServer          = Column(Boolean, nullable=True)
    url               = Column(String(4095), nullable=True)
    auth              = Column(Integer, nullable=True)
    username          = Column(String(4095), nullable=True)
    password          = Column(String(4095), nullable=True)
    lastSessionID     = Column(Integer)
    firstSync         = Column(Integer)
    lastSync          = Column(Integer)
    maxGuidSize       = Column(Integer)
    maxMsgSize        = Column(Integer)
    maxObjSize        = Column(Integer)
    conflictPolicy    = Column(Integer, default=constants.POLICY_ERROR)
    _peer             = None

    @property
    def devinfo(self):
      return self._devinfo
    @devinfo.setter
    def devinfo(self, devinfo):
      if devinfo is self._devinfo:
        return
      self._devinfo = devinfo
      if self.devID is None:
        self.devID = devinfo.devID
      if self.devID is not None:
        self._context._model.session.flush()

    @property
    def stores(self):
      return dict((store.uri, store) for store in self._stores)

    @property
    def peer(self):
      return self._peer
    @peer.setter
    def peer(self, peer):
      if peer is self._peer:
        return
      if peer is not None and peer.id is None:
        model.session.add(peer)
      self._peer = peer

    #--------------------------------------------------------------------------
    def __init__(self, *args, **kw):
      if 'isLocal' not in kw:
        kw['isLocal'] = kw.get('url') is None
      if 'devID' not in kw:
        kw['devID'] = kw.get('url')
      # TODO: why on *EARTH* do i have to do this?...
      self._setDefaults()
      super(Adapter, self).__init__(*args, **kw)
      self._initHelpers()

    #--------------------------------------------------------------------------
    @orm.reconstructor
    def __dbinit__(self):
      self._initHelpers()

    #--------------------------------------------------------------------------
    def _initHelpers(self):
      if not self.isLocal:
        self._ckjar = idict()

    #--------------------------------------------------------------------------
    def cleanUri(self, uri):
      return os.path.normpath(uri)

    #--------------------------------------------------------------------------
    def getKnownPeers(self):
      return model.Adapter.q(isLocal=False).all()

    #--------------------------------------------------------------------------
    def addStore(self, store):
      store.uri = self.cleanUri(store.uri)
      for curstore in self._stores:
        if curstore.uri == store.uri:
          curstore.merge(store)
          return curstore
      self._stores.append(store)
      if self.devID is not None:
        self._context._model.session.flush()
      return self._stores[-1]

    #--------------------------------------------------------------------------
    def _dbsave(self):
      # if model.context.autoCommit:
      #   model.session.commit()
      model.context.save()

    #--------------------------------------------------------------------------
    def sync(self, mode=constants.SYNCTYPE_AUTO):
      # # todo: deal with this paranoia... perhaps move this into the synchronizer?...
      # self._context._model.session.flush()
      # remap mode from SYNCTYPE_ to ALERT_
      if mode is not None:
        mode = common.synctype2alert(mode)
      if self.devinfo is None:
        raise common.InvalidAdapter('no device info provided')
      if self.peer is None:
        raise common.InvalidAdapter('no peer registered')
      log.debug('starting %s sync with peer "%s"', common.mode2string(mode), self.peer.devID)

      session = state.Session(
        id         = ( self.peer.lastSessionID or 0 ) + 1,
        isServer   = False,
        mode       = mode,
        )

      for store in self._stores:
        if store.agent is None:
          continue
        peerUri = self.router.getTargetUri(store.uri, mustExist=False)
        if peerUri is None:
          continue

        # todo: perhaps the mode defaulting should be pushed into synchronizer?
        #       it should be able to perform more in-depth logic...
        ds = common.adict(
          # TODO: perhaps share this "constructor" with router/protocol?...
          lastAnchor = self.peer.stores[peerUri].binding.sourceAnchor,
          nextAnchor = str(int(time.time())),
          mode       = mode or constants.ALERT_TWO_WAY,
          action     = 'alert',
          peerUri    = peerUri,
          stats      = state.Stats(),
          )

        if ds.lastAnchor is None:
          if ds.mode in [
            constants.ALERT_SLOW_SYNC,
            constants.ALERT_REFRESH_FROM_CLIENT,
            constants.ALERT_REFRESH_FROM_SERVER,
            ]:
            pass
          elif ds.mode in [
            constants.ALERT_TWO_WAY,
            constants.ALERT_ONE_WAY_FROM_CLIENT,
            constants.ALERT_ONE_WAY_FROM_SERVER,
            ]:
            log.info('forcing slow-sync for datastore "%s" (no previous successful synchronization)', uri)
            ds.mode = constants.ALERT_SLOW_SYNC
          else:
            raise common.ProtocolError('unexpected sync mode "%d" requested' % (ds.mode,))

        session.dsstates[store.uri] = ds

      commands = self.protocol.initialize(self, session)

      self._transmit(session, commands)
      self._dbsave()
      return self._session2stats(session)

    #--------------------------------------------------------------------------
    def _session2stats(self, session):
      ret = common.adict()
      for uri, ds in session.dsstates.items():
        stats = ds.stats
        stats.mode = common.alert2synctype(ds.mode)
        ret[uri] = stats
      log.info('session statistics: %r', ret)
      return ret

    #--------------------------------------------------------------------------
    def _transmit(self, session, commands, response=None):

      commands = self.protocol.negotiate(self, session, commands)

      if not session.isServer \
         and len(commands) == 3 \
         and commands[0].name == constants.CMD_SYNCHDR \
         and commands[1].name == constants.CMD_STATUS \
         and commands[1].statusOf == constants.CMD_SYNCHDR \
         and commands[1].statusCode == str(constants.STATUS_OK) \
         and commands[2].name == constants.CMD_FINAL:
        for uri, ds in session.dsstates.items():
          log.debug('storing next anchor here="%s", peer="%s" for URI "%s"',
                    ds.nextAnchor, ds.peerNextAnchor, uri)
          self.peer.stores[ds.peerUri].binding.sourceAnchor = ds.nextAnchor
          self.peer.stores[ds.peerUri].binding.targetAnchor = ds.peerNextAnchor
        self.peer.lastSessionID = session.id
        log.debug('synchronization complete for "%s" (s%s.m%s)',
                  self.peer.devID, session.id, session.lastMsgID)
        return

      request = state.Request(
        commands    = commands,
        contentType = None,
        body        = None,
        )

      xtree = self.protocol.commands2tree(self, session, commands)
      (request.contentType, request.body) = self.codec.encode(xtree)

      # update the session with the last request commands so that
      # when we receive the response package, it can be compared against
      # that.
      # TODO: should that only be done on successful transmit?...
      session.lastCommands = commands
      if response is None:
        self.peer.handleRequest(session, request, adapter=self)
      else:
        response.contentType = request.contentType
        response.body        = request.body

    #--------------------------------------------------------------------------
    def handleRequest(self, session, request, response=None, adapter=None):
      # # todo: deal with this paranoia... perhaps move this into the synchronizer?...
      # self._context._model.session.commit()
      if self.isLocal:
        return self._handleRequestLocal(session, request, response)
      return self._handleRequestRemote(session, request, adapter)

    #--------------------------------------------------------------------------
    def _handleRequestLocal(self, session, request, response=None):
      commands = self._receive(session, request) or []
      log.debug('beginning negotiation of response to device "%s" (s%d.m%d)',
                self.peer.devID, session.id, session.msgID)
      if session.msgID > 20:
        log.error('too many client/server messages, pending commands: %r', commands)
        raise common.ProtocolError('too many client/server messages')
      self._transmit(session, commands, response)
      if session.isServer:
        self._dbsave()
        return self._session2stats(session)

    #----------------------------------------------------------------------------
    def _handleRequestRemote(self, session, request, adapter):
      res = requests.post(
        session.respUri or self.url,
        headers  = {
          'content-type'    : request.contentType or 'application/vnd.syncml+xml',
          'x-syncml-client' : 'pysyncml/' + common.version,
          },
        cookies  = self._ckjar,
        data     = request.body,
        )
      # TODO: improve this handling
      if res.status_code != 200:
        log.error('unexpected response: [%d] %s', res.status_code, res.reason)
        raise common.ProtocolError('error response: [%d] %s'
                                   % (res.status_code, res.reason))
      self._ckjar.update(res.cookies)
      adapter.handleRequest(session, state.Request(
        body=res.content, headers=res.headers))

    #--------------------------------------------------------------------------
    def _receive(self, session, request):
      if not session.isServer:
        session.lastMsgID = session.msgID
        session.nextMsgID
      else:
        session.lastCommands = session.lastCommands or []
      xtree = codec.Codec.autoDecode(request.headers['content-type'], request.body)
      return self.protocol.tree2commands(self, session, session.lastCommands, xtree)

    #----------------------------------------------------------------------------
    def describe(self, stream):
      s2 = common.IndentStream(stream)
      s3 = common.IndentStream(s2)
      stream.write('Local device:\n')
      print >>s2, 'Device ID:', self.devinfo.devID
      if len(self._stores) <= 0:
        print >>s2, 'DataStores: (none)'
      else:
        print >>s2, 'DataStores:'
        for store in self._stores:
          store.describe(s3)
      stream.write('Remote device:\n')
      print >>s2, 'Device ID:', self.peer.devID
      if len(self.peer._stores) <= 0:
        print >>s2, 'DataStores: (none)'
      else:
        print >>s2, 'DataStores:'
        for store in self.peer._stores:
          store.describe(s3)

      # if len(self.router.routes) <= 0:
      #   stream.write('Sync routing: N/A\n')
      # else:
      #   stream.write('Sync routing:\n')
      #   for route in self.router.routes.values():
      #     anchors = self.getLastAnchorSet(route.sourceUri)
      #     print >>s2, '%s <=> %s%s, anchors: %s/%s' \
      #           % (route.sourceUri, route.targetUri,
      #              ' (auto)' if route.autoMapped else '',
      #              anchors[0] or '-', anchors[1] or '-')

  model.Adapter = Adapter

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
