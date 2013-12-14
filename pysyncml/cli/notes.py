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
A "note" synchronization engine that stores notes in a
directory. Each note is stored in a separate file - although the
filename is tracked, it may be lost depending on the SyncML server
that is being contacted (if it correctly supports content-type
"text/x-s4j-sifn", then the filename will be preserved).

This program is capable of running as either a client or as a server -
for now however, for any given note directory it is recommended to
only be used as one or the other, not both. When run in server mode,
it currently only supports a single optional authenticated username.

When running in server mode, it currently expects to be run BY a
single user, FOR a single user. In other words, it is not a server
intended to be used by multiple users. The expected scenario is that a
user has multiple sync clients that they would like to centrally
synchronize. Anytime the user wants to sync any of the clients, they
would fire up a server, synchronize, and bring it down again.

Example first-time usage (see "--help" for details) as a client::

  sync-notes --remote https://example.com/funambol/ds \
             --username USERNAME --password PASSWORD \
             NOTE_DIRECTORY

Follow-up synchronizations::

  sync-notes NOTE_DIRECTORY

Example first-time usage as a server (listen port defaults to 80)::

  sync-notes --server --listen 8080 NOTE_DIRECTORY

Follow-up synchronizations::

  sync-notes NOTE_DIRECTORY

For the full documentation of all options, use::

  sync-notes --help

