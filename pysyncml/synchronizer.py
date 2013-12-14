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
The ``pysyncml.synchronizer`` is an internal package that does all of the actual
"work" for the SyncML Adapter.
'''

import sys, base64, logging
import xml.etree.ElementTree as ET
from sqlalchemy.orm.exc import NoResultFound
from . import common, constants, model, state

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
class Synchronizer(object):

  #----------------------------------------------------------------------------
  def __init__(self, adapter, *args, **kw):
    super(Synchronizer, self).__init__(*args, **kw)
    self.adapter = adapter

  #----------------------------------------------------------------------------
  # SYNCHRONIZATION PHASE: ACTION
  #----------------------------------------------------------------------------

  #----------------------------------------------------------------------------
  def actions(self, adapter, session):
    ret = []
    for uri, dsstate in session.dsstates.items():
      if dsstate.action == 'done':
        continue
      method = getattr(self, 'action_' + dsstate.action, None)
      if method is None:
        raise common.InternalError('unexpected datastore action "%s"' % (dsstate.action,))
      # todo: trap errors...
      ret += method(adapter, session, uri, dsstate) or []
    return ret

  #----------------------------------------------------------------------------
  def action_alert(self, adapter, session, uri, dsstate):
    src = adapter.stores[uri]
    tgt = adapter.peer.stores[dsstate.peerUri]

    # TODO: ensure that mode is acceptable...

    # todo: perhaps i should only specify maxObjSize if it differs from
    #       adapter.maxObjSize?...

    return [state.Command(
      name        = constants.CMD_ALERT,
      cmdID       = session.nextCmdID,
      data        = dsstate.mode,
      source      = src.uri,
      target      = tgt.uri,
      lastAnchor  = dsstate.lastAnchor,
      nextAnchor  = dsstate.nextAnchor,
      maxObjSize  = src.maxObjSize,
      )]

  #----------------------------------------------------------------------------
  def action_send(self, adapter, session, uri, dsstate):
    store = adapter.stores[uri]
    agent = store.agent
    peerStore = adapter.peer.stores[adapter.router.getTargetUri(uri)]

    cmd = state.Command(
      name   = constants.CMD_SYNC,
      cmdID  = session.nextCmdID,
      source = uri,
      # target = adapter.router.getTargetUri(uri),
      target = dsstate.peerUri,
      )

    if dsstate.mode not in (
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
      raise common.InternalError('unexpected sync mode "%s"' % (common.mode2string(dsstate.mode),))

    log.debug('sending sync commands for URI "%s" in %s mode (anchor: %s)',
              uri, common.mode2string(dsstate.mode),
              dsstate.lastAnchor or '-')

    if ( session.isServer and dsstate.mode in (constants.ALERT_REFRESH_FROM_CLIENT,
                                               constants.ALERT_ONE_WAY_FROM_CLIENT) ) \
       or ( not session.isServer and dsstate.mode in (constants.ALERT_REFRESH_FROM_SERVER,
                                                      constants.ALERT_ONE_WAY_FROM_SERVER) ):
      # nothing to send (wrong side of the receiving end of one-way sync) and
      # nothing to do (refreshes get performed on "reaction" side of a sync)
      return [cmd]

    if dsstate.mode in (
      constants.ALERT_TWO_WAY,
      constants.ALERT_ONE_WAY_FROM_CLIENT,  # when not session.isServer
      constants.ALERT_ONE_WAY_FROM_SERVER,  # when session.isServer
      ):
      # send local changes
      changes  = adapter._context._model.Change.q(store_id=peerStore.id)
      cmd.data = []
      ctype    = adapter.router.getBestTransmitContentType(uri)

      # TODO: add support for hierarchical operations...
      #       including MOVE, COPY, etc.

      # TODO: this assumes that the entire object set can fit in memory...
      #       perhaps, as a work-around, just keep a reference to the object
      #       and then stream-based serialize it actually gets converted to
      #       XML.

      for change in changes:
        if dsstate.conflicts is not None and change.itemID in dsstate.conflicts:
          continue
        scmdtype = {
          constants.ITEM_ADDED    : constants.CMD_ADD,
          constants.ITEM_MODIFIED : constants.CMD_REPLACE,
          constants.ITEM_DELETED  : constants.CMD_DELETE,
          }.get(change.state)
        if scmdtype is None:
          log.error('could not resolve item state %d to sync command', change.state)
          continue
        # todo: do something with the content-type version?...
        scmd = state.Command(
          name    = scmdtype,
          cmdID   = session.nextCmdID,
          format  = constants.FORMAT_AUTO,
          type    = ctype[0] if change.state != constants.ITEM_DELETED else None,
          uri     = uri,
          )
        # TODO: need to add hierarchical addition support here...
        if scmdtype != constants.CMD_DELETE:
          item = agent.getItem(change.itemID)
          scmd.data = agent.dumpsItem(item, ctype[0], ctype[1])
          if not isinstance(scmd.data, basestring):
            scmd.type = scmd.data[0]
            scmd.data = scmd.data[2]
          if agent.hierarchicalSync and item.parent is not None:
            scmd.sourceParent = str(item.parent)
        if scmdtype == constants.CMD_ADD:
          scmd.source = change.itemID
        else:
          if session.isServer:
            try:
              # todo: this is a bit of an abstraction violation...
              query = adapter._context._model.Mapping.q(store_id=peerStore.id, guid=change.itemID)
              scmd.target = query.one().luid
            except NoResultFound:
              scmd.source = change.itemID
          else:
            scmd.source = change.itemID
        cmd.data.append(scmd)

      cmd.noc  = len(cmd.data)
      return [cmd]

    if dsstate.mode in (
      constants.ALERT_SLOW_SYNC,
      constants.ALERT_REFRESH_FROM_SERVER,  # when session.isServer
      constants.ALERT_REFRESH_FROM_CLIENT,  # when not session.isServer
      ):
      cmd.data = []

      items = agent.getAllItems()

      # TODO: this assumes that the entire object set can fit in memory...
      if agent.hierarchicalSync:
        orditems = []            # the ordered items
        dunitems = dict()        # lut of the ordered items
        curitems = dict()        # lut of current items (for loop detection)
        lutitems = dict([(item.id, item) for item in items])
        def appenditem(item):
          if item.id in dunitems:
            return
          if item.id in curitems:
            raise common.LogicalError('recursive item hierarchy detected at item %r' % (item,))
          curitems[item.id] = True
          if item.parent is not None:
            appenditem(lutitems[item.parent])
          orditems.append(item)
          dunitems[item.id] = item
        for item in items:
          curitems = dict()
          appenditem(item)

      ctype = adapter.router.getBestTransmitContentType(uri)

      for item in items:
        if dsstate.conflicts is not None and str(item.id) in dsstate.conflicts:
          continue
        # TODO: these should all be non-deleted items, right?...
        if session.isServer:
          # check to see if this item has already been mapped. if so,
          # then don't send it.
          try:
            # todo: this is a bit of an abstraction violation...
            query = adapter._context._model.Mapping.q(store_id=peerStore.id, guid=item.id)
            if query.one().luid is not None:
              continue
          except NoResultFound:
            pass
        # todo: do something with the content-type version?...
        scmd  = state.Command(
          name    = constants.CMD_ADD,
          cmdID   = session.nextCmdID,
          format  = constants.FORMAT_AUTO,
          type    = ctype[0],
          uri     = uri,
          source  = str(item.id),
          data    = agent.dumpsItem(item, ctype[0], ctype[1]),
          )
        if not isinstance(scmd.data, basestring):
          scmd.type = scmd.data[0]
          scmd.data = scmd.data[2]
        if agent.hierarchicalSync and item.parent is not None:
          scmd.sourceParent = str(item.parent)
        cmd.data.append(scmd)
      cmd.noc = len(cmd.data)
      return [cmd]

    raise common.InternalError('unexpected sync situation (action=%s, mode=%s, isServer=%s)'
                               % (dsstate.action, common.mode2string(dsstate.mode),
                                  '1' if session.isServer else '0'))

  #----------------------------------------------------------------------------
  def action_save(self, adapter, session, uri, dsstate):
    if not session.isServer:
      # TODO: for now, only servers should take the "save" action - the client
      #       will explicitly do this at the end of the .sync() method.
      #       ... mostly because clients don't call synchronizer.actions()
      #       one final time ...
      #       *BUT* perhaps that should be changed?... for example, .sync()
      #       could call synchronizer.actions() to cause action_save's to occur
      #       *AND* verify that synchronizer.actions() does not return anything...
      raise common.InternalError('unexpected sync situation (action=%s, isServer=%s)'
                                 % (dsstate.action, '1' if session.isServer else '0'))
    log.debug('storing anchors: peer=%s; source=%s/%s; target=%s/%s',
              adapter.peer.devID, uri, dsstate.nextAnchor,
              dsstate.peerUri, dsstate.peerNextAnchor)
    peerStore = adapter.peer.stores[dsstate.peerUri]
    peerStore.binding.sourceAnchor = dsstate.nextAnchor
    peerStore.binding.targetAnchor = dsstate.peerNextAnchor

  #----------------------------------------------------------------------------
  # SYNCHRONIZATION PHASE: REACTION
  #----------------------------------------------------------------------------

  #----------------------------------------------------------------------------
  def reactions(self, adapter, session, commands):
    ret = []
    for cmd in commands:
      method = getattr(self, 'reaction_' + cmd.name.lower(), None)
      if method is None:
        raise common.InternalError('unexpected reaction requested to command "%s"'
                                   % (cmd.name,))
      try:
        ret.extend(method(adapter, session, cmd) or [])
      finally:
        session.hierlut = None
    return ret

  #----------------------------------------------------------------------------
  def reaction_sync(self, adapter, session, command):
    ret = [state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = command.msgID,
      cmdRef     = command.cmdID,
      targetRef  = command.target,
      sourceRef  = command.source,
      statusOf   = command.name,
      statusCode = constants.STATUS_OK,
      )]
    store = adapter.stores[adapter.cleanUri(command.target)]
    if store.agent.hierarchicalSync:
      session.hierlut = dict()
    dsstate = session.dsstates[store.uri]
    if ( not session.isServer and dsstate.mode == constants.ALERT_REFRESH_FROM_SERVER ) \
       or ( session.isServer and dsstate.mode == constants.ALERT_REFRESH_FROM_CLIENT ):
      # delete all local items
      for item in store.agent.getAllItems():
        store.agent.deleteItem(item.id)
        dsstate.stats.hereDel += 1
        if session.isServer:
          store.registerChange(item.id, constants.ITEM_DELETED, excludePeerID=adapter.peer.id)
      # delete pending changes for the remote peer
      adapter._context._model.Change.q(store_id=store.peer.id).delete()

    if len(command.data) > 0:
      # verify that i should be receiving data...
      if not (
        dsstate.mode == constants.ALERT_TWO_WAY
        or dsstate.mode == constants.ALERT_SLOW_SYNC
        or ( not session.isServer and dsstate.mode in (constants.ALERT_ONE_WAY_FROM_SERVER,
                                                       constants.ALERT_REFRESH_FROM_SERVER) )
        or ( session.isServer and dsstate.mode in (constants.ALERT_ONE_WAY_FROM_CLIENT,
                                                   constants.ALERT_REFRESH_FROM_CLIENT) )
        ):
        raise common.ProtocolError('unexpected sync data (role=%s, mode=%s)' %
                                   ('server' if session.isServer else 'client',
                                    common.mode2string(dsstate.mode)))

    for cmd in command.data:
      if cmd.name != constants.CMD_ADD:
        # non-'add' sync commands should only be received in non-refresh modes
        if dsstate.mode not in (constants.ALERT_TWO_WAY,
                                constants.ALERT_ONE_WAY_FROM_SERVER,
                                constants.ALERT_ONE_WAY_FROM_CLIENT):
          raise common.ProtocolError('unexpected non-add sync command (role=%s, mode=%s, command=%s)' %
                                     ('server' if session.isServer else 'client',
                                      common.mode2string(dsstate.mode), cmd.name))

      ret.extend(self.reaction_syncdispatch(adapter, session, cmd, store))
    return ret

  #----------------------------------------------------------------------------
  def reaction_syncdispatch(self, adapter, session, cmd, store):
    method = getattr(self, 'reaction_sync_' + cmd.name.lower(), None)
    if method is None:
      raise common.InternalError('unexpected reaction requested to sync command "%s"'
                                 % (cmd.name,))
    dsstate = session.dsstates[store.uri]
    # server, non-add, non-slowsync, non-refresh commands: check for conflicts.
    # note that certain types of content could be a conflict even if it is an
    # "Add" command; for example, two files with the same name cannot be added
    # from separate clients.
    # todo: allow agents to raise a ConflictError...
    #       ==> perhaps this is already covered by the .matchItem() API?...
    if session.isServer \
       and cmd.name != constants.CMD_ADD \
       and dsstate.mode != constants.ALERT_REFRESH_FROM_CLIENT:
      itemID = self.getSourceMapping(adapter, session, constants.CMD_SYNC,
                                     cmd, store.peer, cmd.source)
      try:
        change = adapter._context._model.Change.q(
          store_id = store.peer.id,
          itemID   = itemID).one()

        retcmd = state.Command(
          name       = constants.CMD_STATUS,
          cmdID      = session.nextCmdID,
          msgRef     = cmd.msgID,
          cmdRef     = cmd.cmdID,
          sourceRef  = cmd.source,
          targetRef  = cmd.target,
          statusOf   = cmd.name,
          # todo: make this error message a bit more descriptive...
          errorMsg   = 'command "%s" conflict for item ID %r (state: %s)' \
                         % (cmd.name, itemID, common.state2string(change.state)),
          )

        # four possible states: mod-mod, mod-del, del-mod, del-del
        if dsstate.conflicts is None:
          dsstate.conflicts = []

        # handle mod-mod (but only if change-tracking is enabled)
        if change.state == constants.ITEM_MODIFIED \
           and cmd.name == constants.CMD_REPLACE:
          cmd._conflict = retcmd
          cmd._change   = change
          # todo: this "raise" is a hack just to abort conflict handling!...
          #       here and let reaction_sync_replace handle it...
          raise NoResultFound

        # handle del-del
        if change.state == constants.ITEM_DELETED \
           and cmd.name == constants.CMD_DELETE:
          # both changes are deletes... that's not a conflict.
          # TODO: should i really be doing all this here?... it does not
          #       follow the pattern...
          adapter._context._model.session.delete(change)
          dsstate.stats.peerDel   += 1
          dsstate.stats.hereDel   += 1
          dsstate.stats.merged    += 1
          retcmd.statusCode = constants.STATUS_CONFLICT_RESOLVED_MERGE
          retcmd.errorCode  = None
          retcmd.errorMsg   = None
          return [retcmd]

        # handle del-mod or mod-del
        if ( change.state == constants.ITEM_DELETED \
             or cmd.name == constants.CMD_DELETE ) \
           and store.conflictPolicy != constants.POLICY_ERROR:
          # one of them is a delete and a conflict that can be solved
          # by the framework
          cmd._conflict = retcmd
          cmd._change   = change
          # todo: this "raise" is a hack just to abort conflict handling
          #       here and let reaction_sync_delete handle it...
          raise NoResultFound

        dsstate.conflicts.append(itemID)
        dsstate.stats.peerErr   += 1
        dsstate.stats.conflicts += 1
        log.warning(retcmd.errorMsg)
        retcmd.statusCode = constants.STATUS_UPDATE_CONFLICT
        retcmd.errorCode  = common.fullClassname(self) + '.RSd.10'
        return [retcmd]

      except NoResultFound:
        pass

    return method(adapter, session, cmd, store)


  #----------------------------------------------------------------------------
  def reaction_sync_add(self, adapter, session, cmd, store):
    curitem = None
    if store.agent.hierarchicalSync:
      if cmd.targetParent is not None:
        cmd.data.parent = cmd.targetParent
      elif cmd.sourceParent is not None:
        cmd.data.parent = session.hierlut[cmd.sourceParent]
    if session.isServer \
       and session.dsstates[store.uri].mode == constants.ALERT_SLOW_SYNC:
      # TODO: if the matched item is already mapped to another client-side
      #       object, then this should cancel the matching...
      curitem = store.agent.matchItem(cmd.data)
      if curitem is not None and cmp(curitem, cmd.data) != 0:
        try:
          cspec = store.agent.mergeItems(curitem, cmd.data, None)
          store.registerChange(curitem.id, constants.ITEM_MODIFIED,
                               changeSpec=cspec, excludePeerID=adapter.peer.id)
        except common.ConflictError:
          curitem = None
    if curitem is None:
      item = store.agent.addItem(cmd.data)
      session.dsstates[store.uri].stats.hereAdd += 1
      store.registerChange(item.id, constants.ITEM_ADDED, excludePeerID=adapter.peer.id)
    if curitem is not None:
      item = curitem
    if store.agent.hierarchicalSync:
      session.hierlut[cmd.source] = item.id
    ret = [state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = cmd.msgID,
      cmdRef     = cmd.cmdID,
      sourceRef  = cmd.source,
      statusOf   = cmd.name,
      statusCode = constants.STATUS_ITEM_ADDED if curitem is None else constants.STATUS_ALREADY_EXISTS,
      )]
    if session.isServer:
      peerStore = adapter.peer.stores[session.dsstates[store.uri].peerUri]
      # todo: this is a bit of an abstraction violation...
      adapter._context._model.Mapping.q(store_id=peerStore.id, guid=item.id).delete()
      newmap = adapter._context._model.Mapping(store_id=peerStore.id, guid=item.id, luid=cmd.source)
      adapter._context._model.session.add(newmap)
    else:
      ret.append(state.Command(
        name       = constants.CMD_MAP,
        cmdID      = session.nextCmdID,
        source     = store.uri,
        target     = adapter.router.getTargetUri(store.uri),
        sourceItem = item.id,
        targetItem = cmd.source,
        ))
    return ret

  #----------------------------------------------------------------------------
  def getSourceMapping(self, adapter, session, cmdctxt, cmd, peerStore, luid):
    try:
      curmap = adapter._context._model.Mapping.q(store_id=peerStore.id, luid=luid).one()
      return str(curmap.guid)
    except NoResultFound:
      msg = 'unexpected "%s/%s" request for unmapped item ID: %r' % (cmdctxt, cmd.name, luid)
      log.warning(msg)
      # todo: this is a bit of a hack when cmdctxt == 'Status'...
      return state.Command(
        name       = constants.CMD_STATUS,
        cmdID      = session.nextCmdID,
        msgRef     = cmd.msgID,
        cmdRef     = cmd.cmdID,
        sourceRef  = cmd.source,
        targetRef  = cmd.target,
        statusOf   = cmd.name if cmdctxt != constants.CMD_STATUS else cmdctxt,
        statusCode = constants.STATUS_COMMAND_FAILED,
        errorCode  = __name__ + '.' + self.__class__.__name__ + '.GSM.10',
        errorMsg   = msg,
        )

  #----------------------------------------------------------------------------
  def reaction_sync_replace(self, adapter, session, cmd, store):

    # TODO: handle hierarchical data...

    item = cmd.data
    if session.isServer:
      item.id = self.getSourceMapping(adapter, session, constants.CMD_SYNC,
                                      cmd, store.peer, cmd.source)
      if not isinstance(item.id, basestring):
        return [item.id]
    else:
      item.id = cmd.target

    dsstate = session.dsstates[store.uri]

    okcmd = state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = cmd.msgID,
      cmdRef     = cmd.cmdID,
      targetRef  = cmd.target,
      sourceRef  = cmd.source,
      statusOf   = cmd.name,
      statusCode = constants.STATUS_OK,
      )

    if cmd._conflict is not None:
      try:
        if cmd._change.state == constants.ITEM_DELETED:
          raise common.ConflictError('item deleted')
        if cmd._change.changeSpec is None:
          raise common.ConflictError('no change tracking enabled - falling back to policy')
        cspec = store.agent.mergeItems(store.agent.getItem(item.id), item, cmd._change.changeSpec)
        log.info('merged conflicting changes for item ID %r' % (item.id,))
        dsstate.stats.hereMod += 1
        store.registerChange(item.id, constants.ITEM_MODIFIED,
                             changeSpec=cspec, excludePeerID=adapter.peer.id)
        okcmd.statusCode = constants.STATUS_CONFLICT_RESOLVED_MERGE
        # NOTE: *not* suppressing the change that is registered from server
        #       to client, since the merge may have resulted in an item that
        #       is not identical to the one on the client.
        return [okcmd]
      except common.ConflictError, e:
        # conflict types: client=mod/server=mod or client=mod/server=del
        if store.conflictPolicy == constants.POLICY_CLIENT_WINS:
          adapter._context._model.session.delete(cmd._change)
          dsstate.stats.merged += 1
          okcmd.statusCode = constants.STATUS_CONFLICT_RESOLVED_CLIENT_DATA
          if cmd._change.state == constants.ITEM_DELETED:
            # todo: this "re-creation" of a new item is detrimental to
            #       clients that are tracking changes to an item (for
            #       example, a SyncML svn client bridge...). but then, to
            #       them, this item may already have been deleted. ugh.
            dsstate.stats.hereMod += 1
            item = store.agent.addItem(item)
            peerStore = store.peer
            adapter._context._model.Mapping.q(store_id=peerStore.id, guid=item.id).delete()
            newmap = adapter._context._model.Mapping(store_id=peerStore.id,
                                                     guid=item.id,
                                                     luid=cmd.source)
            adapter._context._model.session.add(newmap)
            store.registerChange(item.id, constants.ITEM_ADDED,
                                 excludePeerID=adapter.peer.id)
            return [okcmd]
          # falling back to standard handling...
        elif store.conflictPolicy == constants.POLICY_SERVER_WINS:
          dsstate.stats.merged += 1
          okcmd.statusCode = constants.STATUS_CONFLICT_RESOLVED_SERVER_DATA
          return [okcmd]
        else:
          # store.conflictPolicy == constants.POLICY_ERROR or other...
          dsstate.stats.peerErr    += 1
          dsstate.stats.conflicts  += 1
          cmd._conflict.errorMsg   += ', agent failed merge: ' + str(e)
          cmd._conflict.statusCode = constants.STATUS_UPDATE_CONFLICT
          cmd._conflict.errorCode  = common.fullClassname(self) + '.RSR.10'
          log.warning(cmd._conflict.errorMsg)
          dsstate.conflicts.append(str(item.id))
          return [cmd._conflict]

    # if store.agent.hierarchicalSync:
    #   session.hierlut[cmd.source] = item.id

    cspec = store.agent.replaceItem(item, reportChanges=session.isServer)
    dsstate.stats.hereMod += 1
    store.registerChange(item.id, constants.ITEM_MODIFIED,
                         changeSpec=cspec, excludePeerID=adapter.peer.id)
    return [okcmd]

  #----------------------------------------------------------------------------
  def reaction_sync_delete(self, adapter, session, cmd, store):
    status = constants.STATUS_OK
    if session.isServer:
      itemID = self.getSourceMapping(adapter, session, constants.CMD_SYNC,
                                     cmd, store.peer, cmd.source)
      if not isinstance(itemID, basestring):
        return [itemID]
      if cmd._conflict is not None:
        if store.conflictPolicy == constants.POLICY_CLIENT_WINS:
          adapter._context._model.session.delete(cmd._change)
          status = constants.STATUS_CONFLICT_RESOLVED_CLIENT_DATA
          session.dsstates[store.uri].stats.merged += 1
          # falling back to standard handling...
        elif store.conflictPolicy == constants.POLICY_SERVER_WINS:
          adapter._context._model.session.delete(cmd._change)
          store.peer.registerChange(itemID, constants.ITEM_ADDED)
          session.dsstates[store.uri].stats.merged += 1
          cmd._conflict.statusCode = constants.STATUS_CONFLICT_RESOLVED_SERVER_DATA
          cmd._conflict.errorCode  = None
          cmd._conflict.errorMsg   = None
          return [cmd._conflict]
        else:
          # a POLICY_ERROR policy should have been handled by the dispatch
          raise Exception('unexpected conflictPolicy: %r' % (store.conflictPolicy,))
    else:
      itemID = cmd.target
    store.agent.deleteItem(itemID)
    session.dsstates[store.uri].stats.hereDel += 1
    store.registerChange(itemID, constants.ITEM_DELETED, excludePeerID=adapter.peer.id)
    return [state.Command(
      name       = constants.CMD_STATUS,
      cmdID      = session.nextCmdID,
      msgRef     = cmd.msgID,
      cmdRef     = cmd.cmdID,
      targetRef  = cmd.target,
      sourceRef  = cmd.source,
      statusOf   = cmd.name,
      # todo: should this return DELETE_WITHOUT_ARCHIVE instead of OK?...
      # statusCode = constants.STATUS_DELETE_WITHOUT_ARCHIVE,
      statusCode = status,
      )]

  #----------------------------------------------------------------------------
  # SYNCHRONIZATION PHASE: SETTLE
  #----------------------------------------------------------------------------

  #----------------------------------------------------------------------------
  def settle(self, adapter, session, cmd, chkcmd, xnode):
    # TODO: remove the "xnode" parameter... it is a hack so that i can
    #       call badStatus() the same way as in protocol.py
    # todo: there is a bit of a disconnect between how action and reaction
    #       phases are called (for a list of commands), whereas the settle
    #       phase is called on a per-item basis... not ideal, but the protocol
    #       is really set up that way :(
    # TODO: check all valid values of ``data``...
    # todo: anything else in common?...
    # todo: trap errors...
    return getattr(self, 'settle_' + cmd.name.lower())(adapter, session, cmd, chkcmd, xnode)

  #----------------------------------------------------------------------------
  def settle_add(self, adapter, session, cmd, chkcmd, xnode):
    if cmd.data not in (constants.STATUS_OK,
                        constants.STATUS_ITEM_ADDED,
                        constants.STATUS_ALREADY_EXISTS):
      raise badStatus(xnode)
    if cmd.data != constants.STATUS_ALREADY_EXISTS:
      session.dsstates[chkcmd.uri].stats.peerAdd += 1
    peerStore = adapter.peer.stores[adapter.router.getTargetUri(chkcmd.uri)]
    locItemID = chkcmd.source
    # todo: this is *technically* subject to a race condition... but the
    #       same peer should really not be synchronizing at the same time...
    # todo: also potentially check Change.registered...
    # TODO: this could be solved by:
    #         a) never updating a Change record (only deleting and replacing)
    #         b) deleting Change records by ID instead of by store/item/state...
    adapter._context._model.Change.q(
      store_id  = peerStore.id,
      itemID    = locItemID,
      state     = constants.ITEM_ADDED,
      ).delete()

  #----------------------------------------------------------------------------
  def settle_replace(self, adapter, session, cmd, chkcmd, xnode):
    if not session.isServer and cmd.data == constants.STATUS_UPDATE_CONFLICT:
      session.dsstates[chkcmd.uri].stats.hereErr   += 1
      session.dsstates[chkcmd.uri].stats.conflicts += 1
      return
    if cmd.data not in (constants.STATUS_OK,
                        constants.STATUS_CONFLICT_RESOLVED_MERGE,
                        constants.STATUS_CONFLICT_RESOLVED_CLIENT_DATA,
                        constants.STATUS_CONFLICT_RESOLVED_SERVER_DATA,
                        ):
      raise badStatus(xnode)
    if cmd.data in (constants.STATUS_CONFLICT_RESOLVED_MERGE,
                    constants.STATUS_CONFLICT_RESOLVED_CLIENT_DATA,
                    constants.STATUS_CONFLICT_RESOLVED_SERVER_DATA):
      session.dsstates[chkcmd.uri].stats.merged += 1
    if cmd.data != constants.STATUS_CONFLICT_RESOLVED_SERVER_DATA:
      session.dsstates[chkcmd.uri].stats.peerMod += 1
    peerStore = adapter.peer.stores[adapter.router.getTargetUri(chkcmd.uri)]
    locItemID = chkcmd.source
    # todo: handle hierarchical sync...
    if session.isServer and chkcmd.target is not None:
      locItemID = self.getSourceMapping(adapter, session, constants.CMD_STATUS,
                                        cmd, peerStore, chkcmd.target)
      if not isinstance(locItemID, basestring):
        return locItemID
    # todo: this is *technically* subject to a race condition... but the
    #       same peer should really not be synchronizing at the same time...
    # todo: also potentially check Change.registered...
    # TODO: this could be solved by:
    #         a) never updating a Change record (only deleting and replacing)
    #         b) deleting Change records by ID instead of by store/item/state...
    adapter._context._model.Change.q(
      store_id  = peerStore.id,
      itemID    = locItemID,
      state     = constants.ITEM_MODIFIED,
      ).delete()

  #----------------------------------------------------------------------------
  def settle_delete(self, adapter, session, cmd, chkcmd, xnode):
    if not session.isServer and cmd.data == constants.STATUS_UPDATE_CONFLICT:
      session.dsstates[chkcmd.uri].stats.hereErr   += 1
      session.dsstates[chkcmd.uri].stats.conflicts += 1
      return
    elif not session.isServer and cmd.data == constants.STATUS_CONFLICT_RESOLVED_MERGE:
      session.dsstates[chkcmd.uri].stats.hereDel   += 1
      session.dsstates[chkcmd.uri].stats.peerDel   += 1
      session.dsstates[chkcmd.uri].stats.merged    += 1
    elif not session.isServer and cmd.data == constants.STATUS_CONFLICT_RESOLVED_CLIENT_DATA:
      session.dsstates[chkcmd.uri].stats.peerDel   += 1
      session.dsstates[chkcmd.uri].stats.merged    += 1
    elif not session.isServer and cmd.data == constants.STATUS_CONFLICT_RESOLVED_SERVER_DATA:
      session.dsstates[chkcmd.uri].stats.merged    += 1
    elif cmd.data == constants.STATUS_ITEM_NOT_DELETED:
      # note: the reason that this *may* be ok is that some servers (funambol)
      #       will report ITEM_NOT_DELETED when the item did not exist, thus this
      #       is "alright"...
      # todo: perhaps this should be raised as an error if the
      #       remote peer != funambol?...
      log.warn('received ITEM_NOT_DELETED for DELETE command for URI "%s" item "%s"'
               ' - assuming previous pending deletion executed',
               chkcmd.uri, chkcmd.source)
    elif cmd.data == constants.STATUS_OK:
      session.dsstates[chkcmd.uri].stats.peerDel += 1
    else:
      raise badStatus(xnode)
    peerStore = adapter.peer.stores[adapter.router.getTargetUri(chkcmd.uri)]
    locItemID = chkcmd.source
    # todo: handle hierarchical sync...
    if chkcmd.target is not None:
      locItemID = self.getSourceMapping(adapter, session, constants.CMD_STATUS,
                                        cmd, peerStore, chkcmd.target)
      if not isinstance(locItemID, basestring):
        return locItemID
    # todo: this is *technically* subject to a race condition... but the
    #       same peer should really not be synchronizing at the same time...
    # todo: also potentially check Change.registered...
    # TODO: this could be solved by:
    #         a) never updating a Change record (only deleting and replacing)
    #         b) deleting Change records by ID instead of by store/item/state...
    adapter._context._model.Change.q(
      store_id  = peerStore.id,
      itemID    = locItemID,
      state     = constants.ITEM_DELETED,
      ).delete()

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
