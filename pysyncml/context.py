# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/23
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
The ``pysyncml.context`` package provides the entry point into most
pysyncml operations via the :class:`pysyncml.Context
<pysyncml.context.Context>` class.
'''

import sqlalchemy.ext.declarative
from sqlalchemy.orm.exc import NoResultFound
from . import model, codec, router, protocol, synchronizer

#------------------------------------------------------------------------------
class Context(object):
  '''
  The pysyncml Context object creates an environment for an Adapter to
  be created and evaluated in. The primary object is to provide access
  to a storage location so that SyncML state information can be stored
  across multiple synchronization messages, sessions and
  peers. However, it can also be used to specify operational
  parameters, such as whether or not to support specific codecs and
  which to use as the default.
  '''

  #----------------------------------------------------------------------------
  def __init__(self,
               engine=None, storage=None, prefix='pysyncml', owner=None,
               autoCommit=None,
               router=None, protocol=None, synchronizer=None, codec=None,
               ):
    '''
    The Context constructor accepts the following parameters, of which
    all are optional:

    :param owner:

      an integer owner ID. Necessary primarily when the adapter
      storage is shared between multiple users/adapter agents
      (i.e. in server contexts). If it is not shared, `owner` can be
      left as ``None`` (the default).

    :param storage:

      the sqlalchemy storage specification where all the SyncML-
      related data should be stored.

      NOTE: can be overridden by parameter `engine`.

      NOTE: the storage driver **MUST** support cascading deletes;
      this is done automatically for connections created directly by
      pysyncml for mySQL and sqlite, but it is up to the calling
      program to ensure this for other databases or if the database
      engine is passed in via parameter `engine`. Specifically, when
      pysyncml creates the sqlalchemy engine (i.e. by calling
      ``sqlalchemy.create_engine(storage)``), then InnoDB is requested
      for mySQL tables and ``PRAGMA foreign_keys=ON`` is issued for
      sqlite databases. pysyncml provides a helper function to ensure
      that sqlite databases have cascading deletes enabled::

        import sqlalchemy, pysyncml
        db = sqlalchemy.create_engine(...)
        pysyncml.enableSqliteCascadingDeletes(db)

    :param engine:

      the sqlalchemy storage engine where all the SyncML-related
      data should be stored.

      NOTE: overrides parameter `storage`.

      NOTE: see notes under parameter `storage` for details on
      cascading delete support.

      TODO: it would be great to add a check to ensure that provided
      storage engines have cascading deletes enabled.

    :param prefix:

      sets a database table name prefix. This is primarily useful when
      using the `engine` parameter, as multiple pysyncml contexts can
      then be defined within the same database namespace. Defaults to
      ``pysyncml``.

    :param autoCommit:

      whether or not to execute a storage engine "commit" when syncing
      is complete. The default behavior is dependent on if `engine` is
      provided: if not ``None``, then `autoCommit` defaults to
      ``False``, otherwise, defaults to ``True``.

    :param router:

      overrides the default router with an object that must implement
      the interface specified by :class:`pysyncml.router.Router`.

    :param protocol:

      sets the semantic objective to/from protocol evaluation and
      resolution object, which must implement the
      :class:`pysyncml.protocol.Protocol` interface.

    :param synchronizer:

      this is the engine for handling sync requests and dispatching
      them to the various agents. If specified, the object must
      implement the :class:`pysyncml.synchronizer.Synchronizer`
      interface.

    :param codec:

      specify the codec used to encode the SyncML commands - typically
      either ``\'xml\'`` (the default) or ``\'wbxml\'``. It can also
      be an object that implements the :class:`pysyncml.codec.Codec`
      interface.

    '''
    self.autoCommit = autoCommit if autoCommit is not None else engine is None
    self._model = model.createModel(
      engine     = engine,
      storage    = storage,
      prefix     = prefix,
      owner_id   = owner,
      context    = self,
      )
    self.router       = router
    self.protocol     = protocol
    self.synchronizer = synchronizer
    self.codec        = codec
    for attr in dir(self._model):
      if attr in ('DatabaseObject', 'RawDatabaseObject', 'Version', 'Adapter'):
        continue
      value = getattr(self._model, attr)
      if issubclass(value.__class__, sqlalchemy.ext.declarative.DeclarativeMeta) \
         and value != self._model.DatabaseObject:
        setattr(self, attr, value)

  #----------------------------------------------------------------------------
  # TODO: add a method to delete all entries with a specific owner...
  #----------------------------------------------------------------------------

  #----------------------------------------------------------------------------
  def Adapter(self, **kw):
    '''
    .. TODO:: move this documentation into model/adapter.py?...

    The Adapter constructor supports the following parameters:

    :param devID:

      sets the local adapter\'s device identifier. For servers, this
      should be the externally accessible URL that launches the SyncML
      transaction, and for clients this should be a unique ID, such as
      the IMEI number (for mobile phones). If not specified, it will
      be defaulted to the `devID` of the `devinfo` object. If it
      cannot be loaded from the database or from the `devinfo`, then
      it must be provided before any synchronization can begin.

    :param name:

      sets the local adapter\'s device name - usually a human-friendly
      description of this SyncML\'s function.

    :param devinfo:

      sets the local adapter :class:`pysyncml.devinfo.DeviceInfo`.  If
      not specified, it will be auto-loaded from the database. If it
      cannot be loaded from the database, then it must be provided
      before any synchronization can begin.

    :param peer:

      TODO: document...

    :param maxGuidSize:

      TODO: document...

    :param maxMsgSize:

      TODO: document...

    :param maxObjSize:

      TODO: document...

    :param conflictPolicy:

      sets the default conflict handling policy for this adapter,
      and can be overriden on a per-store basis (applies only when
      operating as the server role).

    '''
    try:
      ret = self._model.Adapter.q(isLocal=True).one()
      for k, v in kw.items():
        setattr(ret, k, v)
    except NoResultFound:
      ret = self._model.Adapter(**kw)
      ret.isLocal = True
      self._model.session.add(ret)
      if ret.devID is not None:
        self._model.session.flush()
    ret.context       = self
    # todo: is this really the best place to do this?...
    ret.router        = self.router or router.Router(ret)
    ret.protocol      = self.protocol or protocol.Protocol(ret)
    ret.synchronizer  = self.synchronizer or synchronizer.Synchronizer(ret)
    ret.codec         = self.codec or 'xml'
    if isinstance(ret.codec, basestring):
      ret.codec = codec.Codec.factory(ret.codec)
    if ret.devID is not None:
      peers = ret.getKnownPeers()
      if len(peers) == 1 and peers[0].url is not None:
        ret._peer = peers[0]
    return ret

  #----------------------------------------------------------------------------
  def RemoteAdapter(self, **kw):
    '''
    .. TODO:: move this documentation into model/adapter.py?...

    The RemoteAdapter constructor supports the following parameters:

    :param url:

      specifies the URL that this remote SyncML server can be reached
      at. The URL must be a fully-qualified URL.

    :param auth:

      set what kind of authentication scheme to use, which generally is
      one of the following values:

        **None**:

          indicates no authentication is required.

        **pysyncml.NAMESPACE_AUTH_BASIC**:

          specifies to use "Basic-Auth" authentication scheme.

        **pysyncml.NAMESPACE_AUTH_MD5**:

          specifies to use MD5 "Digest-Auth" authentication scheme.
          NOTE: this may not be implemented yet...

    :param username:

      if the `auth` is not ``None``, then the username to authenticate
      as must be provided via this parameter.

    :param password:

      if the `auth` is not ``None``, then the password to authenticate
      with must be provided via this parameter.

    '''
    # TODO: is this really the right way?...
    ret = self._model.Adapter(isLocal=False, **kw)
    self._model.session.add(ret)
    if ret.devID is not None:
      self._model.session.flush()
    return ret

  #----------------------------------------------------------------------------
  @staticmethod
  def getAuthInfo(request, authorizer):
    xtree = codec.Codec.autoDecode(request.headers['content-type'], request.body)
    return protocol.Protocol.getAuthInfo(xtree, None, authorizer)

  #----------------------------------------------------------------------------
  @staticmethod
  def getTargetID(request):
    xtree = codec.Codec.autoDecode(request.headers['content-type'], request.body)
    return protocol.Protocol.getTargetID(xtree)

  #----------------------------------------------------------------------------
  def save(self):
    # TODO: is this just here for the test classes?... might this be better
    #       marked as an internal method?...
    # todo: is the "flush" really necessary?...
    if self.autoCommit:
      self._model.session.flush()
      self._model.session.commit()

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
