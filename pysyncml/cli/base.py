# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/08/02
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
The ``pysyncml.cli.base`` is a helper module that provides commonly used
functionality when implementing a pysyncml command line interface
synchronization engine.
'''

import sys, os, re, time, uuid, hashlib, logging, getpass, traceback
import BaseHTTPServer, Cookie, urlparse, urllib, yaml, argparse
import xml.etree.ElementTree as ET
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.ext.declarative import _declarative_constructor as SaInit
from sqlalchemy.orm import relation, synonym, backref, sessionmaker
from sqlalchemy.orm.exc import NoResultFound
import pysyncml

log = logging.getLogger(__name__)

#------------------------------------------------------------------------------
class LogFormatter(logging.Formatter):
  levelString = {
    logging.DEBUG:       '[  ] DEBUG   ',
    logging.INFO:        '[--] INFO    ',
    logging.WARNING:     '[++] WARNING ',
    logging.ERROR:       '[**] ERROR   ',
    logging.CRITICAL:    '[**] CRITICAL',
    }
  def __init__(self, logsource, *args, **kw):
    logging.Formatter.__init__(self, *args, **kw)
    self.logsource = logsource
  def format(self, record):
    msg = record.getMessage()
    pfx = '%s|%s: ' % (LogFormatter.levelString[record.levelno], record.name) \
          if self.logsource else \
          '%s ' % (LogFormatter.levelString[record.levelno],)
    if msg.find('\n') < 0:
      return '%s%s' % (pfx, record.getMessage())
    return pfx + ('\n' + pfx).join(msg.split('\n'))

#------------------------------------------------------------------------------
def makeModel(engine):

  #----------------------------------------------------------------------------
  class DatabaseObject(object):
    @declared_attr
    def __tablename__(cls):
      return cls.__name__.lower()
    id = sa.Column(sa.String(32), primary_key=True)
    def __init__(self, *args, **kw):
      if 'id' not in kw:
        kw['id'] = str(uuid.uuid4()).replace('-', '')
      SaInit(self, *args, **kw)
    @classmethod
    def q(cls, **kw):
      return engine.dbsession.query(cls).filter_by(**kw)

  #----------------------------------------------------------------------------
  class Model(object): pass
  model = Model()
  model.engine = engine
  model.DatabaseObject = declarative_base(cls=DatabaseObject, constructor=None)

  #----------------------------------------------------------------------------
  class Server(model.DatabaseObject):
    port   = sa.Column(sa.Integer)
    policy = sa.Column(sa.Integer)
  model.Server = Server

  #----------------------------------------------------------------------------
  class User(model.DatabaseObject):
    username  = sa.Column(sa.String)
    password  = sa.Column(sa.String)
    server_id = sa.Column(sa.String(32),
                          sa.ForeignKey('server.id',
                                        onupdate='CASCADE', ondelete='CASCADE'),
                          nullable=False, index=True)
    server    = relation('Server', backref=backref('users', # order_by=id,
                                                   cascade='all, delete-orphan',
                                                   passive_deletes=True))
  model.User = User

  return model

#------------------------------------------------------------------------------
def hook(name):
  '''
  Decorator used to tag a method that should be used as a hook for the
  specified `name` hook type.
  '''
  def hookTarget(wrapped):
    if not hasattr(wrapped, '__hook__'):
      wrapped.__hook__ = [name]
    else:
      wrapped.__hook__.append(name)
    return wrapped
  return hookTarget

#------------------------------------------------------------------------------
class CommandLineSyncEngine(object):
  '''
  The `CommandLineEngine` class helps ease the burden of creating a command
  line sync engine by implementing the following functionality:

  * Selection and allocation of pysyncml storage repository.
  * Generation of an extensible sqlalchemy model.
  * Support for client-side and/or server-side operation.
  * Configuration of commonly used command line options.

  There are different subclasses that exist to support different operation
  styles:

  * :class:`DirectorySyncEngine`:

    A directory-based approach, where the items being synchronized are
    stored in a directory, and different directories can have different
    application and synchronization profiles.

  * :class:`LocalUserSyncEngine`:

    A more centralized approach, where the items being synchronized are stored
    in some host-local per-user location (for example, in another application\'s
    settings). In this case, the user must specifically request a different
    configuration in order to choose a different application or synchronization
    profile.
  '''

  #----------------------------------------------------------------------------
  def __init__(self,
               appLabel         = None,
               appDisplay       = None,
               appModelVersion  = None,
               defaultDevID     = None,
               defaultListen    = 80,
               devinfoParams    = dict(),
               storeParams      = dict(),
               agent            = None,
               hooks            = None,
               *args, **kw):
    '''
    The CommandLineClient base constructor accepts the following parameters:

    :param appLabel:

      A short unique identifier for this application, typically set to
      the program\'s name, for example "sync-notes". This label should not
      contain any special characters, especially those that are not allowed
      as part of a filename. Amongst other things, it is used to:

      * generate the default device ID, if not specified,
      * create application-specific configuration directory/file names,
      * default datastore URI,
      * and much more.

    :param appDisplay:

      The name of the application when displayed to the user, for
      example "Note Synchronizer".

    The CommandLineClient also has the following additional attributes:

    :param dataDir:

      The directory that contains all of the database files - this
      is usually taken care of by one of the pre-existing subclasses.
      It is expected to end with a "/".

    TODO: document all options...

    '''
    super(CommandLineSyncEngine, self).__init__()#*args, **kw)
    self.appLabel         = appLabel
    self.appDisplay       = appDisplay
    self.appModelVersion  = appModelVersion
    self.defaultDevID     = defaultDevID
    self.defaultListen    = defaultListen
    self.devinfoParams    = devinfoParams
    self.storeParams      = storeParams
    self.agent            = agent
    self.dataDir          = None
    self._hooks           = dict()

    # create a default device ID that is fairly certain to be globally unique. for
    # example, the IMEI number for a mobile phone. in this case, we are using
    # uuid.getnode() which generates a hash based on the local MAC address.
    # note that this is only used the first time an app is used with a
    # given dataDir - after that, the device ID is retrieved from the sync database.
    if self.defaultDevID is None:
      self.defaultDevID = '%s:%x:%x' % (self.appLabel, uuid.getnode(), time.time())

    for meth in dir(self):
      meth = getattr(self, meth)
      if not callable(meth) or not hasattr(meth, '__hook__'):
        continue
      for name in meth.__hook__:
        self.addHook(name, meth)

    for name, funcs in hooks or []:
      for func in funcs:
        self.addHook(name, func)

  #----------------------------------------------------------------------------
  def addHook(self, name, callable):
    '''
    Subscribes `callable` to listen to events of `name` type. The
    parameters passed to `callable` are dependent on the specific
    event being triggered.
    '''
    if name not in self._hooks:
      self._hooks[name] = []
    self._hooks[name].append(callable)

  #----------------------------------------------------------------------------
  def getHooks(self, name, default=None):
    return self._hooks.get(name, default)

  #----------------------------------------------------------------------------
  def _callHooks(self, name, *args, **kw):
    methname = '_callHooks_' + name.replace('.', '_')
    if hasattr(self, methname):
      return getattr(self, methname)(*args, **kw)
    for hook in self.getHooks(name, []):
      hook(*args, **kw)

  #----------------------------------------------------------------------------
  def _setupOptions(self):

    self.parser = argparse.ArgumentParser()
    self._callHooks('options.setup.init')

    self.parser.add_argument(
      '-V', '--version', action='version',
      version='%(prog)s ' + pysyncml.versionString,
      help='displays the program version and exits')

    # TODO: i18n!...
    self.parser.add_argument(
      '-v', '--verbose', default=0, action='count',
      help='enable verbose output to STDERR, mostly for diagnostic'
      ' purposes (multiple invocations increase verbosity)')

    self.parser.add_argument(
      '-q', '--quiet', default=False, action='store_true',
      help='do not display sync summary')

    self._callHooks('options.setup.generic')

    self.parser.add_argument(
      '-d', '--describe', default=False, action='store_true',
      help='configure the local SyncML adapter, display a summary'
      ' and exit without actually synchronizing')

    self.parser.add_argument(
      '-l', '--local', default=False, action='store_true',
      help='display the pending local changes and exit'
      ' without actually synchronizing')

    # todo: this "generated based on..." is potentially not accurate
    #       if the subclass overrides it...
    self.parser.add_argument(
      '-i', '--id', dest='devid', default=None, action='store',
      help='overrides the default device ID, either the stored'
      ' value from a previous sync or the generated default'
      ' (currently "%s" - generated based on local MAC address'
      ' and current time)'
      % (self.defaultDevID,))

    # todo: perhaps display the default from persisted values?...
    self.parser.add_argument(
      '-n', '--name', default=None, action='store',
      help='sets the local adapter/store name (default: "%s")'
      % (self.appDisplay,))

    self.parser.add_argument(
      '-m', '--mode', default='sync', action='store',
      help='set the synchronization mode - can be one of "sync"'
      ' (for two-way synchronization), "full" (for a complete'
      ' re-synchronization), "pull" (for fetching remote'
      ' changes only), "push" (for pushing local changes only),'
      ' or "pull-over" (to obliterate the local data and'
      ' download the remote data) or "push-over" (to obliterate'
      ' the remote data and upload the local data) - the default'
      ' is "%(default)s"')

    # todo: this "only required..." is potentially not accurate
    self.parser.add_argument(
      '-r', '--remote', metavar='URL', default=None, action='store',
      help='specifies the remote URL of the SyncML synchronization'
      ' server - only required if the target DIRECTORY has never'
      ' been synchronized, or the synchronization meta information'
      ' was lost')

    self.parser.add_argument(
      '-R', '--remote-uri', metavar='URI',
      dest='remoteUri', default=None, action='store',
      help='specifies the remote datastore URI to bind to. if'
      ' left unspecified, pysyncml will attempt to identify it'
      ' automatically')

    self.parser.add_argument(
      '-s', '--server', default=False, action='store_true',
      help='enables HTTP server mode. NOTE: currently, a given'
      ' directory should not be used for both client and server'
      ' modes (this can and will eventually be resolved).')

    self.parser.add_argument(
      '-L', '--listen', metavar='PORT', default=None, action='store', type=int,
      help='specifies the port to listen on for server mode'
      ' (implies --server and defaults to port %d)'
      % (self.defaultListen,))

    self.parser.add_argument(
      '-P', '--policy', metavar='POLICY', default=None, action='store',
      help='specifies the conflict resolution policy that this'
      ' SyncML peer (when operating as the server role) should use'
      ' to resolve conflicts that cannot be merged or otherwise'
      ' resolved -- can be one of "error" (default), "client-wins"'
      ' or "server-wins"')

    self.parser.add_argument(
      '-u', '--username', default=None, action='store',
      help='specifies the remote server username to log in with'
      ' (in client mode) or to require authorization for (in'
      ' server mode)')

    self.parser.add_argument(
      '-p', '--password', default=None, action='store',
      help='specifies the remote server password to log in with'
      ' in client mode (if "--remote" and "--username" is'
      ' specified, but not "--password", the password will be'
      ' prompted for to avoid leaking the password into the'
      ' local hosts environment, which is the recommended'
      ' approach). in server mode, specifies the password for'
      ' the required username (a present "--username" and missing'
      ' "--password" is handled the same way as in client'
      ' mode)')

    self._callHooks('options.setup.term')

  #----------------------------------------------------------------------------
  def _loadOptions(self):
    optfile = os.path.join(self.dataDir, 'options.yaml')
    if not os.path.isfile(optfile):
      return
    with open(optfile, 'rb') as fp:
      options = yaml.load(fp)
    self.parser.set_defaults(**options)
    self._callHooks('options.persist.load', options)

  #----------------------------------------------------------------------------
  def _saveOptions(self):
    optfile = os.path.join(self.dataDir, 'options.yaml')
    options = dict()
    if self.options.server:
      options['server'] = True
      options['listen'] = self.options.listen
    self._callHooks('options.persist.save', options)
    with open(optfile, 'wb') as fp:
      yaml.dump(options, stream=fp, default_flow_style=False)

  #----------------------------------------------------------------------------
  def _parseOptions(self, argv=None):
    if argv is None:
      argv = sys.argv[1:]
    self._callHooks('options.parse.init')
    self.options = self.parser.parse_args(argv)
    self._callHooks('options.parse.datadir')
    self._loadOptions()
    self.options = self.parser.parse_args(argv)
    if self.options.server or self.options.listen is not None:
      self.options.server = True
    self._callHooks('options.parse.term')
    self._saveOptions()

  #----------------------------------------------------------------------------
  def _setupLogging(self):
    # setup logging (based on requested verbosity)
    rootlog = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(LogFormatter(self.options.verbose >= 2))
    rootlog.addHandler(handler)
    if self.options.verbose >= 3:   rootlog.setLevel(logging.DEBUG)
    elif self.options.verbose == 2: rootlog.setLevel(logging.INFO)
    elif self.options.verbose == 1: rootlog.setLevel(logging.INFO)
    else:                           rootlog.setLevel(logging.FATAL)

  #----------------------------------------------------------------------------
  def _setupModel(self):
    createDb = not os.path.isfile('%s%s.db' % (self.dataDir, self.appLabel))
    self.dbengine  = sa.create_engine('sqlite:///%s%s.db' % (self.dataDir, self.appLabel))
    pysyncml.enableSqliteCascadingDeletes(self.dbengine)
    self.dbsession = sessionmaker(bind=self.dbengine)()
    self._callHooks('model.setup.init')
    self.model = makeModel(self)
    self._callHooks('model.setup.extend')
    if createDb:
      self.model.DatabaseObject.metadata.create_all(self.dbengine)
    # TODO: implement detection of the schema changing...
    self._callHooks('model.setup.term')

  #----------------------------------------------------------------------------
  def _makeAdapter(self):
    '''
    Creates a tuple of ( Context, Adapter ) based on the options
    specified by `self.options`. The Context is the pysyncml.Context created for
    the storage location specified in `self.options`, and the Adapter is a newly
    created Adapter if a previously created one was not found.
    '''

    self._callHooks('adapter.create.init')

    # create a new pysyncml.Context. the main function that this provides is
    # to give the Adapter a storage engine to store state information across
    # synchronizations.
    context = pysyncml.Context(storage='sqlite:///%ssyncml.db' % (self.dataDir,),
                               owner=None, autoCommit=True)

    self._callHooks('adapter.create.context', context)

    # create an Adapter from the current context. this will either create
    # a new adapter, or load the current local adapter for the specified
    # context storage location. if it is new, then lots of required
    # information (such as device info) will not be set, so we need to
    # check that and specify it if missing.

    adapter = context.Adapter()

    if hasattr(self, 'serverConf') and self.serverConf.policy is not None:
      adapter.conflictPolicy = self.serverConf.policy

    if self.options.name is not None or self.appDisplay is not None:
      adapter.name = self.options.name or self.appDisplay

    # TODO: stop ignoring ``self.options.remoteUri``... (the router must first support
    #       manual routes...)
    # if self.options.remoteUri is not None:
    #   adapter.router.addRoute(self.agent.uri, self.options.remoteUri)

    if adapter.devinfo is None:
      log.info('adapter has no device info - registering new device')
    else:
      if self.options.devid is not None and self.options.devid != adapter.devinfo.devID:
        log.info('adapter has different device ID - overwriting with new device info')
        adapter.devinfo = None

    if adapter.devinfo is None:
      # setup some information about the local device, most importantly the
      # device ID, which the remote peer will use to uniquely identify this peer
      devinfoParams = dict(
        devID             = self.options.devid or self.defaultDevID,
        devType           = pysyncml.DEVTYPE_SERVER if self.options.server else \
                            pysyncml.DEVTYPE_WORKSTATION,
        manufacturerName  = 'pysyncml',
        modelName         = self.appLabel,
        softwareVersion   = pysyncml.versionString,
        hierarchicalSync  = self.agent.hierarchicalSync if self.agent is not None else False,
        )
      if self.devinfoParams is not None:
        devinfoParams.update(self.devinfoParams)
      adapter.devinfo = context.DeviceInfo(**devinfoParams)

    self._callHooks('adapter.create.adapter', context, adapter)

    if not self.options.server:

      # servers don't have a fixed peer; i.e. the SyncML message itself
      # defines which peer is connecting.

      if adapter.peer is None:
        if self.options.remote is None:
          self.options.remote = raw_input('SyncML remote URL: ')
          if self.options.username is None:
            self.options.username = raw_input('SyncML remote username (leave empty if none): ')
            if len(self.options.username) <= 0:
              self.options.username = None
        log.info('adapter has no remote info - registering new remote adapter')
      else:
        if self.options.remote is not None:
          if self.options.remote != adapter.peer.url \
             or self.options.username != adapter.peer.username \
             or self.options.password != adapter.peer.password:
            #or self.options.password is not None:
            log.info('adapter has invalid or rejected remote info - overwriting with new remote info')
            adapter.peer = None

      if adapter.peer is None:
        auth = None
        if self.options.username is not None:
          auth = pysyncml.NAMESPACE_AUTH_BASIC
          if self.options.password is None:
            self.options.password = getpass.getpass('SyncML remote password: ')
        # setup the remote connection parameters, if not already stored in
        # the adapter sync tables or the URL has changed.
        adapter.peer = context.RemoteAdapter(
          url      = self.options.remote,
          auth     = auth,
          username = self.options.username,
          password = self.options.password,
          )

      self._callHooks('adapter.create.peer', context, adapter, adapter.peer)

    # add a datastore attached to the URI "note". the actual value of
    # the URI is irrelevant - it is only an identifier for this item
    # synchronization channel. it must be unique within this adapter
    # and must stay consistent across synchronizations.

    # TODO: this check should be made redundant... (ie. once the
    #       implementation of Store.merge() is fixed this will
    #       become a single "addStore()" call without the check first).
    uri = self.storeParams.get('uri', self.appLabel)
    if uri in adapter.stores:
      store = adapter.stores[uri]
      store.agent = self.agent
    else:
      storeParams = dict(
        uri         = uri,
        displayName = self.options.name or self.appDisplay,
        agent       = self.agent,
        # TODO: adding this for funambol-compatibility...
        maxObjSize  = None)
      if self.storeParams is not None:
        storeParams.update(self.storeParams)
      store = adapter.addStore(context.Store(**storeParams))

    self._callHooks('adapter.create.store', context, adapter, store)

    if self.options.local:
      def locprint(msg):
        print msg
    else:
      locprint = log.info
    def showChanges(changes, prefix):
      for c in changes:
        if c.state != pysyncml.ITEM_DELETED:
          item = self.agent.getItem(c.itemID)
        else:
          item = 'Item ID %s' % (c.itemID,)
        locprint('%s  - %s: %s' % (prefix, item, pysyncml.state2string(c.state)))
    if self.options.server:
      peers = adapter.getKnownPeers()
      if len(peers) > 0:
        locprint('Pending changes to propagate:')
      else:
        locprint('No pending changes to propagate (no peers yet)')
      for peer in peers:
        for puri, pstore in peer.stores.items():
          if pstore.binding is None or pstore.binding.uri != store.uri:
            continue
          changes = list(pstore.getRegisteredChanges())
          if len(changes) <= 0:
            locprint('  Registered to peer "%s" URI "%s": (none)' % (peer.devID, puri))
          else:
            locprint('  Registered to peer "%s" URI "%s":' % (peer.devID, puri))
          showChanges(changes, '  ')
    else:
      if store.peer is None:
        locprint('No pending local changes (not associated yet).')
      else:
        changes = list(store.peer.getRegisteredChanges())
        if len(changes) <= 0:
          locprint('No pending local changes to synchronize.')
        else:
          locprint('Pending local changes:')
        showChanges(changes, '')

    self._callHooks('adapter.create.term', context, adapter)

    return (context, adapter)

  #----------------------------------------------------------------------------
  def _runServer(self, stdout, stderr):
    try:
      sconf = self.model.Server.q().one()
    except NoResultFound:
      log.debug('no prior server - creating new server configuration')
      sconf = self.model.Server()
      self.dbsession.add(sconf)

    # TODO: moves this conversion of command-line options to storage
    #       into the "configure" phase...

    if self.options.policy is not None:
      sconf.policy = {
        'error':          pysyncml.POLICY_ERROR,
        'client-wins':    pysyncml.POLICY_CLIENT_WINS,
        'server-wins':    pysyncml.POLICY_SERVER_WINS,
        }[self.options.policy]
    if self.options.listen is not None:
      sconf.port = self.options.listen
    if sconf.port is None:
      sconf.port = self.defaultListen
    if self.options.username is not None:
      if self.options.password is None:
        self.options.password = getpass.getpass('SyncML remote password: ')
      # todo: support multiple credentials?...
      sconf.users = [self.model.User(username=self.options.username,
                                     password=self.options.password)]
    self.serverConf = sconf
    self.dbsession.commit()
    sessions = dict()
    syncengine = self
    class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
      def version_string(self):
        return 'pysyncml/' + pysyncml.versionString
      def _parsePathParameters(self):
        self.path_params = dict()
        pairs = [e.split('=', 1) for e in self.path.split(';')[1:]]
        for pair in pairs:
          key = urllib.unquote_plus(pair[0])
          if len(pair) < 2:
            self.path_params[key] = True
          else:
            self.path_params[key] = urllib.unquote_plus(pair[1])
      def do_POST(self):
        self._parsePathParameters()
        log.debug('handling POST request to "%s" (parameters: %r)', self.path, self.path_params)
        sid = None
        self.session = None
        if 'Cookie' in self.headers:
          cks = Cookie.SimpleCookie(self.headers["Cookie"])
          if 'sessionid' in cks:
            sid = cks['sessionid'].value
            if sid in sessions:
              self.session = sessions[sid]
              self.session.count += 1
            else:
              sid = None
        if sid is None:
          log.debug('no valid session ID found in cookies - checking path parameters')
          sid = self.path_params.get('sessionid')
          if sid in sessions:
            self.session = sessions[sid]
            self.session.count += 1
          else:
            sid = None
        if sid is None:
          while sid is None or sid in sessions:
            sid = str(uuid.uuid4())
          log.debug('request without valid session ID - creating new session: %s', sid)
          self.session = pysyncml.adict(id=sid, count=1, syncml=pysyncml.Session())
          sessions[sid] = self.session
        log.debug('session: id=%s, count=%d', self.session.id, self.session.count)
        try:
          response = self.handleRequest()
        except Exception, e:
          self.send_response(500)
          self.end_headers()
          self.wfile.write(traceback.format_exc())
          return
        self.send_response(200)
        if self.session.count <= 1:
          cks = Cookie.SimpleCookie()
          cks['sessionid'] = sid
          self.send_header('Set-Cookie', cks.output(header=''))
        if response.contentType is not None:
          self.send_header('Content-Type', response.contentType)
        self.send_header('Content-Length', str(len(response.body)))
        self.send_header('X-PySyncML-Session', 'id=%s, count=%d' % (self.session.id, self.session.count))
        self.end_headers()
        self.wfile.write(response.body)
      def handleRequest(self):
        syncengine.dbsession = sessionmaker(bind=syncengine.dbengine)()
        # TODO: enforce authentication...
        # if len(sconf.users) > 0:
        #   ...
        #   self.assertEqual(pysyncml.Context.getAuthInfo(request, None),
        #                    adict(auth=pysyncml.NAMESPACE_AUTH_BASIC,
        #                          username='guest', password='guest'))
        #                    
        context, adapter = syncengine._makeAdapter()
        clen = 0
        if 'Content-Length' in self.headers:
          clen = int(self.headers['Content-Length'])
        request = pysyncml.adict(headers=dict((('content-type', 'application/vnd.syncml+xml'),)),
                                 body=self.rfile.read(clen))
        self.session.syncml.effectiveID = pysyncml.Context.getTargetID(request)
        # todo: this should be a bit more robust...
        urlparts = list(urlparse.urlsplit(self.session.syncml.effectiveID))
        if self.path_params.get('sessionid') != self.session.id:
          urlparts[2] += ';sessionid=' + self.session.id
          self.session.syncml.returnUrl = urlparse.SplitResult(*urlparts).geturl()
        response = pysyncml.Response()
        self.stats = adapter.handleRequest(self.session.syncml, request, response)
        syncengine.dbsession.commit()
        return response

    server = BaseHTTPServer.HTTPServer(('', sconf.port), Handler)
    log.info('starting server on port %d', sconf.port)
    try:
      server.serve_forever()
    except KeyboardInterrupt:
      log.info('shutting down server (stopped by user)')
    return 0

  #----------------------------------------------------------------------------
  def _runClient(self, stdout, stderr):
    context, adapter = self._makeAdapter()
    mode = {
      'sync':      pysyncml.SYNCTYPE_TWO_WAY,
      'full':      pysyncml.SYNCTYPE_SLOW_SYNC,
      'pull':      pysyncml.SYNCTYPE_ONE_WAY_FROM_SERVER,
      'push':      pysyncml.SYNCTYPE_ONE_WAY_FROM_CLIENT,
      'pull-over': pysyncml.SYNCTYPE_REFRESH_FROM_SERVER,
      'push-over': pysyncml.SYNCTYPE_REFRESH_FROM_CLIENT,
      }[self.options.mode]
    stats = adapter.sync(mode=mode)
    if not self.options.quiet:
      # TODO: i18n!...
      pysyncml.describeStats(stats, stdout, title='Synchronization Summary')
    context.save()
    self.dbsession.commit()
    return 0

  #----------------------------------------------------------------------------
  def describe(self, stream):
    # TODO: i18n!...
    stream.write('%s configuration:\n' % (self.appDisplay,))
    s2 = pysyncml.IndentStream(stream)
    s2.write('Role: %s\n' % ('server' if self.options.server else 'client',))
    if self.options.server:
      print >>s2, 'Listen port:', self.options.listen or self.defaultListen
    self._callHooks('describe', s2)

  #----------------------------------------------------------------------------
  def configure(self, argv=None):
    '''
    Configures this engine based on the options array passed into
    `argv`. If `argv` is ``None``, then ``sys.argv`` is used instead.
    During configuration, the command line options are merged with
    previously stored values. Then the logging subsystem and the
    database model are initialized, and all storable settings are
    serialized to configurations files.
    '''
    self._setupOptions()
    self._parseOptions(argv)
    self._setupLogging()
    self._setupModel()
    self.dbsession.commit()
    return self

  #----------------------------------------------------------------------------
  def run(self, stdout=sys.stdout, stderr=sys.stderr):
    '''
    Runs this SyncEngine by executing one of the following functions
    (as controlled by command-line options or stored parameters):

    * Display local pending changes.
    * Describe local configuration.
    * Run an HTTP server and engage server-side mode.
    * Connect to a remote SyncML peer and engage client-side mode.

    NOTE: when running in the first two modes, all database interactions
    are rolled back in order to keep the SyncEngine idempotent.
    '''
    if self.options.local or self.options.describe:
      context, adapter = self._makeAdapter()
      if self.options.describe:
        self.describe(stdout)
        adapter.describe(stdout)
      self.dbsession.rollback()
      return 0
    if self.options.server:
      return self._runServer(stdout, stderr)
    return self._runClient(stdout, stderr)

#------------------------------------------------------------------------------
class DirectorySyncEngine(CommandLineSyncEngine):
  '''
  The `DirectorySyncEngine` is a helper peer environment where
  synchronized items are stored in a directory (or subdirectories thereof). A special
  (configurable) ``.sync`` subdirectory is created to contain configuration,
  state and synchronization data, which must be ignored by the calling
  framework. Moving the directory and its contents, as a unit, will not affect
  the functionality of the sync.
  '''

  #----------------------------------------------------------------------------
  def __init__(self, syncSubdir='.sync', defaultDir=None,
               *args, **kw):
    '''
    In addition to the :class:`CommandLineSyncEngine` constructor parameters,
    the `DirectorySyncEngine` accepts the following:

    :param syncSubdir:

      Specifies the name of the immediate subdirectory of the base
      directory that should be created to contain configuration, state
      and synchronization data. Removal of this directory will reset
      all client/server states, and synchronization will need to resume
      via a "slow-sync". The application should ignore this directory
      when manipulating any data. The default is ``".sync"``.

    :param defaultDir:

      If specified, will allow the user to invoke the application without
      needing to identify the directory to synchronize, and instead will
      default to this value. If used, this `CommandLineSyncEngine` begins to
      resemble how the :class:`LocalUserSyncEngine` operates, but diverges in
      the fact that the synchronization data is kept in the same directory
      as the synchronized items.

    In addition to the :class:`CommandLineSyncEngine` attributes,
    the `DirectorySyncEngine` also provides the following:

    :param rootDir:

      The path (potentially either relative or absolute) to the
      directory under control by this synchronization engine. The path,
      if valid, ends with a slash ("/").

    '''
    super(DirectorySyncEngine, self).__init__(*args, **kw)
    self.syncSubdir = syncSubdir
    self.defaultDir = defaultDir
    self.rootDir    = None

  #----------------------------------------------------------------------------
  @hook('options.setup.term')
  def _options_setup_term_rootDir(self):
    self.parser.add_argument(
      'rootDir', metavar='DIRECTORY',
      nargs='?' if self.defaultDir is not None else None,
      help='path to the directory to be synchronized (can be either'
      ' relative or absolute)')

  #----------------------------------------------------------------------------
  @hook('options.parse.datadir')
  def _options_parse_term_rootDir(self):
    self.rootDir = self.options.rootDir
    if self.defaultDir is not None and self.options.rootDir is None:
      self.rootDir = self.defaultDir
    if not self.rootDir.startswith('/') and not self.rootDir.startswith('.'):
      self.rootDir = './' + self.rootDir
    if not self.rootDir.endswith('/'):
      self.rootDir += '/'
    if not os.path.isdir(self.rootDir):
      self.parser.error('directory "%s" does not exist' % (self.rootDir,))
    self.options.rootDir = self.rootDir
    self.dataDir = os.path.join(self.rootDir, self.syncSubdir)
    if not self.dataDir.endswith('/'):
      self.dataDir += '/'
    if not os.path.isdir(self.dataDir):
      os.makedirs(self.dataDir)

#------------------------------------------------------------------------------
class LocalUserSyncEngine(CommandLineSyncEngine):

  #----------------------------------------------------------------------------
  def __init__(self,
               *args, **kw):
    '''
    TODO: document & implement...
    '''
    super(LocalUserSyncEngine, self).__init__(*args, **kw)

    raise NotImplementedError()

  #----------------------------------------------------------------------------
  @hook('options.setup.generic')
  def _addOption_config(self):
    self.parser.add_argument(
      '-c', '--config', default='default', action='store',
      help='sets the configuration name (default: "%(default)s")')

  #----------------------------------------------------------------------------
  @hook('options.parse.datadir')
  def _configure_dataDir(self):
    # TODO: there must be python options for evaluating "~"...
    # TODO: and make this sensitive to "OS'isms"...
    self.dataDir = os.path.join('~', '.config', self.appLabel, self.options.config)
    if not self.dataDir.endswith('/'):
      self.dataDir += '/'
    if not os.path.isdir(self.dataDir):
      os.makedirs(self.dataDir)

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
