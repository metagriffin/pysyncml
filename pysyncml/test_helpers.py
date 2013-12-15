# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/06/16
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

import unittest, sys, six, re, difflib, logging, xml.dom, xml.dom.minidom

from . import constants, common, state
from .common import adict

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
def setlogging(enabled):
  if not enabled:
    # kill logging
    logging.disable(logging.CRITICAL)
    return
  rootlog = logging.getLogger()
  handler = logging.StreamHandler(sys.stderr)
  handler.setFormatter(LogFormatter(True))
  rootlog.addHandler(handler)
  rootlog.setLevel(logging.DEBUG)

#------------------------------------------------------------------------------
def makestats(mode=constants.SYNCTYPE_TWO_WAY, conflicts=0, merged=0,
              hereAdd=0, hereMod=0, hereDel=0, hereErr=0,
              peerAdd=0, peerMod=0, peerDel=0, peerErr=0):
  return dict(mode=mode, conflicts=conflicts, merged=merged,
              hereAdd=hereAdd, hereMod=hereMod, hereDel=hereDel, hereErr=hereErr,
              peerAdd=peerAdd, peerMod=peerMod, peerDel=peerDel, peerErr=peerErr)

#------------------------------------------------------------------------------
def stats2str(stats):
  if 'mode' not in stats:
    ret = ''
    for k, v in stats.items():
      if len(ret) > 0:
        ret += ', '
      ret += k + stats2str(v)
    return ret
  ret = [common.mode2string(common.synctype2alert(stats['mode']))]
  for attr in (
    'hereAdd', 'hereMod', 'hereDel', 'hereErr',
    'peerAdd', 'peerMod', 'peerDel', 'peerErr',
    'conflicts', 'merged' ):
    if attr in stats and stats[attr] != 0:
      ret.append('%s=%d' % (attr, stats[attr]))
  return '(' + '; '.join(ret) + ')'

#------------------------------------------------------------------------------
def deepclone(obj):
  if isinstance(obj, basestring):
    return obj
  try:
    ret = dict()
    for k, v in obj.items():
      ret[k] = deepclone(v)
    return ret
  except AttributeError:
    pass
  try:
    return [deepclone(e) for e in obj]
  except TypeError:
    pass
  return obj

#------------------------------------------------------------------------------
def stripsame(dict1, dict2):
  try:
    for key in dict1.keys():
      if key not in dict2:
        continue
      if cmp(dict1.get(key), dict2.get(key)) == 0:
        del dict1[key]
        del dict2[key]
        continue
      stripsame(dict1.get(key), dict2.get(key))
  except AttributeError:
    return

#------------------------------------------------------------------------------
class TrimDictEqual:

  #----------------------------------------------------------------------------
  def assertTrimDictEqual(self, tgt, chk, msg=None):
    try:
      self.assertEqual(tgt, chk, msg)
      return
    except Exception:
      pass
    chkdup = deepclone(chk)
    tgtdup = deepclone(tgt)
    stripsame(tgtdup, chkdup)
    try:
      self.assertEqual(tgtdup, chkdup, msg)
    except Exception:
      raise
    # hm. we somehow stripped the difference... raise the old one...
    self.assertEqual(tgt, chk, msg)

#------------------------------------------------------------------------------
class MultiLineEqual:

  #----------------------------------------------------------------------------
  def assertMultiLineEqual(self, tgt, chk, msg=None):
    try:
      self.assertEqual(tgt, chk, msg)
      return
    except Exception:
      if not isinstance(chk, basestring) \
         or not isinstance(tgt, basestring):
        raise
    print '%s, diff:' % (msg or 'FAIL',)
    print '--- expected'
    print '+++ received'
    differ = difflib.Differ()
    diff = list(differ.compare(chk.split('\n'), tgt.split('\n')))
    cdiff = []
    need = -1
    for idx, line in enumerate(diff):
      if line[0] != ' ':
        need = idx + 2
      if idx > need \
         and line[0] == ' ' \
         and ( len(diff) <= idx + 1 or diff[idx + 1][0] == ' ' ) \
         and ( len(diff) <= idx + 2 or diff[idx + 2][0] == ' ' ):
        continue
      if idx > need:
        cdiff.append('@@ %d @@' % (idx + 1,))
        need = idx + 2
      # if line.startswith('?'):
      #   cdiff.append(line.strip())
      # else:
      #   cdiff.append(line)
      cdiff.append(line.rstrip())
    for line in cdiff:
      print line
    self.assertEqual('received', 'expected')

#------------------------------------------------------------------------------
# LEGACY LEGACY LEGACY LEGACY LEGACY LEGACY LEGACY LEGACY LEGACY LEGACY LEGACY
#------------------------------------------------------------------------------
# TODO: the following is legacy support for unittests which still
#       expect the old implementation of Adapter._handleRequestRemote,
#       which did not use the requests package. upgrade the unit tests!
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def LEGACY_Adapter__handleRequestRemote(self, session, request, adapter):
  import urllib2
  req = urllib2.Request(session.respUri or self.url, request.body)
  req.add_header('content-type', request.contentType or 'application/vnd.syncml+xml')
  req.add_header('x-syncml-client', 'pysyncml/' + common.version)
  res = self._opener.open(req, request.body)
  res = state.Request(body=res.read(), headers=res.info().headers)
  res.headers = [map(lambda x: x.strip(), h.split(':', 1))
                 for h in res.headers]
  res.headers = dict([(k.lower(), v) for k, v in res.headers])
  adapter.handleRequest(session, res)
def LEGACY_makeRequestHandler(peer):
  import new
  return new.instancemethod(LEGACY_Adapter__handleRequestRemote, peer, peer.__class__)

#------------------------------------------------------------------------------
class LEGACY_BridgingOpener(object):

  #----------------------------------------------------------------------------
  def __init__(self, adapter=None, peer=None, returnUrl=None, refresher=None):
    self.peer = peer
    self.refresher = refresher
    if self.refresher is None:
      self.refresher = lambda peer: peer
    self.session = state.Session()
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
    return

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
