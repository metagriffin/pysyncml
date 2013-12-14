# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/14
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
The ``pysyncml.model.store`` provides a SyncML datastore abstraction
via the :class:`pysyncml.model.store.Store` class, which includes both
the datastore meta information and, if the datastore is local, an
agent to execute data interactions.
'''

import sys, json, logging
import xml.etree.ElementTree as ET
from sqlalchemy import Column, Integer, Boolean, String, Text, ForeignKey
from sqlalchemy.orm import relation, synonym, backref
from sqlalchemy.orm.exc import NoResultFound
from .. import common, constants, ctype

log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
def decorateModel(model):

  #----------------------------------------------------------------------------
  class Store(model.DatabaseObject):

    allSyncTypes = [
      constants.SYNCTYPE_TWO_WAY,
      constants.SYNCTYPE_SLOW_SYNC,
      constants.SYNCTYPE_ONE_WAY_FROM_CLIENT,
      constants.SYNCTYPE_REFRESH_FROM_CLIENT,
      constants.SYNCTYPE_ONE_WAY_FROM_SERVER,
      constants.SYNCTYPE_REFRESH_FROM_SERVER,
      constants.SYNCTYPE_SERVER_ALERTED,
      ]

    adapter_id        = Column(Integer, ForeignKey('%s_adapter.id' % (model.prefix,),
                                                   onupdate='CASCADE', ondelete='CASCADE'),
                               nullable=False, index=True)
    adapter           = relation('Adapter', backref=backref('_stores', # order_by=id,
                                                            cascade='all, delete-orphan',
                                                            passive_deletes=True))
    uri               = Column(String(4095), nullable=False, index=True)
    displayName       = Column(String(4095))
    _syncTypes        = Column('syncTypes', String(4095)) # note: default set in __init__
    maxGuidSize       = Column(Integer)                   # note: default set in __init__
    maxObjSize        = Column(Integer)                   # note: default set in __init__
    _conflictPolicy   = Column('conflictPolicy', Integer)
    agent             = None

    @property
    def syncTypes(self):
      return json.loads(self._syncTypes or 'null')
    @syncTypes.setter
    def syncTypes(self, types):
      self._syncTypes = json.dumps(types)

    @property
    def contentTypes(self):
      if self.agent is not None:
        return self.agent.contentTypes
      return self._contentTypes

    @property
    def conflictPolicy(self):
      if self._conflictPolicy is not None:
        return self._conflictPolicy
      # todo: this assumes that this store is the local one...
      return self.adapter.conflictPolicy
    @conflictPolicy.setter
    def conflictPolicy(self, policy):
      self._conflictPolicy = policy

    @property
    def peer(self):
      return self.getPeerStore()

    #--------------------------------------------------------------------------
    def getPeerStore(self, adapter=None):
      if not self.adapter.isLocal:
        if adapter is None:
          # todo: implement this...
          raise common.InternalError('local adapter is required for call to remoteStore.getPeerStore()')
        uri = adapter.router.getSourceUri(self.uri, mustExist=False)
        if uri is None:
          return None
        return adapter.stores[uri]
      if self.adapter.peer is None:
        return None
      ruri = self.adapter.router.getTargetUri(self.uri, mustExist=False)
      if ruri is None:
        return None
      return self.adapter.peer.stores[ruri]

    #--------------------------------------------------------------------------
    def __init__(self, **kw):
      # TODO: this is a little hack... it is because the .merge() will
      #       otherwise override valid values with null values when the merged-in
      #       store has not been flushed, and because this is a valid value,
      #       open flush, is being nullified. ugh.
      # NOTE: the default is set here, not in the Column() definition, so that
      #       NULL values remain NULL during a flush) - since they are valid.
      self._syncTypes  = kw.get('syncTypes',   repr(Store.allSyncTypes))
      self.maxGuidSize = kw.get('maxGuidSize', common.getAddressSize())
      self.maxObjSize  = kw.get('maxObjSize',  common.getMaxMemorySize())
      super(Store, self).__init__(**kw)

    #----------------------------------------------------------------------------
    def __repr__(self):
      ret = '<Store "%s": uri=%s' % (self.displayName or self.uri, self.uri)
      if self.maxGuidSize is not None:
        ret += '; maxGuidSize=%d' % (self.maxGuidSize,)
      if self.maxObjSize is not None:
        ret += '; maxObjSize=%d' % (self.maxObjSize,)
      if self.syncTypes is not None and len(self.syncTypes) > 0:
        ret += '; syncTypes=%s' % (','.join([str(st) for st in self.syncTypes]),)
      if self.contentTypes is not None and len(self.contentTypes) > 0:
        ret += '; contentTypes=%s' % (','.join([str(ct) for ct in self.contentTypes]),)
      return ret + '>'

    #----------------------------------------------------------------------------
    def merge(self, store):
      if self.uri != store.uri:
        raise common.InternalError('unexpected merging of stores with different URIs (%s != %s)'
                                   % (self.uri, store.uri))
      self.displayName   = store.displayName
      if cmp(self._contentTypes, store._contentTypes) != 0:
        # todo: this is a bit drastic... perhaps have an operational setting
        #       which controls how paranoid to be?...
        self.binding = None
      self._contentTypes = [e.clone() for e in store._contentTypes]
      self.syncTypes     = store.syncTypes
      self.maxGuidSize   = store.maxGuidSize
      self.maxObjSize    = store.maxObjSize
      self.agent         = store.agent
      return self

    #----------------------------------------------------------------------------
    def clearChanges(self):
      if self.adapter.isLocal:
        # TODO: THIS NEEDS TO BE SIGNIFICANTLY OPTIMIZED!... either:
        #         a) optimize this reverse lookup, or
        #         b) use a query that targets exactly the set of stores needed
        #       note that a pre-emptive model.session.flush() may be necessary.
        for peer in self.adapter.getKnownPeers():
          for store in peer._stores:
            if store.binding is not None and store.binding.uri == self.uri:
              store.clearChanges()
        return
      if self.id is None:
        model.session.flush()
      model.Change.q(store_id=self.id).delete()

    #----------------------------------------------------------------------------
    def registerChange(self, itemID, state, changeSpec=None, excludePeerID=None):
      if self.adapter.isLocal:
        # TODO: THIS NEEDS TO BE SIGNIFICANTLY OPTIMIZED!... either:
        #         a) optimize this reverse lookup, or
        #         b) use a query that targets exactly the set of stores needed
        #       note that a pre-emptive model.session.flush() may be necessary.
        for peer in self.adapter.getKnownPeers():
          if excludePeerID is not None and peer.id == excludePeerID:
            continue
          for store in peer._stores:
            if store.binding is not None and store.binding.uri == self.uri:
              store.registerChange(itemID, state, changeSpec=changeSpec)
        return
      if self.id is None:
        model.session.flush()
      itemID = str(itemID)
      change = None
      if changeSpec is not None:
        try:
          change = model.Change.q(store_id=self.id, itemID=itemID).one()
          change.state = state
          if change.changeSpec is not None:
            change.changeSpec += ';' + changeSpec
            if len(change.changeSpec) > model.Change.c.changeSpec.type.length:
              change.changeSpec = None
        except NoResultFound:
          change = None
      if change is None:
        model.Change.q(store_id=self.id, itemID=itemID).delete()
        change = model.Change(store_id=self.id, itemID=itemID,
                              state=state, changeSpec=changeSpec)
        model.session.add(change)

    #--------------------------------------------------------------------------
    def getRegisteredChanges(self):
      return model.Change.q(store_id=self.id)

    #----------------------------------------------------------------------------
    def describe(self, s1):
      s2 = common.IndentStream(s1)
      s3 = common.IndentStream(s2)
      print >>s1, self.displayName or self.uri
      print >>s2, 'URI:', self.uri
      print >>s2, 'Sync types:', ','.join([str(e) for e in self.syncTypes or []])
      print >>s2, 'Max ID size:', self.maxGuidSize or '(none)'
      print >>s2, 'Max object size:', self.maxObjSize or '(none)'
      print >>s2, 'Capabilities:'
      for cti in self.contentTypes or []:
        cti.describe(s3)

    #----------------------------------------------------------------------------
    def toSyncML(self):
      xstore = ET.Element('DataStore')
      if self.uri is not None:
        ET.SubElement(xstore, 'SourceRef').text = self.uri
      if self.displayName is not None:
        ET.SubElement(xstore, 'DisplayName').text = self.displayName
      if self.maxGuidSize is not None:
        # todo: this should ONLY be sent by the client... (according to the
        #       spec, but not according to funambol behavior...)
        ET.SubElement(xstore, 'MaxGUIDSize').text = str(self.maxGuidSize)
      if self.maxObjSize is not None:
        ET.SubElement(xstore, 'MaxObjSize').text = str(self.maxObjSize)
      if self.contentTypes is not None:
        rxpref = [ct for ct in self.contentTypes if ct.receive and ct.preferred]
        if len(rxpref) > 1:
          raise common.InvalidAgent('agents can prefer at most one rx content-type, not %r' % (rxpref,))
        if len(rxpref) == 1:
          for idx, xnode in enumerate(rxpref[0].toSyncML('Rx-Pref', uniqueVerCt=True)):
            if idx != 0:
              xnode.tag = 'Rx'
            xstore.append(xnode)
        for rx in [ct for ct in self.contentTypes if ct.receive and not ct.preferred]:
          for xnode in rx.toSyncML('Rx', uniqueVerCt=True):
            xstore.append(xnode)
        txpref = [ct for ct in self.contentTypes if ct.transmit and ct.preferred]
        if len(txpref) > 1:
          raise common.InvalidAgent('agents can prefer at most one tx content-type, not %r' % (txpref,))
        if len(txpref) == 1:
          for idx, xnode in enumerate(txpref[0].toSyncML('Tx-Pref', uniqueVerCt=True)):
            if idx != 0:
              xnode.tag = 'Tx'
            xstore.append(xnode)
        for tx in [ct for ct in self.contentTypes if ct.transmit and not ct.preferred]:
          for xnode in tx.toSyncML('Tx', uniqueVerCt=True):
            xstore.append(xnode)
      if self.syncTypes is not None and len(self.syncTypes) > 0:
        xcap = ET.SubElement(xstore, 'SyncCap')
        for st in self.syncTypes:
          ET.SubElement(xcap, 'SyncType').text = str(st)
      return xstore

    #----------------------------------------------------------------------------
    @staticmethod
    def fromSyncML(xnode):
      store = model.Store()
      store.uri = xnode.findtext('SourceRef')
      store.displayName = xnode.findtext('DisplayName')
      store.maxGuidSize = xnode.findtext('MaxGUIDSize')
      if store.maxGuidSize is not None:
        store.maxGuidSize = int(store.maxGuidSize)
      store.maxObjSize  = xnode.findtext('MaxObjSize')
      if store.maxObjSize is not None:
        store.maxObjSize = int(store.maxObjSize)
      store.syncTypes = [int(x.text) for x in xnode.findall('SyncCap/SyncType')]
      store._contentTypes = []
      for child in xnode:
        if child.tag not in ('Tx-Pref', 'Tx', 'Rx-Pref', 'Rx'):
          continue
        cti = model.ContentTypeInfo.fromSyncML(child)
        for curcti in store._contentTypes:
          if curcti.merge(cti):
            break
        else:
          store._contentTypes.append(cti)
      return store

  #----------------------------------------------------------------------------
  class ContentTypeInfo(model.DatabaseObject, ctype.ContentTypeInfoMixIn):
    store_id          = Column(Integer, ForeignKey('%s_store.id' % (model.prefix,),
                                                   onupdate='CASCADE', ondelete='CASCADE'),
                               nullable=False, index=True)
    store             = relation('Store', backref=backref('_contentTypes', # order_by=id,
                                                          cascade='all, delete-orphan',
                                                          passive_deletes=True))
    ctype             = Column(String(4095))
    _versions         = Column('versions', String(4095))
    preferred         = Column(Boolean, default=False)
    transmit          = Column(Boolean, default=True)
    receive           = Column(Boolean, default=True)

    @property
    def versions(self):
      return json.loads(self._versions or 'null')
    @versions.setter
    def versions(self, types):
      self._versions = json.dumps(types)

    def clone(self):
      # TODO: this should be moved into `model.DatabaseObject`
      #       see:
      #         https://groups.google.com/forum/?fromgroups#!topic/sqlalchemy/bhYvmnRpegE
      #         http://www.joelanman.com/2008/09/making-a-copy-of-a-sqlalchemy-object/
      return ContentTypeInfo(ctype=self.ctype, _versions=self._versions,
                             preferred=self.preferred, transmit=self.transmit, receive=self.receive)

    def __str__(self):
      return ctype.ContentTypeInfoMixIn.__str__(self)

    def __repr__(self):
      return ctype.ContentTypeInfoMixIn.__repr__(self)

    def __cmp__(self, other):
      for attr in ('ctype', 'versions', 'preferred', 'transmit', 'receive'):
        ret = cmp(getattr(self, attr), getattr(other, attr))
        if ret != 0:
          return ret
      return 0

  #----------------------------------------------------------------------------
  class Binding(model.DatabaseObject):
    # todo: since store <=> binding is one-to-one, shouldn't this be a primary key?...
    store_id          = Column(Integer, ForeignKey('%s_store.id' % (model.prefix,),
                                                   onupdate='CASCADE', ondelete='CASCADE'),
                               nullable=False, index=True)
    targetStore       = relation('Store', backref=backref('binding', uselist=False,
                                                          cascade='all, delete-orphan',
                                                          passive_deletes=True))
    # todo: this uri *could* be replaced by an actual reference to the Store object...
    #       and then the getSourceStore() method can go away...
    #       *BUT* this would require a one-to-many Adapter<=>Adapter relationship...
    uri               = Column(String(4095), nullable=True)
    autoMapped        = Column(Boolean)
    sourceAnchor      = Column(String(4095), nullable=True)
    targetAnchor      = Column(String(4095), nullable=True)

    def getSourceStore(self, adapter):
      return adapter.stores[self.uri]

  #----------------------------------------------------------------------------
  class Change(model.DatabaseObject):
    store_id          = Column(Integer, ForeignKey('%s_store.id' % (model.prefix,),
                                                   onupdate='CASCADE', ondelete='CASCADE'),
                               nullable=False, index=True)
    # store             = relation('Store', backref=backref('changes',
    #                                                       cascade='all, delete-orphan',
    #                                                       passive_deletes=True))
    itemID            = Column(String(4095), index=True, nullable=False)
    state             = Column(Integer)
    registered        = Column(Integer, default=common.ts)
    changeSpec        = Column(String(4095))

  model.Store           = Store
  model.ContentTypeInfo = ContentTypeInfo
  model.Binding         = Binding
  model.Change          = Change

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
