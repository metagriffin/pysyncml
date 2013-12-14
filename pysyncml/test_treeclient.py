# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/17
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

import unittest, sys, os, re, time, logging
import sqlalchemy
import pysyncml
from .common import adict, ts, ts_iso, getAddressSize, getMaxMemorySize
from .items.file import FileItem
from .items.folder import FolderItem
from . import codec, test_helpers
from .test_helpers import makestats as stat, setlogging

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
  def replace(self, item, reportChanges):
    item.path = self._makePath(item)
    self.entries[int(item.id)] = item
    return None
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
class Agent(pysyncml.BaseFileAgent):
  def __init__(self, storage=None, *args, **kw):
    super(Agent, self).__init__(*args, **kw)
    self.storage = storage or ItemStorage()
  def getAllItems(self):                      return self.storage.getAll()
  def addItem(self, item):                    return self.storage.add(item)
  def getItem(self, itemID):                  return self.storage.get(itemID)
  def replaceItem(self, item, reportChanges): return self.storage.replace(item, reportChanges)
  def deleteItem(self, itemID):               return self.storage.delete(itemID)

#------------------------------------------------------------------------------
class ProxyPeer(object):

  #----------------------------------------------------------------------------
  def __init__(self, context, proxy=None, **kw):
    self.proxy   = proxy or context.RemoteAdapter(**kw)
    self.pending = False
    self.request = None
    self.adapter = None
    self.session = None

  #----------------------------------------------------------------------------
  def __getattr__(self, key):
    if key in ('proxy', 'pending', 'request', 'adapter', 'session'):
      return self.__dict__[key]
    return getattr(self.__dict__['proxy'], key)
  def __setattr__(self, key, value):
    if key in ('proxy', 'pending', 'request', 'adapter', 'session'):
      self.__dict__[key] = value
      return
    setattr(self.__dict__['proxy'], key, value)
  def __delattr__(self, key):
    if key in ('proxy', 'pending', 'request', 'adapter', 'session'):
      return
    delattr(self.__dict__['proxy'], key)

  #----------------------------------------------------------------------------
  def handleRequest(self, session, request, response=None, adapter=None):
    self.pending = True
    self.request = request
    self.adapter = adapter
    self.session = session

  #----------------------------------------------------------------------------
  def sendResponse(self, response):
    session = self.session
    adapter = self.adapter
    self.pending = False
    self.request = None
    self.adapter = None
    self.session = None
    adapter.handleRequest(session, response)

#----------------------------------------------------------------------------
def findxml(xml, xpath):
  xtree = codec.Codec.autoDecode('application/vnd.syncml+xml', xml)
  return xtree.findtext(xpath)

