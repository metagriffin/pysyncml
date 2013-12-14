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
import sqlalchemy as sa, pxml

import pysyncml
from .common import adict, ts_iso, getAddressSize, getMaxMemorySize
from . import test_helpers
from .items.note import NoteItem
from .test_helpers import setlogging, makestats as stat

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
    self.nextID += 1
    self.entries[item.id] = item
    return item
  def get(self, itemID):
    return self.entries[int(itemID)]
  def replace(self, item, reportChanges):
    self.entries[int(item.id)] = item
    return None
  def delete(self, itemID):
    del self.entries[int(itemID)]

#------------------------------------------------------------------------------
class Agent(pysyncml.BaseNoteAgent):
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
  def __init__(self, context, **kw):
    self.proxy   = context.RemoteAdapter(**kw)
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

#------------------------------------------------------------------------------
class TestClient(unittest.TestCase, pxml.XmlTestMixin):

  maxDiff = None

  #----------------------------------------------------------------------------
  def setUp(self):
    self.initDatabases()
    self.initClient()

  #----------------------------------------------------------------------------
  def initDatabases(self):
    self.items = ItemStorage(nextID=1000)
    self.db    = sa.create_engine('sqlite://')
    # if os.path.exists('../test.db'):
    #   os.unlink('../test.db')
    # self.db = sa.create_engine('sqlite:///../test.db')
    pysyncml.enableSqliteCascadingDeletes(self.db)

  #----------------------------------------------------------------------------
  def initClient(self):
    self.context = pysyncml.Context(engine=self.db, owner=None, autoCommit=True)
    self.store   = self.context.Store(uri='cli_memo', displayName='MemoTaker',
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
  def test_sync_client_note(self):
    proxy = ProxyPeer(self.context,
                      url='http://www.example.com/sync',
                      auth=pysyncml.NAMESPACE_AUTH_BASIC,
                      username='guest', password='guest')
    # step 1: client sends registration/initialization
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
                '       <SourceRef>cli_memo</SourceRef>'
                '       <DisplayName>MemoTaker</DisplayName>'
                '       <MaxGUIDSize>' + str(getAddressSize()) + '</MaxGUIDSize>'
                '       <MaxObjSize>' + str(getMaxMemorySize()) + '</MaxObjSize>'
                '       <Rx-Pref><CTType>text/x-s4j-sifn</CTType><VerCT>1.1</VerCT></Rx-Pref>'
                '       <Rx><CTType>text/x-s4j-sifn</CTType><VerCT>1.0</VerCT></Rx>'
                '       <Rx><CTType>text/plain</CTType><VerCT>1.1</VerCT></Rx>'
                '       <Rx><CTType>text/plain</CTType><VerCT>1.0</VerCT></Rx>'
                '       <Tx-Pref><CTType>text/x-s4j-sifn</CTType><VerCT>1.1</VerCT></Tx-Pref>'
                '       <Tx><CTType>text/x-s4j-sifn</CTType><VerCT>1.0</VerCT></Tx>'
                '       <Tx><CTType>text/plain</CTType><VerCT>1.1</VerCT></Tx>'
                '       <Tx><CTType>text/plain</CTType><VerCT>1.0</VerCT></Tx>'
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
    self.assertEqual(proxy.request.contentType, chk.headers['content-type'])
    self.assertXmlEqual(proxy.request.body, chk.body)

    # step 2: server responds, client sets up routes and requests sync
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
                     '       <SourceRef>srv_note</SourceRef>'
                     '       <DisplayName>Note Storage</DisplayName>'
                     '       <MaxGUIDSize>' + str(getAddressSize()) + '</MaxGUIDSize>'
                     '       <Rx-Pref><CTType>text/x-s4j-sifn</CTType><VerCT>1.1</VerCT></Rx-Pref>'
                     '       <Rx><CTType>text/x-s4j-sifn</CTType><VerCT>1.0</VerCT></Rx>'
                     '       <Rx><CTType>text/plain</CTType><VerCT>1.1</VerCT><VerCT>1.0</VerCT></Rx>'
                     '       <Tx-Pref><CTType>text/x-s4j-sifn</CTType><VerCT>1.1</VerCT></Tx-Pref>'
                     '       <Tx><CTType>text/x-s4j-sifn</CTType><VerCT>1.0</VerCT></Tx>'
                     '       <Tx><CTType>text/plain</CTType><VerCT>1.1</VerCT><VerCT>1.0</VerCT></Tx>'
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
                '    <Source><LocURI>cli_memo</LocURI></Source>'
                '    <Target><LocURI>srv_note</LocURI></Target>'
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
    self.assertEqual(proxy.request.contentType, chk.headers['content-type'])
    self.assertXmlEqual(proxy.request.body, chk.body)
    self.assertEqual(proxy.session.respUri, 'http://www.example.com/sync;s=9D35ACF5AEDDD26AC875EE1286F3C048')

    # step 3: server responds, client sends all of its data (none in this case)
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
                     '   <SourceRef>cli_memo</SourceRef>'
                     '   <TargetRef>srv_note</TargetRef>'
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
                     '    <Source><LocURI>srv_note</LocURI></Source>'
                     '    <Target><LocURI>cli_memo</LocURI></Target>'
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
                '   <SourceRef>srv_note</SourceRef>'
                '   <TargetRef>cli_memo</TargetRef>'
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
                '   <Source><LocURI>cli_memo</LocURI></Source>'
                '   <Target><LocURI>srv_note</LocURI></Target>'
                '   <NumberOfChanges>0</NumberOfChanges>'
                '  </Sync>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')
    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(proxy.request.contentType, chk.headers['content-type'])
    self.assertXmlEqual(proxy.request.body, chk.body)

    # step 4: server responds, client sends mapping
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
                     '   <SourceRef>cli_memo</SourceRef>'
                     '   <TargetRef>srv_note</TargetRef>'
                     '   <Data>200</Data>'
                     '  </Status>'
                     '  <Sync>'
                     '   <CmdID>3</CmdID>'
                     '   <Source><LocURI>srv_note</LocURI></Source>'
                     '   <Target><LocURI>cli_memo</LocURI></Target>'
                     '   <NumberOfChanges>1</NumberOfChanges>'
                     '   <Add>'
                     '    <CmdID>4</CmdID>'
                     '    <Meta><Type xmlns="syncml:metinf">text/plain</Type></Meta>'
                     '    <Item>'
                     '     <Source><LocURI>50</LocURI></Source>'
                     '     <Data>some text content</Data>'
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
                '   <CmdRef>3</CmdRef>'
                '   <Cmd>Sync</Cmd>'
                '   <SourceRef>srv_note</SourceRef>'
                '   <TargetRef>cli_memo</TargetRef>'
                '   <Data>200</Data>'
                '  </Status>'
                '  <Status>'
                '   <CmdID>3</CmdID>'
                '   <MsgRef>3</MsgRef>'
                '   <CmdRef>4</CmdRef>'
                '   <Cmd>Add</Cmd>'
                '   <SourceRef>50</SourceRef>'
                '   <Data>201</Data>'
                '  </Status>'
                '  <Map>'
                '   <CmdID>4</CmdID>'
                '   <Source><LocURI>cli_memo</LocURI></Source>'
                '   <Target><LocURI>srv_note</LocURI></Target>'
                '   <MapItem>'
                '    <Source><LocURI>1000</LocURI></Source>'
                '    <Target><LocURI>50</LocURI></Target>'
                '   </MapItem>'
                '  </Map>'
                '  <Final/>'
                ' </SyncBody>'
                '</SyncML>')
    self.assertTrue(proxy.pending)
    self.assertTrue(proxy.request is not None)
    self.assertEqual(proxy.request.contentType, chk.headers['content-type'])
    self.assertXmlEqual(proxy.request.body, chk.body)
    self.assertEqual(self.items.entries.keys(), [1000])
    self.assertEqual(self.items.entries[1000].body, 'some text content')

    # step 5: server responds, client sends nothing
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
                     '   <SourceRef>cli_memo</SourceRef>'
                     '   <TargetRef>srv_note</TargetRef>'
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
    self.assertEqual(
      stats,
      dict(cli_memo=stat(mode=pysyncml.SYNCTYPE_SLOW_SYNC, hereAdd=1)))

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
