# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/07/22
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

import unittest, sys, os, logging, StringIO
import sqlalchemy
import pysyncml
from .file import BaseFileAgent
from ..items.file import FileItem
from ..items.folder import FolderItem
from .. import state
from ..common import adict
from .. import test_helpers
from ..test_helpers import makestats as stat, setlogging

setlogging(False)

#------------------------------------------------------------------------------
class ItemStorage:
  def __init__(self, nextID=1):
    self.nextID  = nextID
    self.entries = dict()
  def getAll(self):
    return self.entries.values()
  def add(self, item):
    item.id = self.nextID
    item.path = self._makePath(item)
    self.nextID += 1
    self.entries[item.id] = item
    return item
  def get(self, itemID):
    return self.entries[int(itemID)]
  def replace(self, item):
    item.path = self._makePath(item)
    self.entries[int(item.id)] = item
    return item
  def delete(self, itemID):
    # TBD: delete any orphans...
    del self.entries[int(itemID)]
  def _makePath(self, item):
    if item.parent is None:
      return ''
    parent = self.get(item.parent)
    if parent.parent is None:
      return item.name
    return self._makePath(parent) + '/' + item.name

#------------------------------------------------------------------------------
class Agent(BaseFileAgent):
  def __init__(self, storage=None, *args, **kw):
    super(Agent, self).__init__(*args, **kw)
    self.storage = storage or ItemStorage()
  def getAllItems(self):           return self.storage.getAll()
  def addItem(self, item):         return self.storage.add(item)
  def getItem(self, itemID):       return self.storage.get(itemID)
  def replaceItem(self, item):     return self.storage.replace(item)
  def deleteItem(self, itemID):    return self.storage.delete(itemID)
  def matchItem(self, item):
    # for curitem in self.storage.getAll():
    #   if curitem.body == item.body:
    #     return curitem
    return None

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
    res = StringIO.StringIO(response.body)
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
class TestFileAgent(unittest.TestCase, test_helpers.TrimDictEqual):

  #----------------------------------------------------------------------------
  def setUp(self):
    # create the databases
    self.serverSyncDb  = sqlalchemy.create_engine('sqlite://')
    self.desktopSyncDb = sqlalchemy.create_engine('sqlite://')
    self.mobileSyncDb  = sqlalchemy.create_engine('sqlite://')
    pysyncml.enableSqliteCascadingDeletes(self.serverSyncDb)
    pysyncml.enableSqliteCascadingDeletes(self.desktopSyncDb)
    pysyncml.enableSqliteCascadingDeletes(self.mobileSyncDb)
    self.serverItems   = ItemStorage(nextID=1000)
    self.desktopItems  = ItemStorage(nextID=2000)
    self.mobileItems   = ItemStorage(nextID=3000)
    self.server        = None
    self.desktop       = None
    self.mobile        = None
    self.resetAdapters()

  #----------------------------------------------------------------------------
  def refreshServer(self, current=None):
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
      uri='sfile', displayName='File Storage',
      agent=Agent(storage=self.serverItems)))
    return self.server

  #----------------------------------------------------------------------------
  def resetAdapters(self):
    self.server = self.refreshServer()
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
      uri='dfile', displayName='Desktop File Client',
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
      uri='mfile', displayName='Mobile File Client',
      agent=Agent(storage=self.mobileItems)))

  #----------------------------------------------------------------------------
  def refreshAdapters(self):
    # this should be unnecessary - but paranoia is paranoia
    if self.serverContext is not None:
      self.serverContext.save()
    if self.desktopContext is not None:
      self.desktopContext.save()
    if self.mobileContext is not None:
      self.mobileContext.save()
    self.resetAdapters()

  #----------------------------------------------------------------------------
  def test_sync_refreshClient(self):
    root = self.serverItems.add(FolderItem(name='main'))
    self.serverItems.add(FileItem(name='foo.txt', body='content0', parent=root.id))
    dir1 = self.serverItems.add(FolderItem(name='subdir', parent=root.id))
    self.serverItems.add(FileItem(name='bar.txt', body='content1', parent=dir1.id))
    self.assertEqual(['', 'foo.txt', 'subdir', 'subdir/bar.txt'],
                     [e.path for e in self.serverItems.entries.values()])
    stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
    self.assertEqual(['', 'foo.txt', 'subdir', 'subdir/bar.txt'],
                     [e.path for e in self.serverItems.entries.values()])
    self.assertEqual(['', 'foo.txt', 'subdir', 'subdir/bar.txt'],
                     [e.path for e in self.desktopItems.entries.values()])
    chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=4))
    self.assertTrimDictEqual(chk, stats)

  # #----------------------------------------------------------------------------
  # def test_sync_addClient(self):
  #   # step 1: initial sync
  #   self.serverItems.add(FileItem(name='file1', body='file1'))
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1))
  #   self.assertTrimDictEqual(chk, stats)
  #   # step 2: make changes and register
  #   self.refreshAdapters()
  #   item2 = self.serverItems.add(FileItem(name='file2', body='file2'))
  #   self.serverStore.registerChange(item2.id, pysyncml.ITEM_ADDED)
  #   # step 3: re-sync
  #   # TODO: look into why this "refreshAdapters()" is necessary...
  #   self.refreshAdapters()
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER)
  #   self.assertEqual(['file1', 'file2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['file1', 'file2'], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER, hereAdd=1))
  #   self.assertTrimDictEqual(chk, stats)

  # #----------------------------------------------------------------------------
  # def test_sync_modClient(self):
  #   # step 1: initial sync
  #   item = self.serverItems.add(FileItem(name='file1', body='file1'))
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
  #   self.assertEqual(['file1'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['file1'], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1))
  #   self.assertTrimDictEqual(chk, stats)
  #   # step 2: make changes and register
  #   self.refreshAdapters()
  #   self.serverItems.replace(FileItem(name='file1.mod', body='file1.mod', id=item.id))
  #   self.serverStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
  #   # step 3: re-sync
  #   self.refreshAdapters()
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER)
  #   self.assertEqual(['file1.mod'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['file1.mod'], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER, hereMod=1))
  #   self.assertTrimDictEqual(chk, stats)

  # #----------------------------------------------------------------------------
  # def test_sync_delClient(self):
  #   # step 1: initial sync
  #   item = self.serverItems.add(FileItem(name='file1', body='file1'))
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER)
  #   self.assertEqual(['file1'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['file1'], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_SERVER, hereAdd=1))
  #   self.assertTrimDictEqual(chk, stats)
  #   # step 2: make changes and register
  #   self.refreshAdapters()
  #   self.serverItems.delete(item.id)
  #   self.serverStore.registerChange(item.id, pysyncml.ITEM_DELETED)
  #   # step 3: re-sync
  #   self.refreshAdapters()
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER)
  #   self.assertEqual([], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual([], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER, hereDel=1))
  #   self.assertTrimDictEqual(chk, stats)

  # #----------------------------------------------------------------------------
  # def test_sync_refreshServer(self):
  #   # step 1: initial sync
  #   self.desktopItems.add(FileItem(name='file1', body='file1'))
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_REFRESH_FROM_CLIENT)
  #   self.assertEqual(['file1'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['file1'], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_REFRESH_FROM_CLIENT, peerAdd=1))
  #   self.assertTrimDictEqual(chk, stats)

  # #----------------------------------------------------------------------------
  # def test_refresh_with_matching_files(self):
  #   # step 1: initial sync
  #   self.desktopItems.add(FileItem(name='file1', body='file1'))
  #   self.serverItems.add(FileItem(name='file1', body='file1'))
  #   stats = self.desktop.sync(mode=pysyncml.SYNCTYPE_SLOW_SYNC)
  #   self.assertEqual(['file1'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['file1'], [e.body for e in self.desktopItems.entries.values()])
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC))
  #   self.assertTrimDictEqual(chk, stats)

  # #----------------------------------------------------------------------------
  # def baseline(self):
  #   # step 1: initial sync
  #   dstats = self.desktop.sync()
  #   mstats = self.mobile.sync()
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC))
  #   self.assertTrimDictEqual(chk, dstats)
  #   chk = dict(mfile=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC))
  #   self.assertTrimDictEqual(chk, mstats)
  #   self.assertEqual([], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual([], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual([], [e.body for e in self.mobileItems.entries.values()])
  #   # step 2: make changes on desktop and register
  #   self.refreshAdapters()
  #   item1 = self.desktopItems.add(FileItem(name='n1', body='n1'))
  #   item2 = self.desktopItems.add(FileItem(name='n2', body='n2'))
  #   self.desktopStore.registerChange(item1.id, pysyncml.ITEM_ADDED)
  #   self.desktopStore.registerChange(item2.id, pysyncml.ITEM_ADDED)
  #   self.assertEqual([], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual([], [e.body for e in self.mobileItems.entries.values()])
  #   # step 3: re-sync desktop to server (push n1 => server)
  #   self.refreshAdapters()
  #   dstats = self.desktop.sync()
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerAdd=2))
  #   self.assertTrimDictEqual(chk, dstats)
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual([], [e.body for e in self.mobileItems.entries.values()])
  #   # step 4: re-sync mobile to server (push n1 => mobile)
  #   self.refreshAdapters()
  #   mstats = self.mobile.sync()
  #   chk = dict(mfile=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereAdd=2))
  #   self.assertTrimDictEqual(chk, mstats)
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.mobileItems.entries.values()])

  # #----------------------------------------------------------------------------
  # def test_multiclient_add(self):
  #   self.baseline()

  # #----------------------------------------------------------------------------
  # def test_multiclient_replace(self):
  #   # step 1: get a file into all stores
  #   self.baseline()
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.mobileItems.entries.values()])
  #   # step 2: modify the n1 in the desktop and register
  #   self.refreshAdapters()
  #   item = self.desktopItems.entries.values()[0]
  #   item.body = 'n1-bis'
  #   self.desktopStore.registerChange(item.id, pysyncml.ITEM_MODIFIED)
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1-bis', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.mobileItems.entries.values()])
  #   # step 3: re-sync desktop to server (push n1 mod => server)
  #   self.refreshAdapters()
  #   dstats = self.desktop.sync()
  #   chk = dict(dfile=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=1))
  #   self.assertTrimDictEqual(chk, dstats)
  #   self.assertEqual(['n1-bis', 'n2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1-bis', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual(['n1', 'n2'], [e.body for e in self.mobileItems.entries.values()])
  #   # step 4: re-sync mobile to server (push n1 mod => mobile)
  #   self.refreshAdapters()
  #   mstats = self.mobile.sync()
  #   chk = dict(mfile=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, hereMod=1))
  #   self.assertTrimDictEqual(chk, mstats)
  #   self.assertEqual(['n1-bis', 'n2'], [e.body for e in self.serverItems.entries.values()])
  #   self.assertEqual(['n1-bis', 'n2'], [e.body for e in self.desktopItems.entries.values()])
  #   self.assertEqual(['n1-bis', 'n2'], [e.body for e in self.mobileItems.entries.values()])

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
