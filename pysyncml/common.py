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
The ``pysyncml.common`` package provides some commonly used helper routines
and classes used throughout the pysyncml package.
'''

import sys, time, calendar, inspect, six, pkg_resources, platform
import xml.etree.ElementTree as ET
import asset

from . import constants

#------------------------------------------------------------------------------
version = asset.version('pysyncml')

#------------------------------------------------------------------------------
class SyncmlError(Exception): pass
class ProtocolError(SyncmlError): pass
class InternalError(SyncmlError): pass
class ConflictError(SyncmlError): pass
class FeatureNotSupported(SyncmlError): pass
class LogicalError(SyncmlError): pass
class InvalidContext(SyncmlError): pass
class InvalidAdapter(SyncmlError): pass
class InvalidStore(SyncmlError): pass
class InvalidContentType(SyncmlError): pass
class InvalidAgent(SyncmlError): pass
class InvalidContent(SyncmlError): pass
class InvalidItem(SyncmlError): pass
class UnknownCodec(SyncmlError): pass
class NoSuchRoute(SyncmlError): pass
class UnknownAuthType(SyncmlError): pass
class UnknownFormatType(SyncmlError): pass

#------------------------------------------------------------------------------
def ts():
  return int(time.time())

#------------------------------------------------------------------------------
def ts_iso(ts=None):
  if ts is None:
    ts = int(time.time())
  return time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(ts))

#------------------------------------------------------------------------------
def parse_ts_iso(s):
  return calendar.timegm(time.strptime(s, '%Y%m%dT%H%M%SZ'))

#------------------------------------------------------------------------------
def state2string(state):
  return {
    constants.ITEM_OK:          'ok',
    constants.ITEM_ADDED:       'added',
    constants.ITEM_MODIFIED:    'modified',
    constants.ITEM_DELETED:     'deleted',
    constants.ITEM_SOFTDELETED: 'soft-deleted',
    }.get(state, 'UNKNOWN')

#------------------------------------------------------------------------------
def mode2string(mode):
  return {
    constants.ALERT_TWO_WAY:                           'two-way',
    constants.ALERT_SLOW_SYNC:                         'slow-sync',
    constants.ALERT_ONE_WAY_FROM_CLIENT:               'one-way-from-client',
    constants.ALERT_REFRESH_FROM_CLIENT:               'refresh-from-client',
    constants.ALERT_ONE_WAY_FROM_SERVER:               'one-way-from-server',
    constants.ALERT_REFRESH_FROM_SERVER:               'refresh-from-server',
    constants.ALERT_TWO_WAY_BY_SERVER:                 'two-way-by-server',
    constants.ALERT_ONE_WAY_FROM_CLIENT_BY_SERVER:     'one-way-from-client-by-server',
    constants.ALERT_REFRESH_FROM_CLIENT_BY_SERVER:     'refresh-from-client-by-server',
    constants.ALERT_ONE_WAY_FROM_SERVER_BY_SERVER:     'one-way-from-server-by-server',
    constants.ALERT_REFRESH_FROM_SERVER_BY_SERVER:     'refresh-from-server-by-server',
    }.get(mode, 'UNKNOWN')

#------------------------------------------------------------------------------
def auth2string(auth):
  # todo: this is really a silly implementation... it is in the end just
  #      returning the same string!... LOL.
  return {
    constants.NAMESPACE_AUTH_BASIC:                    'syncml:auth-basic',
    constants.NAMESPACE_AUTH_MD5:                      'syncml:auth-md5',
    }.get(auth, 'UNKNOWN')

#------------------------------------------------------------------------------
synctype2alert_lut = {
  constants.SYNCTYPE_TWO_WAY             : constants.ALERT_TWO_WAY,
  constants.SYNCTYPE_SLOW_SYNC           : constants.ALERT_SLOW_SYNC,
  constants.SYNCTYPE_ONE_WAY_FROM_SERVER : constants.ALERT_ONE_WAY_FROM_SERVER,
  constants.SYNCTYPE_ONE_WAY_FROM_CLIENT : constants.ALERT_ONE_WAY_FROM_CLIENT,
  constants.SYNCTYPE_REFRESH_FROM_SERVER : constants.ALERT_REFRESH_FROM_SERVER,
  constants.SYNCTYPE_REFRESH_FROM_CLIENT : constants.ALERT_REFRESH_FROM_CLIENT,
  }

#------------------------------------------------------------------------------
def synctype2alert(synctype):
  if synctype not in synctype2alert_lut:
    raise TypeError('unknown/unsupported sync type "%r"' % (synctype,))
  return synctype2alert_lut[synctype]

#------------------------------------------------------------------------------
def alert2synctype(alert):
  for s, a in synctype2alert_lut.items():
    if a == alert:
      return s
  return None

#------------------------------------------------------------------------------
class IndentStream:
  def __init__(self, stream, indent='  ', stayBlank=False):
    self.stream    = stream
    self.indent    = indent
    self.cleared   = True
    self.stayBlank = stayBlank
  def write(self, data):
    # TODO: this implementation is overly complex and actually fails to
    #       detect a "stayBlank" scenario if consecutive "write('\n')"s
    #       are called... ugh. replace and simplify!
    if len(data) <= 0:
      return
    lines = data.split('\n')
    if self.cleared:
      self.stream.write(self.indent)
    self.cleared = False
    for idx, line in enumerate(lines):
      if line == '':
        if idx + 1 >= len(lines):
          self.cleared = True
        else:
          if idx != 0 and not self.stayBlank:
            self.stream.write(self.indent)
      else:
        if idx != 0 or self.cleared:
          self.stream.write(self.indent)
        self.stream.write(line)
      if idx + 1 < len(lines):
        self.stream.write('\n')

#------------------------------------------------------------------------------
class adict(dict):
  def __getattr__(self, key):
    return self.get(key, None)
  def __setattr__(self, key, value):
    self[key] = value
    return self
  def __delattr__(self, key):
    if key in self:
      del self[key]
    return self
  def copy(self):
    return adict(self.items())

#------------------------------------------------------------------------------
def fullClassname(obj):
  return '.'.join((obj.__class__.__module__, obj.__class__.__name__))

#------------------------------------------------------------------------------
def getAddressSize():
  '''Returns the size of a memory address reference on the current
  platform (e.g. 32 or 64 for respectively 32-bit or 64-bit operating
  platforms) - defaults to 32 if it cannot be determined.'''
  return int(platform.architecture(bits='32bit')[0].replace('bit', ''))

#------------------------------------------------------------------------------
def getMaxMemorySize(context=None):
  '''Returns the maximum size of a memory object. By default this is,
  set to ``sys.maxint``, however the `context` may override this behavior.

  NOTE: currently, this is being hardcoded to a maximum of 2GB for
        compatibility with funambol servers, which croak above that
        value.

  TODO: allow the context to control this, or implement auto-detect to
        determine what the remote peer can support...
  '''
  return min(sys.maxint, int(pow(2,31)-1))

#------------------------------------------------------------------------------
def num2str(num):
  # TODO: i18n...
  # TODO: this is *UGLY*
  # TODO: OMG, i'm *so* embarrassed
  # TODO: but it works... sort of.
  if num == 0:
    return '-'
  s = list(reversed(str(num)))
  for idx in reversed(range(3, len(s), 3)):
    s.insert(idx, ',')
  return ''.join(reversed(s))

#------------------------------------------------------------------------------
def describeStats(stats, stream, title=None, details=True, totals=True, gettext=None):
  from . import state
  modeStringLut = dict((
    (constants.SYNCTYPE_TWO_WAY,             '<>'),
    (constants.SYNCTYPE_SLOW_SYNC,           'SS'),
    (constants.SYNCTYPE_ONE_WAY_FROM_CLIENT, '->'),
    (constants.SYNCTYPE_REFRESH_FROM_CLIENT, '=>'),
    (constants.SYNCTYPE_ONE_WAY_FROM_SERVER, '<-'),
    (constants.SYNCTYPE_REFRESH_FROM_SERVER, '<='),
    ))

  if gettext is not None:
    _ = gettext
  else:
    _ = lambda s: s

  # OBJECTIVE:
  # +----------------------------------------------------------------------------------+
  # |                                      TITLE                                       |
  # +----------+------+-------------------------+--------------------------+-----------+
  # |          |      |          Local          |          Remote          | Conflicts |
  # |   Source | Mode |  Add  | Mod | Del | Err |   Add  | Mod | Del | Err | Col | Mrg |
  # +----------+------+-------+-----+-----+-----+--------+-----+-----+-----+-----+-----+
  # | contacts |  <=  |   -   |  -  |  -  |  -  | 10,387 |  -  |  -  |  -  |  -  |  -  |
  # |     note |  SS  | 1,308 |  -  |   2 |  -  |    -   |  -  |  -  |  -  |  -  |  -  |
  # +----------+------+-------+-----+-----+-----+--------+-----+-----+-----+-----+-----+
  # |                  1,310 local changes and 10,387 remote changes.                  |
  # +----------------------------------------------------------------------------------+

  # todo: this does not handle the case where the title is wider than the table.

  wSrc  = len(_('Source'))
  wMode = len(_('Mode'))
  wCon  = len(_('Conflicts'))
  wCol  = len(_('Col'))
  wMrg  = len(_('Mrg'))
  wHereAdd = wPeerAdd = len(_('Add'))
  wHereMod = wPeerMod = len(_('Mod'))
  wHereDel = wPeerDel = len(_('Del'))
  wHereErr = wPeerErr = len(_('Err'))

  totLoc = 0
  totRem = 0
  totErr = 0
  totCol = 0
  totMrg = 0

  for key in stats.keys():
    wSrc  = max(wSrc, len(key))
    wMode = max(wMode, len(modeStringLut.get(stats[key].mode)))
    wCol  = max(wCol, len(num2str(stats[key].conflicts)))
    wMrg  = max(wMrg, len(num2str(stats[key].merged)))
    wHereAdd = max(wHereAdd, len(num2str(stats[key].hereAdd)))
    wPeerAdd = max(wPeerAdd, len(num2str(stats[key].peerAdd)))
    wHereMod = max(wHereMod, len(num2str(stats[key].hereMod)))
    wPeerMod = max(wPeerMod, len(num2str(stats[key].peerMod)))
    wHereDel = max(wHereDel, len(num2str(stats[key].hereDel)))
    wPeerDel = max(wPeerDel, len(num2str(stats[key].peerDel)))
    wHereErr = max(wHereErr, len(num2str(stats[key].hereErr)))
    wPeerErr = max(wPeerErr, len(num2str(stats[key].peerErr)))
    totLoc += stats[key].hereAdd + stats[key].hereMod + stats[key].hereDel
    totRem += stats[key].peerAdd + stats[key].peerMod + stats[key].peerDel
    totErr += stats[key].hereErr + stats[key].peerErr
    totCol += stats[key].conflicts
    totMrg += stats[key].merged

  # TODO: i'm 100% sure there is a python library that can do this for me...

  if wCon > wCol + 3 + wMrg:
    diff = wCon - ( wCol + 3 + wMrg )
    wCol += diff / 2
    wMrg = wCon - 3 - wCol
  else:
    wCon = wCol + 3 + wMrg

  if details:
    tWid = ( wSrc + 3 + wMode + 3
             + wHereAdd + wHereMod + wHereDel + wHereErr + 9 + 3
             + wPeerAdd + wPeerMod + wPeerDel + wPeerErr + 9 + 3
             + wCon )
  else:
    if title is None:
      tWid = 0
    else:
      tWid = len(title)

  if totals:
    # TODO: oh dear. from an i18n POV, this is *horrible*!...
    sumlist = []
    for val, singular, plural in [
      (totLoc, _('local change'), _('local changes')),
      (totRem, _('remote change'), _('remote changes')),
      (totErr, _('error'), _('errors')),
      ]:
      if val == 1:
        sumlist.append(num2str(val) + ' ' + singular)
      elif val > 1:
        sumlist.append(num2str(val) + ' ' + plural)
    if len(sumlist) <= 0:
      sumlist = _('No changes')
    elif len(sumlist) == 1:
      sumlist = sumlist[0]
    else:
      sumlist = ', '.join(sumlist[:-1]) + ' ' + _('and') + ' ' + sumlist[-1]
    if totMrg > 0 or totCol > 0:
      sumlist += ': '
      if totMrg == 1:
        sumlist += num2str(totMrg) + ' ' + _('merge')
      elif totMrg > 1:
        sumlist += num2str(totMrg) + ' ' + _('merges')
      if totMrg > 0 and totCol > 0:
        sumlist += ' ' + _('and') + ' '
      if totCol == 1:
        sumlist += num2str(totCol) + ' ' + _('conflict')
      elif totCol > 1:
        sumlist += num2str(totCol) + ' ' + _('conflicts')
    sumlist += '.'
    if len(sumlist) > tWid:
      wSrc += len(sumlist) - tWid
      tWid = len(sumlist)

  if title is not None:
    stream.write('+-' + '-' * tWid + '-+\n')
    stream.write('| {0: ^{w}}'.format(title, w=tWid))
    stream.write(' |\n')

  hline = '+-' \
          + '-' * wSrc \
          + '-+-' \
          + '-' * wMode \
          + '-+-' \
          + '-' * ( wHereAdd + wHereMod + wHereDel + wHereErr + 9 ) \
          + '-+-' \
          + '-' * ( wPeerAdd + wPeerMod + wPeerDel + wPeerErr + 9 )  \
          + '-+-' \
          + '-' * wCon \
          + '-+\n'

  if details:

    stream.write(hline)

    stream.write('| ' + ' ' * wSrc)
    stream.write(' | ' + ' ' * wMode)
    stream.write(' | {0: ^{w}}'.format(_('Local'), w=( wHereAdd + wHereMod + wHereDel + wHereErr + 9 )))
    stream.write(' | {0: ^{w}}'.format(_('Remote'), w=( wPeerAdd + wPeerMod + wPeerDel + wPeerErr + 9 )))
    stream.write(' | {0: ^{w}}'.format(_('Conflicts'), w=wCon))
    stream.write(' |\n')

    stream.write('| {0: >{w}}'.format(_('Source'), w=wSrc))
    stream.write(' | {0: >{w}}'.format(_('Mode'), w=wMode))
    stream.write(' | {0: ^{w}}'.format(_('Add'), w=wHereAdd))
    stream.write(' | {0: ^{w}}'.format(_('Mod'), w=wHereMod))
    stream.write(' | {0: ^{w}}'.format(_('Del'), w=wHereDel))
    stream.write(' | {0: ^{w}}'.format(_('Err'), w=wHereErr))
    stream.write(' | {0: ^{w}}'.format(_('Add'), w=wPeerAdd))
    stream.write(' | {0: ^{w}}'.format(_('Mod'), w=wPeerMod))
    stream.write(' | {0: ^{w}}'.format(_('Del'), w=wPeerDel))
    stream.write(' | {0: ^{w}}'.format(_('Err'), w=wPeerErr))
    stream.write(' | {0: ^{w}}'.format(_('Col'), w=wCol))
    stream.write(' | {0: ^{w}}'.format(_('Mrg'), w=wMrg))
    stream.write(' |\n')

    hsline = '+-' + '-' * wSrc \
             + '-+-' + '-' * wMode \
             + '-+-' + '-' * wHereAdd \
             + '-+-' + '-' * wHereMod \
             + '-+-' + '-' * wHereDel \
             + '-+-' + '-' * wHereErr \
             + '-+-' + '-' * wPeerAdd \
             + '-+-' + '-' * wPeerMod \
             + '-+-' + '-' * wPeerDel \
             + '-+-' + '-' * wPeerErr \
             + '-+-' + '-' * wCol \
             + '-+-' + '-' * wMrg \
             + '-+\n'

    stream.write(hsline)

    def numcol(val, wid):
      if val == 0:
        return ' | {0: ^{w}}'.format('-', w=wid)
      return ' | {0: >{w}}'.format(num2str(val), w=wid)

    for key in sorted(stats.keys(), key=lambda k: str(k).lower()):
      stream.write('| {0: >{w}}'.format(key, w=wSrc))
      stream.write(' | {0: ^{w}}'.format(modeStringLut.get(stats[key].mode), w=wMode))
      stream.write(numcol(stats[key].hereAdd, wHereAdd))
      stream.write(numcol(stats[key].hereMod, wHereMod))
      stream.write(numcol(stats[key].hereDel, wHereDel))
      stream.write(numcol(stats[key].hereErr, wHereErr))
      stream.write(numcol(stats[key].peerAdd, wPeerAdd))
      stream.write(numcol(stats[key].peerMod, wPeerMod))
      stream.write(numcol(stats[key].peerDel, wPeerDel))
      stream.write(numcol(stats[key].peerErr, wPeerErr))
      stream.write(numcol(stats[key].conflicts, wCol))
      stream.write(numcol(stats[key].merged, wMrg))
      stream.write(' |\n')

    stream.write(hsline)

  if totals:
    if title is None and not details:
      stream.write('+-' + '-' * tWid + '-+\n')
    stream.write('| {0: ^{w}}'.format(sumlist, w=tWid))
    stream.write(' |\n')
    stream.write('+-' + '-' * tWid + '-+\n')

  return

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
