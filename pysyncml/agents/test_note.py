# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/03
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

import unittest, sys, os, logging, six
import sqlalchemy
import pysyncml
from .note import BaseNoteAgent
from ..items.note import NoteItem
from .. import state, constants
from ..common import adict, fullClassname
from ..change import CompositeMergerFactory, TextMergerFactory
from .. import test_helpers
from ..test_helpers import makestats as stat, stats2str, setlogging

setlogging(False)

#------------------------------------------------------------------------------
class ItemStorage:
  def __init__(self, nextID=1):
    self.nextID   = nextID
    self.entries  = dict()
    self.mfactory = CompositeMergerFactory(body=TextMergerFactory(False))
  def getAll(self):
    return self.entries.values()
  def add(self, item):
    item.id = self.nextID
    self.nextID += 1
    self.entries[item.id] = item
    return item
  def get(self, itemID):
    return self.entries[int(itemID)]
  def replace(self, item, reportChanges):
    cspec = None
    if reportChanges:
      orig = self.entries[int(item.id)]
      cspec = self.mfactory.newMerger() \
          .pushChange('name', orig.name, item.name) \
          .pushChange('body', orig.body, item.body) \
          .getChangeSpec()
    self.entries[int(item.id)] = item
    return cspec
  def delete(self, itemID):
    del self.entries[int(itemID)]
  def __str__(self):
    return ','.join([str(key) + '=' + str(val.name)
                     + ':' + str(val.body)
                     for key, val in
                     sorted(self.entries.items(), key=lambda e: e[1].name)])

#------------------------------------------------------------------------------
class Agent(BaseNoteAgent):
  def __init__(self, storage=None, *args, **kw):
    super(Agent, self).__init__(*args, **kw)
    self.storage = storage or ItemStorage()
  def getAllItems(self):                      return self.storage.getAll()
  def addItem(self, item):                    return self.storage.add(item)
  def getItem(self, itemID):                  return self.storage.get(itemID)
  def replaceItem(self, item, reportChanges): return self.storage.replace(item, reportChanges)
  def deleteItem(self, itemID):               return self.storage.delete(itemID)
  def mergeItems(self, localItem, remoteItem, changeSpec):
    merger = self.storage.mfactory.newMerger(changeSpec)
    newname = merger.mergeChanges('name', localItem.name, remoteItem.name)
    newbody = merger.mergeChanges('body', localItem.body, remoteItem.body)
    remoteItem.body = newbody
    remoteItem.name = newname
    return self.replaceItem(remoteItem, True)

#------------------------------------------------------------------------------
class BridgingOpener(object):

  #----------------------------------------------------------------------------
  def __init__(self, adapter=None, peer=None, returnUrl=None, refresher=None):
    self.peer = peer
    self.refresher = refresher
    if self.refresher is None:
      self.refresher = lambda peer: peer
    self.session = pysyncml.Session()
    if returnUrl is not None:
      self.session.returnUrl = returnUrl

  #----------------------------------------------------------------------------
  def open(self, req, data=None, timeout=None):
    self.peer = self.refresher(self.peer)
    self.log('request', data)
    request = adict(headers=dict(), body=data)
    request.headers['content-type'] = req.headers['Content-type']
    response = state.Request()
    self.peer.handleRequest(self.session, request, response)
    self.log('response', response.body)
    res = six.StringIO(response.body)
    res.info = lambda: adict(headers=['content-type: %s' % (response.contentType,)])
    return res

  #----------------------------------------------------------------------------
  def log(self, iline, content):
    try:
      import utools.pxml
      from utools.common import Font
      with open('../%s-%d.log' % (__name__, os.getpid()), 'ab') as fp:
        if iline == 'request':
          color = Font.get(Font.Style.BRIGHT, Font.Fg.RED, Font.Bg.BLACK)
          symbol = '>'
        else:
          color = Font.get(Font.Style.BRIGHT, Font.Fg.GREEN, Font.Bg.BLACK)
          symbol = '<'
        fp.write('%s%s %s:%s %s%s\n'
                 % (color, symbol * 5, iline.upper(), self.peer.devID,
                    symbol * 5, Font.reset()))
        fp.write(utools.pxml.prettyXml(content, strict=False, color=True) or content)
    except Exception,e:
      return