#------------------------------------------------------------------------------
class TestTreeClient(unittest.TestCase, test_helpers.XmlEqual, test_helpers.TrimDictEqual):

  #----------------------------------------------------------------------------
  def assertIntsNear(self, chk, val, offset=1):
    if chk - offset <= val and chk + offset >= val:
      return
    self.assertEqual(chk, val)

  #----------------------------------------------------------------------------
  def setUp(self):
    self.initDatabases()
    self.initClient()

  #----------------------------------------------------------------------------
  def initDatabases(self):
    self.items = ItemStorage(nextID=1000)
    self.db    = sqlalchemy.create_engine('sqlite://')

    #if os.path.exists('../test.db'):
    #  os.unlink('../test.db')
    #self.db = sqlalchemy.create_engine('sqlite:///../test.db')

    pysyncml.enableSqliteCascadingDeletes(self.db)

  #----------------------------------------------------------------------------
  def initClient(self):
    self.context = pysyncml.Context(engine=self.db, owner=None, autoCommit=True)
    self.store   = self.context.Store(uri='clitree', displayName='LocalFiles',
                                      agent=Agent(storage=self.items))
    self.client  = self.context.Adapter()
    if self.client.name is None:
      self.client.name = 'In-Memory Test Client'
    if self.client.devinfo is None:
      self.client.devinfo = self.context.DeviceInfo(
        devID             = __name__ + '.client',
        devType           = pysyncml.DEVTYPE_WORKSTATION,
        manufacturerName  = 'pysyncml',
        modelName         = __name__ + '.client',
        )
    self.store = self.client.addStore(self.store)

  #----------------------------------------------------------------------------
  def doFirstSync(self):
    proxy = ProxyPeer(self.context,
                      url='http://www.example.com/sync',
                      auth=pysyncml.NAMESPACE_AUTH_BASIC,
                      username='guest', password='guest')

    # step 1: populate client with some data
    root = self.items.add(FolderItem(name='main'))
    self.items.add(FileItem(name='foo.txt', body='content0', parent=root.id))
    dir1 = self.items.add(FolderItem(name='subdir', parent=root.id))
    self.items.add(FileItem(name='bar.txt', body='content1', parent=dir1.id))

    self.assertEqual(['', 'foo.txt', 'subdir', 'subdir/bar.txt'],
                     [e.path for e in self.items.entries.values()])

    # step 2: client sends registration/initialization
    self.client.peer = proxy
    self.client.sync(pysyncml.SYNCTYPE_SLOW_SYNC)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>1</SessionID>'
                '  <MsgID>1</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                '  <Cred>'
                '    <Meta>'
                '      <Format xmlns="syncml:metinf">b64</Format>'
                '      <Type xmlns="syncml:metinf">syncml:auth-basic</Type>'
                '    </Meta>'
                '    <Data>Z3Vlc3Q6Z3Vlc3Q=</Data>'
                '  </Cred>'
                '  <Meta>'
                '   <MaxMsgSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxMsgSize>'
                '   <MaxObjSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxObjSize>'
                '  </Meta>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Put>'
                '   <CmdID>1</CmdID>'
                '   <Meta><Type xmlns="syncml:metinf">application/vnd.syncml-devinf+xml</Type></Meta>'
                '   <Item>'
                '    <Source><LocURI>./devinf12</LocURI><LocName>./devinf12</LocName></Source>'
                '    <Data>'
                '     <DevInf xmlns="syncml:devinf">'
                '      <VerDTD>1.2</VerDTD>'
                '      <Man>pysyncml</Man>'
                '      <Mod>' + __name__ + '.client</Mod>'
                '      <OEM>-</OEM>'
                '      <FwV>-</FwV>'
                '      <SwV>-</SwV>'
                '      <HwV>-</HwV>'
                '      <DevID>' + __name__ + '.client</DevID>'
                '      <DevTyp>workstation</DevTyp>'
                '      <UTC/>'
                '      <SupportLargeObjs/>'
                '      <SupportHierarchicalSync/>'
                '      <SupportNumberOfChanges/>'
                '      <DataStore>'
                '       <SourceRef>clitree</SourceRef>'
                '       <DisplayName>LocalFiles</DisplayName>'
                '       <MaxGUIDSize>' + str(getAddressSize()) + '</MaxGUIDSize>'
                '       <MaxObjSize>' + str(getMaxMemorySize()) + '</MaxObjSize>'
                '       <Rx-Pref><CTType>application/vnd.omads-file</CTType><VerCT>1.2</VerCT></Rx-Pref>'
                '       <Rx><CTType>application/vnd.omads-folder</CTType><VerCT>1.2</VerCT></Rx>'
                '       <Tx-Pref><CTType>application/vnd.omads-file</CTType><VerCT>1.2</VerCT></Tx-Pref>'
                '       <Tx><CTType>application/vnd.omads-folder</CTType><VerCT>1.2</VerCT></Tx>'
                '       <SyncCap>'
                '        <SyncType>1</SyncType>'
                '        <SyncType>2</SyncType>'
                '        <SyncType>3</SyncType>'
                '        <SyncType>4</SyncType>'
                '        <SyncType>5</SyncType>'
                '        <SyncType>6</SyncType>'
                '        <SyncType>7</SyncType>'
                '       </SyncCap>'
                '      </DataStore>'
                '     </DevInf>'
                '    </Data>'
                '   </Item>'
                '  </Put>'
                '  <Get>'
                '   <CmdID>2</CmdID>'
                '   <Meta><Type xmlns="syncml:metinf">application/vnd.syncml-devinf+xml</Type></Meta>'
                '   <Item>'
                '    <Target><LocURI>./devinf12</LocURI><LocName>./devinf12</LocName></Target>'
                '   </Item>'
                '  </Get>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')
    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)

    # step 3: server responds, client sets up routes and requests sync
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>1</SessionID>'
                     '  <MsgID>1</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>1</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>212</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>2</CmdID>'
                     '   <MsgRef>1</MsgRef>'
                     '   <CmdRef>1</CmdRef>'
                     '   <Cmd>Put</Cmd>'
                     '   <SourceRef>./devinf12</SourceRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>3</CmdID>'
                     '   <MsgRef>1</MsgRef>'
                     '   <CmdRef>2</CmdRef>'
                     '   <Cmd>Get</Cmd>'
                     '   <TargetRef>./devinf12</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Results>'
                     '   <CmdID>4</CmdID>'
                     '   <MsgRef>1</MsgRef>'
                     '   <CmdRef>2</CmdRef>'
                     '   <Meta><Type xmlns="syncml:metinf">application/vnd.syncml-devinf+xml</Type></Meta>'
                     '   <Item>'
                     '    <Source><LocURI>./devinf12</LocURI></Source>'
                     '    <Data>'
                     '     <DevInf xmlns="syncml:devinf">'
                     '      <VerDTD>1.2</VerDTD>'
                     '      <Man>pysyncml</Man>'
                     '      <Mod>' + __name__ + '.server</Mod>'
                     '      <OEM>-</OEM>'
                     '      <FwV>-</FwV>'
                     '      <SwV>-</SwV>'
                     '      <HwV>-</HwV>'
                     '      <DevID>' + __name__ + '.server</DevID>'
                     '      <DevTyp>server</DevTyp>'
                     '      <UTC/>'
                     '      <SupportLargeObjs/>'
                     '      <SupportNumberOfChanges/>'
                     '      <DataStore>'
                     '       <SourceRef>srvtree</SourceRef>'
                     '       <DisplayName>Note Storage</DisplayName>'
                     '       <MaxGUIDSize>' + str(getAddressSize()) + '</MaxGUIDSize>'
                     '       <Rx-Pref><CTType>application/vnd.omads-file</CTType><VerCT>1.2</VerCT></Rx-Pref>'
                     '       <Rx><CTType>application/vnd.omads-folder</CTType><VerCT>1.2</VerCT></Rx>'
                     '       <Tx-Pref><CTType>application/vnd.omads-file</CTType><VerCT>1.2</VerCT></Tx-Pref>'
                     '       <Tx><CTType>application/vnd.omads-folder</CTType><VerCT>1.2</VerCT></Tx>'
                     '       <SyncCap>'
                     '        <SyncType>1</SyncType>'
                     '        <SyncType>2</SyncType>'
                     '        <SyncType>3</SyncType>'
                     '        <SyncType>4</SyncType>'
                     '        <SyncType>5</SyncType>'
                     '        <SyncType>6</SyncType>'
                     '        <SyncType>7</SyncType>'
                     '       </SyncCap>'
                     '      </DataStore>'
                     '     </DevInf>'
                     '    </Data>'
                     '   </Item>'
                     '  </Results>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    proxy.sendResponse(response)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>1</SessionID>'
                '  <MsgID>2</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Status>'
                '   <CmdID>1</CmdID>'
                '   <MsgRef>1</MsgRef>'
                '   <CmdRef>0</CmdRef>'
                '   <Cmd>SyncHdr</Cmd>'
                '   <SourceRef>http://www.example.com/sync</SourceRef>'
                '   <TargetRef>' + __name__ + '.client</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>2</CmdID>'
                '   <MsgRef>1</MsgRef>'
                '   <CmdRef>4</CmdRef>'
                '   <Cmd>Results</Cmd>'
                '   <SourceRef>./devinf12</SourceRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Alert>'
                '   <CmdID>3</CmdID>'
                '   <Data>201</Data>'
                '   <Item>'
                '    <Source><LocURI>clitree</LocURI></Source>'
                '    <Target><LocURI>srvtree</LocURI></Target>'
                '    <Meta>'
                '     <Anchor xmlns="syncml:metinf"><Next>' + str(int(time.time())) + '</Next></Anchor>'
                '     <MaxObjSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxObjSize>'
                '    </Meta>'
                '   </Item>'
                '  </Alert>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')
    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)
    self.assertEqual('http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048', proxy.session.respUri)

    # step 4: server responds, client sends all of its data (none in this case)
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>1</SessionID>'
                     '  <MsgID>2</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>2</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>3</CmdRef>'
                     '   <Cmd>Alert</Cmd>'
                     '   <SourceRef>clitree</SourceRef>'
                     '   <TargetRef>srvtree</TargetRef>'
                     '   <Data>200</Data>'
                     '   <Item>'
                     '    <Data>'
                     '     <Anchor xmlns="syncml:metinf"><Next>' + str(int(time.time())) + '</Next></Anchor>'
                     '    </Data>'
                     '   </Item>'
                     '  </Status>'
                     '  <Alert>'
                     '   <CmdID>3</CmdID>'
                     '   <Data>201</Data>'
                     '   <Item>'
                     '    <Source><LocURI>srvtree</LocURI></Source>'
                     '    <Target><LocURI>clitree</LocURI></Target>'
                     '    <Meta>'
                     '     <Anchor xmlns="syncml:metinf"><Next>' + str(int(time.time())) + '</Next></Anchor>'
                     '     <MaxObjSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxObjSize>'
                     '    </Meta>'
                     '   </Item>'
                     '  </Alert>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    proxy.sendResponse(response)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>1</SessionID>'
                '  <MsgID>3</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Status>'
                '   <CmdID>1</CmdID>'
                '   <MsgRef>2</MsgRef>'
                '   <CmdRef>0</CmdRef>'
                '   <Cmd>SyncHdr</Cmd>'
                '   <SourceRef>http://www.example.com/sync</SourceRef>'
                '   <TargetRef>' + __name__ + '.client</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>2</CmdID>'
                '   <MsgRef>2</MsgRef>'
                '   <CmdRef>3</CmdRef>'
                '   <Cmd>Alert</Cmd>'
                '   <SourceRef>srvtree</SourceRef>'
                '   <TargetRef>clitree</TargetRef>'
                '   <Data>200</Data>'
                '   <Item>'
                '    <Data>'
                '     <Anchor xmlns="syncml:metinf">'
                '      <Next>' + str(int(time.time())) + '</Next>'
                '     </Anchor>'
                '    </Data>'
                '   </Item>'
                '  </Status>'
                '  <Sync>'
                '   <CmdID>3</CmdID>'
                '   <Source><LocURI>clitree</LocURI></Source>'
                '   <Target><LocURI>srvtree</LocURI></Target>'
                '   <NumberOfChanges>4</NumberOfChanges>'
                '   <Add>'
                '    <CmdID>4</CmdID>'
                '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-folder+xml</Type></Meta>'
                '    <Item>'
                '     <Source><LocURI>1000</LocURI></Source>'
                '     <Data>&lt;Folder&gt;&lt;name&gt;main&lt;/name&gt;&lt;/Folder&gt;</Data>'
                '    </Item>'
                '   </Add>'
                '   <Add>'
                '    <CmdID>5</CmdID>'
                '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-file+xml</Type></Meta>'
                '    <Item>'
                '     <Source><LocURI>1001</LocURI></Source>'
                '     <SourceParent><LocURI>1000</LocURI></SourceParent>'
                '     <Data>&lt;File&gt;&lt;name&gt;foo.txt&lt;/name&gt;&lt;body&gt;content0&lt;/body&gt;&lt;/File&gt;</Data>'
                '    </Item>'
                '   </Add>'
                '   <Add>'
                '    <CmdID>6</CmdID>'
                '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-folder+xml</Type></Meta>'
                '    <Item>'
                '     <Source><LocURI>1002</LocURI></Source>'
                '     <SourceParent><LocURI>1000</LocURI></SourceParent>'
                '     <Data>&lt;Folder&gt;&lt;name&gt;subdir&lt;/name&gt;&lt;/Folder&gt;</Data>'
                '    </Item>'
                '   </Add>'
                '   <Add>'
                '    <CmdID>7</CmdID>'
                '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-file+xml</Type></Meta>'
                '    <Item>'
                '     <Source><LocURI>1003</LocURI></Source>'
                '     <SourceParent><LocURI>1002</LocURI></SourceParent>'
                '     <Data>&lt;File&gt;&lt;name&gt;bar.txt&lt;/name&gt;&lt;body&gt;content1&lt;/body&gt;&lt;/File&gt;</Data>'
                '    </Item>'
                '   </Add>'
                '  </Sync>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')
    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)

    # step 5: server responds, client sends mapping
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>1</SessionID>'
                     '  <MsgID>3</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>2</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>3</CmdRef>'
                     '   <Cmd>Sync</Cmd>'
                     '   <SourceRef>clitree</SourceRef>'
                     '   <TargetRef>srvtree</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>3</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>4</CmdRef>'
                     '   <Cmd>Add</Cmd>'
                     '   <SourceRef>1000</SourceRef>'
                     '   <Data>418</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>4</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>5</CmdRef>'
                     '   <Cmd>Add</Cmd>'
                     '   <SourceRef>1001</SourceRef>'
                     '   <Data>418</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>5</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>6</CmdRef>'
                     '   <Cmd>Add</Cmd>'
                     '   <SourceRef>1002</SourceRef>'
                     '   <Data>418</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>6</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>7</CmdRef>'
                     '   <Cmd>Add</Cmd>'
                     '   <SourceRef>1003</SourceRef>'
                     '   <Data>201</Data>'
                     '  </Status>'
                     '  <Sync>'
                     '   <CmdID>7</CmdID>'
                     '   <Source><LocURI>srvtree</LocURI></Source>'
                     '   <Target><LocURI>clitree</LocURI></Target>'
                     '   <NumberOfChanges>1</NumberOfChanges>'
                     '   <Add>'
                     '    <CmdID>8</CmdID>'
                     '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-file</Type></Meta>'
                     '    <Item>'
                     '     <Source><LocURI>50</LocURI></Source>'
                     '     <TargetParent><LocURI>1002</LocURI></TargetParent>'
                     '     <Data>&lt;File&gt;&lt;name&gt;bar2.txt&lt;/name&gt;&lt;body&gt;content2&lt;/body&gt;&lt;/File&gt;</Data>'
                     '    </Item>'
                     '   </Add>'
                     '  </Sync>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    proxy.sendResponse(response)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>1</SessionID>'
                '  <MsgID>4</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Status>'
                '   <CmdID>1</CmdID>'
                '   <MsgRef>3</MsgRef>'
                '   <CmdRef>0</CmdRef>'
                '   <Cmd>SyncHdr</Cmd>'
                '   <SourceRef>http://www.example.com/sync</SourceRef>'
                '   <TargetRef>' + __name__ + '.client</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>2</CmdID>'
                '   <MsgRef>3</MsgRef>'
                '   <CmdRef>7</CmdRef>'
                '   <Cmd>Sync</Cmd>'
                '   <SourceRef>srvtree</SourceRef>'
                '   <TargetRef>clitree</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>3</CmdID>'
                '   <MsgRef>3</MsgRef>'
                '   <CmdRef>8</CmdRef>'
                '   <Cmd>Add</Cmd>'
                '   <SourceRef>50</SourceRef>'
                '   <Data>201</Data>'
                '  </Status>'
                '  <Map>'
                '   <CmdID>4</CmdID>'
                '   <Source><LocURI>clitree</LocURI></Source>'
                '   <Target><LocURI>srvtree</LocURI></Target>'
                '   <MapItem>'
                '    <Source><LocURI>1004</LocURI></Source>'
                '    <Target><LocURI>50</LocURI></Target>'
                '   </MapItem>'
                '  </Map>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')

    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)
    self.assertEqual(['', 'foo.txt', 'subdir', 'subdir/bar.txt', 'subdir/bar2.txt'],
                     [e.path for e in self.items.entries.values()])

    # step 6: server responds, client sends nothing
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>1</SessionID>'
                     '  <MsgID>4</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>4</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>2</CmdID>'
                     '   <MsgRef>4</MsgRef>'
                     '   <CmdRef>4</CmdRef>'
                     '   <Cmd>Map</Cmd>'
                     '   <SourceRef>clitree</SourceRef>'
                     '   <TargetRef>srvtree</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    session = proxy.session
    proxy.sendResponse(response)
    self.assertFalse(proxy.pending)
    # this is only because i've interrupted the normal Adapter handling...
    self.client._dbsave()
    stats = self.client._session2stats(session)
    self.assertTrimDictEqual(dict(clitree=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC, hereAdd=1, peerAdd=1)), stats)

  # #----------------------------------------------------------------------------
  # def test_sync_tree(self):
  #   self.doFirstSync()

  #----------------------------------------------------------------------------
  def test_sync_tree_clientupdate(self):

    # first, do a full sync so that the client thinks it has to send updates
    self.doFirstSync()

    # sleep for a second to ensure that anchors are updated
    time.sleep(1)

    self.initClient()
    self.assertTrue(self.client.peer is not None)
    proxy = ProxyPeer(self.context, proxy=self.client.peer)

    # then, make some changes and register them:
    #   - move "foo.txt" to "subdir/new-foo.txt"
    #   - modify subdir/bar.txt
    #   - delete subdir/bar2.txt
    dir1  = [e for e in self.items.entries.values() if e.path == 'subdir'][0]
    item1 = [e for e in self.items.entries.values() if e.path == 'foo.txt'][0]
    item2 = [e for e in self.items.entries.values() if e.path == 'subdir/bar.txt'][0]
    item3 = [e for e in self.items.entries.values() if e.path == 'subdir/bar2.txt'][0]
    item1.parent = dir1.id
    item1.path   = 'subdir/foo.txt'
    item2.body   = 'content1-modified'
    del(self.items.entries[item3.id])
    self.store.registerChange(item1.id, pysyncml.ITEM_MODIFIED)
    self.store.registerChange(item2.id, pysyncml.ITEM_MODIFIED)
    self.store.registerChange(item3.id, pysyncml.ITEM_DELETED)

    # step 2: client sends initialization & update request
    self.client.peer = proxy
    self.client.sync()

    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)

    lastAnchor = findxml(proxy.request.body, './SyncBody/Alert/Item/Meta/Anchor/Last')
    nextAnchor = findxml(proxy.request.body, './SyncBody/Alert/Item/Meta/Anchor/Next')
    self.assertTrue(lastAnchor is not None)
    self.assertTrue(nextAnchor is not None)
    self.assertIntsNear(ts(), int(lastAnchor), offset=2)
    self.assertIntsNear(ts(), int(nextAnchor), offset=1)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>2</SessionID>'
                '  <MsgID>1</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                '  <Cred>'
                '    <Meta>'
                '      <Format xmlns="syncml:metinf">b64</Format>'
                '      <Type xmlns="syncml:metinf">syncml:auth-basic</Type>'
                '    </Meta>'
                '    <Data>Z3Vlc3Q6Z3Vlc3Q=</Data>'
                '  </Cred>'
                '  <Meta>'
                '   <MaxMsgSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxMsgSize>'
                '   <MaxObjSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxObjSize>'
                '  </Meta>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Alert>'
                '   <CmdID>1</CmdID>'
                '   <Data>200</Data>'
                '   <Item>'
                '    <Source><LocURI>clitree</LocURI></Source>'
                '    <Target><LocURI>srvtree</LocURI></Target>'
                '    <Meta>'
                '     <Anchor xmlns="syncml:metinf">'
                '      <Last>' + lastAnchor + '</Last>'
                '      <Next>' + nextAnchor + '</Next>'
                '     </Anchor>'
                '     <MaxObjSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxObjSize>'
                '    </Meta>'
                '   </Item>'
                '  </Alert>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')

    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)

    # step 3: server responds, client sends local changes
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>2</SessionID>'
                     '  <MsgID>1</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>1</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>212</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>2</CmdID>'
                     '   <MsgRef>1</MsgRef>'
                     '   <CmdRef>1</CmdRef>'
                     '   <Cmd>Alert</Cmd>'
                     '   <SourceRef>clitree</SourceRef>'
                     '   <TargetRef>srvtree</TargetRef>'
                     '   <Data>200</Data>'
                     '   <Item>'
                     '    <Data>'
                     '     <Anchor xmlns="syncml:metinf"><Next>' + str(int(time.time())) + '</Next></Anchor>'
                     '    </Data>'
                     '   </Item>'
                     '  </Status>'
                     '  <Alert>'
                     '   <CmdID>3</CmdID>'
                     '   <Data>200</Data>'
                     '   <Item>'
                     '    <Source><LocURI>srvtree</LocURI></Source>'
                     '    <Target><LocURI>clitree</LocURI></Target>'
                     '    <Meta>'
                     '     <Anchor xmlns="syncml:metinf">'
                     '      <Last>' + lastAnchor + '</Last>'
                     '      <Next>' + nextAnchor + '</Next>'
                     '     </Anchor>'
                     '     <MaxObjSize xmlns="syncml:metinf">' + str(getMaxMemorySize()) + '</MaxObjSize>'
                     '    </Meta>'
                     '   </Item>'
                     '  </Alert>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    proxy.sendResponse(response)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>2</SessionID>'
                '  <MsgID>2</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Status>'
                '   <CmdID>1</CmdID>'
                '   <MsgRef>1</MsgRef>'
                '   <CmdRef>0</CmdRef>'
                '   <Cmd>SyncHdr</Cmd>'
                '   <SourceRef>http://www.example.com/sync</SourceRef>'
                '   <TargetRef>' + __name__ + '.client</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>2</CmdID>'
                '   <MsgRef>1</MsgRef>'
                '   <CmdRef>3</CmdRef>'
                '   <Cmd>Alert</Cmd>'
                '   <SourceRef>srvtree</SourceRef>'
                '   <TargetRef>clitree</TargetRef>'
                '   <Data>200</Data>'
                '   <Item>'
                '    <Data>'
                '     <Anchor xmlns="syncml:metinf">'
                # TODO: these are the wrong anchors... i should be
                #       carrying them over from the call to doFirstSync()...
                #       fortunately both client and server use the same algorithm
                #       so this works out...
                '      <Last>' + lastAnchor + '</Last>'
                '      <Next>' + nextAnchor + '</Next>'
                '     </Anchor>'
                '    </Data>'
                '   </Item>'
                '  </Status>'
                '  <Sync>'
                '   <CmdID>3</CmdID>'
                '   <Source><LocURI>clitree</LocURI></Source>'
                '   <Target><LocURI>srvtree</LocURI></Target>'
                '   <NumberOfChanges>3</NumberOfChanges>'
                '   <Replace>'
                '    <CmdID>4</CmdID>'
                '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-file+xml</Type></Meta>'
                '    <Item>'
                '     <Source><LocURI>1001</LocURI></Source>'
                '     <SourceParent><LocURI>1002</LocURI></SourceParent>'
                # TODO: is it really necessary to send the file content?... it hasn't changed!
                '     <Data>&lt;File&gt;&lt;name&gt;foo.txt&lt;/name&gt;&lt;body&gt;content0&lt;/body&gt;&lt;/File&gt;</Data>'
                '    </Item>'
                '   </Replace>'
                '   <Replace>'
                '    <CmdID>5</CmdID>'
                '    <Meta><Type xmlns="syncml:metinf">application/vnd.omads-file+xml</Type></Meta>'
                '    <Item>'
                '     <Source><LocURI>1003</LocURI></Source>'
                '     <SourceParent><LocURI>1002</LocURI></SourceParent>'
                '     <Data>&lt;File&gt;&lt;name&gt;bar.txt&lt;/name&gt;&lt;body&gt;content1-modified&lt;/body&gt;&lt;/File&gt;</Data>'
                '    </Item>'
                '   </Replace>'
                '   <Delete>'
                '    <CmdID>6</CmdID>'
                '    <Item>'
                '     <Source><LocURI>1004</LocURI></Source>'
                '    </Item>'
                '   </Delete>'
                '  </Sync>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')

    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)
    self.assertEqual('http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048', proxy.session.respUri)

    # step 4: server responds (nothing to sync in this case)
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>2</SessionID>'
                     '  <MsgID>2</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>2</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>3</CmdRef>'
                     '   <Cmd>Sync</Cmd>'
                     '   <SourceRef>clitree</SourceRef>'
                     '   <TargetRef>srvtree</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>3</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>4</CmdRef>'
                     '   <Cmd>Replace</Cmd>'
                     '   <SourceRef>1001</SourceRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>4</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>5</CmdRef>'
                     '   <Cmd>Replace</Cmd>'
                     '   <SourceRef>1003</SourceRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Status>'
                     '   <CmdID>5</CmdID>'
                     '   <MsgRef>2</MsgRef>'
                     '   <CmdRef>6</CmdRef>'
                     '   <Cmd>Delete</Cmd>'
                     '   <SourceRef>1004</SourceRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Sync>'
                     '   <CmdID>6</CmdID>'
                     '   <Source><LocURI>srvtree</LocURI></Source>'
                     '   <Target><LocURI>clitree</LocURI></Target>'
                     '   <NumberOfChanges>0</NumberOfChanges>'
                     '  </Sync>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    proxy.sendResponse(response)

    chk = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                body=
                '<SyncML>'
                ' <SyncHdr>'
                '  <VerDTD>1.2</VerDTD>'
                '  <VerProto>SyncML/1.2</VerProto>'
                '  <SessionID>2</SessionID>'
                '  <MsgID>3</MsgID>'
                '  <Source>'
                '   <LocURI>' + __name__ + '.client</LocURI>'
                '   <LocName>In-Memory Test Client</LocName>'
                '  </Source>'
                '  <Target>'
                '   <LocURI>http://www.example.com/sync</LocURI>'
                '  </Target>'
                ' </SyncHdr>'
                ' <SyncBody>'
                '  <Status>'
                '   <CmdID>1</CmdID>'
                '   <MsgRef>2</MsgRef>'
                '   <CmdRef>0</CmdRef>'
                '   <Cmd>SyncHdr</Cmd>'
                '   <SourceRef>http://www.example.com/sync</SourceRef>'
                '   <TargetRef>' + __name__ + '.client</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>2</CmdID>'
                '   <MsgRef>2</MsgRef>'
                '   <CmdRef>6</CmdRef>'
                '   <Cmd>Sync</Cmd>'
                '   <SourceRef>srvtree</SourceRef>'
                '   <TargetRef>clitree</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')
    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(chk.headers['content-type'], proxy.request.contentType)
    self.assertEqualXml(chk.body, proxy.request.body)

    # step 5: server responds with status to header, and client terminates
    response = adict(headers=dict((('content-type', 'application/vnd.syncml+xml; charset=UTF-8'),)),
                     body=
                     '<SyncML>'
                     ' <SyncHdr>'
                     '  <VerDTD>1.2</VerDTD>'
                     '  <VerProto>SyncML/1.2</VerProto>'
                     '  <SessionID>2</SessionID>'
                     '  <MsgID>3</MsgID>'
                     '  <Source>'
                     '   <LocURI>http://www.example.com/sync</LocURI>'
                     '   <LocName>Fake Server</LocName>'
                     '  </Source>'
                     '  <Target>'
                     '   <LocURI>' + __name__ + '.client</LocURI>'
                     '   <LocName>In-Memory Test Client</LocName>'
                     '  </Target>'
                     '  <RespURI>http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048</RespURI>'
                     ' </SyncHdr>'
                     ' <SyncBody>'
                     '  <Status>'
                     '   <CmdID>1</CmdID>'
                     '   <MsgRef>3</MsgRef>'
                     '   <CmdRef>0</CmdRef>'
                     '   <Cmd>SyncHdr</Cmd>'
                     '   <SourceRef>' + __name__ + '.client</SourceRef>'
                     '   <TargetRef>http://www.example.com/sync</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Final/>'
                     ' </SyncBody>'
                     '</SyncML>')
    session = proxy.session
    proxy.sendResponse(response)
    self.assertFalse(proxy.pending)
    # this is only because i've interrupted the normal Adapter handling...
    self.client._dbsave()
    stats = self.client._session2stats(session)
    self.assertTrimDictEqual(dict(clitree=stat(mode=pysyncml.SYNCTYPE_TWO_WAY, peerMod=2, peerDel=1)), stats)

#  #----------------------------------------------------------------------------
#  def test_sync_tree_serverupdate(self):
#    # TODO: copy test_sync_tree_clientupdate, except make changes flow the
#    #       other way and confirm the result of the operations...
#    raise NotImplementedError()

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
