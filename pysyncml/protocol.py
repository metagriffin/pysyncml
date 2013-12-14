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
The ``pysyncml.protocol`` is an internal package that does all of the actual
"work" for the SyncML Adapter.
'''

import sys, time, base64, logging, traceback
import xml.etree.ElementTree as ET
from . import common, constants, state

log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
def badStatus(xnode):
  code  = xnode.findtext('Data')
  cname = xnode.findtext('Cmd')
  msg   = 'unexpected status code %s for command "%s"' % (code, cname)
  xerr  = xnode.find('Error')
  if xerr is not None:
    msg += ': [%s] %s' % (xerr.findtext('Code'), xerr.findtext('Message'))
  return common.ProtocolError(msg)

#------------------------------------------------------------------------------
class Protocol(object):

  #----------------------------------------------------------------------------
  def __init__(self, adapter, *args, **kw):
    super(Protocol, self).__init__(*args, **kw)

  #----------------------------------------------------------------------------
  @staticmethod
  def getAuthInfo(xtree, uri, authorizer):
    if authorizer is None:
     authorizer = common.adict(authorize=lambda uri, data: data)
    assert xtree.tag == 'SyncML'
    xcred = xtree.find('SyncHdr/Cred')
    if xcred is None:
      return authorizer.authorize(uri, None)
    data = xcred.findtext('Data')
    authtype = xcred.findtext('Meta/Type')
    if authtype not in (constants.NAMESPACE_AUTH_BASIC, constants.NAMESPACE_AUTH_MD5):
      raise common.UnknownAuthType(authtype)
    format = xcred.findtext('Meta/Format')
    if format == constants.FORMAT_B64:
      data = base64.b64decode(data)
    elif format is not None:
      raise common.UnknownFormatType(format)
    if authtype == constants.NAMESPACE_AUTH_BASIC:
      data = data.split(':', 1)
      data = common.adict(auth=constants.NAMESPACE_AUTH_BASIC,
                          username=data[0], password=data[1])
      return authorizer.authorize(uri, data)
    if authtype == constants.NAMESPACE_AUTH_MD5:
      data = common.adict(auth=constants.NAMESPACE_AUTH_BASIC, digest=data)
      return authorizer.authorize(uri, data)
    raise common.UnknownAuthType('unknown/unimplemented auth type "%s"' % (authtype,))

  #----------------------------------------------------------------------------
  @staticmethod
  def getTargetID(xtree):
    assert xtree.tag == 'SyncML'
    # todo: do more validity checks?...
    return xtree.findtext('SyncHdr/Target/LocURI')

  #----------------------------------------------------------------------------
  def initialize(self, adapter, session, xsync=None):
    cmd = state.Command(
      name        = constants.CMD_SYNCHDR,
      cmdID       = 0,
      version     = constants.SYNCML_VERSION_1_2,
      source      = session.effectiveID or adapter.devID,
      sourceName  = adapter.name,
      )
    if session.isServer:
      xhdr = xsync.find('SyncHdr')
      peerID = xhdr.findtext('Source/LocURI')
      if session.peerID is not None and session.peerID != peerID:
        log.error('unexpected peer ID "%s" (expected "%s")', peerID, session.peerID)
        raise common.ProtocolError('unexpected peer ID "%s"' % (peerID,))
      if adapter.peer is not None and adapter.peer.devID != peerID:
        log.error('unacceptable peer ID "%s" (expected "%s")', peerID, adapter.peer.devID)
        raise common.ProtocolError('unacceptable peer ID "%s"' % (peerID,))
      session.peerID = peerID
      session.id     = int(xhdr.findtext('SessionID'))
      session.msgID  = int(xhdr.findtext('MsgID'))
      if adapter.peer is None or adapter.peer.devID != peerID:
        for peer in adapter.getKnownPeers():
          # TODO: i should delete unused peers here... ie. anything that
          #       hasn't been used in some configurable number of seconds,
          #       which should probably default to something like a month.
          if peer.devID == peerID:
            adapter.peer = peer
            break
        else:
          log.info('registering new peer "%s"' % (peerID,))
          peer = adapter._context._model.Adapter(devID=peerID, isLocal=False)
          if xhdr.findtext('Source/LocName') is not None:
            peer.name = xhdr.findtext('Source/LocName')
          if xhdr.findtext('Meta/MaxMsgSize') is not None:
            peer.maxMsgSize = long(xhdr.findtext('Meta/MaxMsgSize'))
          if xhdr.findtext('Meta/MaxObjSize') is not None:
            peer.maxObjSize = long(xhdr.findtext('Meta/MaxObjSize'))
          adapter.peer = peer
      if session.returnUrl is not None:
        cmd.respUri = session.returnUrl
    session.pendingMsgID = session.msgID if session.isServer else session.lastMsgID
    session.cmdID        = 0
    cmd.sessionID   = session.id
    cmd.msgID       = session.msgID
    cmd.target      = adapter.peer.devID
    cmd.targetName  = adapter.peer.name
    cmd.auth        = adapter.peer.auth
    if session.msgID == 1:
      # NOTE: normally, the "server" would not send this info. however, in
      #       the pysyncml world where it is much more peer-oriented
      #       instead of client/server, i send this as well... the
      #       idea being, if two "client" peers are communicating in
      #       the event of server unavailability, then they may need
      #       to know each-others limitations...
      cmd.maxMsgSize = common.getMaxMemorySize(adapter.context)
      cmd.maxObjSize = common.getMaxMemorySize(adapter.context)
    return [cmd]

  #----------------------------------------------------------------------------
  def negotiate(self, adapter, session, commands):

    # todo: determine why i decided to copy the commands...
    commands = commands[:]

    if len(commands) > 0 and commands[-1].name == constants.CMD_FINAL:
      return commands

    if len(commands) > 0 \
       and commands[-1].name == constants.CMD_ALERT \
       and commands[-1].data == constants.STATUS_NEXT_MESSAGE:
      # todo: should i add a "final" here?...
      # commands.append(state.Command(name=constants.CMD_FINAL))
      return commands

    # request the remote device info if not currently available
    if adapter.peer.devinfo is None:
      log.debug('no peer.devinfo - requesting from target (and sending source devinfo)')
      commands.append(state.Command(
        name       = constants.CMD_PUT,
        cmdID      = session.nextCmdID,
        type       = constants.TYPE_SYNCML_DEVICE_INFO + '+' + adapter.codec.name,
        source     = './' + constants.URI_DEVINFO_1_2,
        data       = adapter.devinfo.toSyncML(constants.SYNCML_DTD_VERSION_1_2, adapter.stores.values()),
        ))
      commands.append(state.Command(
        name     = constants.CMD_GET,
        cmdID    = session.nextCmdID,
        type     = constants.TYPE_SYNCML_DEVICE_INFO + '+' + adapter.codec.name,
        target   = './' + constants.URI_DEVINFO_1_2,
        ))
    else:
      log.debug('have peer.devinfo - not requesting from target')
      commands += adapter.synchronizer.actions(adapter, session) or []

    commands.append(state.Command(name=constants.CMD_FINAL))
    return commands

  #----------------------------------------------------------------------------
  def commands2tree(self, adapter, session, commands):
    '''Consumes state.Command commands and converts them to an ET protocol tree'''

    # todo: trap errors...

    hdrcmd = commands[0]
    commands = commands[1:]

    if hdrcmd.name != constants.CMD_SYNCHDR:
      raise common.InternalError('unexpected first command "%s" (expected "%s")'
                                 % (hdrcmd.name, constants.CMD_SYNCHDR))

    if hdrcmd.version != constants.SYNCML_VERSION_1_2:
      raise common.FeatureNotSupported('unsupported SyncML version "%s"' % (hdrcmd.version,))

    xsync = ET.Element(constants.NODE_SYNCML)
    xhdr  = ET.SubElement(xsync, hdrcmd.name)
    if hdrcmd.version == constants.SYNCML_VERSION_1_2:
      ET.SubElement(xhdr, 'VerDTD').text = constants.SYNCML_DTD_VERSION_1_2
      ET.SubElement(xhdr, 'VerProto').text = hdrcmd.version

    ET.SubElement(xhdr, 'SessionID').text = hdrcmd.sessionID
    ET.SubElement(xhdr, 'MsgID').text = hdrcmd.msgID
    xsrc = ET.SubElement(xhdr, 'Source')
    ET.SubElement(xsrc, 'LocURI').text = hdrcmd.source
    if hdrcmd.sourceName is not None:
      ET.SubElement(xsrc, 'LocName').text = hdrcmd.sourceName
    xtgt = ET.SubElement(xhdr, 'Target')
    ET.SubElement(xtgt, 'LocURI').text = hdrcmd.target
    if hdrcmd.targetName is not None:
      ET.SubElement(xtgt, 'LocName').text = hdrcmd.targetName
    if hdrcmd.respUri is not None:
      ET.SubElement(xhdr, 'RespURI').text = hdrcmd.respUri

    if hdrcmd.auth is not None and not session.authAccepted:
      if hdrcmd.auth != constants.NAMESPACE_AUTH_BASIC:
        raise NotImplementedError('auth method "%s"' % (common.auth2string(hdrcmd.auth),))
      if hdrcmd.auth == constants.NAMESPACE_AUTH_BASIC:
        xcred = ET.SubElement(xhdr, 'Cred')
        xmeta = ET.SubElement(xcred, 'Meta')
        ET.SubElement(xmeta, 'Format', {'xmlns': constants.NAMESPACE_METINF}).text = 'b64'
        ET.SubElement(xmeta, 'Type', {'xmlns': constants.NAMESPACE_METINF}).text   = hdrcmd.auth
        ET.SubElement(xcred, 'Data').text = base64.b64encode(
          '%s:%s' % (adapter.peer.username, adapter.peer.password))
    if hdrcmd.maxMsgSize is not None or hdrcmd.maxObjSize is not None:
      xmeta = ET.SubElement(xhdr, 'Meta')
      if hdrcmd.maxMsgSize is not None:
        ET.SubElement(xmeta, 'MaxMsgSize', {'xmlns': constants.NAMESPACE_METINF}).text = hdrcmd.maxMsgSize
      if hdrcmd.maxObjSize is not None:
        ET.SubElement(xmeta, 'MaxObjSize', {'xmlns': constants.NAMESPACE_METINF}).text = hdrcmd.maxObjSize

    xbody = ET.SubElement(xsync, constants.NODE_SYNCBODY)

    for cmdidx, cmd in enumerate(commands):

      xcmd = ET.SubElement(xbody, cmd.name)
      if cmd.cmdID is not None:
        ET.SubElement(xcmd, 'CmdID').text = cmd.cmdID

      if cmd.name == constants.CMD_ALERT:
        ET.SubElement(xcmd, 'Data').text = str(cmd.data)
        xitem = ET.SubElement(xcmd, 'Item')
        ET.SubElement(ET.SubElement(xitem, 'Source'), 'LocURI').text = cmd.source
        ET.SubElement(ET.SubElement(xitem, 'Target'), 'LocURI').text = cmd.target
        if cmd.lastAnchor is not None \
           or cmd.nextAnchor is not None \
           or cmd.maxObjSize is not None:
          xmeta = ET.SubElement(xitem, 'Meta')
          xanch = ET.SubElement(xmeta, 'Anchor', {'xmlns': constants.NAMESPACE_METINF})
          if cmd.lastAnchor is not None:
            ET.SubElement(xanch, 'Last').text = cmd.lastAnchor
          if cmd.nextAnchor is not None:
            ET.SubElement(xanch, 'Next').text = cmd.nextAnchor
          if cmd.maxObjSize is not None:
            ET.SubElement(xmeta, 'MaxObjSize', {'xmlns': constants.NAMESPACE_METINF}).text = cmd.maxObjSize
        continue

      if cmd.name == constants.CMD_STATUS:
        ET.SubElement(xcmd, 'MsgRef').text    = cmd.msgRef
        ET.SubElement(xcmd, 'CmdRef').text    = cmd.cmdRef
        ET.SubElement(xcmd, 'Cmd').text       = cmd.statusOf
        if cmd.sourceRef is not None:
          ET.SubElement(xcmd, 'SourceRef').text = cmd.sourceRef
        if cmd.targetRef is not None:
          ET.SubElement(xcmd, 'TargetRef').text = cmd.targetRef
        ET.SubElement(xcmd, 'Data').text      = cmd.statusCode
        if cmd.nextAnchor is not None or cmd.lastAnchor is not None:
          xdata = ET.SubElement(ET.SubElement(xcmd, 'Item'), 'Data')
          xanch = ET.SubElement(xdata, 'Anchor', {'xmlns': constants.NAMESPACE_METINF})
          if cmd.lastAnchor is not None:
            ET.SubElement(xanch, 'Last').text = cmd.lastAnchor
          if cmd.nextAnchor is not None:
            ET.SubElement(xanch, 'Next').text = cmd.nextAnchor
        # NOTE: this is NOT standard SyncML...
        if cmd.errorCode is not None or cmd.errorMsg is not None:
          xerr = ET.SubElement(xcmd, 'Error')
          if cmd.errorCode is not None:
            ET.SubElement(xerr, 'Code').text = cmd.errorCode
          if cmd.errorMsg is not None:
            ET.SubElement(xerr, 'Message').text = cmd.errorMsg
          if cmd.errorTrace is not None:
            ET.SubElement(xerr, 'Trace').text = cmd.errorTrace
        continue

      if cmd.name in [constants.CMD_GET, constants.CMD_PUT]:
        ET.SubElement(ET.SubElement(xcmd, 'Meta'), 'Type',
                      {'xmlns': constants.NAMESPACE_METINF}).text = cmd.type
        if cmd.source is not None or cmd.target is not None or cmd.data:
          xitem = ET.SubElement(xcmd, 'Item')
        if cmd.source is not None:
          xsrc = ET.SubElement(xitem, 'Source')
          ET.SubElement(xsrc, 'LocURI').text  = cmd.source
          ET.SubElement(xsrc, 'LocName').text = cmd.source
        if cmd.target is not None:
          xtgt = ET.SubElement(xitem, 'Target')
          ET.SubElement(xtgt, 'LocURI').text  = cmd.target
          ET.SubElement(xtgt, 'LocName').text = cmd.target
        if cmd.data is not None:
          if isinstance(cmd.data, basestring):
            ET.SubElement(xitem, 'Data').text = cmd.data
          else:
            ET.SubElement(xitem, 'Data').append(cmd.data)
        continue

      if cmd.name == constants.CMD_RESULTS:
        ET.SubElement(xcmd, 'MsgRef').text    = cmd.msgRef
        ET.SubElement(xcmd, 'CmdRef').text    = cmd.cmdRef
        ET.SubElement(ET.SubElement(xcmd, 'Meta'), 'Type',
                      {'xmlns': constants.NAMESPACE_METINF}).text = cmd.type
        xitem = ET.SubElement(xcmd, 'Item')
        xsrc = ET.SubElement(xitem, 'Source')
        ET.SubElement(xsrc, 'LocURI').text  = cmd.source
        ET.SubElement(xsrc, 'LocName').text = cmd.source
        if cmd.data is not None:
          if isinstance(cmd.data, basestring):
            ET.SubElement(xitem, 'Data').text = cmd.data
          else:
            ET.SubElement(xitem, 'Data').append(cmd.data)
        continue

      if cmd.name == constants.CMD_SYNC:
        ET.SubElement(ET.SubElement(xcmd, 'Source'), 'LocURI').text = cmd.source
        ET.SubElement(ET.SubElement(xcmd, 'Target'), 'LocURI').text = cmd.target
        if cmd.noc is not None:
          ET.SubElement(xcmd, 'NumberOfChanges').text = cmd.noc
        if cmd.data is not None:
          for scmd in cmd.data:
            xscmd = ET.SubElement(xcmd, scmd.name)
            if scmd.cmdID is not None:
              ET.SubElement(xscmd, 'CmdID').text = scmd.cmdID
            if scmd.type is not None or \
              ( scmd.format is not None and scmd.format != constants.FORMAT_AUTO ):
              xsmeta = ET.SubElement(xscmd, 'Meta')
              # todo: implement auto encoding determination...
              #       (the current implementation just lets XML encoding do it,
              #        which is for most things good enough, but not so good
              #        for sequences that need a large amount escaping such as
              #        binary data...)
              if scmd.format is not None and scmd.format != constants.FORMAT_AUTO:
                ET.SubElement(xsmeta, 'Format', {'xmlns': constants.NAMESPACE_METINF}).text = scmd.format
              if scmd.type is not None:
                ET.SubElement(xsmeta, 'Type', {'xmlns': constants.NAMESPACE_METINF}).text = scmd.type
            xsitem = ET.SubElement(xscmd, 'Item')
            if scmd.source is not None:
              ET.SubElement(ET.SubElement(xsitem, 'Source'), 'LocURI').text = scmd.source
            if scmd.sourceParent is not None:
              ET.SubElement(ET.SubElement(xsitem, 'SourceParent'), 'LocURI').text = scmd.sourceParent
            if scmd.target is not None:
              ET.SubElement(ET.SubElement(xsitem, 'Target'), 'LocURI').text = scmd.target
            if scmd.targetParent is not None:
              ET.SubElement(ET.SubElement(xsitem, 'TargetParent'), 'LocURI').text = scmd.targetParent
            if scmd.data is not None:
              if isinstance(scmd.data, basestring):
                ET.SubElement(xsitem, 'Data').text = scmd.data
              else:
                ET.SubElement(xsitem, 'Data').append(scmd.data)
        continue

      if cmd.name == constants.CMD_MAP:
        ET.SubElement(ET.SubElement(xcmd, 'Source'), 'LocURI').text = cmd.source
        ET.SubElement(ET.SubElement(xcmd, 'Target'), 'LocURI').text = cmd.target
        if cmd.sourceItem is not None or cmd.targetItem is not None:
          xitem = ET.SubElement(xcmd, constants.CMD_MAPITEM)
          if cmd.sourceItem is not None:
            ET.SubElement(ET.SubElement(xitem, 'Source'), 'LocURI').text = cmd.sourceItem
          if cmd.targetItem is not None:
            ET.SubElement(ET.SubElement(xitem, 'Target'), 'LocURI').text = cmd.targetItem
        continue

      if cmd.name == constants.CMD_FINAL:
        if cmdidx + 1 < len(commands):
          raise common.InternalError('command "%s" not at tail end of commands' % (cmd.name,))
        continue

      raise common.InternalError('unexpected command "%s"' % (cmd.name,))

    return xsync

  #----------------------------------------------------------------------------
  def tree2commands(self, adapter, session, lastcmds, xsync):
    '''Consumes an ET protocol tree and converts it to state.Command commands'''

    # do some preliminary sanity checks...
    # todo: do i really want to be using assert statements?...

    assert xsync.tag == constants.NODE_SYNCML
    assert len(xsync) == 2
    assert xsync[0].tag == constants.CMD_SYNCHDR
    assert xsync[1].tag == constants.NODE_SYNCBODY

    version = xsync[0].findtext('VerProto')
    if version != constants.SYNCML_VERSION_1_2:
      raise common.FeatureNotSupported('unsupported SyncML version "%s" (expected "%s")' \
                                       % (version, constants.SYNCML_VERSION_1_2))
    verdtd = xsync[0].findtext('VerDTD')
    if verdtd != constants.SYNCML_DTD_VERSION_1_2:
      raise common.FeatureNotSupported('unsupported SyncML DTD version "%s" (expected "%s")' \
                                       % (verdtd, constants.SYNCML_DTD_VERSION_1_2))

    ret = self.initialize(adapter, session, xsync)
    hdrcmd = ret[0]

    if session.isServer:
      log.debug('received request SyncML message from "%s" (s%s.m%s)',
                hdrcmd.target, hdrcmd.sessionID, hdrcmd.msgID)
    else:
      log.debug('received response SyncML message from "%s" (s%s.m%s)',
                lastcmds[0].target, lastcmds[0].sessionID, lastcmds[0].msgID)

    try:
      return self._tree2commands(adapter, session, lastcmds, xsync, ret)
    except Exception, e:
      if not session.isServer:
        raise
      # TODO: make this configurable as to whether or not any error
      #       is sent back to the peer as a SyncML "standardized" error
      #       status...
      code = '%s.%s' % (e.__class__.__module__, e.__class__.__name__)
      msg  = ''.join(traceback.format_exception_only(type(e), e)).strip()
      log.exception('failed while interpreting command tree: %s', msg)
      # TODO: for some reason, the active exception is not being logged...
      return [
        hdrcmd,
        state.Command(
          name       = constants.CMD_STATUS,
          cmdID      = '1',
          msgRef     = session.pendingMsgID,
          cmdRef     = 0,
          sourceRef  = xsync[0].findtext('Source/LocURI'),
          targetRef  = xsync[0].findtext('Target/LocURI'),
          statusOf   = constants.CMD_SYNCHDR,
          statusCode = constants.STATUS_COMMAND_FAILED,
          errorCode  = code,
          errorMsg   = msg,
          errorTrace = ''.join(traceback.format_exception(type(e), e, sys.exc_info()[2])),
          ),
        state.Command(name=constants.CMD_FINAL)]

  #----------------------------------------------------------------------------
  def _tree2commands(self, adapter, session, lastcmds, xsync, ret):

    hdrcmd = ret[0]

    statusCode = constants.STATUS_OK

    # analyze the SyncHdr
    for child in xsync[0]:

      if child.tag == 'VerDTD':
        if hdrcmd.version == constants.SYNCML_VERSION_1_2:
          if child.text != constants.SYNCML_DTD_VERSION_1_2:
            raise common.ProtocolError('bad VerDTD "%s"' % (child.text,))
        else:
          raise common.FeatureNotSupported('unsupported internal SyncML version "%s"' \
                                           % (hdrcmd.version,))
        continue

      if child.tag == 'VerProto':
        # this was checked earlier...
        continue

      if child.tag == 'SessionID':
        if child.text != hdrcmd.sessionID:
          raise common.ProtocolError('session ID mismatch: "%s" != "%s"' % (child.text, hdrcmd.sessionID))
        continue

      if child.tag == 'MsgID':
        chkmsg = hdrcmd.msgID if session.isServer else lastcmds[0].msgID
        if child.text != chkmsg:
          raise common.ProtocolError('message ID mismatch: "%s" != "%s"' % (child.text, chkmsg))
        continue

      if child.tag == 'Target':
        uri = child.findtext('LocURI')
        if uri != hdrcmd.source:
          raise common.ProtocolError('incoming target mismatch: "%s" != "%s"' % (uri, hdrcmd.source))
        continue

      if child.tag == 'Source':
        uri = child.findtext('LocURI')
        if uri != hdrcmd.target and uri != lastcmds[0].target:
          raise common.ProtocolError('incoming source mismatch: "%s" != "%s"' % (uri, hdrcmd.target))
        continue

      if child.tag == 'RespURI':
        # hdrcmd.target = child.text
        # session.respUri = child.text
        if not session.isServer:
          session.respUri = child.text
        continue

      if child.tag == 'Cred':
        # the responsibility is on the calling framework to ensure this is
        # checked long before we get here... ie. Adapter.authorize(...)
        statusCode = constants.STATUS_AUTHENTICATION_ACCEPTED
        continue

      if child.tag == 'Meta':
        # this should already have been consumed during the protocol.initialize() call
        continue

      raise common.ProtocolError('unexpected header node "%s"' % (child.tag,))

    # send ok to the status

    ret.append(state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = session.pendingMsgID,
      cmdRef     = 0,
      sourceRef  = xsync[0].findtext('Source/LocURI'),
      targetRef  = xsync[0].findtext('Target/LocURI'),
      statusOf   = constants.CMD_SYNCHDR,
      statusCode = statusCode,
      ))

    # and now evaluate the SyncBody

    chkcmds = [e for e in lastcmds if e.name not in (constants.CMD_STATUS, constants.CMD_FINAL)]

    # for each "sync" command, search for sub-commands
    # todo: should this be generalized to search for any sub-commands?...
    for chkcmd in chkcmds:
      if chkcmd.name != constants.CMD_SYNC:
        continue
      chkcmds.extend(chkcmd.data or [])

    for chkcmd in chkcmds:
      log.debug('outstanding command node "s%s.m%s.c%s.%s"',
                session.id, lastcmds[0].msgID, chkcmd.cmdID, chkcmd.name)

    # first, check all the 'Status' commands
    for child in xsync[1]:
      if child.tag != constants.CMD_STATUS:
        continue
      cname = child.findtext('Cmd')

      log.debug('checking status node "s%s.m%s.c%s.%s"',
                session.id, child.findtext('MsgRef'), child.findtext('CmdRef'), cname)

      # match-up status command and outstanding command with Cmd, CmdRef and MsgRef...
      for chkcmd in chkcmds:
        if chkcmd.cmdID == child.findtext('CmdRef') \
           and chkcmd.name == cname \
           and lastcmds[0].msgID == child.findtext('MsgRef'):
          chkcmds.remove(chkcmd)
          break
      else:
        raise common.ProtocolError('unexpected status node s%s.mr%s.cr%s cmd=%s'
                                   % (session.id, child.findtext('MsgRef'), child.findtext('CmdRef'), cname))

      # TODO: check for unknown elements...

      code = int(child.findtext('Data'))
      # todo: any other common elements?...

      targetRef = child.findtext('TargetRef')
      if targetRef is not None:
        # note: doing a cleanUri on chkcmd.target because it could be "./devinf12"...
        assert adapter.peer.cleanUri(targetRef) == adapter.peer.cleanUri(chkcmd.target)

      sourceRef = child.findtext('SourceRef')
      if sourceRef is not None:
        # note: doing a cleanUri on chkcmd.source because it could be "./devinf12"...
        if cname == constants.CMD_SYNCHDR:
          # this is a little odd, but syncevolution strips the sessionid path
          # parameter off for some reason, so compensating here...
          assert adapter.cleanUri(sourceRef) in (adapter.cleanUri(chkcmd.source),
                                                 session.effectiveID,
                                                 session.returnUrl) \
                 or adapter.cleanUri(chkcmd.source).startswith(adapter.cleanUri(sourceRef))
        else:
          assert adapter.cleanUri(sourceRef) == adapter.cleanUri(chkcmd.source)

      if cname == constants.CMD_SYNCHDR:
        if code not in (constants.STATUS_OK, constants.STATUS_AUTHENTICATION_ACCEPTED):
          raise badStatus(child)
        if code == constants.STATUS_AUTHENTICATION_ACCEPTED:
          session.authAccepted = True
        continue

      if cname == constants.CMD_ALERT:
        if code not in (constants.STATUS_OK,):
          raise badStatus(child)
        # TODO: do something with the Item/Data/Anchor/Next...
        continue

      if cname == constants.CMD_GET:
        if code not in (constants.STATUS_OK,):
          raise badStatus(child)
        continue

      if cname == constants.CMD_PUT:
        if code not in (constants.STATUS_OK,):
          raise badStatus(child)
        continue

      if cname == constants.CMD_RESULTS:
        if code not in (constants.STATUS_OK,):
          raise badStatus(child)
        continue

      if cname == constants.CMD_SYNC:
        # todo: should this be moved into the synchronizer as a "settle" event?...
        if code not in (constants.STATUS_OK,):
          raise badStatus(child)
        ds = session.dsstates[adapter.cleanUri(chkcmd.source)]
        if session.isServer:
          if ds.action == 'send':
            ds.action = 'save'
            continue
        else:
          if ds.action == 'send':
            ds.action = 'recv'
            continue
        raise common.ProtocolError('unexpected sync state for action=%s' % (ds.action,))

      if cname in (constants.CMD_ADD, constants.CMD_REPLACE, constants.CMD_DELETE,):
        scmd = state.Command(
          name       = cname,
          msgID      = hdrcmd.msgID,
          cmdID      = child.findtext('CmdID'),
          sourceRef  = sourceRef,
          targetRef  = targetRef,
          data       = code,
          )
        res = adapter.synchronizer.settle(adapter, session, scmd, chkcmd, child)
        ret.extend(res or [])
        continue

      if cname == constants.CMD_MAP:
        assert not session.isServer
        if code not in (constants.STATUS_OK,):
          raise badStatus(child)
        continue

      raise common.ProtocolError('unexpected status for command "%s"' % (cname,))

    # TODO: is this right?... or should i be getting pissed off and
    #       raising hell that all my commands were not addressed?...
    ret.extend(chkcmds)

    final = False

    # second, check all the non-'Status' commands
    for idx, child in enumerate(xsync[1]):
      if child.tag == constants.CMD_STATUS:
        continue
      log.debug('handling command "%s"', child.tag)
      if child.tag in (constants.CMD_ALERT, constants.CMD_GET, constants.CMD_PUT,
                       constants.CMD_SYNC, constants.CMD_RESULTS, constants.CMD_MAP):
        # todo: trap errors...
        res = getattr(self, 't2c_' + child.tag.lower())(adapter, session, lastcmds, xsync, child)
        ret.extend(res or [])
        continue
      if child.tag == constants.CMD_FINAL:
        if idx + 1 != len(list(xsync[1])):
          log.warning('peer sent non-last final command')
        final = True
        continue
      raise common.ProtocolError('unexpected command node "%s"' % (child.tag,))

    if not final:
      ret.append(state.Command(
        name       = constants.CMD_ALERT,
        cmdID      = session.nextCmdID,
        data       = constants.STATUS_NEXT_MESSAGE,
        source     = adapter.devinfo.devID,
        target     = adapter.peer.devID,
        ))

    return ret

  #----------------------------------------------------------------------------
  def t2c_get(self, adapter, session, lastcmds, xsync, xnode):
    cttype = xnode.findtext('Meta/Type')
    target = xnode.findtext('Item/Target/LocURI')
    if cttype.startswith(constants.TYPE_SYNCML_DEVICE_INFO) \
       and adapter.cleanUri(target) == constants.URI_DEVINFO_1_2:
      return self.t2c_get_devinf12(adapter, session, lastcmds, xsync, xnode)
    # todo: make error status node...
    raise common.ProtocolError('unexpected "Get" command for target "%s"' % (target,))

  #----------------------------------------------------------------------------
  def t2c_get_devinf12(self, adapter, session, lastcmds, xsync, xnode):
    ret = []
    ret.append(state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = session.pendingMsgID,
      cmdRef     = xnode.findtext('CmdID'),
      statusOf   = xnode.tag,
      statusCode = constants.STATUS_OK,
      targetRef  = xnode.findtext('Item/Target/LocURI'),
      ))
    ret.append(state.Command(
      name       = constants.CMD_RESULTS,
      cmdID      = session.nextCmdID,
      msgRef     = session.pendingMsgID,
      cmdRef     = xnode.findtext('CmdID'),
      type       = constants.TYPE_SYNCML_DEVICE_INFO + '+' + adapter.codec.name,
      source     = './' + constants.URI_DEVINFO_1_2,
      data       = adapter.devinfo.toSyncML(constants.SYNCML_DTD_VERSION_1_2, adapter.stores.values()),
      ))
    return ret

  #----------------------------------------------------------------------------
  def t2c_put(self, adapter, session, lastcmds, xsync, xnode):
    cttype = xnode.findtext('Meta/Type')
    source = xnode.findtext('Item/Source/LocURI')
    if cttype.startswith(constants.TYPE_SYNCML_DEVICE_INFO) \
       and adapter.peer.cleanUri(source) == constants.URI_DEVINFO_1_2:
      return self.t2c_put_devinf12(adapter, session, lastcmds, xsync, xnode)
    # todo: make error status node...
    raise common.ProtocolError('unexpected "%s" command for remote "%s"' % (constants.CMD_RESULTS, source))

  #----------------------------------------------------------------------------
  def t2c_put_devinf12(self, adapter, session, lastcmds, xsync, xnode):
    xdev = xnode.find('Item/Data/DevInf')
    (remotedev, stores) = adapter._context._model.DeviceInfo.fromSyncML(xdev)
    adapter.peer.devinfo = remotedev
    # merge the new datastore info
    # step 1: prepare the new stores (clean up the URIs)
    lut = dict([(adapter.peer.cleanUri(s.uri), s) for s in stores])
    for key, store in lut.items():
      store.uri = key
    # step 2: remove all stores that are no longer mentioned
    adapter.peer._stores = [s for s in adapter.peer._stores if s.uri in lut]
    # step 3: merge the datastore info for existing stores
    for store in adapter.peer._stores:
      store.merge(lut[store.uri])
      del lut[store.uri]
    # step 4: add new datastores
    for store in lut.values():
      adapter.peer.addStore(store)
    adapter.router.recalculate(session)
    return [state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = xsync.findtext('SyncHdr/MsgID'),
      cmdRef     = xnode.findtext('CmdID'),
      sourceRef  = xnode.findtext('Item/Source/LocURI'),
      statusOf   = xnode.tag,
      statusCode = constants.STATUS_OK,
      )]

  #----------------------------------------------------------------------------
  def t2c_results(self, adapter, session, lastcmds, xsync, xnode):
    cttype = xnode.findtext('Meta/Type')
    source = xnode.findtext('Item/Source/LocURI')
    if cttype.startswith(constants.TYPE_SYNCML_DEVICE_INFO) \
       and adapter.peer.cleanUri(source) == constants.URI_DEVINFO_1_2:
      return self.t2c_results_devinf12(adapter, session, lastcmds, xsync, xnode)
    # todo: make error status node...
    raise common.ProtocolError('unexpected "%s" command for remote "%s"' % (constants.CMD_RESULTS, source))

  #----------------------------------------------------------------------------
  def t2c_results_devinf12(self, adapter, session, lastcmds, xsync, xnode):
    return self.t2c_put_devinf12(adapter, session, lastcmds, xsync, xnode)

  #----------------------------------------------------------------------------
  def t2c_alert(self, adapter, session, lastcmds, xsync, xnode):
    code = int(xnode.findtext('Data'))
    statusCode = constants.STATUS_OK
    if code not in (
      constants.ALERT_TWO_WAY,
      constants.ALERT_SLOW_SYNC,
      constants.ALERT_ONE_WAY_FROM_CLIENT,
      constants.ALERT_REFRESH_FROM_CLIENT,
      constants.ALERT_ONE_WAY_FROM_SERVER,
      constants.ALERT_REFRESH_FROM_SERVER,
      # todo: these should only be received out-of-band, right?...
      # constants.ALERT_TWO_WAY_BY_SERVER,
      # constants.ALERT_ONE_WAY_FROM_CLIENT_BY_SERVER,
      # constants.ALERT_REFRESH_FROM_CLIENT_BY_SERVER,
      # constants.ALERT_ONE_WAY_FROM_SERVER_BY_SERVER,
      # constants.ALERT_REFRESH_FROM_SERVER_BY_SERVER,
      ):
      if session.isServer and code == constants.STATUS_RESUME:
        log.warn('peer requested resume... pysyncml does not support that yet - forcing slow-sync')
        code = constants.ALERT_SLOW_SYNC
      else:
        raise common.FeatureNotSupported('unimplemented sync mode %d ("%s")'
                                         % (code, common.mode2string(code)))

    # TODO: if this is the server, we need to validate that the requested
    #       sync mode is actually feasible... i.e. check:
    #         - do the anchors match?
    #         - have we bound the datastores together?
    #         - is there a pending sync?

    uri  = adapter.cleanUri(xnode.findtext('Item/Target/LocURI'))
    ruri = adapter.peer.cleanUri(xnode.findtext('Item/Source/LocURI'))
    log.debug('peer requested %s synchronization of "%s" (here) to "%s" (peer)',
              common.mode2string(code), uri, ruri)

    # TODO: this should really be done by the synchronizer... as it can
    #       then also do a lot of checks - potentially responding with
    #       an error...

    if session.isServer:
      if uri in session.dsstates:
        ds = session.dsstates[uri]
      else:
        adapter.router.addRoute(uri, ruri, autoMapped=True)
        peerStore = adapter.peer.stores[ruri]
        ds = common.adict(
          # TODO: perhaps share this "constructor" with router/adapter?...
          peerUri    = ruri,
          lastAnchor = peerStore.binding.sourceAnchor,
          nextAnchor = str(int(time.time())),
          stats      = state.Stats(),
          mode       = None, # setting to null so that the client tells us...
          )
        session.dsstates[uri] = ds
      ds.action = 'alert'
    else:
      if uri not in session.dsstates:
        raise common.ProtocolError('request for unreflected local datastore "%s"' % (uri,))
      ds = session.dsstates[uri]
      ds.action = 'send'
      if code != ds.mode:
        log.info('server-side switched sync modes from %s to %s for datastore "%s"',
                 common.mode2string(ds.mode), common.mode2string(code), uri)

    ds.mode = code
    ds.peerLastAnchor = xnode.findtext('Item/Meta/Anchor/Last')
    ds.peerNextAnchor = xnode.findtext('Item/Meta/Anchor/Next')

    if ds.peerLastAnchor != adapter.peer.stores[ruri].binding.targetAnchor:
      log.warning('last-anchor mismatch (here: %r, peer: %r) for datastore "%s" - forcing slow-sync',
                  adapter.peer.stores[ruri].binding.targetAnchor, ds.peerLastAnchor, uri)
      ds.peerLastAnchor = None
      if ds.mode not in (
        constants.ALERT_SLOW_SYNC,
        constants.ALERT_REFRESH_FROM_CLIENT,
        constants.ALERT_REFRESH_FROM_SERVER,
        ):
        if session.isServer:
          ds.mode = constants.ALERT_SLOW_SYNC
          statusCode = constants.STATUS_REFRESH_REQUIRED
        else:
          # todo: should i assume that the server knows something
          #       that i don't and just go along with it?...
          raise common.ProtocolError('server-side requested inappropriate %s sync mode on unbound datastore "%s"'
                                     % (common.mode2string(ds.mode), uri))

    return [state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = xsync.findtext('SyncHdr/MsgID'),
      cmdRef     = xnode.findtext('CmdID'),
      targetRef  = xnode.findtext('Item/Target/LocURI'),
      sourceRef  = xnode.findtext('Item/Source/LocURI'),
      statusOf   = xnode.tag,
      statusCode = statusCode,
      # todo: syncevolution does not echo the remote last anchor... why not?
      lastAnchor = ds.peerLastAnchor,
      nextAnchor = ds.peerNextAnchor,
      )]

  #----------------------------------------------------------------------------
  def t2c_sync(self, adapter, session, lastcmds, xsync, xnode):
    uri    = xnode.findtext('Target/LocURI')
    store  = adapter.stores[adapter.cleanUri(uri)]
    ds     = session.dsstates[adapter.cleanUri(uri)]

    commands = [state.Command(
      name        = constants.CMD_SYNC,
      msgID       = xsync.findtext('SyncHdr/MsgID'),
      cmdID       = xnode.findtext('CmdID'),
      source      = xnode.findtext('Source/LocURI'),
      target      = uri,
      data        = [],
      )]

    noc = xnode.findtext('NumberOfChanges')
    if noc is not None:
      noc = int(noc)

    for child in xnode:
      if child.tag in ('CmdID', 'Target', 'Source', 'NumberOfChanges'):
        continue
      if child.tag in (constants.CMD_ADD, constants.CMD_REPLACE, constants.CMD_DELETE):
        # todo: trap errors...
        res = getattr(self, 't2c_sync_' + child.tag.lower())(adapter, session, lastcmds, store, xsync, child)
        commands[0].data.extend(res or [])
        continue
      raise common.ProtocolError('unexpected sync command "%s"' % (child.tag,))

    # confirm that i received the right number of changes...
    if noc is not None and noc != len(commands[0].data):
      raise common.ProtocolError('number-of-changes mismatch (received %d, expected %d)'
                                 % (len(commands[0].data), noc))

    if not session.isServer:
      if ds.action != 'recv':
        raise common.ProtocolError('unexpected sync state for URI "%s": action=%s'
                                   % (uri, ds.action))
      # todo: is there really nothing else to do?...
      ds.action = 'done'
    else:
      if ds.action != 'alert':
        raise common.ProtocolError('unexpected sync state for URI "%s": action=%s'
                                   % (uri, ds.action))
      ds.action = 'send'

    return adapter.synchronizer.reactions(adapter, session, commands)

  #----------------------------------------------------------------------------
  def t2c_xnode2item(self, adapter, session, lastcmds, store, xsync, xnode):
    ctype  = xnode.findtext('Meta/Type')
    # todo: can the version be specified in the Meta tag?... maybe create an
    #       extension to SyncML to communicate this?...
    ctver  = None
    format = xnode.findtext('Meta/Format')
    xitem  = xnode.findall('Item/Data')
    if len(xitem) > 1:
      raise common.ProtocolError('"%s" command with non-singular item data nodes'
                                 % (xnode.tag,))
    if len(xitem) < 1:
      raise common.ProtocolError('"%s" command with missing data node' % (xnode.tag,))
    xitem = xitem[0]
    if len(xitem) == 1:
      data = xitem[0]
    else:
      data = xitem.text
      if format == constants.FORMAT_B64:
        data = base64.b64decode(data)
    return store.agent.loadsItem(data, ctype, ctver)

  #----------------------------------------------------------------------------
  def t2c_sync_add(self, adapter, session, lastcmds, store, xsync, xnode):
    item = self.t2c_xnode2item(adapter, session, lastcmds, store, xsync, xnode)
    return [state.Command(
      name          = constants.CMD_ADD,
      msgID         = xsync.findtext('SyncHdr/MsgID'),
      cmdID         = xnode.findtext('CmdID'),
      source        = xnode.findtext('Item/Source/LocURI'),
      sourceParent  = xnode.findtext('Item/SourceParent/LocURI'),
      targetParent  = xnode.findtext('Item/TargetParent/LocURI'),
      data          = item,
      )]

  #----------------------------------------------------------------------------
  def t2c_sync_replace(self, adapter, session, lastcmds, store, xsync, xnode):
    item = self.t2c_xnode2item(adapter, session, lastcmds, store, xsync, xnode)
    return [state.Command(
      name          = constants.CMD_REPLACE,
      msgID         = xsync.findtext('SyncHdr/MsgID'),
      cmdID         = xnode.findtext('CmdID'),
      source        = xnode.findtext('Item/Source/LocURI'),
      sourceParent  = xnode.findtext('Item/SourceParent/LocURI'),
      target        = xnode.findtext('Item/Target/LocURI'),
      targetParent  = xnode.findtext('Item/TargetParent/LocURI'),
      data          = item,
      )]

  #----------------------------------------------------------------------------
  def t2c_sync_delete(self, adapter, session, lastcmds, store, xsync, xnode):
    return [state.Command(
      name          = constants.CMD_DELETE,
      msgID         = xsync.findtext('SyncHdr/MsgID'),
      cmdID         = xnode.findtext('CmdID'),
      source        = xnode.findtext('Item/Source/LocURI'),
      sourceParent  = xnode.findtext('Item/SourceParent/LocURI'),
      target        = xnode.findtext('Item/Target/LocURI'),
      targetParent  = xnode.findtext('Item/TargetParent/LocURI'),
      )]

  #----------------------------------------------------------------------------
  def makeStatus(self, session, xsync, xnode, status=constants.STATUS_OK, **kw):
    return state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = xsync.findtext('SyncHdr/MsgID'),
      cmdRef     = xnode.findtext('CmdID'),
      statusOf   = xnode.tag,
      statusCode = status,
      **kw
      )

  #----------------------------------------------------------------------------
  def t2c_map(self, adapter, session, lastcmds, xsync, xnode):
    # TODO: should this be moved into the synchronizer?...
    srcUri = xnode.findtext('Source/LocURI')
    tgtUri = xnode.findtext('Target/LocURI')
    peerStore = adapter.peer.stores[adapter.peer.cleanUri(srcUri)]
    # todo: should i verify that the GUID is valid?...
    for xitem in xnode.findall('MapItem'):
      luid = xitem.findtext('Source/LocURI')
      guid = xitem.findtext('Target/LocURI')
      # TODO: is there a better way of doing this than DELETE + INSERT?...
      #       ie. is there an SQL INSERT_OR_UPDATE?...
      adapter._context._model.Mapping.q(store_id=peerStore.id, guid=guid).delete()
      newmap = adapter._context._model.Mapping(store_id=peerStore.id, guid=guid, luid=luid)
      adapter._context._model.session.add(newmap)
    return [self.makeStatus(session, xsync, xnode,
                            targetRef=tgtUri, sourceRef=srcUri)]

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
