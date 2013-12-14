# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/20
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
The ``pysyncml.router`` is an internal package that helps an adapter
select which target (i.e. remote) datastore a source (i.e. local)
datastore routes its requests to and which Content-Type to use.
'''

# todo: i think this class has mostly been deprecated by the introduction
#       of the Adapter => Store => Binding database relationship setup...
#       perhaps it is time to refactor it?...

import time, logging
from . import common, constants, state, matcher, smp

log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
class Router(object):

  #----------------------------------------------------------------------------
  def __init__(self, adapter, *args, **kw):
    super(Router, self).__init__(*args, **kw)
    self.adapter = adapter
    self.routes  = dict() # key(uri) => targetUri       # these are manual routes
    self.bestCt  = dict() # key(uri) => contentType

  #----------------------------------------------------------------------------
  def getTargetUri(self, sourceUri, mustExist=True):
    # todo: convert this to cacheable?...
    sourceUri = self.adapter.cleanUri(sourceUri)
    if sourceUri in self.routes:
      targetUri = self.adapter.peer.cleanUri(self.routes[sourceUri])
      if targetUri not in self.adapter.peer.stores:
        if mustExist:
          # todo: should i raise a different error here?
          raise common.NoSuchRoute(sourceUri)
        return None
      return targetUri
    for rstore in self.adapter.peer.stores.values():
      if rstore.binding is not None and rstore.binding.uri == sourceUri:
        return rstore.uri
    if mustExist:
      raise common.NoSuchRoute(sourceUri)
    return None

  #----------------------------------------------------------------------------
  def getSourceUri(self, targetUri):
    targetUri = self.adapter.peer.cleanUri(targetUri)
    for k, v in self.routes.items():
      if self.adapter.peer.cleanUri(v) == targetUri:
        return k
    for rstore in self.adapter.peer.stores.values():
      if rstore.binding is not None and rstore.uri == targetUri:
        return rstore.binding.uri
    raise common.NoSuchRoute(targetUri)

  #----------------------------------------------------------------------------
  def addRoute(self, sourceUri, targetUri, autoMapped=False):
    sourceUri = self.adapter.cleanUri(sourceUri)
    # purge the best-contentType cache
    if sourceUri in self.bestCt:
      del self.bestCt[sourceUri]
    # note: not cleaning the targetUri as the peer may not have been set
    #       yet by the client if this is not being auto-mapped...
    if not autoMapped:
      self.routes[sourceUri] = targetUri
      return
    targetUri = self.adapter.peer.cleanUri(targetUri)

    log.debug('adding auto-mapped route from "%s" to "%s"', sourceUri, targetUri)

    # todo: this is ignoring the manual routes... i.e. a manual route should
    #       preclude the ability to bind to either of the specified stores...

    if sourceUri in self.routes:
      manual = self.adapter.peer.cleanUri(self.routes[sourceUri])
      if manual != targetUri:
        log.warn('autoMapped route %s=>%s overridden by manual route %s=>%s',
                 sourceUri, targetUri, sourceUri, manual)

    done = False
    for rstore in self.adapter.peer.stores.values():
      if rstore.uri == targetUri:
        if rstore.binding is None or rstore.binding.uri != sourceUri:
          rstore.binding = self.adapter._context._model.Binding(uri=sourceUri, autoMapped=autoMapped)
        done = True
        continue
      if rstore.binding is not None and rstore.binding.uri == sourceUri:
        rstore.binding = None

    if not done:
      raise common.NoSuchRoute(targetUri)

  #----------------------------------------------------------------------------
  def getBestTransmitContentType(self, sourceUri):
    sourceUri = self.adapter.cleanUri(sourceUri)
    if sourceUri in self.bestCt:
      return self.bestCt[sourceUri]
    targetUri = self.getTargetUri(sourceUri)
    best = matcher.pickTransmitContentType(
      self.adapter.stores[sourceUri], self.adapter.peer.stores[targetUri])
    self.bestCt[sourceUri] = best
    return best

  #----------------------------------------------------------------------------
  def recalculate(self, session):
    if session.isServer:
      # only the client makes routing decisions...
      return

    not_srcs = self.routes.keys()
    not_tgts = [self.adapter.peer.cleanUri(e) for e in self.routes.values()]

    srcs = [e for e in self.adapter.stores.keys() if e not in not_srcs]
    tgts = [e for e in self.adapter.peer.stores.keys() if e not in not_tgts]

    log.debug('re-calculating routes for local %s to remote URI %s',
              repr(srcs), repr(tgts))

    sources = self.adapter.stores
    targets = self.adapter.peer.stores

    matches = smp.match(
      srcs, tgts,
      lambda src, a, b: matcher.cmpToDataStore(sources[src], targets[a], targets[b]),
      lambda tgt, a, b: matcher.cmpToDataStore(targets[tgt], sources[a], sources[b]),
      )

    for src, tgt in matches:
      self.addRoute(src, tgt, True)

    newstates = dict()
    for store in self.adapter.stores.values():
      if store.agent is None:
        continue
      peerUri = self.getTargetUri(store.uri, mustExist=False)
      if peerUri is None:
        continue
      if store.uri in session.dsstates and session.dsstates[store.uri].peerUri == peerUri:
        newstates[store.uri] = session.dsstates[store.uri]
        continue
      mode = session.mode
      if mode not in (
        # this is a new binding, so only full-syncs are allowed
        constants.ALERT_SLOW_SYNC,
        constants.ALERT_REFRESH_FROM_CLIENT,
        constants.ALERT_REFRESH_FROM_SERVER,
        ):
        mode = constants.ALERT_SLOW_SYNC
      newstates[store.uri] = common.adict(
        # TODO: perhaps share this "constructor" with protocol/adapter?...
        lastAnchor = self.adapter.peer.stores[peerUri].binding.sourceAnchor,
        nextAnchor = str(int(time.time())),
        mode       = mode,
        action     = 'alert',
        peerUri    = peerUri,
        stats      = state.Stats(),
        )
    session.dsstates = newstates

  # #----------------------------------------------------------------------------
  # def _dbsave(self):
  #   pass
  # #   if self.adapter.target is None:
  # #     return
  # #   self.adapter.model.Route.q(devID=self.adapter.target.devID).delete()
  # #   for route in self.routes.values():
  # #     dbr = self.adapter.model.Route(
  # #       devID             = self.adapter.target.devID,
  # #       autoMapped        = route.autoMapped,
  # #       sourceUri         = route.sourceUri,
  # #       targetUri         = route.targetUri,
  # #       )
  # #     self.adapter.model.session.add(dbr)

  # #----------------------------------------------------------------------------
  # @staticmethod
  # def _dbload(adapter):
  #   return Router(adapter)
  # #   self.routes = dict([(k, v)
  # #                       for k, v in self.routes.items()
  # #                       if not v.autoMapped])
  # #   if self.adapter.target is None:
  # #     return
  # #   for route in self.adapter.model.Route.q(devID=self.adapter.target.devID):
  # #     if route.sourceUri in self.routes:
  # #       if route.autoMapped:
  # #         continue
  # #     self.routes[route.sourceUri] = common.adict(
  # #       sourceUri  = route.sourceUri,
  # #       targetUri  = route.targetUri,
  # #       autoMapped = route.autoMapped,
  # #       )
  # #   # purge the best-contentType cache
  # #   self.bestCt = dict()

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
