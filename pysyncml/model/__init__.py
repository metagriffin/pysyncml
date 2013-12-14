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
The ``pysyncml.model`` module provides the data model for the SyncML adapter.
'''

import time, re, json, logging, sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy import Column, Integer, Boolean, String, Text, ForeignKey
from sqlalchemy.orm import relation, synonym, backref
from .. import common, constants
from . import adapter, devinfo, store, mapping

log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
def enableSqliteCascadingDeletes(engine):
  def onConnect(conn, record):
    conn.execute('PRAGMA foreign_keys=ON;')
  from sqlalchemy import event
  event.listen(engine, 'connect', onConnect)

# TODO: look into making all backref's lazy... so that the full recursive
#       loading of objects is not needed... see:
#         http://docs.sqlalchemy.org/en/rel_0_7/orm/collections.html
#       this is most necessary server-side, since client-side will not require
#       reloads for every message...

#------------------------------------------------------------------------------
def createModel(engine       = None,
                storage      = 'sqlite:///:memory:',
                prefix       = 'pysyncml',
                sessionMaker = None,
                owner_id     = None,
                context      = None,
                ):

  if not re.match('^[a-z_]+$', prefix, re.IGNORECASE):
    raise common.InvalidContext('invalid storage prefix "%s" - valid chars: alphabet and underscore'
                                % (prefix,))

  if engine is None:
    log.debug('configuring pysyncml model to use storage "%s" with prefix "%s"', storage, prefix)
    engine = sqlalchemy.create_engine(storage)
    if engine.dialect.driver == 'pysqlite' or storage.startswith('sqlite://'):
      enableSqliteCascadingDeletes(engine)
  else:
    log.debug('configuring pysyncml model to use engine %r with prefix "%s"', engine, prefix)

  # TODO: THIS IS INCORRECT! THE SESSION SHOULD NOT BE MADE HERE, BUT INSTEAD
  #       WHEN A TRANSACTION BEGINS...
  if sessionMaker is None:
    session = sessionmaker(bind=engine)()
  else:
    # sessionMaker.configure(bind=engine)
    session = sessionMaker()

  # TODO: this needs to be made much more efficient... ie. it should create
  #       the classes once, and have a "context" that will pre-populate the
  #       .owner, instead of here where the classes are generated for every
  #       request to the server (client-side, this is not so bad...).

  #------------------------------------------------------------------------------
  class DatabaseObject(object):
    __table_args__ = {'mysql_engine': 'InnoDB'}
    # todo: investigate making these configurable:
    #   __mapper_args__= {'always_refresh': True}
    __syscols__ = ('id', 'owner')
    @declared_attr
    def __tablename__(cls):
      return prefix + '_' + cls.__name__.lower()
    id       = Column(Integer, autoincrement=True, primary_key=True)
    # TODO: make the owner_id read-only somehow...
    # TODO: make type(owner) configurable...
    owner    = Column(Integer, default=owner_id)
    _context = context
    @classmethod
    def q(cls, **kw):
      return session.query(cls).filter_by(owner=owner_id).filter_by(**kw)
    def _setDefaults(self):
      # TODO: this seems like such a broken way of setting default values
      #       such that they are made available before a session.flush()...
      #         http://www.mail-archive.com/sqlalchemy@googlegroups.com/msg24705.html
      for col in self.__table__.c:
        if col.default is not None:
          try:
            val = col.default.arg(self)
          except TypeError:
            val = col.default.arg
          self.__setattr__(col.key, val)
    def __repr__(self):
      ret = '<%s: ' % (self.__class__.__name__,)
      ret += '; '.join(['%s=%s' % (col.name, getattr(self, col.name))
                        for col in self.__table__.c
                        if getattr(self, col.name) is not None])
      return ret + '>'

  RawDatabaseObject = declarative_base()
  DatabaseObject    = declarative_base(cls=DatabaseObject)
  #----------------------------------------------------------------------------
  class Model:

    def __init__(self, engine, session):
      self.RawDatabaseObject = RawDatabaseObject
      self.DatabaseObject    = DatabaseObject
      self.engine            = engine
      self.prefix            = prefix
      self.session           = session
      self.version           = 1
      self.context           = context

    class Version(RawDatabaseObject):
      __tablename__     = prefix + '_migrate'
      repository_id     = Column(String(250), nullable=False, primary_key=True)
      repository_path   = Column(Text)
      version           = Column(Integer, default=None)

    # class Route(DatabaseObject):
    #   # note: these are "manual" routes - automatic routes do not get an
    #   #       entry here, only a Binding (which manual routes also get)
    #   adapter_id        = Column(Integer, ForeignKey('%s_adapter.id' % (prefix,),
    #                                                  onupdate='CASCADE', ondelete='CASCADE'),
    #                              nullable=False, index=True)
    #   adapter           = relation('Adapter', backref=backref('routes', # order_by=id,
    #                                                           cascade='all, delete-orphan',
    #                                                           passive_deletes=True))

    #   sourceUri         = Column(String(4095), nullable=True)
    #   targetUri         = Column(String(4095), nullable=True)

  model = Model(engine, session)

  # TODO: there must be a way to "discover" packages...
  for module in (adapter, devinfo, store, mapping):
    module.decorateModel(model)

  # TODO: it would be *great* if i could use sqlalchemy-migrate for this...
  try:
    sql = sqlalchemy.text('SELECT version FROM %s_migrate WHERE repository_id=:repid'
                          % (prefix,),
                          bindparams=[sqlalchemy.bindparam('repid', String)])
    version = engine.execute(sql, repid=prefix).scalar()
    if version is None:
      log.fatal('corrupt pysyncml storage: no migration table entry')
      raise common.InvalidAdapter('corrupt pysyncml storage: no migration table entry')
  except sqlalchemy.exc.OperationalError, e:
  # TODO: figure out if there is a db-agnostic way to check for this error.
  #       e.g. the mysql error is:
  #         sqlalchemy.exc.ProgrammingError: (ProgrammingError) (1146, \
  #           "Table '...' doesn't exist") 'SELECT ...' ()
    if 'no such table' not in str(e):
      log.exception('could not determine pysyncml storage schema version')
      raise
    version = None

  if version is None:
    # TODO: delete tables first?...
    # TODO: this should be controllable by the invoking context...
    log.warn('pysyncml database migration table not found - assuming new and creating all')
    RawDatabaseObject.metadata.create_all(model.engine)
    DatabaseObject.metadata.create_all(model.engine)
    version = model.Version(repository_id=prefix, repository_path='migration', version=model.version)
    model.session.add(version)
    model.session.flush()
    model.session.commit()
  elif version != model.version:
    raise NotImplementedError('pysyncml database version out of sync and no upgrade path implemented')

  return model

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