#------------------------------------------------------------------------------
class TestNoteAgent(unittest.TestCase, test_helpers.TrimDictEqual):

  #----------------------------------------------------------------------------
  def setUp(self):
    # create the databases
    self.serverSyncDb  = sqlalchemy.create_engine('sqlite://')
    self.desktopSyncDb = sqlalchemy.create_engine('sqlite://')
    self.mobileSyncDb  = sqlalchemy.create_engine('sqlite://')
    pysyncml.enableSqliteCascadingDeletes(self.serverSyncDb)
    pysyncml.enableSqliteCascadingDeletes(self.desktopSyncDb)
    pysyncml.enableSqliteCascadingDeletes(self.mobileSyncDb)
    self.serverItems   = ItemStorage(nextID=10)
    self.desktopItems  = ItemStorage(nextID=20)
    self.mobileItems   = ItemStorage(nextID=30)
    self.server        = None
    self.desktop       = None
    self.mobile        = None
    self.serverOptions = None
    self.resetAdapters()

  #----------------------------------------------------------------------------
  def refreshServer(self, current=None, options=None):
    self.serverContext = pysyncml.Context(engine=self.serverSyncDb, owner=None, autoCommit=True)
    self.server = self.serverContext.Adapter()
    if self.server.name is None:
      self.server.name = 'In-Memory Test Server'
    if self.server.devinfo is None:
      self.server.devinfo = self.serverContext.DeviceInfo(
        devID             = 'http://www.example.com/sync',
        devType           = pysyncml.DEVTYPE_SERVER,
        manufacturerName  = 'pysyncml',
        modelName         = __name__ + '.server',
        )
    self.serverStore = self.server.addStore(self.serverContext.Store(
      uri='snote', displayName='Note Storage',
      agent=Agent(storage=self.serverItems)))
    if options is not None:
      self.serverOptions = options
    if self.serverOptions is not None:
      if 'conflictPolicy' in self.serverOptions:
        self.server.conflictPolicy = self.serverOptions['conflictPolicy']
    return self.server

  #----------------------------------------------------------------------------
  def resetAdapters(self, serverOptions=None):
    self.server = self.refreshServer(options=serverOptions)
    #--------------------------------------------------------------------------
    # a "desktop" client
    self.desktopContext = pysyncml.Context(engine=self.desktopSyncDb, owner=None, autoCommit=True)
    self.desktop = self.desktopContext.Adapter()
    if self.desktop.name is None:
      self.desktop.name = 'In-Memory Test Desktop Client'
    if self.desktop.devinfo is None:
      self.desktop.devinfo = self.desktopContext.DeviceInfo(
        devID             = __name__ + '.desktop',
        devType           = pysyncml.DEVTYPE_WORKSTATION,
        manufacturerName  = 'pysyncml',
        modelName         = __name__ + '.desktop',
        )
    if self.desktop.peer is None:
      self.desktop.peer = self.desktopContext.RemoteAdapter(
        url='http://www.example.com/sync',
        auth=pysyncml.NAMESPACE_AUTH_BASIC, username='guest', password='guest')
    self.desktop.peer._opener = BridgingOpener(
      returnUrl='http://example.com/sync?s=123-DESKTOP',
      refresher=self.refreshServer,
      )
    self.desktopStore = self.desktop.addStore(self.desktopContext.Store(
      uri='dnote', displayName='Desktop Note Client',
      agent=Agent(storage=self.desktopItems)))
    #--------------------------------------------------------------------------
    # a "mobile" client
    self.mobileContext = pysyncml.Context(engine=self.mobileSyncDb, owner=None, autoCommit=True)
    self.mobile = self.mobileContext.Adapter(maxMsgSize=40960, maxObjSize=40960)
    if self.mobile.name is None:
      self.mobile.name = 'In-Memory Test Mobile Client'
    if self.mobile.devinfo is None:
      self.mobile.devinfo = self.mobileContext.DeviceInfo(
        devID             = __name__ + '.mobile',
        devType           = pysyncml.DEVTYPE_WORKSTATION,
        manufacturerName  = 'pysyncml',
        modelName         = __name__ + '.mobile',
        )
    if self.mobile.peer is None:
      self.mobile.peer = self.mobileContext.RemoteAdapter(
        url='http://www.example.com/sync',
        auth=pysyncml.NAMESPACE_AUTH_BASIC, username='guest', password='guest')
    self.mobile.peer._opener = BridgingOpener(
      returnUrl='http://example.com/sync?s=ABC-MOBILE',
      refresher=self.refreshServer,
      )
    self.mobileStore = self.mobile.addStore(self.mobileContext.Store(
      uri='mnote', displayName='Mobile Note Client',
      agent=Agent(storage=self.mobileItems)))

  #----------------------------------------------------------------------------
  def refreshAdapters(self, serverOptions=None):
    # this should be unnecessary - but paranoia is paranoia
    if self.serverContext is not None:
      self.serverContext.save()
    if self.desktopContext is not None:
      self.desktopContext.save()
    if self.mobileContext is not None:
      self.mobileContext.save()
    self.resetAdapters(serverOptions=serverOptions)

  #----------------------------------------------------------------------------
  def test_sync_refreshClient(self):
    self.serverItems.add(NoteItem(name='note1', body='note1'))
    self.desktopItems.add(NoteItem(name='note2', body='note2'))
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1, hereDel=1))
    self.assertTrimDictEqual(stats, chk)

  #----------------------------------------------------------------------------
  def test_sync_addClient(self):
    # step 1: initial sync
    self.serverItems.add(NoteItem(name='note1', body='note1'))
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1))
    self.assertTrimDictEqual(stats, chk)
    # step 2: make changes and register
    self.refreshAdapters()
    item2 = self.serverItems.add(NoteItem(name='note2', body='note2'))
    self.serverStore.registerChange(item2.id, pysyncml.ITEM_ADDED)
    # step 3: re-sync
    # TODO: look into why this "refreshAdapters()" is necessary...
    self.refreshAdapters()
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1', 'note2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1', 'note2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER, hereAdd=1))
    self.assertTrimDictEqual(stats, chk)

  #----------------------------------------------------------------------------
  def test_sync_modClient(self):
    # step 1: initial sync
    item = self.serverItems.add(NoteItem(name='note1', body='note1'))
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1))
    self.assertTrimDictEqual(stats, chk)
    # step 2: make changes and register
    self.refreshAdapters()
    self.serverItems.replace(NoteItem(name='note1.mod', body='note1.mod', id=item.id), False)
    self.serverStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    # step 3: re-sync
    self.refreshAdapters()
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1.mod'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1.mod'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER, hereMod=1))
    self.assertTrimDictEqual(stats, chk)

  #----------------------------------------------------------------------------
  def test_sync_delClient(self):
    # step 1: initial sync
    item = self.serverItems.add(NoteItem(name='note1', body='note1'))
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1))
    self.assertTrimDictEqual(stats, chk)
    # step 2: make changes and register
    self.refreshAdapters()
    self.serverItems.delete(item.id)
    self.serverStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    # step 3: re-sync
    self.refreshAdapters()
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], [])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], [])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER, hereDel=1))
    self.assertTrimDictEqual(stats, chk)

  #----------------------------------------------------------------------------
  def test_sync_refreshServer(self):
    # step 1: initial sync
    self.desktopItems.add(NoteItem(name='note1', body='note1'))
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_CLIENT)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_CLIENT, peerAdd=1))
    self.assertTrimDictEqual(stats, chk)

  #----------------------------------------------------------------------------
  def test_slowsync_with_matching_notes(self):
    # step 1: initial sync
    self.desktopItems.add(NoteItem(name='note1', body='note1'))
    self.serverItems.add(NoteItem(name='note1', body='note1'))
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_SLOW_SYNC)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['note1'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['note1'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC))
    self.assertTrimDictEqual(stats, chk)

  #----------------------------------------------------------------------------
  def baseline(self):
    # step 1: initial sync
    dstats = self.desktop.sync()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], [])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], [])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], [])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC))
    self.assertTrimDictEqual(dstats, chk)
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC))
    self.assertTrimDictEqual(mstats, chk)
    # step 2: make changes on desktop and register
    self.refreshAdapters()
    item1 = self.desktopItems.add(NoteItem(name='n1', body='n1'))
    item2 = self.desktopItems.add(NoteItem(name='n2', body='n2'))
    self.desktopStore.registerChange(item1.id, pysyncml.ITEM_ADDED)
    self.desktopStore.registerChange(item2.id, pysyncml.ITEM_ADDED)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], [])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], [])
    # step 3: re-sync desktop to server (push n1 => server)
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], [])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerAdd=2))
    self.assertTrimDictEqual(dstats, chk)
    # step 4: re-sync mobile to server (push n1 => mobile)
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereAdd=2))
    self.assertTrimDictEqual(mstats, chk)
    # step 5: re-sync mobile to server (expect no changes)
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(mstats, chk)
    # step 6: re-sync desktop to server (expect no changes)
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_multiclient_add(self):
    self.baseline()

  #----------------------------------------------------------------------------
  def test_multiclient_replace(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: modify n1 in the desktop and register
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 3: re-sync desktop to server (push n1 mod => server)
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 4: re-sync mobile to server (push n1 mod => mobile)
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereMod=1))
    self.assertTrimDictEqual(mstats, chk)
    # step 5: re-sync mobile to server (expect no changes)
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(mstats, chk)
    # step 6: re-sync desktop to server (expect no changes)
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_multiclient_delete(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: delete n1 in the desktop and register
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    del self.desktopItems.entries[item.id]
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 3: re-sync desktop to server (push n1 del => server)
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 4: re-sync mobile to server (push n1 del => mobile)
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereDel=1))
    self.assertTrimDictEqual(mstats, chk)
    # step 5: re-sync mobile to server (expect no changes)
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(mstats, chk)
    # step 6: re-sync desktop to server (expect no changes)
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_deldel_ok(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: delete n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    del self.desktopItems.entries[item.id]
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: delete n1 in the mobile and push to server => conflict-but-ok delete
    self.refreshAdapters()
    item = self.mobileItems.entries.values()[0]
    del self.mobileItems.entries[item.id]
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1, hereDel=1, merged=1))
    self.assertTrimDictEqual(mstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_modmod_error(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters()
    item = self.mobileItems.entries.values()[0]
    item.body = 'n1-BIS'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-BIS', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereErr=1, conflicts=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: re-sync'ing again should not change the outcome
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-BIS', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereErr=1, conflicts=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))

  #----------------------------------------------------------------------------
  def test_conflict_modmod_clientWins(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server
    #         with the server conflict policy set to 'client-wins'
    self.refreshAdapters(serverOptions=dict(conflictPolicy=constants.POLICY_CLIENT_WINS))
    item = self.mobileItems.entries.values()[0]
    item.body = 'n1-BIS'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-BIS', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-BIS', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: sync desktop (expect "conflicted" record to propagate)
    self.serverOptions = None
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-BIS', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-BIS', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-BIS', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereMod=1))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_modmod_serverWins(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters(serverOptions=dict(conflictPolicy=constants.POLICY_SERVER_WINS))
    self.refreshAdapters()
    item = self.mobileItems.entries.values()[0]
    item.body = 'n1-BIS'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereMod=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: ensure nothing propagates when sync'ing the desktop
    self.serverOptions = None
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(dstats, chk)
    # step 5: re-sync to mobile to ensure nothing got "polluted"...
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1-bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(mstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_modmod_merge(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1 bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1 bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1 bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters()
    item = self.mobileItems.entries.values()[0]
    item.body = 'N1'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['N1 bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1 bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['N1 bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereMod=1, peerMod=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: propagate the merge to the desktop
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['N1 bis', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['N1 bis', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['N1 bis', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereMod=1))
    self.assertEqual(stats2str(dstats), stats2str(chk))

  #----------------------------------------------------------------------------
  def test_conflict_delmod_error(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n1', 'n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    # step 2: delete n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    del self.desktopItems.entries[item.id]
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    dstats = self.desktop.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1', 'n2'])
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters()
    item = self.mobileItems.entries.values()[0]
    item.body = 'n1-bis'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereErr=1, conflicts=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: re-sync'ing again should not change the outcome
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual([e.body for e in self.serverItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.desktopItems.entries.values()], ['n2'])
    self.assertEqual([e.body for e in self.mobileItems.entries.values()], ['n1-bis', 'n2'])
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereErr=1, conflicts=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))

  #----------------------------------------------------------------------------
  def test_conflict_delmod_clientWins(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual(str(self.serverItems), '10=n1:n1,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    # step 2: delete n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    del self.desktopItems.entries[item.id]
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '11=n2:n2')
    self.assertEqual(str(self.desktopItems), '21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters(serverOptions=dict(conflictPolicy=constants.POLICY_CLIENT_WINS))
    item = self.mobileItems.entries.values()[0]
    item.body = 'n1-bis'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual(str(self.serverItems), '12=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1-bis,31=n2:n2')
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: sync desktop (expect "conflicted" record to propagate)
    self.serverOptions = None
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '12=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '22=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1-bis,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereAdd=1))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_delmod_serverWins(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual(str(self.serverItems), '10=n1:n1,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    # step 2: delete n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    del self.desktopItems.entries[item.id]
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '11=n2:n2')
    self.assertEqual(str(self.desktopItems), '21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters(serverOptions=dict(conflictPolicy=constants.POLICY_SERVER_WINS))
    item = self.mobileItems.entries.values()[0]
    item.body = 'n1-bis'
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    mstats = self.mobile.sync()
    self.assertEqual(str(self.serverItems), '11=n2:n2')
    self.assertEqual(str(self.desktopItems), '21=n2:n2')
    self.assertEqual(str(self.mobileItems), '31=n2:n2')
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereDel=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: sync desktop (expect "conflicted" record to propagate)
    self.serverOptions = None
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '11=n2:n2')
    self.assertEqual(str(self.desktopItems), '21=n2:n2')
    self.assertEqual(str(self.mobileItems), '31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_moddel_error(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual(str(self.serverItems), '10=n1:n1,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: delete n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters()
    item = self.mobileItems.entries.values()[0]
    del self.mobileItems.entries[item.id]
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    mstats = self.mobile.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '31=n2:n2')
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereErr=1, conflicts=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: re-sync'ing again should not change the outcome
    self.refreshAdapters()
    mstats = self.mobile.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '31=n2:n2')
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereErr=1, conflicts=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))

  #----------------------------------------------------------------------------
  def test_conflict_moddel_clientWins(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual(str(self.serverItems), '10=n1:n1,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: delete n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters(serverOptions=dict(conflictPolicy=constants.POLICY_CLIENT_WINS))
    item = self.mobileItems.entries.values()[0]
    del self.mobileItems.entries[item.id]
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    mstats = self.mobile.sync()
    self.assertEqual(str(self.serverItems), '11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '31=n2:n2')
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerDel=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: sync desktop (expect "conflicted" record to propagate)
    self.serverOptions = None
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '11=n2:n2')
    self.assertEqual(str(self.desktopItems), '21=n2:n2')
    self.assertEqual(str(self.mobileItems), '31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereDel=1))
    self.assertTrimDictEqual(dstats, chk)

  #----------------------------------------------------------------------------
  def test_conflict_moddel_serverWins(self):
    # step 1: get notes into all stores and all synchronized
    self.baseline()
    self.assertEqual(str(self.serverItems), '10=n1:n1,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    # step 2: modify n1 in the desktop and push to server
    self.refreshAdapters()
    item = self.desktopItems.entries.values()[0]
    item.body = 'n1-bis'
    self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '30=n1:n1,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
    self.assertTrimDictEqual(dstats, chk)
    # step 3: modify n1 in the mobile (without propagating) and push to server => conflict
    self.refreshAdapters(serverOptions=dict(conflictPolicy=constants.POLICY_SERVER_WINS))
    item = self.mobileItems.entries.values()[0]
    del self.mobileItems.entries[item.id]
    self.mobileStore.registerChange(item.id, pysyncml.ITEM_DELETED)
    mstats = self.mobile.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '32=n1:n1-bis,31=n2:n2')
    chk = dict(mnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereAdd=1, merged=1))
    self.assertEqual(stats2str(mstats), stats2str(chk))
    # step 4: sync desktop (expect "conflicted" record to propagate)
    self.serverOptions = None
    self.refreshAdapters()
    dstats = self.desktop.sync()
    self.assertEqual(str(self.serverItems), '10=n1:n1-bis,11=n2:n2')
    self.assertEqual(str(self.desktopItems), '20=n1:n1-bis,21=n2:n2')
    self.assertEqual(str(self.mobileItems), '32=n1:n1-bis,31=n2:n2')
    chk = dict(dnote=stat(mode=pysyncml.SYNCTYPE_TWO_WAY))
    self.assertTrimDictEqual(dstats, chk)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