'''

#------------------------------------------------------------------------------
# IMPORTS
#------------------------------------------------------------------------------

import sys, os, re, logging, hashlib
import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.orm.exc import NoResultFound

import pysyncml
import pysyncml.cli
from pysyncml import adict
from pysyncml.i18n import _

#------------------------------------------------------------------------------
# GLOBALS
#------------------------------------------------------------------------------

# setup a logger
log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
# SYNC ENGINE
#------------------------------------------------------------------------------

# create a command-line interface synchronization engine. the key aspects here
# are to subclass :class:`pysyncml.cli.DirectorySyncEngine`, and invoke the
# constructor with parameters that define:
#   - the application name
#   - the local device information
#   - the Agent that will act as glue between pysyncml and the local data

#------------------------------------------------------------------------------
class NotesEngine(pysyncml.cli.DirectorySyncEngine):

  #----------------------------------------------------------------------------
  def __init__(self):
    super(NotesEngine, self).__init__(
      appLabel          = 'notes',
      appDisplay        = 'Note Synchronizer',
      devinfoParams     = dict(
        softwareVersion   = pysyncml.versionString,
        manufacturerName  = 'pysyncml',
        modelName         = 'pysyncml.cli.notes',
        ),
      agent             = NotesAgent(self),
      )

  #----------------------------------------------------------------------------
  @pysyncml.cli.hook('describe')
  def describe_notes(self, stream):
    # when the program is called with "--describe", it is supposed to report
    # current configuration and state. any program-specific output can be
    # added to the default output by hooking into the "describe" event.
    stream.write('Sync filename-only changes: %s\n'
                 % ('yes' if self.options.syncFilename else 'no',))

  #----------------------------------------------------------------------------
  @pysyncml.cli.hook('options.setup.term')
  def _syncFilenameOption(self):
    # the command-line parsing can be tweaked by hooking into the
    # "options.setup.*" events and modifying the engine ``self.parser``
    # attribute. for example, here an extra parameter "--no-filename-sync"
    # is being added to the end of the standard parameters.
    self.parser.add_argument(
      _('-F'), _('--no-filename-sync'),
      dest='syncFilename', default=True, action='store_false',
      help=_('by default, a change in a note\'s filename will cause the item'
             ' to be synchronized, even if there was no change to the content. This'
             ' option overrides this behavior to only synchronize filename changes'
             ' if there are also content changes (this is primarily useful to reduce'
             ' the overhead when synchronizing with a peer that does not properly'
             ' support filename synchronization, such as funambol).'))
    self.parser.description = \
      'Synchronizes notes stored as files in a directory' \
      ' using the SyncML protocol - see' \
      ' http://packages.python.org/pysyncml/pysyncml/cli/index.html' \
      ' for details.'


  #----------------------------------------------------------------------------
  @pysyncml.cli.hook('options.persist.save')
  def _options_persist_save_filename(self, options):
    # by default, the options parsed from the command line (and stored into
    # ``self.options``) are not persisted, so if the user calls the program
    # without the option, then the option will not be automatically set to
    # the previous value. by hooking into the "options.persist.save" event,
    # the program can alter this behavior and persist any values.

    # todo: it would be great if in 'options.setup.term' i could somehow tell
    #       the SyncEngine that syncFilename should be persisted...
    options['syncFilename'] = self.options.syncFilename

  #----------------------------------------------------------------------------
  @pysyncml.cli.hook('model.setup.extend')
  def _createNoteItemModel(self):
    # extending the standard sync engine model to keep track of meta
    # information about note files, so that changes to the files can
    # be detected from run to run. if a SyncEngine program does not
    # need to save state, or if it is already handled externally, then
    # this is not necessary.
    engine = self
    class NoteItem(engine.model.DatabaseObject, pysyncml.NoteItem):
      inode   = sqlalchemy.Column(sqlalchemy.Integer, index=True)
      name    = sqlalchemy.Column(sqlalchemy.String)
      sha256  = sqlalchemy.Column(sqlalchemy.String(64))
      lastmod = sqlalchemy.Column(sqlalchemy.Integer)
      def __init__(self, *args, **kw):
        engine.model.DatabaseObject.__init__(self, *args, **kw)
        # TODO: check this (and __dbinit__ too)...
        # NOTE: not calling NoteItem.__init__ as it can conflict with the
        #       sqlalchemy stuff done here...
        # todo: is this really necessary?...
        skw = dict()
        skw.update(kw)
        for key in self.__table__.c.keys():
          if key in skw:
            del skw[key]
        pysyncml.Ext.__init__(self, *args, **skw)
      @orm.reconstructor
      def __dbinit__(self):
        # note: not calling ``NoteItem.__init__`` - see ``__init__`` notes.
        pysyncml.Ext.__init__(self)
      def __str__(self):
        return 'Note "%s"' % (self.name,)
      def dump(self, stream, contentType, version):
        # todo: convert this to a .body @property?...
        with open(os.path.join(engine.rootDir, self.name), 'rb') as fp:
          self.body = fp.read()
        pysyncml.NoteItem.dump(self, stream, contentType, version)
        self.body = None
        return self
      @classmethod
      def load(cls, stream, contentType=None, version=None):
        base = pysyncml.NoteItem.load(stream, contentType, version)
        if contentType == pysyncml.TYPE_TEXT_PLAIN:
          # remove special characters, windows illegal set: \/:*?"<>|
          base.name = re.sub(r'[^a-zA-Z0-9,_+=!@#$%^&() -]+', '', base.name)
          # collapse white space and replace with '_'
          base.name = re.sub(r'\s+', '_', base.name) + '.txt'
        ret = NoteItem(name=base.name, sha256=hashlib.sha256(base.body).hexdigest())
        # temporarily storing the content in "body" attribute (until addItem()
        # is called)
        ret.body = base.body
        return ret
    self.model.NoteItem = NoteItem

  #----------------------------------------------------------------------------
  @pysyncml.cli.hook('adapter.create.store')
  def _scanNotes(self, context, adapter, store):
    # adding a hook to when the pysyncml store is created to detect and
    # register changes on the filesystem.
    self.agent.scan(store)

#------------------------------------------------------------------------------
# SYNC AGENT
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def hashstream(hash, stream):
  while True:
    buf = stream.read(8192)
    if len(buf) <= 0:
      return hash
    hash.update(buf)

#------------------------------------------------------------------------------
class NotesAgent(pysyncml.BaseNoteAgent):

  #----------------------------------------------------------------------------
  def __init__(self, engine, *args, **kw):
    super(NotesAgent, self).__init__(*args, **kw)
    self.engine     = engine
    self.ignoreRoot = None
    self.ignoreAll  = None
    self.mfactory   = pysyncml.CompositeMergerFactory(
      mergers=dict(body=pysyncml.TextMergerFactory()))
    # note: overriding contentTypes to remove multiple versions for funambol
    #       compatibility...
    # TODO: remove this! pysyncml should auto-detect the remote server's
    #       idiosyncracies and adjust!...
    self.contentTypes = [
      pysyncml.ContentTypeInfo(pysyncml.TYPE_SIF_NOTE, '1.1', preferred=True),
      pysyncml.ContentTypeInfo(pysyncml.TYPE_SIF_NOTE, '1.0'),
      # pysyncml.ContentTypeInfo(pysyncml.TYPE_TEXT_PLAIN, ['1.1', '1.0']),
      pysyncml.ContentTypeInfo(pysyncml.TYPE_TEXT_PLAIN, '1.0'),
      ]

  #----------------------------------------------------------------------------
  def scan(self, store):
    '''
    Scans the local files for changes (either additions, modifications or
    deletions) and reports them to the `store` object, which is expected to
    implement the :class:`pysyncml.Store` interface.
    '''
    # steps:
    #   1) generate a table of all store files, with filename,
    #      inode, checksum
    #   2) generate a table of all current files, with filename,
    #      inode, checksum
    #   3) iterate over all stored values and find matches, delete
    #      them from the "not-matched-yet" table, and record the
    #      change

    # TODO: if this engine is running as the client, i think the best
    #       strategy is to delete all pending changes before starting
    #       the scan process. that way, any left-over gunk from a
    #       previous sync that did not terminate well is cleaned up...

    # TODO: this algorithm, although better than the last, has the
    #       inconvenient downside of being very memory-hungry: it
    #       assumes that the entire list of notes (with sha256
    #       checksums - not the entire body) fits in memory. although
    #       it is not a ridiculous assumption (these are "notes" after
    #       all...), it would be nice if it did not rely on that.

    # todo: by tracking inode's, this *could* also potentially reduce
    #       some "del/add" operations with a single "mod"

    # todo: should this make use of lastmod timestamps?... that may
    #       help to reduce the number of checksums calculated and the
    #       number of entries loaded into memory...

    if self.ignoreRoot is None:
      self.ignoreRoot = re.compile('^(%s)$' % (re.escape(self.engine.syncSubdir),))

    dbnotes = list(self.engine.model.NoteItem.q())
    dbnames = dict((e.name, e) for e in dbnotes)

    fsnotes = list(self._scandir('.'))
    fsnames = dict((e.name, e) for e in fsnotes)

    # first pass: eliminate all entries with matching filenames & checksum

    for fsent in fsnames.values():
      if fsent.name in dbnames and dbnames[fsent.name].sha256 == fsent.sha256:
        log.debug('entry "%s" not modified', fsent.name)
        # todo: update db inode and lastmod if needed...
        del dbnames[fsent.name]
        del fsnames[fsent.name]

    # second pass: find entries that were moved to override another entry

    dbskip = []
    for dbent in dbnames.values():
      if dbent.id in dbskip or dbent.name in fsnames:
        continue
      for fsent in fsnames.values():
        if fsent.sha256 != dbent.sha256 or fsent.name not in dbnames:
          continue
        log.debug('entry "%s" deleted and replaced by "%s"', fsent.name, dbent.name)
        dbother = dbnames[fsent.name]
        del dbnames[dbent.name]
        del dbnames[fsent.name]
        del fsnames[fsent.name]
        dbskip.append(dbother.id)
        store.registerChange(dbent.id, pysyncml.ITEM_DELETED)
        for key, val in fsent.items():
          setattr(dbother, key, val)
        # the digest didn't change, so this is just a filename change...
        if self.engine.options.syncFilename:
          store.registerChange(dbother.id, pysyncml.ITEM_MODIFIED)
        break

    # third pass: find entries that were renamed

    dbskip = []
    for dbent in dbnames.values():
      if dbent.id in dbskip:
        continue
      for fsent in fsnames.values():
        if fsent.sha256 != dbent.sha256:
          continue
        log.debug('entry "%s" renamed to "%s"', dbent.name, fsent.name)
        del dbnames[dbent.name]
        del fsnames[fsent.name]
        for key, val in fsent.items():
          setattr(dbent, key, val)
        # the digest didn't change, so this is just a filename change...
        if self.engine.options.syncFilename:
          store.registerChange(dbent.id, pysyncml.ITEM_MODIFIED)
        break

    # fourth pass: find new and modified entries

    for fsent in fsnames.values():
      if fsent.name in dbnames:
        log.debug('entry "%s" modified', fsent.name)
        dbent = dbnames[fsent.name]
        del dbnames[fsent.name]
        store.registerChange(dbent.id, pysyncml.ITEM_MODIFIED)
      else:
        log.debug('entry "%s" added', fsent.name)
        dbent = self.engine.model.NoteItem()
        self.engine.dbsession.add(dbent)
        store.registerChange(dbent.id, pysyncml.ITEM_ADDED)
      for key, val in fsent.items():
        setattr(dbent, key, val)
      del fsnames[fsent.name]

    # fifth pass: find deleted entries

    for dbent in dbnames.values():
      store.registerChange(dbent.id, pysyncml.ITEM_DELETED)
      self.engine.dbsession.add(dbent)

  #----------------------------------------------------------------------------
  def _scandir(self, dirname):
    curdir = os.path.normcase(os.path.normpath(os.path.join(self.engine.rootDir, dirname)))
    log.debug('scanning directory "%s"...', curdir)
    for name in os.listdir(curdir):
      # apply the "ignoreRoot" and "ignoreAll" regex's - this is primarily to
      # ignore the pysyncml storage file in the root directory
      if dirname == '.':
        if self.ignoreRoot is not None and self.ignoreRoot.match(name):
          continue
      if self.ignoreAll is not None and self.ignoreAll.match(name):
        continue
      path = os.path.join(curdir, name)
      if os.path.islink(path):
        # TODO: should i special-handle?... ie. use SyncML "Ext" nodes...
        continue
      if os.path.isfile(path):
        yield self._scanfile(path, os.path.join(dirname, name))
      if os.path.isdir(path):
        # and recurse!...
        for fsnote in self._scandir(os.path.join(dirname, name)):
          yield fsnote

  #----------------------------------------------------------------------------
  def _scanfile(self, path, name):
    log.debug('analyzing file "%s"...', path)
    with open(path,'rb') as fp:
      return adict(
        inode   = os.stat(path).st_ino,
        name    = os.path.normpath(name),
        sha256  = hashstream(hashlib.sha256(), fp).hexdigest(),
        # todo: implement lastmod...
        lastmod = None,
        )

  #----------------------------------------------------------------------------
  def getAllItems(self):
    for note in self.engine.model.NoteItem.q():
      yield note

  #----------------------------------------------------------------------------
  def dumpItem(self, item, stream, contentType=None, version=None):
    item.dump(stream, contentType, version)

  #----------------------------------------------------------------------------
  def loadItem(self, stream, contentType=None, version=None):
    return self.engine.model.NoteItem.load(stream, contentType, version)

  #----------------------------------------------------------------------------
  def getItem(self, itemID):
    try:
      return self.engine.model.NoteItem.q(id=itemID).one()
    except NoResultFound:
      raise pysyncml.InvalidItem('could not find note ID "%s"' % (itemID,))

  #----------------------------------------------------------------------------
  def addItem(self, item):
    path = os.path.join(self.engine.rootDir, item.name)
    if '.' not in item.name:
      pbase = item.name
      psufx = ''
    else:
      pbase = item.name[:item.name.rindex('.')]
      psufx = item.name[item.name.rindex('.'):]
    count = 0
    while os.path.exists(path):
      count += 1
      item.name = '%s(%d)%s' % (pbase, count, psufx)
      path = os.path.join(self.engine.rootDir, item.name)
    with open(path, 'wb') as fp:
      fp.write(item.body)
    item.inode  = os.stat(path).st_ino
    delattr(item, 'body')
    self.engine.dbsession.add(item)
    log.debug('added: %s', item)
    return item

  #----------------------------------------------------------------------------
  def replaceItem(self, item, reportChanges):
    curitem = self.getItem(item.id)
    opath   = os.path.join(self.engine.rootDir, curitem.name)
    if reportChanges:
      orig = adict(name=curitem.name)
      with open(opath, 'rb') as fp:
        orig.body = fp.read()
    npath = os.path.join(self.engine.rootDir, item.name)
    with open(npath, 'wb') as fp:
      fp.write(item.body)
    curitem.name   = item.name
    curitem.inode  = os.stat(npath).st_ino
    curitem.sha256 = hashlib.sha256(item.body).hexdigest()
    cspec = None
    if reportChanges:
      merger = self.mfactory.newMerger()
      merger.pushChange('name', orig.name, item.name)
      merger.pushChange('body', orig.body, item.body)
      cspec = merger.getChangeSpec()
      delattr(orig, 'body')
    delattr(item, 'body')
    if npath != opath:
      os.unlink(opath)
    log.debug('updated: %s', curitem)
    return cspec

  #----------------------------------------------------------------------------
  def deleteItem(self, itemID):
    item = self.getItem(itemID)
    path = os.path.join(self.engine.rootDir, item.name)
    if os.path.exists(path):
      os.unlink(path)
    # note: writing log before actual delete as otherwise object is invalid
    log.debug('deleted: %s', item)
    self.engine.dbsession.delete(item)

  #----------------------------------------------------------------------------
  def mergeItems(self, localItem, remoteItem, changeSpec):
    opath = os.path.join(self.engine.rootDir, localItem.name)
    with open(opath, 'rb') as fp:
      oldbody = fp.read()
    merger = self.mfactory.newMerger(changeSpec)
    # the merger will raise ConflictError in the case of conflicts...
    newname = merger.mergeChanges('name', localItem.name, remoteItem.name)
    newbody = merger.mergeChanges('body', oldbody, remoteItem.body)
    newItem = pysyncml.NoteItem(name=remoteItem.name, body=newbody)
    newItem.id = localItem.id
    # todo: optimize this a bit because replaceItem is just going to
    #       read the note file again...
    return self.replaceItem(newItem, True)

#------------------------------------------------------------------------------
def main(argv=None):
  engine = NotesEngine()
  return engine.configure(argv).run()

#------------------------------------------------------------------------------
if __name__ == '__main__':
  sys.exit(main())

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
